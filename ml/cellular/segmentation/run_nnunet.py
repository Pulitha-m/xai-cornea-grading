"""
Phase 2, Step 2.6 — nnU-Net v2 (2D), the self-configuring U-Net benchmark.

nnU-Net plans its own network, patch size, normalisation and augmentation from
the data. It is given exactly what the other models get:
  * the same preprocessed crops (saved as 8-bit PNG),
  * the same reference masks — 0 interior ("background"), 1 wall, 2 ignore;
    nnU-Net supports an ignore label natively, so blue regions are excluded
    from the loss as for U-Net,
  * the same folds (written to nnU-Net's splits_final.json).
For each fold it trains with ``nnunet.trainer`` (reduced epoch budget) and
predicts the held-out fold with the FINAL checkpoint (no checkpoint selection on
the test fold). The wall probability goes through the same watershed
(seg_models.watershed_h) and the same metrics as U-Net / U-Net++ / SegFormer.

Storage: nnU-Net raw + preprocessed data on the Colab disk (rebuilt each
session in a few seconds); trained folds (nnUNet_results) on Drive, so a
disconnected fold resumes from its latest checkpoint.

Outputs (run = nnunet_<preprocess>):
  <models_dir>/seg/nnunet_results/...           nnU-Net checkpoints + validation npz
  <outputs_dir>/seg/<run>/oof/<crop_id>.npy     out-of-fold wall probability (float16)
  <outputs_dir>/seg/<run>/masks/, scores.csv    as for every run

Usage (from ml/cellular/; Colab GPU runtime, after the setup cell and
`pip install "nnunetv2>=2.5,<3"`):
    python -m segmentation.run_nnunet --folds 0       # one fold per call is safest on Colab
    python -m segmentation.run_nnunet                 # all unfinished folds
    python -m segmentation.run_nnunet --score-only    # just (re)score finished folds
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from config import load_config
from segmentation.data import Sample, load_samples
from segmentation.metrics import print_summary, score_run
from segmentation.postprocess import walls_to_mask

LOCAL_ROOT = Path("/content/nnunet")                      # Colab disk: raw + preprocessed


def setup_env(cfg: dict) -> Path:
    """nnU-Net reads its folders from environment variables (inherited by the CLI calls)."""
    results = cfg["paths"]["models_dir"] / "seg" / "nnunet_results"
    for key, path in (("nnUNet_raw", LOCAL_ROOT / "raw"), ("nnUNet_preprocessed", LOCAL_ROOT / "preprocessed"),
                      ("nnUNet_results", results)):
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    os.environ.setdefault("nnUNet_compile", "false")      # avoid torch.compile issues on new Python / torch
    return results


def dataset_name(cfg: dict, mode: str) -> tuple[int, str]:
    did = cfg["seg_models"]["nnunet"]["dataset_id"] + (0 if mode == "flat" else 1)
    return did, f"Dataset{did:03d}_EndoCells{mode.capitalize()}"


def prepare(cfg: dict, samples: list[Sample], mode: str) -> None:
    """Write the nnU-Net raw dataset, plan + preprocess, then impose our folds."""
    did, name = dataset_name(cfg, mode)
    raw = LOCAL_ROOT / "raw" / name
    (raw / "imagesTr").mkdir(parents=True, exist_ok=True)
    (raw / "labelsTr").mkdir(parents=True, exist_ok=True)
    for s in samples:
        cv2.imwrite(str(raw / "imagesTr" / f"{s.crop_id}_0000.png"), np.round(s.image * 255).astype(np.uint8))
        cv2.imwrite(str(raw / "labelsTr" / f"{s.crop_id}.png"), s.mask)
    (raw / "dataset.json").write_text(json.dumps({
        "channel_names": {"0": "specular"},
        "labels": {"background": 0, "wall": 1, "ignore": 2},   # background = cell interior
        "numTraining": len(samples),
        "file_ending": ".png",
        "overwrite_image_reader_writer": "NaturalImage2DIO",
    }, indent=2))

    subprocess.run(["nnUNetv2_plan_and_preprocess", "-d", str(did), "-c", "2d",
                    "--verify_dataset_integrity", "-np", "4"], check=True)

    n_folds = cfg["seg_models"]["n_folds"]
    splits = [{"train": [s.crop_id for s in samples if s.fold != k],
               "val": [s.crop_id for s in samples if s.fold == k]} for k in range(n_folds)]
    (LOCAL_ROOT / "preprocessed" / name / "splits_final.json").write_text(json.dumps(splits, indent=2))
    print(f"Prepared {name}: {len(samples)} crops, our {n_folds} folds written to splits_final.json")


def fold_dir(results: Path, name: str, trainer: str, k: int) -> Path:
    return results / name / f"{trainer}__nnUNetPlans__2d" / f"fold_{k}"


def wall_probability(npz_path: Path) -> np.ndarray:
    """Softmax probability of class 1 (wall) from nnU-Net's validation export."""
    return np.squeeze(np.load(npz_path)["probabilities"][1]).astype(np.float32)


def main() -> None:
    cfg = load_config()
    sm, nn = cfg["seg_models"], cfg["seg_models"]["nnunet"]

    ap = argparse.ArgumentParser(description="nnU-Net v2 (2D) on the shared folds.")
    ap.add_argument("--preprocess", choices=["raw", "flat"], default=sm["preprocess"])
    ap.add_argument("--folds", type=int, nargs="*", help="only these folds (default: all unfinished)")
    ap.add_argument("--score-only", action="store_true", help="do not train; score finished folds")
    args = ap.parse_args()

    results = setup_env(cfg)
    did, name = dataset_name(cfg, args.preprocess)
    run = f"nnunet_{args.preprocess}"
    out_dir = cfg["paths"]["outputs_dir"] / "seg" / run
    oof_dir = out_dir / "oof"
    oof_dir.mkdir(parents=True, exist_ok=True)
    samples = load_samples(cfg, args.preprocess)

    if not args.score_only:
        if not (LOCAL_ROOT / "preprocessed" / name / "splits_final.json").exists():
            prepare(cfg, samples, args.preprocess)
        for k in (args.folds if args.folds else range(sm["n_folds"])):
            fd = fold_dir(results, name, nn["trainer"], k)
            test = [s for s in samples if s.fold == k]
            have_npz = all((fd / "validation" / f"{s.crop_id}.npz").exists() for s in test)
            if (fd / "checkpoint_final.pth").exists() and have_npz:
                print(f"  fold {k}: done already - skipped")
                continue
            print(f"  fold {k}: training {nn['trainer']} (resumes from the latest checkpoint if any)", flush=True)
            t0 = time.time()
            cmd = ["nnUNetv2_train", str(did), "2d", str(k), "-tr", nn["trainer"], "--npz", "--c"]
            if (fd / "checkpoint_final.pth").exists():
                cmd.append("--val")                        # trained already, only the export is missing
            subprocess.run(cmd, check=True)
            print(f"  fold {k}: finished in {(time.time() - t0) / 60:.1f} min", flush=True)

    for s in samples:                                       # collect out-of-fold wall probabilities
        npz = fold_dir(results, name, nn["trainer"], s.fold) / "validation" / f"{s.crop_id}.npz"
        if npz.exists():
            np.save(oof_dir / f"{s.crop_id}.npy", wall_probability(npz).astype(np.float16))

    preds = {s.crop_id: walls_to_mask(np.load(oof_dir / f"{s.crop_id}.npy"), sm["watershed_h"])
             for s in samples if (oof_dir / f"{s.crop_id}.npy").exists()}
    scores = score_run(samples, preds, out_dir)
    if len(scores) < len(samples):
        print(f"\nOnly {len(scores)} / {len(samples)} crops predicted so far - run the remaining folds.")
    print_summary(run, scores)
    print(f"Results: {out_dir}")


if __name__ == "__main__":
    main()
