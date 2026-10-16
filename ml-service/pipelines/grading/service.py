"""Donor cornea grading: the hybrid model's grade plus the ECD tree as a reference.

The grade comes from the hybrid Random Forest on the 24 features and the image
(pipelines/grading/hybrid.py).
The ECD reference uses the exported threshold-tree spec
(models/grading_ecd_tree.json, from ml/grading/scripts/train_grading_model.py):
the cut points of a depth-2 decision tree on ECD and the recorded grades of its
training tissues in each ECD band. Both are decision support only; a specialist
confirms every grade.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_SPEC_PATH = Path(__file__).resolve().parents[2] / "models" / "grading_ecd_tree.json"
METHOD = "ecd_threshold_tree"


@lru_cache
def load_spec(path: str | None = None) -> dict:
    spec_path = Path(path or os.environ.get("GRADING_SPEC_PATH", DEFAULT_SPEC_PATH))
    spec = json.loads(spec_path.read_text())

    bands = spec["bands"]
    if bands[0]["lower_exclusive"] is not None or bands[-1]["upper_inclusive"] is not None:
        raise ValueError("Grading spec bands must be unbounded at both ends")
    for lower, upper in zip(bands, bands[1:]):
        if lower["upper_inclusive"] != upper["lower_exclusive"]:
            raise ValueError("Grading spec bands must be contiguous")
    return spec


def find_band(spec: dict, ecd: float) -> dict:
    return next(
        band for band in spec["bands"]
        if (band["lower_exclusive"] is None or ecd > band["lower_exclusive"])
        and (band["upper_inclusive"] is None or ecd <= band["upper_inclusive"])
    )


def ecd_reference(ecd: float | None) -> dict:
    """Grade from the ECD threshold tree alone (shown as a reference next to the 24-feature grade)."""
    spec = load_spec()

    if ecd is None:
        return {
            "status": "review_required",
            "method": METHOD,
            "reviewRequired": True,
            "message": "ECD is required for automated grading. Grade this tissue manually.",
        }

    valid = spec["valid_range"]
    if not valid["min_exclusive"] < ecd <= valid["max_inclusive"]:
        return {
            "status": "review_required",
            "method": METHOD,
            "ecdUsed": ecd,
            "reviewRequired": True,
            "message": f"ECD {ecd:g} is outside the range the ECD rule supports; no reference grade.",
        }

    band = find_band(spec, ecd)
    counts = band["training_counts"]
    total = sum(counts.values())
    training = spec["training_ecd_range"]
    outside_training = not training["min"] <= ecd <= training["max"]

    message = (
        f"Grade based on ECD only (cut points {', '.join(f'{c:g}' for c in spec['cut_points'])} "
        "cells/mm²). Slit-lamp findings and other morphology are not considered and may "
        "justify a lower grade. Specialist confirmation required."
    )
    if outside_training:
        message += (
            f" ECD is outside the training range ({training['min']:g}–{training['max']:g}); "
            "review carefully."
        )

    return {
        "status": "completed",
        "grade": band["grade"],
        "method": METHOD,
        "ecdUsed": ecd,
        "ecdBand": {
            "lowerExclusive": band["lower_exclusive"],
            "upperInclusive": band["upper_inclusive"],
        },
        "bandDistribution": {grade: round(n / total, 3) for grade, n in counts.items()},
        "bandTrainingTissues": total,
        "reviewRequired": outside_training,
        "message": message,
    }


HYBRID_METHOD = "hybrid_random_forest_24_resnet50"


def run_grading_analysis(values: dict, warnings: list[dict], image) -> dict:
    """Grade from the hybrid model (24 features + image), with the ECD tree's grade as a reference.

    `values` are the validated features by name (None = not recorded); the model's
    training pipeline handles missing values. `warnings` come from the feature schema.
    `image` is the decoded, domain-validated image.
    """
    from pipelines.grading import hybrid
    from pipelines.grading.feature_schema import load_schema

    embedding, resized = hybrid.embed(image)
    warnings = list(warnings)
    if resized:
        width, height = hybrid.load_classifier()[1]["backbone"]["training_image_size"]
        warnings.append({
            "code": "IMAGE_NOT_TRAINING_SIZE",
            "field": "image",
            "message": f"The image is {image.width} × {image.height} px; the model's image features were "
                       f"trained on {width} × {height} px specular images. It was resized, so the image's "
                       "contribution to the grade may be unreliable.",
        })

    grade, probabilities = hybrid.predict(values, embedding, load_schema())
    missing = [name for name, value in values.items() if value is None]
    reference = ecd_reference(values.get("ECD_CD_cells_per_mm2"))

    message = (
        "Grade from the hybrid model (24 Konan and slit-lamp inputs plus image features). In nested "
        "cross-validation it was not better than the ECD rule shown below. Specialist confirmation required."
    )
    if missing:
        message += f" {len(missing)} of 24 inputs were not recorded and were handled as in training."

    return {
        "status": "completed",
        "grade": grade,
        "method": HYBRID_METHOD,
        "modelProbabilities": probabilities,
        "featuresNotRecorded": missing,
        "warnings": warnings,
        "ecdReference": reference,
        "reviewRequired": bool(warnings) or reference["status"] != "completed",
        "message": message,
    }
