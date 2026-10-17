"""The hybrid grading model: 24 clinical features + ResNet-50 image embedding (Random Forest).

Trained and exported by ml/grading/scripts/train_hybrid_grading_model.py. The
pipeline includes the training-time preprocessing (median imputation and scaling
for Konan measurements; missing-as-category one-hot encoding for slit-lamp
findings; standardisation and PCA for the image embedding), so features are passed
exactly as recorded, with None for "not recorded".

Fails closed: if the model does not match its recorded SHA-256, or the ONNX
backbone is missing or not verified against this model (pipelines/image/backbone.py),
grading raises HybridModelNotReady and no grade is given.
"""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from pipelines.image.backbone import verification_error
from pipelines.image.embedding import to_embedding_input

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "models"


class HybridModelNotReady(Exception):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _directory() -> Path:
    return Path(os.environ.get("GRADING_MODEL_DIR", DEFAULT_DIR))


@lru_cache
def load_classifier():
    """The fitted scikit-learn pipeline and its metadata, checked against the recorded SHA-256."""
    meta_path = _directory() / "grading_hybrid_rf.json"
    model_path = _directory() / "grading_hybrid_rf.joblib"
    if not meta_path.exists() or not model_path.exists():
        raise HybridModelNotReady("Hybrid grading model files not found")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if _sha256(model_path) != meta["model_sha256"]:
        raise HybridModelNotReady("Hybrid grading model does not match its metadata")

    import joblib  # imported lazily: only needed once the model is used

    return joblib.load(model_path), meta


@lru_cache
def load_backbone():
    """ONNX session for the ResNet-50 backbone the model was trained with."""
    _, meta = load_classifier()
    backbone = _directory() / meta["backbone"]["file"]
    problem = verification_error(backbone, meta["backbone"]["reference"])
    if problem:
        raise HybridModelNotReady(f"Grading backbone: {problem}")

    import onnxruntime as ort

    return ort.InferenceSession(str(backbone), providers=["CPUExecutionProvider"])


def embed(image: Image.Image) -> tuple[np.ndarray, np.ndarray | None, bool]:
    """2048-d embedding of the image, its layer4 feature maps (2048 × h × w; None from a backbone exported
    without them) and whether the image had to be resized to the training size."""
    _, meta = load_classifier()
    width, height = meta["backbone"]["training_image_size"]
    tensor, resized = to_embedding_input(image, (width, height))
    outputs = load_backbone().run(None, {"input": tensor})
    return outputs[0][0], (outputs[1][0] if len(outputs) > 1 else None), resized


def to_frame(values: dict, embedding: np.ndarray, meta: dict, schema: dict) -> pd.DataFrame:
    """One-row frame with the training dtypes: float for numbers and binaries, str for categories."""
    types = {f["name"]: f["type"] for f in schema["features"]}
    frame = pd.DataFrame([values], columns=meta["features"])
    for name in meta["features"]:
        if types[name] == "category":
            frame[name] = frame[name].astype("str").where(frame[name].notna(), np.nan).astype("str")
        else:
            frame[name] = pd.to_numeric(frame[name], errors="raise").astype("float64")
    image = pd.DataFrame(np.asarray(embedding, dtype=np.float32).reshape(1, -1),
                         columns=[f"emb_{i}" for i in range(meta["embedding_columns"])])
    return pd.concat([frame, image], axis=1)


def predict(values: dict, embedding: np.ndarray, schema: dict) -> tuple[str, dict[str, float]]:
    pipeline, meta = load_classifier()
    probabilities = pipeline.predict_proba(to_frame(values, embedding, meta, schema))[0]
    classes = pipeline.classes_
    grade = str(classes[int(np.argmax(probabilities))])
    return grade, {str(c): round(float(p), 3) for c, p in zip(classes, probabilities)}
