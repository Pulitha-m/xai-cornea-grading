"""Load-time check that an ONNX backbone is the one verified against its model.

The export step (scripts/backbone_check.py) checks that a freshly exported
backbone reproduces the trained model's reference output and then writes
`<file>.verified.json`. Here the file must still have the verified SHA-256, and
the record must refer to the same reference as the model's metadata.
"""
import hashlib
import json
from pathlib import Path


def verification_error(onnx_path: Path, reference: dict) -> str | None:
    """None if the backbone may be used, otherwise the reason it may not."""
    if not onnx_path.exists():
        return f"Backbone not found ({onnx_path.name})"
    record_path = onnx_path.with_name(onnx_path.name + ".verified.json")
    if not record_path.exists():
        return f"Backbone has not been verified against its model ({record_path.name} missing)"
    record = json.loads(record_path.read_text())
    if record.get("reference_sha256") != hashlib.sha256(json.dumps(reference["features"]).encode()).hexdigest():
        return "Backbone was verified against a different model"
    if record.get("sha256") != hashlib.sha256(onnx_path.read_bytes()).hexdigest():
        return "Backbone has changed since it was verified"
    return None
