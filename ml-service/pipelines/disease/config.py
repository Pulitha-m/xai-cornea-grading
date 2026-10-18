"""Runtime config and model files of the v2 disease + severity models.

Everything comes from models/disease_v2/corneal_config.json, exported by
ml/disease-new/scripts/export_corneal_config.py (number scaling, thresholds, check
limits) and export_onnx_models.py (ONNX files and their SHA-256). The service never
reads the training CSV.

Fails closed: missing files, or model files that do not match the SHA-256 recorded
in the config, raise DiseaseModelNotReady and no prediction is made.
"""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "models" / "disease_v2"


class DiseaseModelNotReady(Exception):
    pass


def model_dir() -> Path:
    return Path(os.environ.get("DISEASE_MODEL_DIR", DEFAULT_DIR))


@lru_cache
def load_config() -> dict:
    path = model_dir() / "corneal_config.json"
    if not path.exists():
        raise DiseaseModelNotReady(f"Disease model config not found ({path.name})")
    config = json.loads(path.read_text(encoding="utf-8"))
    if "models" not in config:
        raise DiseaseModelNotReady("Disease model config has no exported models (run export_onnx_models.py)")
    return config


def checked_file(name: str, expected_sha256: str) -> Path:
    """The file in the model folder, if it exists and has the recorded SHA-256."""
    path = model_dir() / name
    if not path.exists():
        raise DiseaseModelNotReady(f"Disease model file not found ({name})")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise DiseaseModelNotReady(f"Disease model file does not match its config ({name})")
    return path
