"""
Phase 5 — biomarkers from per-cell tables with known answers.

Run (from ml/cellular/):  python -m pytest tests/test_biomarkers.py -q
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from biomarkers.compute import compute_biomarkers, report
from extraction.cells import CELL_COLUMNS, ExtractionParams, extract_cells, instances_from_mask, summarise_cells
from tests.test_extraction import as_mask, hex_points, voronoi_labels


def cells(areas, sides, compactness=None) -> pd.DataFrame:
    n = len(areas)
    df = pd.DataFrame(0.0, index=range(n), columns=CELL_COLUMNS)
    df["cell_id"] = np.arange(1, n + 1)
    df["area_px"] = areas
    df["sides"] = sides
    df["compactness"] = compactness if compactness is not None else 0.9
    df["flag_small"] = df["flag_large"] = False
    return df


def test_uniform_hexagons():
    # 625 px^2 at 0.8 um/px = 400 um^2 -> 2500 cells/mm^2; all 6-sided, no spread
    b = compute_biomarkers(cells([625.0] * 50, [6.0] * 50, 0.907), 0.8)
    assert np.isclose(b["ecd_cells_per_mm2"], 2500) and np.isclose(b["mean_area_um2"], 400)
    assert b["cv_pct"] == 0 and b["sd_area_um2"] == 0 and b["hex_pct"] == 100
    assert b["side_distribution_pct"]["6"] == 100 and b["side_distribution_pct"]["5"] == 0
    assert np.isclose(b["mean_compactness"], 0.907) and b["cv_compactness_pct"] == 0


def test_known_spread_sides_and_unknown_sides():
    areas = [400.0, 600.0, 800.0, 1000.0]                # mean 700, population SD sqrt(50000)
    b = compute_biomarkers(cells(areas, [5.0, 6.0, 7.0, np.nan]), 1.0)
    assert np.isclose(b["mean_area_um2"], 700) and np.isclose(b["ecd_cells_per_mm2"], 1e6 / 700)
    assert np.isclose(b["sd_area_um2"], np.sqrt(50000), atol=1e-3)
    assert np.isclose(b["cv_pct"], 100 * np.sqrt(50000) / 700, atol=1e-3)
    assert np.isclose(b["hex_pct"], 100 / 3, atol=1e-3) and b["n_cells_with_sides"] == 3
    assert b["side_distribution_pct"]["7"] is not None and b["area_percentiles_um2"]["p50"] == 700


def test_same_definitions_as_phases_3_and_4():
    """Mean area, CV, HEX are exactly the Phase 3 summary, converted with the scale."""
    df, _, _ = extract_cells(instances_from_mask(as_mask(voronoi_labels(hex_points(30.0)))), p=ExtractionParams())
    s, b = summarise_cells(df), compute_biomarkers(df, 0.7945)
    assert np.isclose(b["mean_area_um2"], s["mean_area_px"] * 0.7945 ** 2, rtol=1e-4)
    assert np.isclose(b["cv_pct"], s["cv_area_pct"], atol=1e-3)
    assert np.isclose(b["hex_pct"], s["hex_pct"], atol=1e-3)


def test_report_is_json_and_has_no_nan():
    df = cells([500.0, 700.0], [np.nan, np.nan])                 # no side counts -> HEX unknown
    rep = report("img", df, 0.8, "stardist_finetune_flat")
    text = json.dumps(rep, allow_nan=False)                       # NaN would raise here
    assert json.loads(text)["biomarkers"]["hex_pct"] is None
