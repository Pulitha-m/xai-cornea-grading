import io
import json
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image

import pipelines.image.domain as domain
from pipelines.image.decode import ImageRejected, decode_image
from pipelines.image.domain import NON_CORNEAL, UNCERTAIN, ModelNotReady
from tests.conftest import image_bytes

VALIDATOR_DIR = Path(__file__).resolve().parents[1] / "models" / "domain_validator"
HAS_VALIDATOR = (VALIDATOR_DIR / "classifier.json").exists() and (
    VALIDATOR_DIR / json.loads((VALIDATOR_DIR / "classifier.json").read_text())["backbone"]["file"]
).exists() if (VALIDATOR_DIR / "classifier.json").exists() else False


def code_of(data: bytes) -> str:
    with pytest.raises(ImageRejected) as exc:
        decode_image(data)
    return exc.value.code


# ---------------------------------------------------------------- decoding
def test_valid_png_and_jpeg_decode_to_greyscale():
    for fmt in ("PNG", "JPEG"):
        decoded = decode_image(image_bytes(fmt=fmt, mode="RGB"))
        assert decoded.format == fmt and decoded.image.mode == "L"


def test_empty_upload_rejected():
    assert code_of(b"") == "IMAGE_DECODE_FAILED"


def test_non_image_bytes_rejected():
    assert code_of(b"%PDF-1.7 not an image") == "IMAGE_DECODE_FAILED"


def test_truncated_image_rejected():
    data = image_bytes(fmt="JPEG")
    assert code_of(data[: len(data) // 2]) == "IMAGE_DECODE_FAILED"


def test_unsupported_format_rejected():
    buffer = io.BytesIO()
    Image.new("L", (400, 300)).save(buffer, format="BMP")
    assert code_of(buffer.getvalue()) == "UNSUPPORTED_IMAGE_FORMAT"


def test_misleading_extension_does_not_matter_signature_does(analyze, domain_status):
    # A BMP named .png is judged by its content, not its name.
    buffer = io.BytesIO()
    Image.new("L", (400, 300)).save(buffer, format="BMP")
    response = analyze(image=buffer.getvalue(), filename="photo.png", content_type="image/png")
    assert response.json()["error"]["code"] == "UNSUPPORTED_IMAGE_FORMAT"


@pytest.mark.parametrize("size", [(100, 400), (9000, 300)])
def test_extreme_dimensions_rejected(size):
    assert code_of(image_bytes(size=size)) == "IMAGE_DIMENSIONS_INVALID"


def test_oversized_file_rejected(monkeypatch):
    import pipelines.image.decode as decode
    monkeypatch.setattr(decode, "MAX_BYTES", 1000)
    assert code_of(image_bytes()) == "IMAGE_TOO_LARGE"


def test_decompression_bomb_rejected_before_pixels_are_decoded():
    # A tiny PNG whose header claims 50,000 x 50,000 pixels.
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    header = struct.pack(">IIBBBBB", 50_000, 50_000, 8, 0, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00")) + chunk(b"IEND", b"")
    assert code_of(png) == "IMAGE_DIMENSIONS_INVALID"


# ---------------------------------------------------------------- domain gate in the API
def test_non_corneal_image_cannot_produce_a_grade(analyze, domain_status):
    """Regression: a rejected image never reaches grading, even with a valid ECD."""
    domain_status["status"] = NON_CORNEAL
    response = analyze()
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "rejected"
    assert body["error"] == {"code": "INVALID_IMAGE_DOMAIN", "field": "image",
                             "message": "Upload a specular microscopy image showing corneal endothelial cells."}
    assert "grading" not in body


def test_uncertain_image_is_rejected_for_review(analyze, domain_status):
    domain_status["status"] = UNCERTAIN
    response = analyze()
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CORNEAL_IMAGE_UNCERTAIN"


def test_missing_validator_fails_closed(analyze, monkeypatch):
    def unavailable(image):
        raise ModelNotReady("artifacts missing")
    monkeypatch.setattr("app.main.validate_domain", unavailable)
    response = analyze()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_NOT_READY"
    assert "artifacts" not in response.text  # internal detail not exposed


def test_validator_with_missing_artifacts_raises(tmp_path):
    with pytest.raises(ModelNotReady):
        domain.DomainValidator(tmp_path)


def test_validator_rejects_tampered_backbone(tmp_path):
    if not HAS_VALIDATOR:
        pytest.skip("domain validator artifacts not present")
    spec = json.loads((VALIDATOR_DIR / "classifier.json").read_text())
    (tmp_path / "classifier.json").write_text(json.dumps(spec))
    (tmp_path / spec["backbone"]["file"]).write_bytes(b"not the trained backbone")
    with pytest.raises(ModelNotReady):
        domain.DomainValidator(tmp_path)


def test_dev_bypass_is_labelled_and_never_valid(analyze, monkeypatch):
    monkeypatch.setenv("DOMAIN_VALIDATOR_DEV_BYPASS", "true")
    body = analyze().json()
    assert body["imageValidation"]["domainStatus"] == "UNVALIDATED_DEV_MODE"
    assert body["imageValidation"]["qualityAssessed"] is False


def test_missing_image_field_returns_structured_error(client):
    import json
    from tests.conftest import feature_payload
    response = client.post("/analyze", data={"caseId": "case-1", "clinicalFeatures": json.dumps(feature_payload())})
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "image"


# ---------------------------------------------------------------- real validator (skipped without artifacts)
@pytest.mark.skipif(not HAS_VALIDATOR, reason="domain validator artifacts not present")
def test_real_validator_rejects_synthetic_non_corneal_content(analyze):
    """Noise, a flat grey image and a text-like document must not pass as corneal images."""
    from PIL import ImageDraw
    document = Image.new("L", (1240, 1754), 255)
    draw = ImageDraw.Draw(document)
    for y in range(80, 1700, 36):
        draw.text((60, y), "Patient report summary table value total status " * 3, fill=0)
    buffer = io.BytesIO()
    document.save(buffer, format="PNG")

    flat = io.BytesIO()
    Image.new("L", (800, 600), 128).save(flat, format="PNG")

    for data in (buffer.getvalue(), flat.getvalue(), image_bytes(seed=3)):
        response = analyze(image=data)
        assert response.status_code == 422, response.json()
        assert response.json()["error"]["code"] in ("INVALID_IMAGE_DOMAIN", "CORNEAL_IMAGE_UNCERTAIN")
