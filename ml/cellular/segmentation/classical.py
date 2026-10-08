"""
Classical (non-learning) cell segmentation for corneal specular images — Phase 1.

Two roles in Component 3:
  1. Baseline that the U-Net (Sub-component 3.2) must beat.
  2. Draft boundary masks for annotation (correcting is faster than drawing).

Method:
  1. Flatten illumination: divide by a heavily blurred background; ignore areas
     that are too dark to analyse ("valid" mask, eroded by one cell).
  2. Contrast-normalise inside the valid area (percentile stretch + CLAHE).
  3. Seeds + watershed, two variants (config: classical.method):
       "ridge" (default) — enhance the thin dark cell WALLS with a Sato ridge
           filter; seeds are basins enclosed by walls of at least h_threshold
           contrast (h-minima). Cell size comes from the image, not a parameter.
       "seeds" (v1)      — cell CENTRES as bright local maxima with a minimum
           spacing. Kept for comparison: its cell size is set by the spacing
           parameter, so it merges cells when interiors are uneven.
  4. Marker-controlled watershed with a 1-px wall between neighbouring cells.
  5. Keep only complete cells: plausible area, not touching the image border or
     the edge of the valid area. Size limits are multiples of the expected
     hexagon area for the ~28 px cell spacing (from the audit).

Usage:
    from segmentation.classical import ClassicalParams, segment
    res = segment(gray_image, ClassicalParams.from_config(cfg))
    res.labels      # int32 label map of kept cells (0 = wall / background)
    res.boundary    # uint8 0/1 wall map — draft annotation
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage.feature import peak_local_max
from skimage.filters import sato
from skimage.measure import label, regionprops
from skimage.morphology import h_minima
from skimage.segmentation import relabel_sequential, watershed


@dataclass(frozen=True)
class ClassicalParams:
    """Tunable parameters; *_factor values are multiples of cell_px."""
    method: str = "ridge"                       # "ridge" or "seeds"
    cell_px: float = 28.2
    ridge_sigmas_px: tuple[float, ...] = (1.5, 2.5)
    h_threshold: float = 0.12
    dark_threshold: float = 40.0
    smooth_sigma_factor: float = 0.08
    seed_sigma_factor: float = 0.22
    min_seed_distance_factor: float = 0.45
    min_area_factor: float = 0.30
    max_area_factor: float = 2.50

    @classmethod
    def from_config(cls, cfg: dict) -> "ClassicalParams":
        """Build parameters from config.yaml (image.cell_spacing_px + classical.*)."""
        c = dict(cfg.get("classical", {}))
        if "ridge_sigmas_px" in c:                       # YAML list -> hashable tuple
            c["ridge_sigmas_px"] = tuple(c["ridge_sigmas_px"])
        return cls(cell_px=float(cfg["image"]["cell_spacing_px"]), **c)

    @property
    def expected_area_px(self) -> float:
        """Area of a regular hexagon whose centre-to-centre distance is cell_px."""
        return np.sqrt(3) / 2 * self.cell_px ** 2


@dataclass
class ClassicalResult:
    labels: np.ndarray       # int32; 1..n_cells = kept complete cells, 0 = everything else
    boundary: np.ndarray     # uint8 0/1; watershed walls inside the valid area
    valid: np.ndarray        # bool; area where segmentation was attempted
    flat: np.ndarray         # float32 0..1; illumination-flattened image (for display)
    n_cells: int
    areas_px: np.ndarray     # area of each kept cell, px
    n_regions: int = 0       # all watershed regions before filtering (diagnostic)

    @property
    def kept_fraction(self) -> float:
        """Share of watershed regions kept as complete cells; low = many merges / edge cells."""
        return self.n_cells / self.n_regions if self.n_regions else float("nan")

    @property
    def mean_area_px(self) -> float:
        return float(self.areas_px.mean()) if self.n_cells else float("nan")

    def ecd(self, um_per_px: float) -> float:
        """Konan-style ECD (cells/mm^2) = 1e6 / mean cell area in um^2."""
        return 1e6 / (self.mean_area_px * um_per_px ** 2) if self.n_cells else float("nan")

    def cv_percent(self) -> float:
        """Coefficient of variation of cell area, % (population SD)."""
        return float(100 * self.areas_px.std() / self.areas_px.mean()) if self.n_cells else float("nan")


# -----------------------------------------------------------------------------
# Steps
# -----------------------------------------------------------------------------
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


def wall_map(flat: np.ndarray, valid: np.ndarray, p: ClassicalParams) -> np.ndarray:
    """0..1 map that is high on thin dark cell walls ("ridge" method)."""
    walls = sato(flat, sigmas=p.ridge_sigmas_px, black_ridges=True).astype(np.float32)
    walls[~valid] = 0
    if valid.any():
        walls = np.clip(walls / (np.percentile(walls[valid], 99) + 1e-6), 0, 1)
    return cv2.GaussianBlur(walls, (0, 0), 1.0)


def detect_basins(walls: np.ndarray, valid: np.ndarray, p: ClassicalParams) -> np.ndarray:
    """Marker image: one label per basin enclosed by walls of >= h_threshold contrast."""
    minima = h_minima(walls, p.h_threshold).astype(bool) & valid
    return label(minima, connectivity=2).astype(np.int32)


def detect_cell_centres(flat: np.ndarray, valid: np.ndarray, p: ClassicalParams) -> np.ndarray:
    """Marker image: one integer label per detected cell centre ("seeds" method)."""
    seed_map = cv2.GaussianBlur(flat, (0, 0), p.seed_sigma_factor * p.cell_px)
    coords = peak_local_max(
        seed_map,
        min_distance=max(1, int(round(p.min_seed_distance_factor * p.cell_px))),
        labels=valid.astype(np.int32),
        exclude_border=False,
    )
    markers = np.zeros(flat.shape, np.int32)
    markers[tuple(coords.T)] = np.arange(1, len(coords) + 1)
    return markers


def segment(img: np.ndarray, p: ClassicalParams | None = None) -> ClassicalResult:
    """Segment one grayscale specular image into individual cells."""
    p = p or ClassicalParams()
    flat, valid = flatten_illumination(img, p)

    if p.method == "ridge":
        elevation = wall_map(flat, valid, p)             # walls high, interiors low
        markers = detect_basins(elevation, valid, p)
    elif p.method == "seeds":
        markers = detect_cell_centres(flat, valid, p)
        # bright interiors become basins, dark walls ridges
        elevation = -cv2.GaussianBlur(flat, (0, 0), p.smooth_sigma_factor * p.cell_px)
    else:
        raise ValueError(f"unknown method {p.method!r} (use 'ridge' or 'seeds')")

    # watershed_line leaves a 1-px wall (label 0) between neighbouring cells.
    ws = watershed(elevation, markers, mask=valid, watershed_line=True)
    boundary = ((ws == 0) & valid).astype(np.uint8)
    n_regions = int(len(np.unique(ws)) - (1 if (ws == 0).any() else 0))

    # --- keep only complete, plausibly sized cells ---------------------------
    edge_zone = ndi.binary_dilation(~valid, iterations=2)
    edge_zone[[0, -1], :] = True
    edge_zone[:, [0, -1]] = True
    touching = set(np.unique(ws[edge_zone])) - {0}

    lo = p.min_area_factor * p.expected_area_px
    hi = p.max_area_factor * p.expected_area_px
    keep = [r.label for r in regionprops(ws)
            if r.label not in touching and lo <= r.area <= hi]

    labels = np.where(np.isin(ws, keep), ws, 0).astype(np.int32)
    labels, _, _ = relabel_sequential(labels)
    areas = np.bincount(labels.ravel())[1:].astype(np.float64)

    return ClassicalResult(labels=labels, boundary=boundary, valid=valid, flat=flat,
                           n_cells=int(labels.max()), areas_px=areas, n_regions=n_regions)


# -----------------------------------------------------------------------------
# Helpers for annotation and display
# -----------------------------------------------------------------------------
def draft_boundary_mask(result: ClassicalResult, width_px: int = 2) -> np.ndarray:
    """Wall mask for annotation drafts: 255 = wall, 0 = interior / background."""
    walls = result.boundary.astype(np.uint8)
    if width_px > 1:
        walls = cv2.dilate(walls, np.ones((width_px, width_px), np.uint8))
    return walls * 255


def overlay(img: np.ndarray, result: ClassicalResult) -> np.ndarray:
    """RGB view: kept cells tinted green, walls red, unanalysed area darkened."""
    base = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB).astype(np.float32)
    base[~result.valid] *= 0.35
    cells = result.labels > 0
    base[cells] = 0.75 * base[cells] + 0.25 * np.array([0, 255, 0], np.float32)
    base[result.boundary.astype(bool)] = (255, 0, 0)
    return base.clip(0, 255).astype(np.uint8)
