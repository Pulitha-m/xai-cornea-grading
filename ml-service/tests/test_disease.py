"""POST /disease/analyze and the v2 disease input checks (notebook 10, Step 12).

Uses the committed ONNX models in models/disease_v2/; the domain validator is stubbed.
Parity with the evaluated notebook models is checked in test_disease_parity.py.
"""
import io
import json

import numpy as np
import pytest
from PIL import Image

import pipelines.image.domain as domain
from pipelines.disease import checks, config as disease_config, model
from pipelines.image.domain import NON_CORNEAL, VALID, DomainResult
from tests.conftest import image_bytes

HAS_MODELS = (disease_config.DEFAULT_DIR / "corneal_config.json").exists()
pytestmark = pytest.mark.skipif(not HAS_MODELS, reason="disease models not available")

GOOD = {"ECD_CD_cells_per_mm2": 2650.0, "SD": 143.0, "CV": 38.0, "HEX_percent": 55.0, "Donor_Age": 65.0}


@pytest.fixture
def disease_domain(monkeypatch):
    state = {"status": VALID}
    monkeypatch.setattr(domain, "validate_domain", lambda image: DomainResult(state["status"], None, None, None))
    return state


def specular_like(size=(1296, 972), mode="L") -> bytes:
    """Smoothed noise in the brightness range of specular images (not a real cornea)."""
    rng = np.random.default_rng(3)
    small = rng.integers(60, 200, size=(size[1] // 8, size[0] // 8), dtype=np.uint8)
    image = Image.fromarray(small, mode="L").resize(size, Image.Resampling.BICUBIC)
    if mode == "RGB":
        image = Image.merge("RGB", (image, image.point(lambda v: v // 2), image))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def analyze_disease(client, disease_domain):
    def call(values=None, image=None, force=False, raw=None):
        data = {"caseId": "case-1", "measurements": raw if raw is not None else json.dumps(values or GOOD),
                "force": str(force).lower()}
        files = {"image": ("image.png", image if image is not None else specular_like(), "image/png")}
        return client.post("/disease/analyze", data=data, files=files)

    return call


# ------------------------------------------------------------ number checks
@pytest.mark.parametrize("values, rejected", [
    ((0, 0, 0, 0, 0), True),
    ((2650, 143, 38, 55, 65), False),
    ((2650, 120, 38, 55, 65), True),     # SD does not match ECD and CV
    ((None, None, None, 55, 65), True),  # too many missing
    ((-5, 143, 38, 55, 65), True),
])
def test_notebook_number_self_test(values, rejected):
    errors, _ = checks.validate_numbers(dict(zip(checks.MEASUREMENTS, values)))
    assert bool(errors) == rejected


def test_missing_value_is_a_warning_and_uses_the_training_median():
    values = dict(GOOD, Donor_Age=None)
    errors, warnings = checks.validate_numbers(values)
    assert not errors and [w.code for w in warnings] == ["VALUE_MISSING"]
    config = disease_config.load_config()
    expected = (config["imputer_median"][5] - config["scaler_mean"][5]) / config["scaler_scale"][5]
    assert model.scale_numbers(values)[0, 5] == pytest.approx(expected, abs=1e-5)


def test_ecd_deficit_is_derived_and_missing_with_ecd():
    assert model.feature_row(GOOD)["ECD_Deficit"] == 0
    assert model.feature_row(dict(GOOD, ECD_CD_cells_per_mm2=2000.0))["ECD_Deficit"] == 500
    assert model.feature_row(dict(GOOD, ECD_CD_cells_per_mm2=None))["ECD_Deficit"] is None


# ------------------------------------------------------------ endpoint
def test_measurements_must_name_all_five(analyze_disease):
    response = analyze_disease(raw=json.dumps({"ECD_CD_cells_per_mm2": 2650}))
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "FEATURE_SCHEMA_MISMATCH"
    assert {e["field"] for e in body["errors"]} == {"SD", "CV", "HEX_percent", "Donor_Age"}


def test_text_value_is_a_type_error(analyze_disease):
    response = analyze_disease(raw=json.dumps(dict(GOOD, CV="38%")))
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_FEATURE_TYPE"


def test_non_corneal_image_is_rejected_before_the_model(analyze_disease, disease_domain):
    disease_domain["status"] = NON_CORNEAL
    response = analyze_disease()
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_IMAGE_DOMAIN"


def test_failed_checks_reject_with_every_error_and_warning(analyze_disease):
    response = analyze_disease(values=dict(GOOD, ECD_CD_cells_per_mm2=0.0, Donor_Age=None))
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INPUT_CHECK_FAILED"
    assert "VALUE_NOT_POSSIBLE" in [e["code"] for e in body["inputCheck"]["errors"]]
    assert "VALUE_MISSING" in [w["code"] for w in body["inputCheck"]["warnings"]]
    assert body["imageQuality"]["rating"] in {"OK", "Low", "Unusable"}


def test_colour_image_is_rejected(analyze_disease):
    response = analyze_disease(image=specular_like(mode="RGB"))
    assert "IMAGE_IS_COLOUR" in [e["code"] for e in response.json()["inputCheck"]["errors"]]


def test_low_resolution_image_is_rejected(analyze_disease):
    response = analyze_disease(image=specular_like(size=(400, 280)))
    assert "IMAGE_RESOLUTION_TOO_LOW" in [e["code"] for e in response.json()["inputCheck"]["errors"]]


def test_force_produces_a_result_marked_not_reliable(analyze_disease):
    response = analyze_disease(values=dict(GOOD, ECD_CD_cells_per_mm2=0.0), force=True)
    assert response.status_code == 200
    body = response.json()
    assert body["inputCheck"] == body["inputCheck"] | {"passed": False, "forced": True}
    assert body["reliable"] is False and "NOT reliable" in body["message"]
    assert [d["code"] for d in body["diseases"]] == ["FECD", "Guttata", "Folds", "PolyPleo", "LowCD"]


def test_result_structure(analyze_disease):
    body = analyze_disease(force=True).json()
    for finding in body["diseases"]:
        assert 0 <= finding["probability"] <= 1
        assert finding["detected"] == (finding["probability"] >= finding["threshold"])
        assert (finding["gradcamPng"] is not None) == finding["detected"]
        assert (finding["gradcamFocus"] is not None) == finding["detected"]
    assert body["detected"] == [d["code"] for d in body["diseases"] if d["detected"]]
    assert body["overallSeverity"] in {"None", "Mild", "Mod/Sev"}
    assert body["normal"] == (not body["detected"])
    for group in body["severity"]:
        assert group["grade"] in {"Mild", "Mod/Sev"}
    assert body["measurementsUsed"]["ECD_Deficit"] == 0


@pytest.mark.parametrize("y, x, region", [
    (0, 0, "upper left"), (0, 6, "upper"), (4, 11, "right"), (4, 6, "centre"), (8, 0, "lower left"), (8, 11, "lower right"),
])
def test_gradcam_focus_names_the_hottest_region(y, x, region):
    cam = np.zeros((9, 12), dtype=np.float32)
    cam[y, x] = 1.0
    focus = model.gradcam_focus(cam)
    assert focus["region"] == region
    assert 0 < focus["coverage"] < 0.1   # one hot cell of 108


def test_gradcam_focus_coverage_of_a_diffuse_map():
    cam = np.ones((9, 12), dtype=np.float32)
    cam[0, 0] = 0.0   # high everywhere except one corner
    assert model.gradcam_focus(cam)["coverage"] > 0.9


def test_gradcam_is_a_png_of_the_model_input_size():
    import base64
    gray = np.full((972, 1296), 120, dtype=np.uint8)
    png = base64.b64decode(model.overlay_png(gray, np.random.default_rng(0).random((9, 12)).astype(np.float32)))
    with Image.open(io.BytesIO(png)) as image:
        assert image.format == "PNG" and image.size == (384, 288)


def test_model_file_that_does_not_match_its_config_fails_closed(tmp_path, monkeypatch):
    config = disease_config.load_config()
    (tmp_path / "corneal_config.json").write_text(json.dumps(config))
    for name in (config["models"]["disease"]["file"], config["models"]["severity"]["file"], config["ood"]["file"]):
        (tmp_path / name).write_bytes(b"not the model")
    monkeypatch.setenv("DISEASE_MODEL_DIR", str(tmp_path))
    disease_config.load_config.cache_clear()
    model.load_models.cache_clear()
    try:
        with pytest.raises(disease_config.DiseaseModelNotReady):
            model.load_models()
    finally:
        monkeypatch.delenv("DISEASE_MODEL_DIR")
        disease_config.load_config.cache_clear()
        model.load_models.cache_clear()


def test_combined_analyze_does_not_run_the_disease_module(analyze, domain_status):
    assert analyze().json()["disease"]["status"] == "not_implemented"
