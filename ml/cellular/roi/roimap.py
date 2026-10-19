"""
Phase 6 — from window scores to an ROI mask.

Windows of one tile (162 px) slide over the image with half-tile stride; every
pixel gets the mean probability ("analysable") of the windows covering it.
ROI = (probability >= threshold) AND lit area; parts and holes smaller than
min_island_px are removed (holes are only filled where the image is lit).
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi


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


def largest_component(mask: np.ndarray) -> np.ndarray:
    lab, n = ndi.label(mask)
    if n == 0:
        return mask
    sizes = np.bincount(lab.ravel())[1:]
    return lab == (1 + int(np.argmax(sizes)))
