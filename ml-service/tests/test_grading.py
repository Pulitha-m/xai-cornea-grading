import json
from pathlib import Path

import pytest

from app.schemas.analysis import ECD_MAX_INCLUSIVE, ECD_MIN_EXCLUSIVE
from pipelines.grading.service import load_spec, run_grading_analysis

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "grading_golden.json").read_text())

# Every test here runs with the domain validator stubbed to VALID, so it tests grading only.
pytestmark = pytest.mark.usefixtures("domain_status")


def test_spec_matches_golden_source():
    assert load_spec()["training"]["data_sha256"] == GOLDEN["data_sha256"]


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: str(c["ecd"]))
def test_api_matches_fitted_tree(analyze, case):
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


def test_missing_ecd_requires_review(analyze):
    grading = analyze().json()["grading"]
    assert grading["status"] == "review_required"
    assert grading["grade"] is None
    assert grading["reviewRequired"] is True


@pytest.mark.parametrize("ecd,code", [
    (0, "FEATURE_OUT_OF_RANGE"), (-100, "FEATURE_OUT_OF_RANGE"), (6000.5, "FEATURE_OUT_OF_RANGE"),
    ("abc", "INVALID_FEATURE_TYPE"), ("nan", "INVALID_FEATURE_TYPE"), ("inf", "INVALID_FEATURE_TYPE"),
])
def test_invalid_ecd_rejected_with_structured_error(analyze, ecd, code):
    response = analyze(ecd=ecd)
    assert response.status_code == 422
    assert response.json() == {"status": "rejected", "error": {"code": code, "field": "ecd", "message": response.json()["error"]["message"]}}


def test_ecd_outside_training_range_flagged():
    spec = load_spec()
    high = spec["training_ecd_range"]["max"] + 100
    assert high <= spec["valid_range"]["max_inclusive"]
    result = run_grading_analysis(high)
    assert result["status"] == "completed"
    assert result["reviewRequired"] is True


def test_no_confidence_field(analyze):
    grading = analyze(ecd=2800).json()["grading"]
    assert "confidence" not in grading


def test_schema_range_matches_spec():
    spec_range = load_spec()["valid_range"]
    assert ECD_MIN_EXCLUSIVE == spec_range["min_exclusive"]
    assert ECD_MAX_INCLUSIVE == spec_range["max_inclusive"]


def test_unavailable_modules_report_not_implemented_without_values(analyze):
    body = analyze(ecd=2800).json()
    assert body["status"] == "partial"
    assert body["cellular"]["status"] == "not_implemented"
    assert body["cellular"]["ecd"] is None and body["cellular"]["hexagonality"] is None
    assert body["disease"]["status"] == "not_implemented" and body["disease"]["confidence"] is None
    assert body["recommendation"]["status"] == "not_implemented" and body["recommendation"]["recommendation"] is None
