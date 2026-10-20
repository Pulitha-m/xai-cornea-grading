"""
Phase 2, Step 2.5 — StarDist 2D, fine-tuned on the shared folds.

StarDist describes every cell as a star-convex polygon (32 rays from its centre),
a shape prior that suits the convex, mostly hexagonal endothelial cells.

For every fold of splits/seg_folds_<round>.csv:
  1. copy the pretrained model (stardist.pretrained) and fine-tune it on the
     fold's training crops; ``stardist.n_val_crops`` of THOSE training crops are
     held out to pick the best checkpoint and to optimise the probability / NMS
     thresholds — the test fold is never used for any decision;
  2. predict the held-out test crops.
Same input (preprocessed crops, percentile-normalised), same augmentation
(segmentation/data.augment) and same scoring as every other model. Training
labels: reference cells as instances; ignore regions become background
(StarDist has no ignore label).

Outputs (run = stardist_finetune_<preprocess>):
  <models_dir>/seg/<run>/fold<k>/              fine-tuned models (~20 MB each)
  <outputs_dir>/seg/<run>/inst/<crop_id>.png   instance labels (16-bit)
  <outputs_dir>/seg/<run>/masks/, scores.csv   as for every run

Usage (from ml/cellular/; Colab GPU runtime, after the setup cell and
`pip install tensorflow tf-keras stardist`):
    python -m segmentation.run_stardist                 # all folds; finished folds skipped
    python -m segmentation.run_stardist --folds 0 1
"""

from __future__ import annotations

import os

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")       # StarDist / CSBDeep are written for Keras 2

import argparse
import shutil
import time
from pathlib import Path

import cv2
import numpy as np

from config import load_config
from segmentation.data import Sample, augment, load_samples
from segmentation.metrics import print_summary, score_run
from segmentation.postprocess import instances_to_mask, mask_to_instances


def to_input(img: np.ndarray) -> np.ndarray:
    """Percentile normalisation expected by StarDist, clipped to 0..1 for the shared augmentation."""
    from csbdeep.utils import normalize
    return np.clip(normalize(img, 1, 99.8), 0, 1).astype(np.float32)


def make_augmenter(seed: int):
    rng = np.random.default_rng(seed)

    def aug(x: np.ndarray, y: np.ndarray):
        x, y = augment(x, y.astype(np.uint16), rng)       # same augmentation as the other models
        return x, y.astype(np.int32)
    return aug


def finetune(train: list[Sample], val: list[Sample], sd: dict, fold_dir: Path, seed: int):
    import tensorflow as tf
    from stardist import fill_label_holes
    from stardist.models import StarDist2D

    tf.keras.utils.set_random_seed(seed)
    pretrained = StarDist2D.from_pretrained(sd["pretrained"])
    if fold_dir.exists():
        shutil.rmtree(fold_dir)                           # unfinished earlier attempt
    shutil.copytree(pretrained.logdir, fold_dir)
    model = StarDist2D(None, name=fold_dir.name, basedir=str(fold_dir.parent))

    model.config.train_batch_size = sd["batch_size"]
    model.config.train_learning_rate = sd["learning_rate"]
    model.config.train_patch_size = train[0].image.shape
    model.prepare_for_training()

    prep = lambda group: ([to_input(s.image) for s in group],
                          [fill_label_holes(mask_to_instances(s.mask)) for s in group])
    x_train, y_train = prep(train)
    x_val, y_val = prep(val)
    model.train(x_train, y_train, validation_data=(x_val, y_val), augmenter=make_augmenter(seed),
                epochs=sd["epochs"], steps_per_epoch=sd["steps_per_epoch"])
    model.optimize_thresholds(x_val, y_val)               # on held-out TRAINING crops only
    return model


def main() -> None:
    cfg = load_config()
    sm, sd = cfg["seg_models"], cfg["seg_models"]["stardist"]

    ap = argparse.ArgumentParser(description="StarDist fine-tuned on the shared folds.")
    ap.add_argument("--preprocess", choices=["raw", "flat"], default=sm["preprocess"])
    ap.add_argument("--folds", type=int, nargs="*", help="only these folds (default: all)")
    ap.add_argument("--force", action="store_true", help="redo folds that are already predicted")
    args = ap.parse_args()

    import tensorflow as tf
    print(f"TensorFlow {tf.__version__}, GPUs: {len(tf.config.list_physical_devices('GPU'))}")

    run = f"stardist_finetune_{args.preprocess}"
    out_dir = cfg["paths"]["outputs_dir"] / "seg" / run
    inst_dir = out_dir / "inst"
    inst_dir.mkdir(parents=True, exist_ok=True)
    model_root = cfg["paths"]["models_dir"] / "seg" / run
    model_root.mkdir(parents=True, exist_ok=True)
    samples = load_samples(cfg, args.preprocess)

    for k in (args.folds if args.folds else range(sm["n_folds"])):
        test = [s for s in samples if s.fold == k]
        if not args.force and all((inst_dir / f"{s.crop_id}.png").exists() for s in test):
            print(f"  fold {k}: done already - skipped")
            continue
        rest = [s for s in samples if s.fold != k]
        rng = np.random.default_rng(sd["seed"] + k)
        val_ids = set(rng.choice([s.crop_id for s in rest], size=sd["n_val_crops"], replace=False))
        train = [s for s in rest if s.crop_id not in val_ids]
        val = [s for s in rest if s.crop_id in val_ids]
        print(f"  fold {k}: fine-tune on {len(train)} crops (+{len(val)} validation), test {len(test)} crops",
              flush=True)

        t0 = time.time()
        model = finetune(train, val, sd, model_root / f"fold{k}", sd["seed"] + k)
        for s in test:
            inst, _ = model.predict_instances(to_input(s.image))
            cv2.imwrite(str(inst_dir / f"{s.crop_id}.png"), inst.astype(np.uint16))
        print(f"  fold {k}: finished in {(time.time() - t0) / 60:.1f} min  "
              f"(thresholds prob {model.thresholds.prob:.2f}, nms {model.thresholds.nms:.2f})", flush=True)

    preds = {s.crop_id: instances_to_mask(cv2.imread(str(inst_dir / f"{s.crop_id}.png"), cv2.IMREAD_UNCHANGED))
             for s in samples if (inst_dir / f"{s.crop_id}.png").exists()}
    scores = score_run(samples, preds, out_dir)
    if len(scores) < len(samples):
        print(f"\nOnly {len(scores)} / {len(samples)} crops predicted so far - run the remaining folds.")
    print_summary(run, scores)
    print(f"Results: {out_dir}")


if __name__ == "__main__":
    main()
