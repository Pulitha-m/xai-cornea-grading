"""
End-to-end pipeline wiring on a synthetic image, with the two models replaced by stand-ins
(segmentation = a known hexagonal tessellation, ROI = a known region).

Run (from ml/cellular/):  python -m pytest tests/test_pipeline.py -q
"""

from __future__ import annotations

import json

import numpy as np

from config import load_config
from data_prep.check_annotations import IGNORE
from extraction.cells import ExtractionParams
from pipeline import CellularPipeline, quality_flags
from tests.test_extraction import as_mask, hex_points, voronoi_labels

RULES = {"min_cells": 30, "min_cells_with_sides": 100, "min_roi_share_of_lit": 0.5, "max_flagged_share": 0.05}


class StubRoi:
    method = "stub"

    def __init__(self, roi):
        self.roi = roi

    def __call__(self, planes):
        return self.roi, self.roi.astype(np.float32)


def stub_pipeline(roi: np.ndarray, mask: np.ndarray) -> CellularPipeline:
    p = object.__new__(CellularPipeline)                     # skip model loading
    p.cfg = load_config()
    p.rules, p.run, p.um_per_px = RULES, "stub", 0.8
    p.params = ExtractionParams()
    p.segment = lambda img: mask
    p.roi = StubRoi(roi)
    return p


def synthetic(shape=(480, 640)):
    mask = as_mask(voronoi_labels(hex_points(30.0, shape), shape))
    img = np.where(mask == 1, 60, 180).astype(np.uint8)
    return img, mask


def test_end_to_end_report_overlay_and_roi_restriction(tmp_path):
    img, mask = synthetic()
    full = np.ones(mask.shape, bool)
    half = full.copy()
    half[:, 320:] = False
    r_full = stub_pipeline(full, mask).analyse(img, "full")
    r_half = stub_pipeline(half, mask).analyse(img, "half")
    bf, bh = r_full["report"]["biomarkers"], r_half["report"]["biomarkers"]
    # hexagons of spacing 30 px at 0.8 um/px: area sqrt(3)/2 * 30^2 * 0.64 = 499 um^2 -> ~2004 cells/mm^2
    assert abs(bf["ecd_cells_per_mm2"] / 2004 - 1) < 0.05 and bf["hex_pct"] > 90
    assert bh["n_cells"] < 0.6 * bf["n_cells"]                       # cells outside the ROI are not measured
    assert r_full["cells"]["cx"].max() > 400 and r_half["cells"]["cx"].max() < 320
    assert r_half["report"]["roi"]["share_of_lit_area"] == 0.5
    assert r_full["overlay"].shape == (*mask.shape, 3)
    path = stub_pipeline(full, mask).save(r_full, tmp_path)
    rep = json.loads(path.read_text())
    assert rep["image_id"] == "full" and rep["reliable"] and "quality_flags" in rep
    assert (tmp_path / "full_cells.csv").exists() and (tmp_path / "full_overlay.png").exists()


def test_unlit_area_is_never_measured():
    img, mask = synthetic()
    mask = mask.copy()
    mask[:, :320] = IGNORE                                           # left half unlit
    res = stub_pipeline(np.ones(mask.shape, bool), mask).analyse(img, "x")
    assert res["cells"]["cx"].min() > 320


def test_quality_flags():
    ok = {"n_cells": 1200, "n_cells_with_sides": 500, "n_flagged": 10}
    assert quality_flags(ok, 0.8, RULES) == []
    bad = {"n_cells": 20, "n_cells_with_sides": 5, "n_flagged": 5}
    codes = {f["code"]: f["level"] for f in quality_flags(bad, 0.3, RULES)}
    assert codes == {"too_few_cells": "error", "few_side_counts": "warning",
                     "small_roi": "warning", "many_flagged_cells": "warning"}
