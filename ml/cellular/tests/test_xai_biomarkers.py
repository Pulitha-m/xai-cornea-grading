"""
XAI step 2 — reliability, evidence and uncertainty of the biomarkers, on synthetic data with known answers.

Run (from ml/cellular/):  python -m pytest tests/test_xai_biomarkers.py -q
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from biomarkers.compute import compute_biomarkers
from segmentation.infer_full import instance_prob_image
from xai.biomarker_explain import label_cells
from xai.reliability import (area_overlay, bootstrap_ci, cell_confidence, reliability, reliability_overlay,
                             variance_share)

RULES = {"min_compactness": 0.70, "sides_range": [4, 8], "error_area_pct": 20}


def test_instance_prob_image_maps_through_centre_points():
    labels = np.zeros((10, 10), np.int32)
    labels[1:4, 1:4] = 2                                   # StarDist numbering is NOT assumed
    labels[6:9, 6:9] = 1
    p = instance_prob_image(labels, np.array([0.9, 0.6]), np.array([[2, 2], [7, 7]]))
    assert np.isclose(p[2, 2], 0.9) and np.isclose(p[7, 7], 0.6) and p[0, 0] == 0
    p = instance_prob_image(labels, np.array([0.9]), np.array([[2, 2]]))
    assert np.isnan(p[7, 7])                               # an instance without its point -> unknown


def test_cell_confidence_is_the_median_over_instance_pixels():
    cells = np.zeros((6, 6), np.int32)
    cells[:, :3], cells[:, 3:] = 1, 2
    prob = np.zeros((6, 6), np.float32)
    prob[:, :2] = 0.8                                      # cell 1: two columns 0.8, one background column
    prob[:, 3:] = np.nan                                   # cell 2: unknown instance
    c = cell_confidence(cells, prob, [1, 2, 3])
    assert np.isclose(c[1], 0.8) and np.isnan(c[2]) and np.isnan(c[3])


def cells_table():
    return pd.DataFrame({"cell_id": [1, 2, 3, 4, 5, 6],
                         "flag_small": [False, True, False, False, False, False],
                         "flag_large": [False] * 6,
                         "sides": [6, 6, 3, np.nan, 6, 6],
                         "compactness": [0.88, 0.88, 0.88, 0.88, 0.60, 0.88],
                         "area_px": [400.0] * 6})


def test_reliability_levels():
    conf = pd.Series([0.95, 0.95, 0.95, 0.95, 0.95, 0.70], index=pd.Index([1, 2, 3, 4, 5, 6], name="cell_id"))
    rel = reliability(cells_table(), conf, prob_thresh=0.5, rules=RULES)   # yellow below (0.5 + 1) / 2 = 0.75
    assert rel["level"].tolist() == ["green", "red", "red", "green", "red", "yellow"]
    assert rel["implausible_size"].tolist() == [False, True, False, False, False, False]
    assert rel["implausible_shape"].tolist() == [False, False, True, False, True, False]
    rel = reliability(cells_table(), conf.drop(1), 0.5, RULES)
    assert rel.loc[1, "level"] == "yellow"                 # unknown confidence


def grid(n=40, gradient=False, seed=0):
    """Cells on a grid; areas random, or growing from left to right (spatially correlated)."""
    rng = np.random.default_rng(seed)
    cy, cx = np.meshgrid(np.arange(n) * 25.0 + 12, np.arange(n) * 25.0 + 12, indexing="ij")
    base = 300 + 300 * cx / cx.max() if gradient else np.full(cx.shape, 450.0)
    area = base * rng.lognormal(0, 0.15, cx.shape)
    sides = rng.choice([5, 6, 6, 7, np.nan], cx.size)
    return pd.DataFrame({"cell_id": np.arange(1, cx.size + 1), "cx": cx.ravel(), "cy": cy.ravel(),
                         "area_px": area.ravel(), "sides": sides, "compactness": 0.88,
                         "flag_small": False, "flag_large": False})


def test_bootstrap_value_matches_the_biomarkers_and_ci_contains_it():
    cells = grid()
    bm = compute_biomarkers(cells, 0.8)
    ci = bootstrap_ci(cells, 0.8, 64, 500, 1)
    for b, key in (("ecd", "ecd_cells_per_mm2"), ("cv", "cv_pct"), ("hex", "hex_pct")):
        assert np.isclose(ci[b]["value"], bm[key], rtol=1e-3)
        assert ci[b]["lo"] <= ci[b]["value"] <= ci[b]["hi"]
    assert ci == bootstrap_ci(cells, 0.8, 64, 500, 1)      # reproducible


def test_block_bootstrap_is_wider_when_neighbours_are_correlated():
    cells = grid(gradient=True)
    w = lambda ci: ci["ecd"]["hi"] - ci["ecd"]["lo"]
    assert w(bootstrap_ci(cells, 0.8, 200, 1000, 2)) > w(bootstrap_ci(cells, 0.8, 0, 1000, 2))


def test_variance_share_finds_the_extreme_cell():
    cells = grid(n=10)
    cells.loc[17, "area_px"] = 5000
    top, share = variance_share(cells, 0.05)
    assert len(top) == 5 and cells.loc[17, "cell_id"] in top and share > 0.8


def test_label_cells_wrong_rule():
    pred = pd.DataFrame({"cell_id": [1, 2, 3], "area_px": [100.0, 130.0, 100.0], "sides": [6, 5, 6]})
    ref = pd.DataFrame({"cell_id": [7, 8], "area_px": [100.0, 100.0], "sides": [6, 6]})
    m = pd.DataFrame({"pred_id": [1, 2], "gt_id": [7, 8], "iou": [0.9, 0.7]})
    lab = label_cells(pred, m, ref, RULES).set_index("cell_id")
    assert lab["wrong"].tolist() == [False, True, True]    # ok / area +30 % / unmatched
    assert lab.loc[1, "side_error"] == 0 and lab.loc[2, "side_error"] == 1 and np.isnan(lab.loc[3, "side_error"])


def test_overlays_colour_the_cells():
    img = np.full((20, 20), 100, np.uint8)
    complete = np.zeros((20, 20), np.int32)
    complete[2:9, 2:9], complete[11:18, 11:18] = 1, 2
    rel = pd.DataFrame({"level": ["red", "green"]}, index=pd.Index([1, 2], name="cell_id"))
    v = reliability_overlay(img, complete, rel).astype(int)
    assert v[5, 5, 0] > v[5, 5, 1] and v[14, 14, 1] > v[14, 14, 0] and (v[0, 0] == 100).all()
    cells = pd.DataFrame({"cell_id": [1, 2], "area_px": [100.0, 400.0]})
    a = area_overlay(img, complete, cells, [2]).astype(int)
    assert a[5, 5, 2] > a[5, 5, 0] and a[14, 14, 0] > a[14, 14, 2]     # small = blue, large = red
    assert tuple(a[11, 14]) == (255, 230, 0)                            # extreme cell outlined
