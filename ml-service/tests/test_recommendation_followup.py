"""Tests for POST /recommendation/followup. Uses made-up graft values only."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.recommendation import router
from pipelines.recommendation import followup as F

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _body(**over):
    body = {"graft_id": "G0001", "procedure": "PK", "indication": "Fuchs/Endothelial", "donor_age": 60,
            "baseline_ecd": 2700, "baseline_cv": 36, "baseline_hex": 56,
            "visit_3m": {"ecd": 2450, "cv": 37, "hex": 55}, "visit_6m": {"ecd": 2300, "cv": 38, "hex": 54},
            "visit_12m": {"ecd": 2100, "cv": 39, "hex": 53}, "rejection_by_12m": False}
    body.update(over)
    return body


def _post(**over):
    return client.post("/recommendation/followup", json=_body(**over))


def test_healthy_graft_gets_a_full_answer():
    r = _post()
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["graft_id"] == "G0001" and d["alert"] in ("green", "amber", "red")
    assert d["next_visit_months"] in (3, 6, 12)
    assert [p["months"] for p in d["predicted_ecd"]] == [24, 36, 60]
    assert all(p["low"] <= p["ecd"] <= p["high"] for p in d["predicted_ecd"])
    assert {(x["outcome"], x["within_months"]) for x in d["risk"]} == {
        ("graft_failure", 12), ("graft_failure", 24), ("low_ecd", 12), ("low_ecd", 24)}
    assert all(0 <= x["probability"] <= 1 for x in d["risk"])
    assert "clinician" in d["disclaimer"] and d["data_source"]


def test_rapid_cell_loss_is_red_with_regraft_prompt_and_counterfactual():
    d = _post(visit_6m={"ecd": 1300, "cv": 45, "hex": 45}, visit_12m={"ecd": 700, "cv": 48, "hex": 42}).json()
    assert d["alert"] == "red" and d["next_visit_months"] == 3
    assert any("regraft" in a for a in d["actions"])
    assert d["reasons"]["graft_failure"] and d["counterfactuals"]
    assert all("[descriptive]" in c for c in d["counterfactuals"])


def test_rejection_is_always_red():
    d = _post(rejection_by_12m=True).json()
    assert d["alert"] == "red" and "Review for graft rejection" in d["actions"]


def test_lower_12_month_ecd_never_lowers_risk():
    good = {(x["outcome"], x["within_months"]): x["probability"] for x in _post().json()["risk"]}
    worse = {(x["outcome"], x["within_months"]): x["probability"]
             for x in _post(visit_12m={"ecd": 1500, "cv": 42, "hex": 50}).json()["risk"]}
    assert all(worse[k] >= good[k] for k in good)


def test_missing_3_month_visit_is_accepted():
    assert _post(visit_3m=None).status_code == 200


def test_ecd_already_below_1000_counts_as_low():
    d = _post(visit_6m={"ecd": 1100, "cv": 44, "hex": 46}, visit_12m={"ecd": 950, "cv": 46, "hex": 44}).json()
    low = [x for x in d["risk"] if x["outcome"] == "low_ecd"]
    assert all(x["probability"] == 1.0 for x in low) and d["reasons"]["low_ecd"] == []


def test_invalid_input_is_rejected():
    assert _post(procedure="XYZ").status_code == 422
    assert _post(visit_12m=None).status_code == 422
    assert _post(visit_12m={"ecd": -5, "cv": 40, "hex": 50}).status_code == 422


def test_missing_model_returns_model_not_ready(monkeypatch):
    monkeypatch.setattr(F, "load_model", lambda *a, **k: None)
    r = _post()
    assert r.status_code == 503 and r.json()["error"]["code"] == "MODEL_NOT_READY"
