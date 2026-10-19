"""Runtime config and model files of the cellular analysis (Component 3).

Everything comes from models/cellular/cellular_config.json, written by ml/cellular/export_web.py together with
the two ONNX networks: the settings of the validated pipeline (copied from ml/cellular/config.yaml), the
SHA-256 of both model files, and the parity of the exported pipeline with the validated one.

Fails closed: missing files, or model files that do not match the SHA-256 recorded in the config, raise
CellularModelNotReady and no analysis is made.
"""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "models" / "cellular"


class CellularModelNotReady(Exception):
    pass


def model_dir() -> Path:
    return Path(os.environ.get("CELLULAR_MODEL_DIR", DEFAULT_DIR))


@lru_cache
def load_config() -> dict:
    path = model_dir() / "cellular_config.json"
    if not path.exists():
        raise CellularModelNotReady(f"Cellular model config not found ({path.name})")
    config = json.loads(path.read_text(encoding="utf-8"))
    for key in ("models", "image", "classical", "roi", "extraction", "scale", "pipeline", "xai"):
        if key not in config:
            raise CellularModelNotReady(f"Cellular model config has no '{key}' section (re-run export_web.py)")
    return config


def checked_file(name: str, expected_sha256: str) -> Path:
    """The file in the model folder, if it exists and has the recorded SHA-256."""
    path = model_dir() / name
    if not path.exists():
        raise CellularModelNotReady(f"Cellular model file not found ({name})")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise CellularModelNotReady(f"Cellular model file does not match its config ({name})")
    return path
