"""Corneal-image domain validation.

Answers one question: is this image a specular microscopy image of the
corneal endothelium, like those the system was built for? It does not
assess image quality, cell visibility or disease (those are reported as
not assessed). Trained and evaluated by
ml/grading/scripts/train_domain_validator.py; see
models/domain_validator/evaluation.json for its measured error rates.

Fails closed: if the classifier artifacts are missing or do not match, every
image is refused with MODEL_NOT_READY, unless the development-only bypass
DOMAIN_VALIDATOR_DEV_BYPASS=true is set, in which case images are marked
UNVALIDATED_DEV_MODE and never as valid.
"""
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from pipelines.image.backbone import verification_error
from pipelines.image.preprocess import to_model_input

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "models" / "domain_validator"

VALID = "VALID_CORNEAL_IMAGE"
UNCERTAIN = "CORNEAL_IMAGE_UNCERTAIN"
NON_CORNEAL = "NON_CORNEAL_IMAGE"
DEV_MODE = "UNVALIDATED_DEV_MODE"


class ModelNotReady(Exception):
    pass


@dataclass
class DomainResult:
    status: str
    score: float | None  # classifier probability of "corneal"; not a calibrated clinical confidence
    accept_threshold: float | None
    reject_threshold: float | None

    @property
    def passed(self) -> bool:
        return self.status in (VALID, DEV_MODE)


def dev_bypass_enabled() -> bool:
    return os.environ.get("DOMAIN_VALIDATOR_DEV_BYPASS", "").lower() == "true"


class DomainValidator:
    def __init__(self, directory: Path):
        spec_path = directory / "classifier.json"
        if not spec_path.exists():
            raise ModelNotReady(f"Domain validator spec not found ({spec_path.name})")
        spec = json.loads(spec_path.read_text())

        backbone = directory / spec["backbone"]["file"]
        problem = verification_error(backbone, spec["backbone"]["reference"])
        if problem:
            raise ModelNotReady(f"Domain validator: {problem}")

        import onnxruntime as ort  # imported lazily so the service starts without it in dev-bypass mode

        self.session = ort.InferenceSession(str(backbone), providers=["CPUExecutionProvider"])
        self.mean = np.asarray(spec["scaler_mean"], dtype=np.float64)
        self.scale = np.asarray(spec["scaler_scale"], dtype=np.float64)
        self.coef = np.asarray(spec["coef"], dtype=np.float64)
        self.intercept = float(spec["intercept"])
        self.reject_threshold = float(spec["thresholds"]["reject_below"])
        self.accept_threshold = float(spec["thresholds"]["accept_at_or_above"])

    def score(self, image: Image.Image) -> float:
        features = self.session.run(None, {"input": to_model_input(image)[np.newaxis]})[0][0]
        logit = float(((features - self.mean) / self.scale) @ self.coef + self.intercept)
        return float(1.0 / (1.0 + np.exp(-logit)))

    def validate(self, image: Image.Image) -> DomainResult:
        score = self.score(image)
        if score >= self.accept_threshold:
            status = VALID
        elif score >= self.reject_threshold:
            status = UNCERTAIN
        else:
            status = NON_CORNEAL
        return DomainResult(status, score, self.accept_threshold, self.reject_threshold)


@lru_cache
def get_validator() -> DomainValidator:
    """Loaded once per process; raises ModelNotReady if artifacts are unavailable."""
    return DomainValidator(Path(os.environ.get("DOMAIN_VALIDATOR_DIR", DEFAULT_DIR)))


def validate_domain(image: Image.Image) -> DomainResult:
    if dev_bypass_enabled():
        return DomainResult(DEV_MODE, None, None, None)
    return get_validator().validate(image)
