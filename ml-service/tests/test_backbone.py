import hashlib
import json
from pathlib import Path

import pytest

from pipelines.image.backbone import verification_error

MODELS = Path(__file__).resolve().parents[1] / "models"
REFERENCE = {"features": [0.5, 1.25, 2.0]}


def write_backbone(tmp_path, content=b"onnx bytes", reference=REFERENCE, record=True):
    onnx = tmp_path / "backbone.onnx"
    onnx.write_bytes(content)
    if record:
        (tmp_path / "backbone.onnx.verified.json").write_text(json.dumps({
            "sha256": hashlib.sha256(content).hexdigest(),
            "reference_sha256": hashlib.sha256(json.dumps(reference["features"]).encode()).hexdigest(),
        }))
    return onnx


def test_verified_backbone_is_accepted(tmp_path):
    assert verification_error(write_backbone(tmp_path), REFERENCE) is None


def test_missing_backbone(tmp_path):
    assert "not found" in verification_error(tmp_path / "backbone.onnx", REFERENCE)


def test_unverified_backbone_is_refused(tmp_path):
    assert "not been verified" in verification_error(write_backbone(tmp_path, record=False), REFERENCE)


def test_backbone_changed_after_verification_is_refused(tmp_path):
    onnx = write_backbone(tmp_path)
    onnx.write_bytes(b"something else")
    assert "changed" in verification_error(onnx, REFERENCE)


def test_backbone_verified_for_another_model_is_refused(tmp_path):
    onnx = write_backbone(tmp_path, reference={"features": [9.0]})
    assert "different model" in verification_error(onnx, REFERENCE)


@pytest.mark.parametrize("meta_file, onnx_file", [
    ("domain_validator/classifier.json", "domain_validator/resnet18_backbone.onnx"),
    ("grading_hybrid_rf.json", "grading_backbone/resnet50_backbone.onnx"),
])
def test_exported_backbones_are_verified_against_their_models(meta_file, onnx_file):
    if not (MODELS / onnx_file).exists():
        pytest.skip("ONNX backbone not exported (see README)")
    reference = json.loads((MODELS / meta_file).read_text(encoding="utf-8"))["backbone"]["reference"]
    assert len(reference["features"]) in (512, 2048)
    assert verification_error(MODELS / onnx_file, reference) is None
