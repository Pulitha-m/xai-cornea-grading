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


@pytest.fixture
def analyze(client):
    def call(ecd=None, image=None, filename="image.png", content_type="image/png", case_id="case-1"):
        data = {"caseId": case_id}
        if ecd is not None:
            data["ecd"] = str(ecd)
        files = {"image": (filename, image if image is not None else image_bytes(), content_type)}
        return client.post("/analyze", data=data, files=files)

    return call


__all__ = ["image_bytes", "NON_CORNEAL", "UNCERTAIN", "VALID"]
