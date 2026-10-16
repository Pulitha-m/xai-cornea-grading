"""Donor cornea grading from ECD using the exported threshold-tree spec.

The spec (models/grading_ecd_tree.json) is produced by
ml/grading/scripts/train_grading_model.py. It holds the cut points of a
depth-2 decision tree on ECD and the recorded grades of its training
tissues in each ECD band. The grade is decision support only: it ignores
slit-lamp findings and other morphology, and a specialist confirms it.
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


def run_grading_analysis(ecd: float | None) -> dict:
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
        raise ValueError(f"ECD {ecd} is outside the valid range {valid}")

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
