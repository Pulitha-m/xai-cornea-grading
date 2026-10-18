"""Input checks of the v2 disease pipeline (notebook 10, Steps 7 and 12).

Errors stop the analysis unless the caller forces it; warnings are reported with the
result. Every limit comes from corneal_config.json.
"""
import math
from dataclasses import dataclass

import cv2
import numpy as np

from pipelines.disease.config import load_config

# Measurement names (as in the training CSV) and their notebook keys and labels.
MEASUREMENTS = {
    "ECD_CD_cells_per_mm2": ("ecd", "ECD"),
    "SD": ("sd", "SD"),
    "CV": ("cv", "CV"),
    "HEX_percent": ("hex_pct", "HEX %"),
    "Donor_Age": ("age", "Donor age"),
}


@dataclass
class Issue:
    code: str
    field: str | None
    message: str


@dataclass
class Quality:
    rating: str  # "OK", "Low" or "Unusable"
    std: float
    focus: float
    dark: float
    saturated: float


def check_quality(gray: np.ndarray) -> Quality:
    """notebook check_quality(): contrast, focus (Laplacian variance), dark and saturated share at 640 x 480."""
    q = load_config()["quality"]
    g = cv2.resize(gray, tuple(q["resize"]), interpolation=cv2.INTER_AREA)
    std = float(g.std())
    focus = float(cv2.Laplacian(g, cv2.CV_64F).var())
    dark = float((g < q["dark_pixel_below"]).mean())
    saturated = float((g > q["saturated_pixel_above"]).mean())
    if std < q["unusable_std_below"] or saturated > q["unusable_saturated_above"]:
        rating = "Unusable"
    elif focus < q["low_focus_below"] or dark > q["low_dark_above"]:
        rating = "Low"
    else:
        rating = "OK"
    return Quality(rating, std, focus, dark, saturated)


def colour_score(rgb: np.ndarray) -> float:
    """notebook validate_image(): mean absolute difference between neighbouring channels."""
    c = rgb.astype(np.float32)
    return float(np.abs(c[..., 0] - c[..., 1]).mean() + np.abs(c[..., 1] - c[..., 2]).mean())


def validate_image(rgb: np.ndarray, quality: Quality, distance: float) -> tuple[list[Issue], list[Issue]]:
    """Colour, resolution, shape, quality and unusual-image checks."""
    config = load_config()
    limits, ood = config["image_checks"], config["ood"]
    errors, warnings = [], []

    colour = colour_score(rgb)
    if colour > limits["colour_score_max"]:
        errors.append(Issue("IMAGE_IS_COLOUR", "image",
                            f"Colour image (colour score {colour:.1f}). Specular microscopy images are greyscale."))
    h, w = rgb.shape[:2]
    if min(h, w) < limits["min_side"]:
        errors.append(Issue("IMAGE_RESOLUTION_TOO_LOW", "image",
                            f"Resolution too low ({w}×{h}; the minimum side is {limits['min_side']} px). Enlarging "
                            "an image makes cells look bigger, which would falsely suggest low cell density or FECD."))
    if not limits["aspect_min"] <= w / h <= limits["aspect_max"]:
        warnings.append(Issue("IMAGE_SHAPE_UNUSUAL", "image",
                              f"Unusual shape {w}×{h} (specular images are 4:3). It may be a screenshot or a crop."))
    if quality.rating == "Unusable":
        errors.append(Issue("IMAGE_QUALITY_UNUSABLE", "image", "Image quality is unusable (blank or saturated)."))
    elif quality.rating == "Low":
        warnings.append(Issue("IMAGE_QUALITY_LOW", "image",
                              "Low image quality (blurred or dark). Treat the result with caution or re-image."))
    if distance > ood["reject_above"]:
        errors.append(Issue("IMAGE_UNUSUAL", "image",
                            f"The image does not look like the training specular images "
                            f"(distance {distance:.3f} > {ood['reject_above']:.3f})."))
    elif distance > ood["warn_above"]:
        warnings.append(Issue("IMAGE_UNUSUAL_WARNING", "image",
                              f"The image is unusual compared with the training images (distance {distance:.3f})."))
    return errors, warnings


def validate_numbers(values: dict) -> tuple[list[Issue], list[Issue]]:
    """notebook validate_numbers(): possible ranges, training ranges, SD consistency, missing values.

    `values` maps measurement names to float or None (None = not recorded, never 0).
    """
    checks = load_config()["number_checks"]
    errors, warnings, clean = [], [], {}
    for name, (key, label) in MEASUREMENTS.items():
        val = values.get(name)
        if val is None:
            warnings.append(Issue("VALUE_MISSING", name, f"{label} not recorded; the training median is used."))
            clean[key] = None
            continue
        clean[key] = val
        lo, hi = checks["limits"][key]
        if val <= 0:
            errors.append(Issue("VALUE_NOT_POSSIBLE", name,
                                f"{label} = {val:g}: zero or negative is impossible. Leave it blank if unknown."))
        elif not lo <= val <= hi:
            errors.append(Issue("VALUE_NOT_POSSIBLE", name, f"{label} = {val:g} is outside the possible range {lo:g}–{hi:g}."))
        elif key in checks["training_range"]:
            t_lo, t_hi = checks["training_range"][key]
            if not t_lo <= val <= t_hi:
                warnings.append(Issue("OUTSIDE_TRAINING_RANGE", name,
                                      f"{label} = {val:g} is outside the range seen in training ({t_lo:g}–{t_hi:g})."))

    e, s, c = clean["ecd"], clean["sd"], clean["cv"]
    if not errors and None not in (e, s, c):
        expected_sd = c / 100 * 1e6 / e   # CellChek: SD = CV x mean cell area
        if abs(s / expected_sd - 1) > checks["sd_consistency_tolerance"]:
            errors.append(Issue("SD_INCONSISTENT", "SD",
                                f"SD {s:g} does not match ECD and CV (expected about {expected_sd:.0f}). "
                                "Check for a typing mistake."))
    if sum(v is None for v in clean.values()) > checks["max_missing"]:
        errors.append(Issue("TOO_MANY_MISSING", None,
                            "Too many CellChek values are missing; the model needs at least "
                            f"{len(MEASUREMENTS) - checks['max_missing']} of the 5."))
    return errors, warnings


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
