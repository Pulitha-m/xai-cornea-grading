"""
Phase 5 (Sub-component 3.4) — biomarkers of one image from its per-cell table.

Input: the Phase 3 per-cell table (complete cells, areas in px, side counts)
and the Phase 4 scale (um/px). The image-level statistics come from
extraction.cells.summarise_cells, so they are defined exactly as in Phases 3-4;
this module only converts units and adds the distributions.

  ECD               cells/mm^2 = 1e6 / mean cell area [um^2]
  mean / SD area    um^2 (population SD, scope definition)
  CV                % = SD / mean x 100
  HEX               % of 6-sided cells among cells with a known side count
  compactness       4 pi A / P^2 per cell (1 = circle, 0.907 = regular hexagon): mean, SD, CV
  distributions     area percentiles (um^2), side-count shares (<=4, 5, 6, 7, >=8)

The report contains no Konan values: it is what the pipeline returns for a new image.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from extraction.cells import summarise_cells

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
    """Biomarker report of one image (the JSON the pipeline hands to the platform)."""
    return {"image_id": image_id, "component": "3 - cellular intelligence",
            "segmentation_run": run, "um_per_px": um_per_px,
            "cells_used": "all complete cells (not touching the image border or unanalysable area)",
            "biomarkers": compute_biomarkers(cells, um_per_px)}
