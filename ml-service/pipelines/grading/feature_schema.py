"""Validation of the 24-feature tabular schema used to train the grading models.

The schema (models/grading_feature_schema.json) is exported from the training
code by ml/grading/scripts/export_feature_schema.py. The deployed grade uses
only ECD; this validator is the contract any tabular inference must pass.

Policy:
- All 24 keys must be present; unknown keys are rejected.
- null means "not recorded" and is allowed for every feature, because the
  training pipeline imputes or encodes missing values (see each feature's
  "missing" entry). Zero is never treated as missing.
- Malformed or mathematically impossible values are errors. Values outside
  the training range, or an ECD inconsistent with count/area, are warnings.
"""
import json
import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "models" / "grading_feature_schema.json"


@dataclass
class FeatureIssue:
    code: str
    field: str
    message: str


@dataclass
class FeatureValidation:
    values: list  # in schema order; None where not recorded
    errors: list[FeatureIssue] = field(default_factory=list)
    warnings: list[FeatureIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@lru_cache
def load_schema(path: str | None = None) -> dict:
    schema = json.loads(Path(path or os.environ.get("GRADING_FEATURE_SCHEMA_PATH", DEFAULT_PATH)).read_text(encoding="utf-8"))
    if schema["feature_count"] != len(schema["order"]) or schema["order"] != [f["name"] for f in schema["features"]]:
        raise ValueError("Feature schema is internally inconsistent")
    return schema


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_feature(spec: dict, value, result: FeatureValidation) -> object:
    name = spec["name"]
    if value is None:
        return None

    if spec["type"] == "number":
        if not _is_number(value):
            result.errors.append(FeatureIssue("INVALID_FEATURE_TYPE", name, f"{name} must be a number ({spec['unit']})."))
            return None
        if not math.isfinite(value):
            result.errors.append(FeatureIssue("INVALID_FEATURE_TYPE", name, f"{name} must be a finite number."))
            return None
        valid = spec["valid"]
        if value <= valid["min_exclusive"] or (valid["max_inclusive"] is not None and value > valid["max_inclusive"]):
            upper = "" if valid["max_inclusive"] is None else f" and at most {valid['max_inclusive']}"
            result.errors.append(FeatureIssue("FEATURE_OUT_OF_RANGE", name,
                                              f"{name} must be greater than {valid['min_exclusive']}{upper} {spec['unit']}."))
            return None
        if spec["integer"] and value != int(value):
            result.errors.append(FeatureIssue("INVALID_FEATURE_TYPE", name, f"{name} must be a whole number."))
            return None
        lo, hi = spec["training_range"]["min"], spec["training_range"]["max"]
        if not lo <= value <= hi:
            result.warnings.append(FeatureIssue("FEATURE_OUTSIDE_TRAINING_RANGE", name,
                                                f"{name} = {value:g} is outside the training range {lo:g}–{hi:g} {spec['unit']}."))
        return float(value)

    if spec["type"] == "binary":
        if not _is_number(value) or value not in (0, 1):
            result.errors.append(FeatureIssue("INVALID_FEATURE_TYPE", name, f"{name} must be 0, 1 or null."))
            return None
        return int(value)

    if not isinstance(value, str) or value not in spec["allowed"]:
        result.errors.append(FeatureIssue("FEATURE_OUT_OF_RANGE", name,
                                          f"{name} must be one of {', '.join(spec['allowed'])} or null."))
        return None
    return value


def validate_features(payload: dict) -> FeatureValidation:
    schema = load_schema()
    expected = schema["order"]
    result = FeatureValidation(values=[None] * len(expected))

    if not isinstance(payload, dict):
        result.errors.append(FeatureIssue("FEATURE_SCHEMA_MISMATCH", "clinicalFeatures", "Clinical features must be an object."))
        return result

    missing = [name for name in expected if name not in payload]
    extra = sorted(set(payload) - set(expected))
    for name in missing:
        result.errors.append(FeatureIssue("MISSING_CLINICAL_FEATURES", name, f"{name} is required (use null if not recorded)."))
    for name in extra:
        result.errors.append(FeatureIssue("FEATURE_SCHEMA_MISMATCH", name, f"{name} is not one of the {len(expected)} model features."))

    for i, spec in enumerate(schema["features"]):
        if spec["name"] in payload:
            result.values[i] = _check_feature(spec, payload[spec["name"]], result)

    # Cross-field identity verified on the training data (see the schema).
    index = {name: i for i, name in enumerate(expected)}
    ecd, count, area = (result.values[index[n]] for n in ("ECD_CD_cells_per_mm2", "Total_Cell_Count", "Total_Area_um2"))
    if ecd is not None and count is not None and area is not None:
        if abs(count / area * 1e6 / ecd - 1) >= 0.01:
            result.warnings.append(FeatureIssue("FEATURE_INCONSISTENT", "ECD_CD_cells_per_mm2",
                                                "ECD differs by 1% or more from Total_Cell_Count / Total_Area_um2 × 10^6."))
    return result
