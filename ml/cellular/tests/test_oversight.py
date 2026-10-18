"""
XAI step 4 — expert oversight on a synthetic pipeline result (stub models): edits, recompute, log, evaluation.

Run (from ml/cellular/):  python -m pytest tests/test_oversight.py -q
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from biomarkers.compute import compute_biomarkers
from config import load_config
from oversight import holm, policy_errors, review, review_queue, validate
from tests.test_pipeline import stub_pipeline, synthetic


@pytest.fixture()
def saved(tmp_path):
    """A pipeline result saved like the real pipeline (low confidence on the left -> yellow cells)."""
    img, mask = synthetic()
    full = np.ones(mask.shape, bool)
    prob = np.where(mask == 0, 0.95, 0).astype(np.float32)
    prob[:, :100][mask[:, :100] == 0] = 0.6
    p = stub_pipeline(full, mask)
    p.segment, p.prob_thresh = (lambda im: (mask, prob)), 0.5
    res = p.analyse(img, "x")
    p.save(res, tmp_path)
    cfg = load_config()
    cfg["pipeline"] = p.rules
    return tmp_path, res, cfg


def edits_file(d, edits, reviewer="dr test"):
    f = d / f"edits_{len(list(d.glob('edits_*')))}.json"
    f.write_text(json.dumps({"reviewer": reviewer, "edits": edits}))
    return f


def test_pipeline_saves_what_a_review_needs(saved):
    d, res, _ = saved
    for f in ("x_mask.png", "x_roi.png", "x_review_queue.png", "x_review_queue.csv"):
        assert (d / f).exists()
    q = pd.read_csv(d / "x_review_queue.csv")
    assert len(q) == res["report"]["reliability"]["yellow"] + res["report"]["reliability"]["red"]


def test_no_edits_reproduce_the_pipeline_exactly(saved):
    d, res, cfg = saved
    rep = review(d / "x.json", edits_file(d, []), cfg=cfg)
    assert rep["biomarkers"] == res["report"]["biomarkers"]
    assert rep["uncertainty"] == res["report"]["uncertainty"]
    assert rep["oversight"]["before"] == rep["oversight"]["after"]
    assert json.loads((d / "x.json").read_text()) == json.loads(json.dumps(res["report"]))   # original untouched


def test_excluding_cells_recomputes_from_the_rest(saved):
    d, res, cfg = saved
    drop = res["cells"]["cell_id"].iloc[:5].tolist()
    rep = review(d / "x.json", edits_file(d, [{"action": "exclude_cells", "cell_ids": drop}]), cfg=cfg)
    kept = pd.read_csv(d / "x_reviewed_cells.csv")
    assert rep["biomarkers"]["n_cells"] == res["report"]["biomarkers"]["n_cells"] - 5
    assert not kept["cell_id"].isin(drop).any()
    expected = compute_biomarkers(res["cells"][~res["cells"]["cell_id"].isin(drop)], res["report"]["um_per_px"])
    assert rep["biomarkers"]["ecd_cells_per_mm2"] == expected["ecd_cells_per_mm2"]
    rep2 = review(d / "x.json", edits_file(d, [{"action": "exclude_cells", "cell_ids": drop},
                                               {"action": "include_cells", "cell_ids": drop}]), cfg=cfg)
    assert rep2["biomarkers"] == res["report"]["biomarkers"]                                  # undone


def test_area_edits_change_the_roi_and_drop_cut_cells(saved):
    d, res, cfg = saved
    right = [[320, 0], [640, 0], [640, 480], [320, 480]]
    rep = review(d / "x.json", edits_file(d, [{"action": "remove_area", "polygon": right}]), cfg=cfg)
    kept = pd.read_csv(d / "x_reviewed_cells.csv")
    assert kept["cx"].max() < 320 and rep["biomarkers"]["n_cells"] < 0.6 * res["report"]["biomarkers"]["n_cells"]
    assert rep["oversight"]["area_removed_px"] > 0 and rep["roi"]["edited_by_expert"]
    assert rep["roi"]["share_of_lit_area"] < 0.6
    back = review(d / "x.json", edits_file(d, [{"action": "remove_area", "polygon": right},
                                               {"action": "add_area", "polygon": right}]), cfg=cfg)
    assert back["biomarkers"] == res["report"]["biomarkers"]                                  # same ids, same cells


def test_log_is_append_only(saved):
    d, _, cfg = saved
    review(d / "x.json", edits_file(d, []), cfg=cfg)
    first = (d / "x_edits.jsonl").read_text().splitlines()
    review(d / "x.json", edits_file(d, [{"action": "exclude_cells", "cell_ids": [1]}], "dr two"), cfg=cfg)
    lines = (d / "x_edits.jsonl").read_text().splitlines()
    assert len(lines) == 2 and lines[0] == first[0] and json.loads(lines[1])["reviewer"] == "dr two"


def test_bad_edits_are_rejected():
    with pytest.raises(ValueError):
        validate([{"action": "delete_everything"}])
    with pytest.raises(ValueError):
        validate([{"action": "remove_area", "polygon": [[0, 0], [1, 1]]}])
    with pytest.raises(ValueError):
        validate([{"action": "exclude_cells"}])


def test_review_queue_order():
    cells = pd.DataFrame({"cell_id": [1, 2, 3, 4, 5], "level": ["green", "yellow", "red", "yellow", "red"],
                          "confidence": [0.9, 0.7, 0.8, 0.6, np.nan]})
    assert review_queue(cells)["cell_id"].tolist() == [5, 3, 4, 2]          # red first, least confident first


def test_simulated_reviewer_and_holm():
    rng = np.random.default_rng(0)
    rows = []
    for c in range(6):
        area = rng.normal(500, 60, 50)
        level = np.array(["green"] * 45 + ["red"] * 5)
        area[45:] = 100                                                     # red = too-small fragments
        rows.append(pd.DataFrame({"crop_id": f"c{c}", "cell_id": range(50), "area_px": area,
                                  "sides": 6.0, "level": level, "wrong": level == "red"}))
    cells = pd.concat(rows)
    um = 0.8
    truth = 1e6 / (500 * um ** 2)
    refs = pd.DataFrame([{"crop_id": f"c{c}", "biomarker": b, "reference": v}
                         for c in range(6) for b, v in (("ecd", truth), ("cv", 12.0), ("hex", 100.0))])
    t = policy_errors(cells, refs, {"none": lambda c: np.zeros(len(c), bool),
                                    "red": lambda c: (c["level"] == "red").to_numpy()}, um)
    none, red = t[t["policy"] == "none"], t[t["policy"] == "red"]
    assert (red["excluded"] == 5).all() and (none["excluded"] == 0).all()
    assert red["ecd_err"].abs().median() < none["ecd_err"].abs().median()    # removing fragments helps ECD
    adj = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert np.isclose(adj["a"], 0.03) and np.isclose(adj["c"], 0.06) and np.isclose(adj["b"], 0.06)
