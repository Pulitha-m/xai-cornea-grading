"""Cellular analysis: endpoint handling, response shape, fail-closed model loading, and the real ONNX networks on a
synthetic cell lattice. Parity with the validated pipeline: tests/test_cellular_parity.py."""
import io

import numpy as np
import pandas as pd
import pytest
from PIL import Image
from scipy.spatial import cKDTree

import pipelines.cellular.config as cellular_config
import pipelines.cellular.model as cellular_model
from pipelines.cellular import service
from pipelines.image import domain
from tests.conftest import image_bytes

MODELS = cellular_config.DEFAULT_DIR
HAVE_MODELS = (MODELS / "cellular_config.json").exists()


def lattice(h=972, w=1296, spacing=28.2, seed=0) -> np.ndarray:
    """Bright cells, dark 2 px walls on a jittered hexagonal lattice (no real tissue texture)."""
    ys, xs = np.mgrid[0:h, 0:w]
    rows = np.arange(0, h, spacing * 0.866)
    pts = np.array([(y, x + (spacing / 2 if k % 2 else 0)) for k, y in enumerate(rows) for x in np.arange(0, w, spacing)])
    pts += np.random.default_rng(seed).normal(0, 1.5, pts.shape)
    d, _ = cKDTree(pts).query(np.stack([ys.ravel(), xs.ravel()], 1), k=2)
    wall = (d[:, 1] - d[:, 0]).reshape(h, w) < 2.0
    noise = np.random.default_rng(seed + 1).normal(0, 8, (h, w))
    return np.clip(np.where(wall, 70, 190) + noise, 0, 255).astype(np.uint8)


def png_bytes(gray: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(gray, mode="L").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def cellular_domain(monkeypatch):
    """Stub the domain validator used by the cellular router (default VALID)."""
    state = {"status": domain.VALID}
    monkeypatch.setattr(domain, "validate_domain", lambda image: domain.DomainResult(state["status"], None, None, None))
    return state


def fake_outcome(n_cells=120) -> service.CellularOutcome:
    rgb = np.zeros((972, 1296, 3), np.uint8)
    rep = {
        "image_id": "c1", "um_per_px": 0.796, "validated_image_size": True,
        "biomarkers": {"n_cells": n_cells, "ecd_cells_per_mm2": 2800.5, "mean_area_um2": 357.1, "sd_area_um2": 100.0,
                       "cv_pct": 28.0, "hex_pct": 61.2, "n_cells_with_sides": 80, "mean_compactness": 0.88,
                       "sd_compactness": 0.04, "cv_compactness_pct": 4.5,
                       "area_percentiles_um2": {"p5": 200.0, "p25": 300.0, "p50": 350.0, "p75": 400.0, "p95": 520.0},
                       "side_distribution_pct": {"<=4": 1.0, "5": 20.0, "6": 61.2, "7": 16.0, ">=8": 1.8},
                       "n_flagged": 2},
        "roi": {"method": "cnn", "share_of_image": 0.7, "share_of_lit_area": 0.8, "quality_score": 0.75},
        "quality_flags": [{"level": "warning", "code": "few_side_counts", "message": "HEX from only 80 cells"}],
        "reliable": True,
        "uncertainty": {"method": "95 % CI", "ecd_ci95": [2750.0, 2850.0], "cv_ci95": [26.0, 30.0],
                        "hex_ci95": [57.0, 65.0]},
        "evidence": {"most_extreme_cells_pct": 5.0, "their_share_of_area_variance_pct": 33.0},
        "reliability": {"rule": "r", "green": 100, "yellow": 15, "red": 5, "median_confidence": 0.9},
        "seconds": 3.2}
    return service.CellularOutcome(report=rep, cells=pd.DataFrame(),
                                   images={"overlay": rgb, "cv_evidence": rgb, "reliability": rgb})


def post(client, data: bytes, case="case-1"):
    return client.post("/cellular/analyze", data={"caseId": case}, files={"image": ("img.png", data, "image/png")})


def test_success_maps_the_report_to_the_response(client, cellular_domain, monkeypatch):
    monkeypatch.setattr(service, "analyse", lambda gray, case: fake_outcome())
    r = post(client, image_bytes())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed" and body["caseId"] == "case-1" and body["method"] == service.METHOD
    b = body["biomarkers"]
    assert (b["cellCount"], b["ecd"], b["coefficientOfVariation"], b["hexagonality"]) == (120, 2800.5, 28.0, 61.2)
    assert b["sideDistributionPct"]["6"] == 61.2 and b["flaggedCells"] == 2
    assert body["uncertainty"]["ecdCi95"] == [2750.0, 2850.0] and body["reliability"]["yellow"] == 15
    assert body["qualityFlags"][0]["code"] == "few_side_counts" and body["reliable"] is True
    for key in ("overlayJpeg", "reliabilityJpeg", "cvEvidenceJpeg"):
        assert body["images"][key][:4] == "/9j/"                           # base64 JPEG signature
    assert "not a clinical measurement" in body["message"]


def test_non_corneal_and_uncertain_images_are_rejected_before_the_pipeline(client, cellular_domain, monkeypatch):
    def fail(*a):
        raise AssertionError("the pipeline must not run")
    monkeypatch.setattr(service, "analyse", fail)
    cellular_domain["status"] = domain.NON_CORNEAL
    r = post(client, image_bytes())
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_IMAGE_DOMAIN"
    cellular_domain["status"] = domain.UNCERTAIN
    assert post(client, image_bytes()).json()["error"]["code"] == "CORNEAL_IMAGE_UNCERTAIN"


def test_unreadable_upload_is_rejected(client, cellular_domain):
    r = post(client, b"not an image")
    assert r.status_code == 422 and r.json()["error"]["code"] == "IMAGE_DECODE_FAILED"


def test_model_not_ready_and_pipeline_failure(client, cellular_domain, monkeypatch):
    def not_ready(*a):
        raise cellular_config.CellularModelNotReady("missing")
    monkeypatch.setattr(service, "analyse", not_ready)
    r = post(client, image_bytes())
    assert r.status_code == 503 and r.json()["error"]["code"] == "MODEL_NOT_READY"

    def broken(*a):
        raise RuntimeError("boom")
    monkeypatch.setattr(service, "analyse", broken)
    r = post(client, image_bytes())
    assert r.status_code == 500 and r.json()["error"]["code"] == "MODEL_INFERENCE_FAILED"


def test_missing_or_changed_model_files_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("CELLULAR_MODEL_DIR", str(tmp_path))
    cellular_config.load_config.cache_clear()
    cellular_model.load_models.cache_clear()
    try:
        with pytest.raises(cellular_config.CellularModelNotReady):
            cellular_config.load_config()
        if HAVE_MODELS:
            for f in MODELS.iterdir():
                (tmp_path / f.name).write_bytes(f.read_bytes())
            cellular_config.load_config.cache_clear()
            (tmp_path / "stardist.onnx").write_bytes(b"tampered")
            with pytest.raises(cellular_config.CellularModelNotReady, match="does not match"):
                cellular_model.load_models()
    finally:
        cellular_config.load_config.cache_clear()
        cellular_model.load_models.cache_clear()


def test_combined_analyze_does_not_run_cellular():
    with pytest.raises(NotImplementedError, match="own page"):
        service.run_cellular_analysis(None)


@pytest.mark.skipif(not HAVE_MODELS, reason="cellular models not present")
def test_real_networks_on_a_synthetic_lattice(client, cellular_domain):
    """StarDist (ONNX + TensorFlow-free post-processing) finds the lattice cells; the ROI CNN does not accept the
    artificial texture, so no region is analysable: 0 cells, flagged not reliable, but no failure."""
    img = lattice()
    from pipelines.cellular import steps
    from pipelines.cellular.config import load_config
    cfg = load_config()
    flat, lit = steps.flatten_illumination(img, steps.ClassicalParams.from_config(cfg))
    labels, _ = cellular_model.load_models().stardist.predict_instances(steps.normalise_lit(flat, lit, 1, 99.8))
    expected = img.size / (np.sqrt(3) / 2 * 28.2 ** 2)
    assert abs(labels.max() / expected - 1) < 0.05

    r = post(client, png_bytes(img))
    assert r.status_code == 200
    body = r.json()
    assert body["reliable"] is False and "too_few_cells" in [f["code"] for f in body["qualityFlags"]]
    assert body["biomarkers"]["cellCount"] == 0 and body["images"]["cvEvidenceJpeg"]
