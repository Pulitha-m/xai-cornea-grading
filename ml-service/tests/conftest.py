import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main
from app.main import app
from pipelines.image.domain import NON_CORNEAL, UNCERTAIN, VALID, DomainResult


def image_bytes(fmt="PNG", size=(640, 480), mode="L", seed=0) -> bytes:
    """Synthetic noise image. Not a corneal image; tests that need one stub the validator."""
    rng = np.random.default_rng(seed)
    channels = 3 if mode == "RGB" else 1
    pixels = rng.integers(0, 256, size=(size[1], size[0], channels), dtype=np.uint8).squeeze()
    buffer = io.BytesIO()
    Image.fromarray(pixels, mode=mode).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def domain_status(monkeypatch):
    """Stub the domain validator; tests set the status it returns (default VALID)."""
    state = {"status": VALID}

    def fake_validate(image):
        return DomainResult(state["status"], None, None, None)

    monkeypatch.setattr(main, "validate_domain", fake_validate)
    return state


def synthetic_embedding(seed: int) -> np.ndarray:
    """Same generator as ml/grading/scripts/train_hybrid_grading_model.py (golden cases)."""
    return np.random.default_rng(seed).exponential(0.45, 2048).astype(np.float32)


def synthetic_maps(embedding: np.ndarray, size=(6, 8), seed: int = 0) -> np.ndarray:
    """Layer4-like maps (2048 × h × w) whose spatial mean is exactly `embedding`, as for the real backbone."""
    noise = np.random.default_rng(seed).normal(0, 0.3, (embedding.size, *size))
    return (embedding[:, None, None] + noise - noise.mean(axis=(1, 2), keepdims=True)).astype(np.float64)


@pytest.fixture(autouse=True)
def image_embedding(request, monkeypatch):
    """Stub the ResNet-50 backbone (a 94 MB file not in git) with a synthetic embedding.

    Tests marked `real_backbone` use the exported ONNX backbone instead. Tests may set
    the seed, whether the image counts as resized and whether feature maps are returned.
    """
    state = {"seed": 1000, "resized": False, "maps": True}

    def fake_embed(image):
        embedding = synthetic_embedding(state["seed"])
        return embedding, synthetic_maps(embedding) if state["maps"] else None, state["resized"]

    if "real_backbone" not in request.keywords:
        from pipelines.grading import hybrid
        monkeypatch.setattr(hybrid, "embed", fake_embed)
    return state


def feature_payload(**overrides):
    """A complete, valid 24-feature payload (Konan values consistent: 104 / 40000 µm² ≈ 2600 cells/mm²)."""
    from pipelines.grading.feature_schema import load_schema
    payload = {}
    for spec in load_schema()["features"]:
        payload[spec["name"]] = {"number": None, "binary": 0, "category": None}[spec["type"]]
    payload.update({"ECD_CD_cells_per_mm2": 2600.0, "CV": 35.0, "HEX_percent": 55.0, "SD": 130.0,
                    "Total_Cell_Count": 104, "Total_Area_um2": 40000.0})
    payload.update(overrides)
    return payload


@pytest.fixture
def analyze(client):
    def call(features=None, image=None, filename="image.png", content_type="image/png", case_id="case-1", raw_features=None):
        import json
        data = {"caseId": case_id,
                "clinicalFeatures": raw_features if raw_features is not None else json.dumps(features if features is not None else feature_payload())}
        files = {"image": (filename, image if image is not None else image_bytes(), content_type)}
        return client.post("/analyze", data=data, files=files)

    return call


__all__ = ["image_bytes", "NON_CORNEAL", "UNCERTAIN", "VALID"]
