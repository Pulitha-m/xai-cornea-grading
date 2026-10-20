"""
Error analysis — Konan-sized patches on synthetic per-cell tables with known density.

Run (from ml/cellular/):  python -m pytest tests/test_error_analysis.py -q
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from biomarkers.error_analysis import patch_stats, pick


def grid_cells(spacing_left: float, spacing_right: float, shape=(972, 1296)) -> pd.DataFrame:
    """Cells on square grids; left half one density, right half another. Area = spacing^2."""
    rows = []
    for x0, x1, s in ((0, shape[1] // 2, spacing_left), (shape[1] // 2, shape[1], spacing_right)):
        for cy in np.arange(s / 2, shape[0], s):
            for cx in np.arange(x0 + s / 2, x1, s):
                rows.append({"cx": cx, "cy": cy, "area_px": s * s, "sides": 6.0 if cx < 300 else 5.0})
    return pd.DataFrame(rows)


def test_patches_see_the_density_difference_and_counts():
    cells = grid_cells(20, 25)
    p = patch_stats(cells, 1.0, 252, 63, 60)
    assert len(p) > 0 and (p["n_cells"] >= 60).all()
    # pure left / right patches: ECD = 1e6 / spacing^2
    assert np.isclose(p["ecd"].max(), 1e6 / 400) and np.isclose(p["ecd"].min(), 1e6 / 625)
    assert np.allclose(p["cv"][p["ecd"].isin([1e6 / 400, 1e6 / 625])], 0)


def test_rules_pick_expected_patches():
    cells = grid_cells(20, 20)
    p = patch_stats(cells, 1.0, 252, 63, 60)
    assert pick(p, "most regular patch (max HEX)")["x"] < 300 - 252 + 63     # the all-hexagon strip on the left
    c = pick(p, "centre patch")
    assert abs(c["x"] + 126 - 648) <= 63 and abs(c["y"] + 126 - 486) <= 63
    assert pick(pd.DataFrame(), "centre patch") is None


def test_too_sparse_patches_are_dropped():
    cells = grid_cells(60, 60)                       # ~16 cells per 252 px patch
    assert patch_stats(cells, 1.0, 252, 63, 60).empty
