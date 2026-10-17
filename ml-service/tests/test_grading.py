import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pipelines.grading import hybrid
from pipelines.grading.feature_schema import load_schema
from pipelines.grading.service import ecd_reference, load_spec
from pipelines.image.embedding import to_embedding_input
from tests.conftest import feature_payload, synthetic_embedding

FIXTURES = Path(__file__).parent / "fixtures"
TREE_GOLDEN = json.loads((FIXTURES / "grading_golden.json").read_text())
HYBRID_GOLDEN = json.loads((FIXTURES / "hybrid_golden.json").read_text())
BACKBONE = Path(hybrid.DEFAULT_DIR) / "grading_backbone" / "resnet50_backbone.onnx"

# Every API test here runs with the domain validator stubbed to VALID, so it tests grading only.
pytestmark = pytest.mark.usefixtures("domain_status")


# ---------------------------------------------------------------- hybrid model (the grade)
def test_hybrid_model_matches_golden_file():
    _, meta = hybrid.load_classifier()
    assert meta["model_sha256"] == HYBRID_GOLDEN["model_sha256"]
    assert meta["features"] == load_schema()["order"]


@pytest.mark.parametrize("case", HYBRID_GOLDEN["cases"], ids=lambda c: f"seed{c['embedding_seed']}")
def test_hybrid_predictions_reproduce_training(case):
    grade, probabilities = hybrid.predict(case["features"], synthetic_embedding(case["embedding_seed"]), load_schema())
    assert grade == case["grade"]
    for cls, expected in case["probabilities"].items():
        assert probabilities[cls] == pytest.approx(expected, abs=1e-3)


def test_api_grade_comes_from_the_hybrid_model(analyze, image_embedding):
    case = HYBRID_GOLDEN["cases"][1]
    image_embedding["seed"] = case["embedding_seed"]
    response = analyze(features=case["features"])
    assert response.status_code == 200, response.json()
    grading = response.json()["grading"]
    assert grading["method"] == "hybrid_random_forest_24_resnet50"
    assert grading["grade"] == case["grade"]
    assert sum(grading["modelProbabilities"].values()) == pytest.approx(1.0, abs=0.01)
    assert "confidence" not in grading


def test_the_image_changes_the_model_input(analyze, image_embedding):
    """The grade depends on the image, not only on the 24 features."""
    grades = set()
    for case in HYBRID_GOLDEN["cases"]:
        image_embedding["seed"] = case["embedding_seed"]
        grades.add(json.dumps(analyze(features=HYBRID_GOLDEN["cases"][0]["features"]).json()["grading"]["modelProbabilities"]))
    assert len(grades) > 1


def test_resized_image_is_a_warning_and_requires_review(analyze, image_embedding):
    image_embedding["resized"] = True
    grading = analyze().json()["grading"]
    assert [w["code"] for w in grading["warnings"]] == ["IMAGE_NOT_TRAINING_SIZE"]
    assert grading["warnings"][0]["field"] == "image"
    assert grading["reviewRequired"] is True


def test_missing_backbone_fails_grading_without_a_grade(analyze, monkeypatch):
    def unavailable(image):
        raise hybrid.HybridModelNotReady("Grading backbone not found")
    monkeypatch.setattr(hybrid, "embed", unavailable)
    body = analyze().json()
    assert body["grading"]["status"] == "failed" and body["grading"]["grade"] is None
    assert body["status"] == "partial"


# ---------------------------------------------------------------- image input to the backbone
def test_training_size_image_is_not_resized():
    image = Image.new("L", (1296, 972), 128)
    tensor, resized = to_embedding_input(image, (1296, 972))
    assert tensor.shape == (1, 3, 972, 1296) and tensor.dtype == np.float32 and not resized
    # 128/255 normalised with the ImageNet red-channel statistics.
    assert tensor[0, 0, 0, 0] == pytest.approx((128 / 255 - 0.485) / 0.229, abs=1e-5)


def test_other_sizes_are_resized_to_training_size():
    tensor, resized = to_embedding_input(Image.new("L", (640, 480), 0), (1296, 972))
    assert tensor.shape == (1, 3, 972, 1296) and resized


@pytest.mark.real_backbone
@pytest.mark.skipif(not BACKBONE.exists(), reason="ONNX backbone not exported (see README)")
def test_real_backbone_produces_a_2048_d_embedding():
    embedding, maps, resized = hybrid.embed(Image.new("L", (1296, 972), 100))
    assert embedding.shape == (2048,) and np.isfinite(embedding).all() and not resized
    assert maps.shape == (2048, 31, 41)
    assert np.abs(maps.mean(axis=(1, 2)) - embedding).max() < 1e-4


def test_api_includes_ecd_reference(analyze):
    grading = analyze(features=feature_payload(ECD_CD_cells_per_mm2=2400.0, Total_Cell_Count=96)).json()["grading"]
    assert grading["ecdReference"]["method"] == "ecd_threshold_tree"
    assert grading["ecdReference"]["grade"] == "A"
    assert grading["ecdReference"]["ecdBand"] == {"lowerExclusive": 2232.0, "upperInclusive": 2497.0}


def test_not_recorded_values_are_listed_and_grade_still_given(analyze):
    payload = feature_payload(Stroma_Has_Scar=None, Epi_Has_Haze=None)
    grading = analyze(features=payload).json()["grading"]
    assert grading["status"] == "completed" and grading["grade"] in ("A+", "A", "B")
    assert set(grading["featuresNotRecorded"]) >= {"Stroma_Has_Scar", "Epi_Has_Haze"}


def test_missing_ecd_gives_no_ecd_reference_and_requires_review(analyze):
    payload = feature_payload(ECD_CD_cells_per_mm2=None, Total_Cell_Count=None, Total_Area_um2=None)
    grading = analyze(features=payload).json()["grading"]
    assert grading["grade"] is not None
    assert grading["ecdReference"]["status"] == "review_required"
    assert grading["reviewRequired"] is True


def test_unusual_values_are_warnings(analyze):
    grading = analyze(features=feature_payload(ECD_CD_cells_per_mm2=4600.0, Total_Cell_Count=184)).json()["grading"]
    assert [w["code"] for w in grading["warnings"]] == ["FEATURE_OUTSIDE_TRAINING_RANGE"]
    assert grading["reviewRequired"] is True


# ---------------------------------------------------------------- request validation
def test_incomplete_feature_set_is_rejected_before_inference(analyze, monkeypatch):
    """Regression: inference cannot run on an incomplete 24-feature request."""
    called = []
    monkeypatch.setattr(hybrid, "predict", lambda *a: called.append(1))
    payload = feature_payload()
    del payload["HEX_percent"]
    response = analyze(features=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == {"code": "MISSING_CLINICAL_FEATURES", "field": "HEX_percent",
                             "message": "HEX_percent is required (use null if not recorded)."}
    assert called == []


def test_all_field_errors_are_reported(analyze):
    response = analyze(features=feature_payload(CV="35", Descemet_Fold_Severity="Severe"))
    fields = {e["field"]: e["code"] for e in response.json()["errors"]}
    assert fields == {"CV": "INVALID_FEATURE_TYPE", "Descemet_Fold_Severity": "FEATURE_OUT_OF_RANGE"}


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '{"ECD_CD_cells_per_mm2": NaN}'])
def test_malformed_feature_payloads_are_rejected(analyze, raw):
    response = analyze(raw_features=raw)
    assert response.status_code == 422
    assert response.json()["status"] == "rejected"


def test_missing_clinical_features_field(client):
    from tests.conftest import image_bytes
    response = client.post("/analyze", data={"caseId": "c"}, files={"image": ("a.png", image_bytes(), "image/png")})
    assert response.json()["error"]["code"] == "MISSING_CLINICAL_FEATURES"


# ---------------------------------------------------------------- ECD reference tree
def test_spec_matches_golden_source():
    assert load_spec()["training"]["data_sha256"] == TREE_GOLDEN["data_sha256"]


@pytest.mark.parametrize("case", TREE_GOLDEN["cases"], ids=lambda c: str(c["ecd"]))
def test_ecd_reference_matches_fitted_tree(case):
    assert ecd_reference(case["ecd"])["grade"] == case["grade"]


def test_band_distribution_reports_training_counts():
    for band in load_spec()["bands"]:
        ecd = band["upper_inclusive"] if band["upper_inclusive"] is not None else band["lower_exclusive"] + 1
        result = ecd_reference(ecd)
        counts = band["training_counts"]
        total = sum(counts.values())
        assert result["bandTrainingTissues"] == total
        assert result["bandDistribution"] == {g: round(n / total, 3) for g, n in counts.items()}


def test_ecd_reference_outside_supported_range_has_no_grade():
    result = ecd_reference(7000.0)
    assert result["status"] == "review_required" and "grade" not in result


def test_unavailable_modules_report_not_implemented_without_values(analyze):
    body = analyze().json()
    assert body["status"] == "partial"
    assert body["cellular"]["status"] == "not_implemented" and body["cellular"]["ecd"] is None
    assert body["disease"]["status"] == "not_implemented" and body["disease"]["confidence"] is None
    assert body["recommendation"]["status"] == "not_implemented"
