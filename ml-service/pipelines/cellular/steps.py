"""Image steps of the validated cellular pipeline: lit area + flat image, ROI from tile probabilities,
segmentation post-processing.

Copied unchanged from ml/cellular (commit 7c26b0d) - keep identical; tests/test_cellular_parity.py checks the
served numbers against the validated pipeline:
  ClassicalParams, flatten_illumination   segmentation/classical.py
  image_planes, crop                      roi/tiles.py
  window_grid, prob_map, roi_from_prob    roi/roimap.py
  normalise_lit, instance_prob_image      segmentation/infer_full.py
  instances_to_mask                       segmentation/postprocess.py
  INTERIOR, WALL, IGNORE                  data_prep/check_annotations.py
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage.segmentation import find_boundaries

INTERIOR, WALL, IGNORE = 0, 1, 2


@dataclass(frozen=True)
class ClassicalParams:
    """Tunable parameters; *_factor values are multiples of cell_px."""
    method: str = "ridge"
    cell_px: float = 28.2
    ridge_sigmas_px: tuple[float, ...] = (1.5, 2.5)
    h_threshold: float = 0.30
    dark_threshold: float = 40.0
    smooth_sigma_factor: float = 0.08
    seed_sigma_factor: float = 0.22
    min_seed_distance_factor: float = 0.45
    min_area_factor: float = 0.30
    max_area_factor: float = 2.50

    @classmethod
    def from_config(cls, cfg: dict) -> "ClassicalParams":
        c = dict(cfg.get("classical", {}))
        c.pop("draft_h_threshold", None)
        if "ridge_sigmas_px" in c:
            c["ridge_sigmas_px"] = tuple(c["ridge_sigmas_px"])
        return cls(cell_px=float(cfg["image"]["cell_spacing_px"]), **c)


def flatten_illumination(img: np.ndarray, p: ClassicalParams) -> tuple[np.ndarray, np.ndarray]:
    """Return (flattened image in 0..1, valid mask)."""
    f = img.astype(np.float32)
    background = cv2.GaussianBlur(f, (0, 0), 2 * p.cell_px)
    valid = background > p.dark_threshold
    # Shrink the valid area by one cell so half-lit cells at its edge are not analysed.
    k = max(3, int(round(p.cell_px)) | 1)
    valid = cv2.erode(valid.astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool)

    flat = f / np.maximum(background, 1.0)
    if valid.any():
        lo, hi = np.percentile(flat[valid], [1, 99])
        flat = np.clip((flat - lo) / (hi - lo + 1e-6), 0, 1)
    flat[~valid] = 0

    # Local contrast equalisation (tile ~ 4 cells) evens out residual shading.
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    flat = clahe.apply((flat * 255).astype(np.uint8)).astype(np.float32) / 255.0
    flat[~valid] = 0
    return flat, valid


def image_planes(img: np.ndarray, flat: np.ndarray, lit: np.ndarray) -> np.ndarray:
    """uint8 grayscale image -> (3, H, W) uint8 planes raw / flat / lit (roi/tiles.py, flatten done once)."""
    return np.stack([img, (flat * 255).astype(np.uint8), lit.astype(np.uint8) * 255])


def crop(planes: np.ndarray, y0: int, x0: int, size: int) -> np.ndarray:
    return planes[:, y0:y0 + size, x0:x0 + size]


def window_grid(height: int, width: int, size: int, stride: int) -> list[tuple[int, int]]:
    """Top-left corners of all windows; the last row / column is aligned to the image edge."""
    ys = list(range(0, height - size + 1, stride))
    xs = list(range(0, width - size + 1, stride))
    if ys[-1] != height - size:
        ys.append(height - size)
    if xs[-1] != width - size:
        xs.append(width - size)
    return [(y, x) for y in ys for x in xs]


def prob_map(probs, windows: list[tuple[int, int]], shape: tuple[int, int], size: int) -> np.ndarray:
    """Per-pixel mean of the window probabilities."""
    acc = np.zeros(shape, np.float32)
    cnt = np.zeros(shape, np.float32)
    for p, (y, x) in zip(probs, windows):
        acc[y:y + size, x:x + size] += p
        cnt[y:y + size, x:x + size] += 1
    return acc / np.maximum(cnt, 1)


def _drop_small(mask: np.ndarray, min_px: int) -> np.ndarray:
    """Remove 8-connected parts smaller than min_px."""
    lab, n = ndi.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return mask
    keep = np.bincount(lab.ravel()) >= min_px
    keep[0] = False
    return keep[lab]


def roi_from_prob(prob: np.ndarray, lit: np.ndarray, threshold: float, min_island_px: int) -> np.ndarray:
    m = _drop_small((prob >= threshold) & lit, min_island_px)
    holes = _drop_small(~m, min_island_px)        # background parts large enough to stay background
    return ~holes & lit


def normalise_lit(x: np.ndarray, lit: np.ndarray, pmin: float, pmax: float) -> np.ndarray:
    """Percentile normalisation over the LIT tissue only, clipped to 0..1 (dark area -> 0)."""
    lo, hi = np.percentile(x[lit], [pmin, pmax]) if lit.any() else (0.0, 1.0)
    out = np.clip((x - lo) / (hi - lo + 1e-6), 0, 1).astype(np.float32)
    out[~lit] = 0
    return out


def instance_prob_image(labels: np.ndarray, prob: np.ndarray, points: np.ndarray) -> np.ndarray:
    """StarDist details -> per-pixel object probability of the instance it belongs to (0 = background,
    NaN = an instance whose centre point was overwritten by a neighbour); higher prob wins on conflicts."""
    lut = np.full(int(labels.max()) + 1, np.nan, np.float32)
    lut[0] = 0
    if len(prob):
        pts = np.clip(np.round(np.asarray(points)).astype(int), 0, np.array(labels.shape) - 1)
        at = labels[pts[:, 0], pts[:, 1]]
        for i in np.argsort(prob, kind="stable"):
            if at[i] > 0:
                lut[at[i]] = prob[i]
    return lut[labels]


def instances_to_mask(instances: np.ndarray) -> np.ndarray:
    """Instance labels (0 = background) -> uint8 mask; touching cells are split by their boundary pixels."""
    walls = (instances == 0) | find_boundaries(instances, connectivity=1, mode="inner")
    return np.where(walls, WALL, INTERIOR).astype(np.uint8)
