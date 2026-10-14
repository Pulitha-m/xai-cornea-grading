"""
Wall probability map -> cell mask, shared by every wall-map model (U-Net,
U-Net++, SegFormer, nnU-Net). Same idea as the classical baseline: one seed per
basin enclosed by walls of at least `h` contrast, then a watershed whose 1-px
lines become the walls.
"""

from __future__ import annotations

import numpy as np
from skimage.measure import label
from skimage.morphology import h_minima
from skimage.segmentation import watershed

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
