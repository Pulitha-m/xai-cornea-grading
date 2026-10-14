"""
Phase 2, Steps 2.2-2.3 — cross-validated training of the segmentation-models-pytorch
models: U-Net, U-Net++ (ResNet34) and SegFormer (MiT-B2), all ImageNet-pretrained.

For every fold of splits/seg_folds_<round>.csv:
  1. train on the other folds (fixed number of epochs — no early stopping, so the
     held-out fold is never used for any decision);
  2. predict the held-out crops: wall probability, averaged over the 8 flips /
     90-degree rotations (TTA);
  3. wall map -> cells by watershed (segmentation/postprocess.py, h = seg_models.watershed_h).
Then every crop has an out-of-fold prediction and is scored (segmentation/metrics.py).

Loss: BCE (walls up-weighted) + soft Dice on the wall class; ignore pixels excluded.

Outputs (run = <model>_<preprocess>):
  <models_dir>/seg/<run>/fold<k>.pt          checkpoints
  <outputs_dir>/seg/<run>/oof/<crop_id>.npy  out-of-fold wall probability (float16)
  <outputs_dir>/seg/<run>/masks/<crop_id>.png predicted masks
  <outputs_dir>/seg/<run>/scores.csv         one row per crop
  <outputs_dir>/seg/<run>/train_log.csv      loss per epoch and fold

Usage (from ml/cellular/; Colab GPU runtime, after the setup cell):
    python -m segmentation.train_smp --model unet
    python -m segmentation.train_smp --model unet --folds 0 1      # some folds now, the rest later
    python -m segmentation.train_smp --model unet --preprocess raw # preprocessing ablation
Finished folds are skipped, so a disconnected session just re-runs the same command.
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from config import load_config
from data_prep.check_annotations import IGNORE, WALL
from segmentation.data import Sample, augment, load_samples
from segmentation.metrics import print_summary, score_run
from segmentation.postprocess import walls_to_mask

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], np.float32)[:, None, None]
IMAGENET_STD = np.array([0.229, 0.224, 0.225], np.float32)[:, None, None]


def to_tensor(img: np.ndarray) -> torch.Tensor:
    """Grayscale 0..1 -> 3-channel ImageNet-normalised tensor (all encoders take 3 channels)."""
    return torch.from_numpy(((np.repeat(img[None], 3, 0) - IMAGENET_MEAN) / IMAGENET_STD).astype(np.float32))


class TrainSet(Dataset):
    """Draws `length` augmented crops per epoch from the training samples."""

    def __init__(self, samples: list[Sample], length: int):
        self.samples, self.length = samples, length

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, i: int):
        s = self.samples[i % len(self.samples)]
        rng = np.random.default_rng(int(torch.randint(0, 2**31 - 1, (1,))))   # follows torch seeding
        img, mask = augment(s.image, s.mask, rng)
        return to_tensor(img), torch.from_numpy(mask.astype(np.int64))


def build_model(spec: dict, weights: str | None) -> torch.nn.Module:
    import segmentation_models_pytorch as smp
    return getattr(smp, spec["arch"])(encoder_name=spec["encoder"], encoder_weights=weights,
                                      in_channels=3, classes=1)


def wall_loss(logits: torch.Tensor, mask: torch.Tensor, pos_weight: float) -> torch.Tensor:
    """BCE + soft Dice on walls; ignore pixels contribute nothing."""
    logits = logits[:, 0].float()
    valid = (mask != IGNORE).float()
    target = (mask == WALL).float()
    bce = F.binary_cross_entropy_with_logits(
        logits, target, pos_weight=torch.tensor(pos_weight, device=logits.device), reduction="none")
    bce = (bce * valid).sum() / valid.sum().clamp(min=1)
    p = torch.sigmoid(logits) * valid
    dice = 1 - (2 * (p * target).sum() + 1) / (p.sum() + (target * valid).sum() + 1)
    return bce + dice


def train_fold(train: list[Sample], spec: dict, hp: dict, device: torch.device, seed: int,
               log: list) -> torch.nn.Module:
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = build_model(spec, hp["encoder_weights"]).to(device)
    lr = spec.get("lr", hp["lr"])
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=hp["weight_decay"])
    loader = DataLoader(TrainSet(train, hp["samples_per_epoch"]), batch_size=hp["batch_size"], shuffle=True,
                        num_workers=2, drop_last=True, pin_memory=device.type == "cuda")
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=hp["epochs"] * len(loader),
                                                pct_start=0.1)
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler(device.type, enabled=use_amp)

    model.train()
    for epoch in range(1, hp["epochs"] + 1):
        total = 0.0
        for x, m in loader:
            x, m = x.to(device, non_blocking=True), m.to(device, non_blocking=True)
            with torch.autocast(device.type, enabled=use_amp):
                logits = model(x)
            loss = wall_loss(logits, m, hp["wall_pos_weight"])
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            total += loss.item()
        log.append({"epoch": epoch, "loss": total / len(loader)})
        if epoch % 10 == 0 or epoch == hp["epochs"]:
            print(f"    epoch {epoch:3d}/{hp['epochs']}  loss {total / len(loader):.4f}", flush=True)
    model.eval()
    return model


@torch.no_grad()
def predict(model: torch.nn.Module, img: np.ndarray, tta: bool, device: torch.device) -> np.ndarray:
    """Wall probability for one image (H and W must be multiples of 32)."""
    x = to_tensor(img)[None].to(device)
    outs = []
    for k in range(4 if tta else 1):
        for flip in ((False, True) if tta else (False,)):
            t = torch.rot90(x, k, (2, 3))
            t = t.flip(3) if flip else t
            with torch.autocast(device.type, enabled=device.type == "cuda"):
                p = torch.sigmoid(model(t).float())
            p = p.flip(3) if flip else p
            outs.append(torch.rot90(p, -k, (2, 3)))
    return torch.stack(outs).mean(0)[0, 0].float().cpu().numpy()


def main() -> None:
    cfg = load_config()
    sm = cfg["seg_models"]
    hp = sm["smp"]

    ap = argparse.ArgumentParser(description="Cross-validated training of smp segmentation models.")
    ap.add_argument("--model", required=True, choices=sorted(hp["architectures"]))
    ap.add_argument("--preprocess", choices=["raw", "flat"], default=sm["preprocess"])
    ap.add_argument("--folds", type=int, nargs="*", help="only these folds (default: all)")
    ap.add_argument("--force", action="store_true", help="retrain folds that are already finished")
    args = ap.parse_args()

    spec = hp["architectures"][args.model]
    run = f"{args.model}_{args.preprocess}"
    ckpt_dir = cfg["paths"]["models_dir"] / "seg" / run
    out_dir = cfg["paths"]["outputs_dir"] / "seg" / run
    oof_dir = out_dir / "oof"
    for d in (ckpt_dir, oof_dir):
        d.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Run {run}: {spec['arch']} / {spec['encoder']} on {device}"
          + ("" if device.type == "cuda" else "  (NO GPU - Runtime > Change runtime type > T4 GPU)"))
    samples = load_samples(cfg, args.preprocess)

    log_rows = []
    for k in (args.folds if args.folds else range(sm["n_folds"])):
        test = [s for s in samples if s.fold == k]
        train = [s for s in samples if s.fold != k]
        ckpt = ckpt_dir / f"fold{k}.pt"
        if not args.force and ckpt.exists() and all((oof_dir / f"{s.crop_id}.npy").exists() for s in test):
            print(f"  fold {k}: done already - skipped")
            continue
        print(f"  fold {k}: train {len(train)} crops, test {len(test)} crops", flush=True)
        t0, log = time.time(), []
        model = train_fold(train, spec, hp, device, hp["seed"] + k, log)
        torch.save({"state_dict": model.state_dict(), "spec": spec, "preprocess": args.preprocess,
                    "fold": k, "train_crops": [s.crop_id for s in train]}, ckpt)
        for s in test:
            np.save(oof_dir / f"{s.crop_id}.npy", predict(model, s.image, hp["tta"], device).astype(np.float16))
        log_rows += [{"fold": k, **r} for r in log]
        print(f"  fold {k}: finished in {(time.time() - t0) / 60:.1f} min", flush=True)

    if log_rows:
        log_csv = out_dir / "train_log.csv"
        new = pd.DataFrame(log_rows)
        if log_csv.exists():
            old = pd.read_csv(log_csv)
            new = pd.concat([old[~old["fold"].isin(new["fold"].unique())], new])
        new.to_csv(log_csv, index=False)

    preds = {s.crop_id: walls_to_mask(np.load(oof_dir / f"{s.crop_id}.npy"), sm["watershed_h"])
             for s in samples if (oof_dir / f"{s.crop_id}.npy").exists()}
    scores = score_run(samples, preds, out_dir)
    if len(scores) < len(samples):
        print(f"\nOnly {len(scores)} / {len(samples)} crops predicted so far - run the remaining folds.")
    print_summary(run, scores)
    print(f"Results: {out_dir}")


if __name__ == "__main__":
    main()
