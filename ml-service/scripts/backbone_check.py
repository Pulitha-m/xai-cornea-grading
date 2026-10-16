"""Functional verification of exported ONNX backbones.

The bytes of an ONNX export are not reproducible across machines: the exporter
folds batch-norm into the convolutions on the host CPU, and different CPUs round
those products differently (a GitHub runner produced a different ResNet-18 file
from the one the domain validator was trained with, from the same torch,
torchvision and weights). So a build does not compare file hashes with training.
Instead it checks what the backbone computes:

- At training, `reference()` records the backbone's output on a fixed probe input
  in the model's metadata.
- After every export, `verify_and_record()` requires the new file to reproduce that
  output within tolerance, then writes `<file>.verified.json` with the new file's
  SHA-256 and the reference it was checked against.
- At load, ml-service accepts a backbone only if it matches its verified record
  (pipelines/image/backbone.py), so the file cannot change after verification.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

PROBE_SHAPE = (1, 3, 224, 224)
PROBE_DESCRIPTION = "numpy default_rng(42).standard_normal((1, 3, 224, 224)), float32"
TOLERANCE = {"rtol": 1e-3, "atol": 1e-3}


def probe() -> np.ndarray:
    return np.random.default_rng(42).standard_normal(PROBE_SHAPE).astype(np.float32)


def features(onnx_path: Path) -> np.ndarray:
    import onnxruntime as ort
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    return session.run(None, {"input": probe()})[0][0]


def reference(onnx_path: Path) -> dict:
    """The backbone's output on the probe, recorded in the model metadata at training."""
    return {
        "probe": PROBE_DESCRIPTION,
        "tolerance": TOLERANCE,
        "features": [round(float(v), 6) for v in features(onnx_path)],
    }


def reference_sha256(ref: dict) -> str:
    return hashlib.sha256(json.dumps(ref["features"]).encode()).hexdigest()


def sidecar_path(onnx_path: Path) -> Path:
    return onnx_path.with_name(onnx_path.name + ".verified.json")


def verify_and_record(onnx_path: Path, ref: dict) -> float:
    """Fail unless the backbone reproduces the reference; then record the verified file."""
    expected = np.asarray(ref["features"], dtype=np.float64)
    got = features(onnx_path).astype(np.float64)
    max_diff = float(np.abs(got - expected).max()) if got.shape == expected.shape else float("inf")
    if not np.allclose(got, expected, **ref["tolerance"]):
        sidecar_path(onnx_path).unlink(missing_ok=True)
        print(f"Backbone output differs from the trained model's reference (max abs difference {max_diff:.2e})",
              file=sys.stderr)
        sys.exit(1)
    sidecar_path(onnx_path).write_text(json.dumps({
        "sha256": hashlib.sha256(onnx_path.read_bytes()).hexdigest(),
        "reference_sha256": reference_sha256(ref),
        "max_abs_difference": max_diff,
    }, indent=2) + "\n")
    return max_diff
