"""
Phase 2, Step 2.1 — annotated crops, reference masks and augmentation.

Reference mask per crop: the expert-revised mask (expert/masks/) where it exists,
otherwise the researcher's mask (masks/), both written by
data_prep/check_annotations.py (0 = interior, 1 = wall, 2 = ignore).

Augmentation (numpy / OpenCV, identical for every trained model):
  * 90-degree rotations and flips (lossless; cells have no orientation)
  * small rotation and +-15 % zoom (cell size differs between tissues)
  * brightness / contrast / gamma, mild blur, Gaussian noise (image quality varies)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from segmentation.preprocess import Preprocessor


@dataclass
class Sample:
    crop_id: str
    fold: int
    image: np.ndarray          # float32 0..1, preprocessed full image cropped to the window
    mask: np.ndarray           # uint8 0 interior / 1 wall / 2 ignore
    mask_source: str           # "expert" or "annotator"
    meta: dict                 # index.csv row (image_file, y0, x0, size, ecd, ecd_band, difficulty, ...)


def round_dir(cfg: dict) -> Path:
    return cfg["paths"]["annotations_dir"] / "seg" / cfg["seg_models"]["round"]


def folds_path(cfg: dict) -> Path:
    return cfg["paths"]["splits_dir"] / f"seg_folds_{cfg['seg_models']['round']}.csv"


def reference_mask(rd: Path, crop_id: str) -> tuple[np.ndarray, str]:
    """Expert-revised mask if available, else the researcher's."""
    for who, path in (("expert", rd / "expert" / "masks" / f"{crop_id}.png"),
                      ("annotator", rd / "masks" / f"{crop_id}.png")):
        if path.exists():
            return cv2.imread(str(path), cv2.IMREAD_GRAYSCALE), who
    raise FileNotFoundError(f"no mask for {crop_id} - run python -m data_prep.check_annotations first")


def load_samples(cfg: dict, mode: str) -> list[Sample]:
    """All annotated crops with their fold, preprocessed with `mode`."""
    rd = round_dir(cfg)
    if not folds_path(cfg).exists():
        raise FileNotFoundError(f"{folds_path(cfg)} missing - run python -m data_prep.make_seg_folds first")
    index = pd.read_csv(rd / "index.csv").merge(
        pd.read_csv(folds_path(cfg))[["crop_id", "fold"]], on="crop_id", how="inner")
    pre = Preprocessor(cfg, mode)

    samples = []
    for _, r in index.iterrows():
        img = cv2.imread(str(cfg["paths"]["images_dir"] / r["image_file"]), cv2.IMREAD_GRAYSCALE)
        y0, x0, size = int(r["y0"]), int(r["x0"]), int(r["size"])
        mask, who = reference_mask(rd, r["crop_id"])
        samples.append(Sample(r["crop_id"], int(r["fold"]), pre(img)[y0:y0 + size, x0:x0 + size],
                              mask, who, r.to_dict()))
    return samples


def augment(img: np.ndarray, mask: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Random geometric + intensity augmentation of one crop (mask follows the geometry)."""
    k = int(rng.integers(4))
    img, mask = np.rot90(img, k), np.rot90(mask, k)
    if rng.random() < 0.5:
        img, mask = img[:, ::-1], mask[:, ::-1]
    img, mask = np.ascontiguousarray(img), np.ascontiguousarray(mask)

    if rng.random() < 0.5:                                   # small rotation + zoom
        h, w = img.shape
        m = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-15, 15), rng.uniform(0.85, 1.15))
        img = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
        mask = cv2.warpAffine(mask, m, (w, h), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_REFLECT_101)

    if rng.random() < 0.8:                                   # brightness / contrast / gamma
        img = np.clip(img * rng.uniform(0.8, 1.2) + rng.uniform(-0.1, 0.1), 0, 1) ** rng.uniform(0.8, 1.25)
    if rng.random() < 0.2:                                   # mild defocus
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.3, 1.0))
    if rng.random() < 0.3:                                   # sensor noise
        img = img + rng.normal(0, rng.uniform(0.005, 0.03), img.shape)
    return np.clip(img, 0, 1).astype(np.float32), mask
