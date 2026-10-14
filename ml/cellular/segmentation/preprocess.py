"""
Component 3 preprocessing, shared by every segmentation model (Phase 2).

Two modes, compared as an ablation on the winning model:
    raw   grayscale / 255, nothing else
    flat  illumination flattening + percentile stretch + CLAHE inside the lit
          area (the same steps as the classical baseline, segmentation/classical.py)

Always applied to the FULL image and cropped afterwards, so training crops and
full-image inference see identical intensities.
"""

from __future__ import annotations

import numpy as np

from segmentation.classical import ClassicalParams, flatten_illumination

MODES = ("raw", "flat")


class Preprocessor:
    def __init__(self, cfg: dict, mode: str):
        if mode not in MODES:
            raise ValueError(f"preprocess mode must be one of {MODES}, got {mode!r}")
        self.mode = mode
        self.params = ClassicalParams.from_config(cfg)

    def __call__(self, img: np.ndarray) -> np.ndarray:
        """uint8 grayscale image -> float32 in 0..1."""
        if self.mode == "raw":
            return img.astype(np.float32) / 255.0
        return flatten_illumination(img, self.params)[0].astype(np.float32)
