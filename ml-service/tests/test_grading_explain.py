"""SHAP explanation of the hybrid grade and the SHAP-weighted image map (pipelines/grading/explain.py).

Uses the committed model with the synthetic embedding and feature maps from conftest.
"""
import base64
import io
import json

import numpy as np
import pytest
from PIL import Image

import pipelines.image.domain as domain
from pipelines.grading import explain, hybrid
from pipelines.grading.feature_schema import load_schema
from pipelines.image.domain import VALID, DomainResult
from tests.conftest import feature_payload, image_bytes, synthetic_embedding, synthetic_maps


@pytest.fixture
def grade(client, monkeypatch):
    monkeypatch.setattr(domain, "validate_domain", lambda image: DomainResult(VALID, None, None, None))

    def call(features=None):
        data = {"caseId": "case-1", "clinicalFeatures": json.dumps(features or feature_payload())}
        response = client.post("/grading/analyze", data=data, files={"image": ("i.png", image_bytes(), "image/png")})
        assert response.status_code == 200, response.json()
        return response.json()

    return call


def model_scores(embedding):
    pipeline, meta = hybrid.load_classifier()
    row = pipeline.named_steps["features"].transform(hybrid.to_frame(feature_payload(), embedding, meta, load_schema()))
    return row[0, -32:]


def test_contributions_add_up_to_the_share_of_votes(grade):
    body = grade()
    e = body["explanation"]
    assert e["method"] == "tree_shap_path_dependent" and e["explainedGrade"] == body["grade"]
    total = e["baseline"] + sum(f["contribution"] for f in e["features"]) + e["imageContribution"]
    assert total == pytest.approx(e["prediction"], abs=2e-3)
    assert e["prediction"] == pytest.approx(body["modelProbabilities"][body["grade"]], abs=2e-3)


def test_every_input_appears_once_largest_first(grade):
    features = grade(feature_payload(Stroma_Has_Scar=None))["explanation"]["features"]
    assert sorted(f["name"] for f in features) == sorted(load_schema()["order"])
    sizes = [abs(f["contribution"]) for f in features]
    assert sizes == sorted(sizes, reverse=True)
    scar = next(f for f in features if f["name"] == "Stroma_Has_Scar")
    assert scar["value"] is None


def test_one_hot_columns_are_summed_into_their_input():
    _, owners = explain.load_explainer()
    assert (owners == "image").sum() == 32
    assert (owners == "Stroma_Has_Scar").sum() > 1  # one-hot: 0, 1 and missing
    assert (owners == "ECD_CD_cells_per_mm2").sum() == 1


def test_location_scores_average_to_the_models_pca_scores():
    embedding = synthetic_embedding(1000)
    local = explain.location_scores(synthetic_maps(embedding))
    # Equal up to float32 rounding: the model's PCA runs in float32.
    np.testing.assert_allclose(local.mean(axis=(0, 1)), model_scores(embedding), rtol=1e-6, atol=1e-3)


def test_map_sums_to_the_mapped_components_shap_values():
    embedding = synthetic_embedding(1000)
    maps = synthetic_maps(embedding)
    scores = explain.location_scores(maps).mean(axis=(0, 1))
    phi = np.random.default_rng(5).normal(0, 0.01, 32)
    attribution, share = explain.attribution_map(maps, phi)
    pca = hybrid.load_classifier()[0].named_steps["features"].named_transformers_["image"].named_steps["pca"]
    mapped = np.abs(scores) >= explain.MIN_SCORE_SD * np.sqrt(pca.explained_variance_)
    assert attribution.sum() == pytest.approx(phi[mapped].sum(), abs=1e-9)
    assert share == pytest.approx(np.abs(phi[mapped]).sum() / np.abs(phi).sum())


def test_image_maps_are_pngs_at_display_size(grade):
    image_map = grade()["explanation"]["imageMap"]
    assert image_map["method"] == "shap_weighted_layer4_map" and 0 <= image_map["localisedShare"] <= 1
    assert image_map["supportingTotal"] >= 0 >= image_map["opposingTotal"]
    pngs = [image_map[k] for k in ("supportingPng", "opposingPng") if image_map[k]]
    assert pngs
    for png in pngs:
        assert Image.open(io.BytesIO(base64.b64decode(png))).size == explain.DISPLAY_SIZE


def test_backbone_without_maps_still_gives_shap(grade, image_embedding):
    image_embedding["maps"] = False
    e = grade()["explanation"]
    assert e["imageMap"] is None and len(e["features"]) == 24


def test_explanation_failure_keeps_the_grade(grade, monkeypatch):
    def broken(*args):
        raise RuntimeError("shap failed")
    monkeypatch.setattr(explain, "explain", broken)
    body = grade()
    assert body["grade"] in ("A+", "A", "B") and body["explanation"] is None


def test_combined_analyze_has_no_explanation(analyze, domain_status):
    assert "explanation" not in analyze().json()["grading"]
