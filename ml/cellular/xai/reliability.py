"""
XAI step 2 — explaining the biomarkers: per-cell reliability, evidence, uncertainty.

  cell_confidence(...)      StarDist object probability per measured cell (median over its pixels)
  reliability(...)          GREEN / YELLOW / RED per cell (rules: config xai.biomarkers)
  bootstrap_ci(...)         95 % CI of ECD, CV, HEX by bootstrap over spatial blocks of cells
                            (block_px = 0: over single cells)
  variance_share(...)       the most extreme cells and their share of the area variance (why this CV)
  reliability_overlay / area_overlay / sides_overlay   RGB images of the measured cells

The biomarkers themselves are fixed formulas (biomarkers/compute.py); nothing here changes them.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import ndimage as ndi

from extraction.cells import overlay_sides

LEVEL_RGB = {"green": (60, 190, 60), "yellow": (245, 200, 0), "red": (225, 40, 40)}


def cell_confidence(cell_labels: np.ndarray, prob_img: np.ndarray, ids) -> pd.Series:
    """Median object probability over each cell's pixels that came from a StarDist instance
    (background 0 ignored; NaN = unknown instance). Index = cell_id."""
    m = (cell_labels > 0) & (prob_img != 0)
    df = pd.DataFrame({"cell_id": cell_labels[m], "p": prob_img[m]})
    return df.groupby("cell_id")["p"].median().reindex(pd.Index(ids, name="cell_id"))


def reliability(cells: pd.DataFrame, confidence: pd.Series, prob_thresh: float, rules: dict) -> pd.DataFrame:
    """Per cell: confidence, the three signals and the level (index = cell_id)."""
    c = cells.set_index("cell_id")
    conf = confidence.reindex(c.index)
    size = c["flag_small"].astype(bool) | c["flag_large"].astype(bool)
    lo, hi = rules["sides_range"]
    sides = c["sides"]
    shape = (sides.notna() & ((sides < lo) | (sides > hi))) | (c["compactness"] < rules["min_compactness"])
    low = conf.isna() | (conf < (prob_thresh + 1) / 2)
    level = np.where(size | shape, "red", np.where(low, "yellow", "green"))
    return pd.DataFrame({"confidence": conf, "implausible_size": size, "implausible_shape": shape,
                         "low_confidence": low, "level": level}, index=c.index)


def _block_sums(cells: pd.DataFrame, block_px: int) -> np.ndarray:
    """Per block (or per cell if block_px = 0): sum area, sum area^2, n, n six-sided, n with sides."""
    a = cells["area_px"].to_numpy(float)
    s = cells["sides"].to_numpy(float)
    cols = np.stack([a, a * a, np.ones_like(a), (s == 6).astype(float), (~np.isnan(s)).astype(float)], 1)
    if not block_px:
        return cols
    key = (cells["cy"].to_numpy() // block_px).astype(np.int64) * 100000 + (cells["cx"].to_numpy() // block_px)
    _, inv = np.unique(key, return_inverse=True)
    out = np.zeros((inv.max() + 1, 5))
    np.add.at(out, inv, cols)
    return out


def _stats(t: np.ndarray, um_per_px: float) -> np.ndarray:
    """Totals (..., 5) -> ECD, CV %, HEX % (same definitions as biomarkers/compute.py)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = t[..., 0] / t[..., 2]
        ecd = 1e6 / (mean * um_per_px ** 2)
        cv = 100 * np.sqrt(np.maximum(t[..., 1] / t[..., 2] - mean ** 2, 0)) / mean
        hexp = np.where(t[..., 4] > 0, 100 * t[..., 3] / t[..., 4], np.nan)
    return np.stack([ecd, cv, hexp], -1)


def bootstrap_ci(cells: pd.DataFrame, um_per_px: float, block_px: int, n_boot: int, seed: int,
                 level: float = 95) -> dict:
    """{'ecd'|'cv'|'hex': {'value', 'lo', 'hi'}}: percentile CI, resampling blocks with replacement."""
    names = ("ecd", "cv", "hex")
    if len(cells) < 2:
        return {k: {"value": None, "lo": None, "hi": None} for k in names}
    sums = _block_sums(cells, block_px)
    value = _stats(sums.sum(0), um_per_px)
    rng = np.random.default_rng(seed)
    w = rng.multinomial(len(sums), np.full(len(sums), 1 / len(sums)), size=n_boot)
    boot = _stats(w @ sums, um_per_px)
    q = (100 - level) / 2
    lo, hi = np.nanpercentile(boot, [q, 100 - q], axis=0)
    rnd = lambda x: None if not np.isfinite(x) else round(float(x), 3)
    return {k: {"value": rnd(value[i]), "lo": rnd(lo[i]), "hi": rnd(hi[i])} for i, k in enumerate(names)}


def variance_share(cells: pd.DataFrame, top_share: float) -> tuple[np.ndarray, float]:
    """cell_ids of the top_share most extreme cells (largest squared deviation from the mean area)
    and their share of the area variance."""
    a = cells["area_px"].to_numpy(float)
    if len(a) < 2:
        return np.array([], int), float("nan")
    d = (a - a.mean()) ** 2
    k = max(1, math.ceil(top_share * len(a)))
    top = np.argsort(-d, kind="stable")[:k]
    return cells["cell_id"].to_numpy()[top], float(d[top].sum() / d.sum()) if d.sum() > 0 else float("nan")


# ---------------------------------------------------------------- overlays ----------
def _paint(img: np.ndarray, complete: np.ndarray, lut: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    """Tint each cell with lut[cell_id] (RGB; NaN = no tint), thin black outlines."""
    view = np.dstack([img] * 3).astype(np.float32)
    cells = complete > 0
    col = lut[complete[cells]]
    ok = ~np.isnan(col).any(1)
    idx = np.flatnonzero(cells.ravel())[ok]
    flat = view.reshape(-1, 3)
    flat[idx] = (1 - alpha) * flat[idx] + alpha * col[ok]
    view[complete != ndi.grey_erosion(complete, size=3)] = 0
    return view.clip(0, 255).astype(np.uint8)


def reliability_overlay(img: np.ndarray, complete: np.ndarray, rel: pd.DataFrame) -> np.ndarray:
    lut = np.full((int(complete.max()) + 1, 3), np.nan, np.float32)
    for lev, rgb in LEVEL_RGB.items():
        lut[rel.index[rel["level"] == lev].to_numpy()] = rgb
    return _paint(img, complete, lut)


def area_overlay(img: np.ndarray, complete: np.ndarray, cells: pd.DataFrame, top_ids) -> np.ndarray:
    """Cells coloured by area relative to the median (blue = half or less, white = median, red = double or
    more); the most extreme cells (variance_share) outlined in yellow."""
    from matplotlib import colormaps
    lut = np.full((int(complete.max()) + 1, 3), np.nan, np.float32)
    r = np.clip(np.log2(cells["area_px"].to_numpy(float) / cells["area_px"].median()), -1, 1)
    lut[cells["cell_id"].to_numpy()] = colormaps["coolwarm"]((r + 1) / 2)[:, :3] * 255
    view = _paint(img, complete, lut, alpha=0.6)
    top = np.isin(complete, np.asarray(top_ids)) & (complete > 0)
    edge = top & ~ndi.binary_erosion(top, iterations=2)
    view[edge] = (255, 230, 0)
    return view


def sides_overlay(img: np.ndarray, complete: np.ndarray, cells: pd.DataFrame) -> np.ndarray:
    """Phase 3 side-count overlay (<=4 purple, 5 orange, 6 green, 7 blue, >=8 red, unknown grey), as RGB."""
    return overlay_sides(img, complete, cells)[..., ::-1].copy()
