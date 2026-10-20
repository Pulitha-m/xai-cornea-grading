"""
Phase 6 — ROI tile data: labels, image planes, tile quality features, folds, tile IoU.

Labels come from the Phase 1 / Phase 6 labelling rounds (data_prep/roi_labeller.py):
every tile of a 6 x 8 grid (162 px) is good / usable / poor. The model target is
ANALYSABLE (good or usable) = 1 vs POOR = 0. Repeat labellings are only used for
the human ceiling (intra-rater IoU), never for training.

An image is represented by three uint8 planes (3, H, W):
  raw   the grayscale image
  flat  Component 3's flat preprocessing (illumination flattening + CLAHE, 0 outside the lit area)
  lit   the lit-area mask used so far (classical.flatten_illumination), 0 / 255
"""

from __future__ import annotations

import cv2
import numpy as np
import pandas as pd

from segmentation.classical import ClassicalParams, flatten_illumination

ANALYSABLE = {"good": 1, "usable": 1, "poor": 0}
FEATURES = ["lit_share", "raw_mean", "raw_std", "flat_std", "laplacian_var", "grad_mean",
            "cell_peak", "hf_ratio"]


def _bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq("true")


def load_labels(cfg: dict) -> pd.DataFrame:
    """First labelling of every tile in the configured rounds, with target y (1 = analysable)."""
    parts = []
    for rnd in cfg["roi_model"]["rounds"]:
        d = cfg["paths"]["annotations_dir"] / "roi" / rnd
        lab, idx = pd.read_csv(d / "labels.csv"), pd.read_csv(d / "index.csv")
        lab = lab[~_bool(lab["is_repeat"])]
        idx = idx[~_bool(idx["is_repeat"])][["image_id", "image_file", "group_id"]]
        parts.append(lab.merge(idx, on="image_id").assign(round=rnd))
    df = pd.concat(parts, ignore_index=True)
    df["y"] = df["label"].map(ANALYSABLE).astype(int)
    return df


def repeat_pairs(cfg: dict) -> pd.DataFrame:
    """Tiles labelled twice (blind, rotated repeats): first and repeat label, all rounds."""
    first, rep = [], []
    for rnd in cfg["roi_model"]["rounds"]:
        lab = pd.read_csv(cfg["paths"]["annotations_dir"] / "roi" / rnd / "labels.csv")
        is_rep = _bool(lab["is_repeat"])
        first.append(lab[~is_rep])
        rep.append(lab[is_rep])
    return pd.concat(rep).merge(pd.concat(first), on=["image_id", "tile_row", "tile_col"],
                                suffixes=("_repeat", "_first"))


def image_planes(cfg: dict, img: np.ndarray) -> np.ndarray:
    """uint8 grayscale image -> (3, H, W) uint8 planes raw / flat / lit."""
    flat, lit = flatten_illumination(img, ClassicalParams.from_config(cfg))
    return np.stack([img, (flat * 255).astype(np.uint8), lit.astype(np.uint8) * 255])


def crop(planes: np.ndarray, y0: int, x0: int, size: int) -> np.ndarray:
    return planes[:, y0:y0 + size, x0:x0 + size]


def tile_features(tile: np.ndarray, cell_px: float) -> np.ndarray:
    """Classical quality features of one (3, s, s) uint8 tile (order = FEATURES)."""
    raw = tile[0].astype(np.float32) / 255
    flat = tile[1].astype(np.float32) / 255
    lit = tile[2] > 0
    share = float(lit.mean())
    if share == 0:
        return np.array([0, raw.mean(), raw.std(), 0, 0, 0, 0, 0], np.float32)
    lap = cv2.Laplacian(flat, cv2.CV_32F)
    grad = np.hypot(cv2.Sobel(flat, cv2.CV_32F, 1, 0), cv2.Sobel(flat, cv2.CV_32F, 0, 1))
    # Strength of the regular cell pattern: spectral power in a ring at the cell spacing.
    s = flat.shape[0]
    win = np.outer(np.hanning(s), np.hanning(s))
    power = np.abs(np.fft.fftshift(np.fft.fft2((flat - flat[lit].mean()) * lit * win))) ** 2
    yy, xx = np.indices(power.shape) - s // 2
    r = np.hypot(yy, xx)
    f_cell = s / cell_px
    total = power[r > 1].sum() + 1e-9
    ring = power[(r > 0.8 * f_cell) & (r < 1.25 * f_cell)].sum()
    high = power[r > 1.6 * f_cell].sum()
    return np.array([share, raw.mean(), raw.std(), flat[lit].std(), lap[lit].var(), grad[lit].mean(),
                     ring / total, high / total], np.float32)


def make_folds(images: pd.DataFrame, n_folds: int, seed: int) -> dict:
    """image_id -> fold. Images (not tiles) are dealt to folds, balanced by their share of
    poor tiles (sorted, then snake order), so no image is in two folds."""
    rng = np.random.default_rng(seed)
    order = images.iloc[rng.permutation(len(images))].sort_values("poor_share", kind="stable")
    folds = {}
    for k, iid in enumerate(order["image_id"]):
        rnd, pos = divmod(k, n_folds)
        folds[iid] = pos if rnd % 2 == 0 else n_folds - 1 - pos
    return folds


def tile_iou(ref: np.ndarray, pred: np.ndarray) -> float:
    """IoU of the analysable area on a tile grid (both empty -> 1)."""
    ref, pred = np.asarray(ref, bool), np.asarray(pred, bool)
    union = (ref | pred).sum()
    return float((ref & pred).sum() / union) if union else 1.0


def mask_to_tiles(mask: np.ndarray, rows: int, cols: int, min_share: float = 0.5) -> np.ndarray:
    """Pixel mask -> tile grid: a tile is in if MORE than min_share of it is in the mask
    (the labelling protocol's 'more than half' rule)."""
    h, w = mask.shape
    t = mask.reshape(rows, h // rows, cols, w // cols).mean(axis=(1, 3))
    return t > min_share
