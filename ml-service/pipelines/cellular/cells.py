"""Complete cells, their measurements and the biomarker report.

Copied unchanged from ml/cellular (commit 7c26b0d) - keep identical; tests/test_cellular_parity.py checks the
served numbers against the validated pipeline:
  ExtractionParams, instances_from_mask, tessellate, complete_cells, side_counts, extract_cells,
  summarise_cells, SIDE_COLOURS, overlay_sides                            extraction/cells.py
  SIDE_BINS, compute_biomarkers, report                                    biomarkers/compute.py
"""
from __future__ import annotations

from dataclasses import dataclass, fields

import cv2
import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage.measure import label, regionprops_table
from skimage.segmentation import expand_labels

from pipelines.cellular.steps import INTERIOR

CELL_COLUMNS = ["cell_id", "area_px", "perimeter_px", "compactness", "eccentricity", "eq_diameter_px",
                "orientation", "cx", "cy", "sides", "sides_raw", "sides_poly", "n_neighbours", "open_fraction",
                "flag_small", "flag_large"]


@dataclass
class ExtractionParams:
    grow_px: int = 3
    edge_margin_px: int = 2
    ring_px: int = 2
    min_contact_fraction: float = 0.04
    max_open_fraction: float = 0.10
    poly_epsilon_fraction: float = 0.04
    min_area_factor: float = 0.25
    max_area_factor: float = 3.0

    @classmethod
    def from_config(cls, cfg: dict) -> "ExtractionParams":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in cfg["extraction"].items() if k in names})


def instances_from_mask(mask: np.ndarray) -> np.ndarray:
    """Common mask -> instance labels (walls / boundary pixels separate the cells)."""
    return label(mask == INTERIOR, connectivity=1).astype(np.int32)


def tessellate(instances: np.ndarray, analysable: np.ndarray, p: ExtractionParams) -> np.ndarray:
    """Grow every cell up to the wall centre line; nothing outside the analysable area."""
    grown = expand_labels(instances, distance=p.grow_px)
    grown[~analysable] = 0
    return grown


def complete_cells(tess: np.ndarray, analysable: np.ndarray, p: ExtractionParams) -> np.ndarray:
    """Keep cells that touch neither the image border nor the unanalysable area."""
    edge = ndi.binary_dilation(~analysable, iterations=p.edge_margin_px) if (~analysable).any() \
        else np.zeros(tess.shape, bool)
    m = max(1, p.edge_margin_px)
    edge[:m, :] = edge[-m:, :] = True
    edge[:, :m] = edge[:, -m:] = True
    out = tess.copy()
    out[np.isin(out, np.unique(tess[edge]))] = 0
    return out


def side_counts(tess: np.ndarray, ids: np.ndarray, p: ExtractionParams) -> pd.DataFrame:
    """Neighbour-based side count (on the full tessellation, so partial neighbours count) + polygon fit."""
    slices = ndi.find_objects(tess)
    pad = p.ring_px + 1
    rows = []
    for lab in ids:
        sl = slices[lab - 1]
        y0, x0 = max(sl[0].start - pad, 0), max(sl[1].start - pad, 0)
        crop = tess[y0:sl[0].stop + pad, x0:sl[1].stop + pad]
        me = crop == lab
        ring = ndi.binary_dilation(me, iterations=p.ring_px) & ~me
        vals = crop[ring]
        open_fraction = float((vals == 0).mean()) if len(vals) else 1.0
        labs, counts = np.unique(vals[vals > 0], return_counts=True)
        sides = int((counts >= p.min_contact_fraction * len(vals)).sum())

        contours, _ = cv2.findContours(me.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        c = max(contours, key=cv2.contourArea)
        poly = cv2.approxPolyDP(c, p.poly_epsilon_fraction * cv2.arcLength(c, True), True)
        rows.append({"cell_id": int(lab),
                     "sides": sides if open_fraction <= p.max_open_fraction else np.nan,
                     "sides_raw": sides,
                     "sides_poly": len(poly), "n_neighbours": len(labs), "open_fraction": open_fraction})
    return pd.DataFrame(rows)


def extract_cells(instances: np.ndarray, analysable: np.ndarray | None = None,
                  p: ExtractionParams | None = None) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Return (per-cell table, tessellation, complete-cell labels)."""
    p = p or ExtractionParams()
    analysable = np.ones(instances.shape, bool) if analysable is None else analysable.astype(bool)
    tess = tessellate(instances, analysable, p)
    complete = complete_cells(tess, analysable, p)
    ids = np.unique(complete)
    ids = ids[ids > 0]
    if len(ids) == 0:
        return pd.DataFrame(columns=CELL_COLUMNS), tess, complete

    props = pd.DataFrame(regionprops_table(
        complete, properties=("label", "area", "perimeter_crofton", "centroid", "eccentricity",
                              "equivalent_diameter_area", "orientation")))
    df = props.rename(columns={"label": "cell_id", "area": "area_px", "perimeter_crofton": "perimeter_px",
                               "centroid-0": "cy", "centroid-1": "cx",
                               "equivalent_diameter_area": "eq_diameter_px"})
    df["compactness"] = 4 * np.pi * df["area_px"] / df["perimeter_px"].clip(lower=1e-6) ** 2
    df = df.merge(side_counts(tess, ids, p), on="cell_id")
    median = df["area_px"].median()
    df["flag_small"] = df["area_px"] < p.min_area_factor * median
    df["flag_large"] = df["area_px"] > p.max_area_factor * median
    return df[CELL_COLUMNS], tess, complete


def summarise_cells(df: pd.DataFrame) -> dict:
    """Image-level summary in pixels: all complete cells, and without flagged cells.
    CV uses the population SD (scope definition); HEX % over cells with a known side count."""
    def stats(d: pd.DataFrame, suffix: str) -> dict:
        a = d["area_px"].astype(float)
        known = d["sides"].dropna()
        return {f"n_cells{suffix}": len(d),
                f"mean_area_px{suffix}": a.mean() if len(a) else np.nan,
                f"cv_area_pct{suffix}": 100 * a.std(ddof=0) / a.mean() if len(a) > 1 else np.nan,
                f"hex_pct{suffix}": 100 * (known == 6).mean() if len(known) else np.nan,
                f"n_sides_known{suffix}": len(known),
                f"mean_compactness{suffix}": d["compactness"].mean() if len(d) else np.nan}
    clean = df[~(df["flag_small"].astype(bool) | df["flag_large"].astype(bool))] if len(df) else df
    return {**stats(df, ""), **stats(clean, "_unflagged"), "n_flagged": len(df) - len(clean)}


SIDE_COLOURS = {4: (180, 60, 160), 5: (0, 140, 255), 6: (60, 190, 60), 7: (255, 160, 0), 8: (40, 40, 220)}


def overlay_sides(img: np.ndarray, complete: np.ndarray, df: pd.DataFrame) -> np.ndarray:
    """Cells coloured by side count (<=4 purple, 5 orange, 6 green, 7 blue, >=8 red, unknown grey). BGR."""
    view = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR).astype(np.float32)
    colour = np.zeros((int(complete.max()) + 1, 3), np.float32)
    for r in df.itertuples(index=False):
        s = r.sides
        colour[r.cell_id] = (150, 150, 150) if pd.isna(s) else SIDE_COLOURS[int(min(max(s, 4), 8))]
    cells = complete > 0
    view[cells] = 0.55 * view[cells] + 0.45 * colour[complete[cells]]
    view[complete != ndi.grey_erosion(complete, size=3)] = (0, 0, 0)      # thin outlines
    return view.clip(0, 255).astype(np.uint8)


SIDE_BINS = {"<=4": lambda s: s <= 4, "5": lambda s: s == 5, "6": lambda s: s == 6,
             "7": lambda s: s == 7, ">=8": lambda s: s >= 8}


def _num(x) -> float | None:
    """JSON-safe number (NaN -> None)."""
    return None if x is None or not np.isfinite(x) else round(float(x), 4)


def compute_biomarkers(cells: pd.DataFrame, um_per_px: float) -> dict:
    """Biomarkers of one image (all complete cells) in physical units."""
    s = summarise_cells(cells)
    um2 = um_per_px ** 2
    mean_um2 = s["mean_area_px"] * um2
    area_um2 = cells["area_px"].astype(float) * um2
    comp = cells["compactness"].astype(float)
    sides = cells["sides"].dropna()
    pct = np.percentile(area_um2, [5, 25, 50, 75, 95]) if len(area_um2) else [np.nan] * 5
    return {
        "n_cells": int(s["n_cells"]),
        "ecd_cells_per_mm2": _num(1e6 / mean_um2) if mean_um2 > 0 else None,
        "mean_area_um2": _num(mean_um2),
        "sd_area_um2": _num(area_um2.std(ddof=0)) if len(area_um2) > 1 else None,
        "cv_pct": _num(s["cv_area_pct"]),
        "hex_pct": _num(s["hex_pct"]),
        "n_cells_with_sides": int(s["n_sides_known"]),
        "mean_compactness": _num(comp.mean()) if len(comp) else None,
        "sd_compactness": _num(comp.std(ddof=0)) if len(comp) > 1 else None,
        "cv_compactness_pct": _num(100 * comp.std(ddof=0) / comp.mean()) if len(comp) > 1 else None,
        "area_percentiles_um2": dict(zip(["p5", "p25", "p50", "p75", "p95"], map(_num, pct))),
        "side_distribution_pct": {k: _num(100 * f(sides).mean()) if len(sides) else None
                                  for k, f in SIDE_BINS.items()},
        "n_flagged": int(s["n_flagged"]),
    }


def report(image_id: str, cells: pd.DataFrame, um_per_px: float, run: str) -> dict:
    """Biomarker report of one image."""
    return {"image_id": image_id, "component": "3 - cellular intelligence",
            "segmentation_run": run, "um_per_px": um_per_px,
            "cells_used": "all complete cells (not touching the image border or unanalysable area)",
            "biomarkers": compute_biomarkers(cells, um_per_px)}
