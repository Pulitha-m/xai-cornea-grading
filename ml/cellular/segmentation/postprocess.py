"""
Model outputs -> the common cell mask (0 interior / 1 wall / 2 ignore).

walls_to_mask      wall-map models (U-Net, U-Net++, SegFormer, nnU-Net). Same idea
                   as the classical baseline: one seed per basin enclosed by walls
                   of at least `h` contrast, then a watershed whose 1-px lines
                   become the walls.
instances_to_mask  instance models (Cellpose, StarDist): background and the
                   boundary pixels of every cell become walls.
"""

from __future__ import annotations

import numpy as np
from skimage.measure import label
from skimage.morphology import h_minima
from skimage.segmentation import find_boundaries, watershed

from data_prep.check_annotations import IGNORE, INTERIOR, WALL


def walls_to_mask(wall_prob: np.ndarray, h: float, valid: np.ndarray | None = None) -> np.ndarray:
    """uint8 mask (0 interior / 1 wall / 2 ignore outside `valid`)."""
    prob = wall_prob.astype(np.float32)
    valid = np.ones(prob.shape, bool) if valid is None else valid
    markers = label(h_minima(prob, h).astype(bool) & valid, connectivity=2)
    ws = watershed(prob, markers, mask=valid, watershed_line=True)
    mask = np.where(ws == 0, WALL, INTERIOR).astype(np.uint8)
    mask[~valid] = IGNORE
    return mask


def instances_to_mask(instances: np.ndarray) -> np.ndarray:
    """Instance labels (0 = background) -> uint8 mask; touching cells are split by their boundary pixels."""
    walls = (instances == 0) | find_boundaries(instances, connectivity=1, mode="inner")
    return np.where(walls, WALL, INTERIOR).astype(np.uint8)


def mask_to_instances(mask: np.ndarray) -> np.ndarray:
    """Reference mask -> instance labels for training instance models (all cells, incl. edge cells).
    Ignore regions become background: these models have no ignore label."""
    return label(mask == INTERIOR, connectivity=1).astype(np.int32)
