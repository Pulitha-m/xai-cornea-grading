"""Tests for the donor-tissue ranking endpoint. Uses small made-up candidates only."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.recommendation import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _cand(record_id, **over):
    base = {"record_id": record_id, "grade": "A+", "ecd": 2800, "cv": 35, "hex": 55,
            "donor_age": 50, "death_to_preservation_h": 3, "days_in_storage": 3,
            "serology_clear": "Yes"}
    base.update(over)
    return base


def _post(candidates, surgery="PK", requested="A+", **extra):
    body = {"request": {"request_id": "Q0001", "requested_grade": requested, "surgery_type": surgery},
            "candidates": candidates, **extra}
    return client.post("/recommendation/match", json=body)


def test_returns_ranked_list():
    r = _post([_cand("R1"), _cand("R2", grade="B")])
    assert r.status_code == 200
    data = r.json()
    assert [c["rank"] for c in data["ranked"]] == [1, 2]
    assert data["ranked"][0]["record_id"] == "R1"


def test_positive_serology_excluded():
    data = _post([_cand("R1"), _cand("R2", serology_clear="No")]).json()
    assert [c["record_id"] for c in data["ranked"]] == ["R1"]
    assert data["excluded"] == [{"record_id": "R2", "reason": "positive serology"}]


def test_unknown_serology_flagged():
    data = _post([_cand("R1", serology_clear="Unknown")]).json()
    assert "serology not confirmed" in data["ranked"][0]["flags"]


def test_endothelium_ignored_for_dalk():
    good = _cand("R1", ecd=3400, cv=26, hex=68)
    poor = _cand("R2", ecd=2050, cv=49, hex=41)
    data = _post([good, poor], surgery="DALK").json()
    s = {c["record_id"]: c["match_score"] for c in data["ranked"]}
    assert s["R1"] == s["R2"]
    assert data["endothelium_considered"] is False


def test_top_k_limits_results():
    data = _post([_cand(f"R{i}") for i in range(10)], top_k=3).json()
    assert len(data["ranked"]) == 3


def test_reasons_and_disclaimer_present():
    data = _post([_cand("R1")]).json()
    assert data["ranked"][0]["reasons"]
    assert "clinician" in data["disclaimer"]


def test_invalid_grade_rejected():
    assert _post([_cand("R1", grade="Z")]).status_code == 422


def test_empty_candidates_rejected():
    assert _post([]).status_code == 422


def test_accepts_nulls_from_java_client():
    body = {"request": {"request_id": "Q1", "requested_grade": "A", "surgery_type": None, "urgency": None},
            "candidates": [{"record_id": "R1", "grade": "A", "ecd": None, "cv": None, "hex": None,
                            "donor_age": None, "death_to_preservation_h": None,
                            "days_in_storage": None, "serology_clear": None}],
            "top_k": None,
            "weights": {"grade_fit": 0.5, "endothelium": None, "serology": None,
                        "freshness": None, "surgery_compatibility": None}}
    r = client.post("/recommendation/match", json=body)
    assert r.status_code == 200
    assert r.json()["ranked"][0]["flags"] == ["serology not confirmed"]


def test_custom_weights_change_scores():
    a = _post([_cand("R1", days_in_storage=13)]).json()["ranked"][0]["match_score"]
    b = _post([_cand("R1", days_in_storage=13)],
              weights={"freshness": 5.0}).json()["ranked"][0]["match_score"]
    assert a != b


# ---- trained ranker (method="ml", the default) ----

def test_ml_is_default_and_adds_explanations():
    data = _post([_cand("R1"), _cand("R2", grade="B", days_in_storage=10)]).json()
    assert data["method_used"] == "ml"
    top = data["ranked"][0]
    assert top["record_id"] == "R1" and top["ml_score"] is not None
    assert top["why_text"] and {w["reason"] for w in top["why"]} >= {"grade match", "freshness"}
    assert top["mcda_rank"] is not None


def test_ml_counterfactual_only_for_pending_serology():
    better_but_pending = _cand("R2", ecd=3300, cv=26, hex=66, days_in_storage=1, serology_clear="Unknown")
    data = _post([_cand("R1", days_in_storage=4), better_but_pending]).json()
    pending = next(c for c in data["ranked"] if c["record_id"] == "R2")
    assert pending["rank"] == 2 and pending["counterfactual"] == "would be #1 if: serology confirmed clear"
    # A confirmed cornea below #1 gets none: storage, ECD and grade cannot be changed by the clinician.
    data = _post([_cand("R1", days_in_storage=1), _cand("R2", days_in_storage=9)]).json()
    assert [c["counterfactual"] for c in data["ranked"]] == [None, None]


def test_long_stock_list_is_fast():
    import time
    many = [_cand(f"R{i}", ecd=2000 + 7 * i, days_in_storage=i % 14,
                  serology_clear="Unknown" if i % 3 else "Yes") for i in range(200)]
    start = time.perf_counter()
    assert _post(many).status_code == 200
    assert time.perf_counter() - start < 10


def test_ml_excludes_positive_serology():
    data = _post([_cand("R1"), _cand("R2", serology_clear="No")]).json()
    assert [c["record_id"] for c in data["ranked"]] == ["R1"]
    assert data["excluded"][0]["record_id"] == "R2"


def test_mcda_can_be_requested():
    data = _post([_cand("R1"), _cand("R2", grade="B")], method="mcda").json()
    assert data["method_used"] == "mcda"
    assert data["ranked"][0]["ml_score"] is None


def test_falls_back_to_mcda_without_model(monkeypatch):
    import app.routers.recommendation as r
    monkeypatch.setattr(r, "rank_ml", lambda *a, **k: None)
    data = _post([_cand("R1")]).json()
    assert data["method_used"].startswith("mcda")


def test_duplicate_tissue_ids_rejected():
    assert _post([_cand("R1"), _cand("r1 ")]).status_code == 422


def test_impossible_values_rejected():
    for field, value in [("ecd", 90000), ("cv", 500), ("donor_age", 300),
                         ("death_to_preservation_h", 100), ("days_in_storage", 400)]:
        assert _post([_cand("R1", **{field: value})]).status_code == 422, field


def test_all_zero_weights_rejected():
    zero = {k: 0 for k in ("grade_fit", "endothelium", "serology", "freshness", "surgery_compatibility")}
    assert _post([_cand("R1")], weights=zero).status_code == 422
    assert _post([_cand("R1")], weights={**zero, "freshness": 1}).status_code == 200


def test_unusual_values_are_warned_not_rejected():
    r = _post([_cand("R1"), _cand("R2", days_in_storage=20, ecd=1800)])
    assert r.status_code == 200
    w = r.json()["warnings"]
    assert any("R2: stored 20 days" in x for x in w) and any("R2: ECD 1800" in x for x in w)
    assert not any(x.startswith("R1") for x in w)
    # ECD minimum applies only to surgeries that transplant the endothelium
    assert not any("ECD" in x for x in _post([_cand("R1", ecd=1800)], surgery="DALK").json()["warnings"])
