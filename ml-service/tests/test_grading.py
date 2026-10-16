import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import AnalyzeRequest
from pipelines.grading.service import load_spec, run_grading_analysis

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "grading_golden.json").read_text())
client = TestClient(app)


def analyze(**fields):
    return client.post("/analyze", json={"imageUrl": "http://example/img.jpg", "caseId": "case-1", **fields})


def test_spec_matches_golden_source():
    assert load_spec()["training"]["data_sha256"] == GOLDEN["data_sha256"]


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: str(c["ecd"]))
def test_api_matches_fitted_tree(case):
    response = analyze(ecd=case["ecd"])
    assert response.status_code == 200
    grading = response.json()["grading"]
    assert grading["status"] == "completed"
    assert grading["grade"] == case["grade"]


def test_band_distribution_reports_training_counts():
    spec = load_spec()
    for band in spec["bands"]:
        ecd = band["upper_inclusive"] if band["upper_inclusive"] is not None else band["lower_exclusive"] + 1
        result = run_grading_analysis(ecd)
        counts = band["training_counts"]
        total = sum(counts.values())
        assert result["bandTrainingTissues"] == total
        assert result["bandDistribution"] == {g: round(n / total, 3) for g, n in counts.items()}
        assert result["grade"] == band["grade"]


def test_missing_ecd_requires_review():
    grading = analyze().json()["grading"]
    assert grading["status"] == "review_required"
    assert grading["grade"] is None
    assert grading["reviewRequired"] is True


@pytest.mark.parametrize("ecd", [0, -100, 6000.5])
def test_invalid_ecd_rejected(ecd):
    assert analyze(ecd=ecd).status_code == 422


def test_ecd_outside_training_range_flagged():
    spec = load_spec()
    high = spec["training_ecd_range"]["max"] + 100
    assert high <= spec["valid_range"]["max_inclusive"]
    result = run_grading_analysis(high)
    assert result["status"] == "completed"
    assert result["reviewRequired"] is True


def test_no_confidence_field():
    grading = analyze(ecd=2800).json()["grading"]
    assert "confidence" not in grading


def test_schema_range_matches_spec():
    spec_range = load_spec()["valid_range"]
    constraints = {type(m).__name__: m for m in AnalyzeRequest.model_fields["ecd"].metadata}
    assert constraints["Gt"].gt == spec_range["min_exclusive"]
    assert constraints["Le"].le == spec_range["max_inclusive"]


def test_cellular_not_implemented():
    cellular = analyze(ecd=2800).json()["cellular"]
    assert cellular["status"] == "not_implemented"
    assert cellular["ecd"] is None and cellular["hexagonality"] is None
