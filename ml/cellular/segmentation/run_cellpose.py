"""
Phase 2, Step 2.4 — Cellpose 4 (Cellpose-SAM, "cpsam"), zero-shot and fine-tuned.

zeroshot   the pretrained generalist model as-is on all 40 crops (no training on
           our data) -> "what does an off-the-shelf tool achieve without annotation?"
finetune   for every fold of splits/seg_folds_<round>.csv: fine-tune a fresh copy
           of cpsam on the training crops (Cellpose's recommended settings,
           fixed in config.yaml), predict the held-out crops.

Cellpose predicts cell instances directly; they are converted to the common
mask format (segmentation/postprocess.instances_to_mask) and scored with the
same metrics as every other model. Input = the same preprocessed crops.
Training labels: reference cells as instances; ignore regions become background
(Cellpose has no ignore label).

Outputs (run = cellpose_<mode>_<preprocess>):
  <outputs_dir>/seg/<run>/inst/<crop_id>.png    instance labels (16-bit)
  <outputs_dir>/seg/<run>/masks/, scores.csv    as for every run
Fine-tuned models (~1.2 GB each) stay on the Colab disk unless
cellpose.keep_checkpoints is true.

Usage (from ml/cellular/; Colab GPU runtime, after the setup cell and
`pip install "cellpose>=4.0,<5"`):
    python -m segmentation.run_cellpose --mode zeroshot
    python -m segmentation.run_cellpose --mode finetune            # all folds; finished folds skipped
    python -m segmentation.run_cellpose --mode finetune --folds 0 1
"""

from __future__ import annotations

import argparse
import shutil
import time
from importlib.metadata import version
from pathlib import Path

import cv2
import numpy as np

from config import load_config
from segmentation.data import Sample, load_samples
from segmentation.metrics import print_summary, score_run
from segmentation.postprocess import instances_to_mask, mask_to_instances

LOCAL_CKPT_DIR = Path("/content/cellpose_models")         # Colab disk (not Drive)


def check_version() -> None:
    v = version("cellpose")
    if int(v.split(".")[0]) < 4:
        raise SystemExit(f"cellpose {v} found; this script needs Cellpose 4: pip install \"cellpose>=4.0,<5\"")
    print(f"cellpose {v}")


def load_model(pretrained: str):
    import torch
    from cellpose import models
    if not torch.cuda.is_available():
        print("WARNING: no GPU - Runtime > Change runtime type > T4 GPU")
    return models.CellposeModel(gpu=torch.cuda.is_available(), pretrained_model=pretrained)


def predict(model, samples: list[Sample], diameter, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for s in samples:
        inst = model.eval(s.image, diameter=diameter)[0]
        cv2.imwrite(str(out_dir / f"{s.crop_id}.png"), inst.astype(np.uint16))


def finetune(train: list[Sample], cp: dict, name: str, save_dir: Path) -> str:
    import torch
    from cellpose import train as cp_train
    torch.manual_seed(cp["seed"])
    save_dir.mkdir(parents=True, exist_ok=True)           # Cellpose creates only <save_dir>/models
    model = load_model(cp["pretrained"])
    result = cp_train.train_seg(
        model.net,
        train_data=[s.image for s in train],
        train_labels=[mask_to_instances(s.mask) for s in train],
        batch_size=cp["batch_size"], learning_rate=cp["learning_rate"],
        weight_decay=cp["weight_decay"], n_epochs=cp["epochs"],
        save_path=str(save_dir), model_name=name)
    return str(result[0] if isinstance(result, tuple) else result)   # path of the fine-tuned model


def main() -> None:
    cfg = load_config()
    sm, cp = cfg["seg_models"], cfg["seg_models"]["cellpose"]

    ap = argparse.ArgumentParser(description="Cellpose zero-shot / fine-tuned on the shared folds.")
    ap.add_argument("--mode", required=True, choices=["zeroshot", "finetune"])
    ap.add_argument("--preprocess", choices=["raw", "flat"], default=sm["preprocess"])
    ap.add_argument("--folds", type=int, nargs="*", help="finetune: only these folds (default: all)")
    ap.add_argument("--force", action="store_true", help="redo crops / folds that are already predicted")
    args = ap.parse_args()

    check_version()
    run = f"cellpose_{args.mode}_{args.preprocess}"
    out_dir = cfg["paths"]["outputs_dir"] / "seg" / run
    inst_dir = out_dir / "inst"
    samples = load_samples(cfg, args.preprocess)
    done = lambda group: not args.force and all((inst_dir / f"{s.crop_id}.png").exists() for s in group)

    if args.mode == "zeroshot":
        if done(samples):
            print("All crops predicted already - skipped (use --force to redo)")
        else:
            t0 = time.time()
            predict(load_model(cp["pretrained"]), samples, cp["diameter"], inst_dir)
            print(f"Zero-shot on {len(samples)} crops: {time.time() - t0:.0f} s")
    else:
        ckpt_root = (cfg["paths"]["models_dir"] / "seg" / run) if cp["keep_checkpoints"] else LOCAL_CKPT_DIR / run
        for k in (args.folds if args.folds else range(sm["n_folds"])):
            test = [s for s in samples if s.fold == k]
            train = [s for s in samples if s.fold != k]
            if done(test):
                print(f"  fold {k}: done already - skipped")
                continue
            print(f"  fold {k}: fine-tune on {len(train)} crops, test {len(test)} crops", flush=True)
            t0 = time.time()
            path = finetune(train, cp, f"fold{k}", ckpt_root)
            predict(load_model(path), test, cp["diameter"], inst_dir)
            if not cp["keep_checkpoints"]:
                shutil.rmtree(ckpt_root, ignore_errors=True)          # free the Colab disk
            print(f"  fold {k}: finished in {(time.time() - t0) / 60:.1f} min", flush=True)

    preds = {s.crop_id: instances_to_mask(cv2.imread(str(inst_dir / f"{s.crop_id}.png"), cv2.IMREAD_UNCHANGED))
             for s in samples if (inst_dir / f"{s.crop_id}.png").exists()}
    scores = score_run(samples, preds, out_dir)
    if len(scores) < len(samples):
        print(f"\nOnly {len(scores)} / {len(samples)} crops predicted so far - run the remaining folds.")
    print_summary(run, scores)
    print(f"Results: {out_dir}")


if __name__ == "__main__":
    main()
