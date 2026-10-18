"""POST /grading/analyze: grading on its own page (the model itself is tested in test_grading.py).

The ResNet-50 backbone is stubbed (conftest.image_embedding) and so is the domain validator.
"""
import json
from pathlib import Path

import pytest

import pipelines.image.domain as domain
from pipelines.grading import hybrid
from pipelines.image.domain import NON_CORNEAL, UNCERTAIN, VALID, DomainResult
from tests.conftest import feature_payload, image_bytes

HYBRID_GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "hybrid_golden.json").read_text())


@pytest.fixture
def grading_domain(monkeypatch):
    state = {"status": VALID}
    monkeypatch.setattr(domain, "validate_domain", lambda image: DomainResult(state["status"], None, None, None))
    return state


@pytest.fixture
def analyze_grading(client, grading_domain):
    def call(features=None, raw=None, image=None):
        data = {"caseId": "case-1",
                "clinicalFeatures": raw if raw is not None else json.dumps(features if features is not None else feature_payload())}
        files = {"image": ("image.png", image if image is not None else image_bytes(), "image/png")}
        return client.post("/grading/analyze", data=data, files=files)

    return call


def test_grade_comes_from_the_hybrid_model(analyze_grading, image_embedding):
    case = HYBRID_GOLDEN["cases"][1]
    image_embedding["seed"] = case["embedding_seed"]
    response = analyze_grading(features=case["features"])
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "completed" and body["caseId"] == "case-1"
    assert body["method"] == "hybrid_random_forest_24_resnet50"
    assert body["grade"] == case["grade"]
    assert sum(body["modelProbabilities"].values()) == pytest.approx(1.0, abs=0.01)
    assert body["imageValidation"]["domainStatus"] == VALID
    assert body["ecdReference"]["method"] == "ecd_threshold_tree"


def test_features_used_echo_the_validated_inputs(analyze_grading):
    body = analyze_grading(features=feature_payload(Stroma_Has_Scar=None)).json()
    assert len(body["featuresUsed"]) == 24
    assert body["featuresUsed"]["ECD_CD_cells_per_mm2"] == 2600.0
    assert body["featuresUsed"]["Stroma_Has_Scar"] is None
    assert "Stroma_Has_Scar" in body["featuresNotRecorded"]


def test_feature_errors_reject_before_the_image(analyze_grading, grading_domain, monkeypatch):
    called = []
    monkeypatch.setattr(domain, "validate_domain", lambda image: called.append(1))
    response = analyze_grading(features=feature_payload(CV="35", Descemet_Fold_Severity="Severe"))
    assert response.status_code == 422
    assert {e["field"] for e in response.json()["errors"]} == {"CV", "Descemet_Fold_Severity"}
    assert called == []


@pytest.mark.parametrize("status, code", [(NON_CORNEAL, "INVALID_IMAGE_DOMAIN"), (UNCERTAIN, "CORNEAL_IMAGE_UNCERTAIN")])
def test_non_corneal_images_are_rejected(analyze_grading, grading_domain, status, code):
    grading_domain["status"] = status
    response = analyze_grading()
    assert response.status_code == 422
    assert response.json()["error"] == {"code": code, "field": "image", "message": response.json()["error"]["message"]}


def test_missing_model_is_model_not_ready_without_a_grade(analyze_grading, monkeypatch):
    def unavailable(image):
        raise hybrid.HybridModelNotReady("Grading backbone not found")
    monkeypatch.setattr(hybrid, "embed", unavailable)
    response = analyze_grading()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_NOT_READY"
    assert "grade" not in response.json()


def test_missing_clinical_features_field(client, grading_domain):
    response = client.post("/grading/analyze", data={"caseId": "c"}, files={"image": ("a.png", image_bytes(), "image/png")})
    assert response.json()["error"]["code"] == "MISSING_CLINICAL_FEATURES"


def test_combined_analyze_still_grades(analyze, domain_status):
    """/analyze keeps grading in its combined report after the parser moved to the grading router."""
    assert analyze().json()["grading"]["status"] == "completed"
