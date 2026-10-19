"""Corneal endothelial disease detection and severity grading (v2).

Port of safe_analyse() / analyse() in
ml/disease-new/notebooks/10_Inference_Final_Models_v2.ipynb. One specular microscopy
image plus five CellChek values (ECD, SD, CV, HEX %, donor age; None = not recorded)
give, for FECD, Guttata, Folds, PolyPleo and LowCD, a probability and found / not
found (per-disease threshold), the severity (Mild or Mod/Sev) of each detected disease
group, the overall (worst) severity and a Grad-CAM map per detected disease.

Research tool, not a medical diagnosis. Served by POST /disease/analyze
(app/routers/disease.py) on its own page; the combined /analyze endpoint does not run it.
"""
from dataclasses import asdict, dataclass

import numpy as np

from pipelines.disease import checks, explain, model
from pipelines.disease.config import load_config

METHOD = "densenet121_image_numbers_fusion_v2"
LABELS = {
    "FECD": "Fuchs endothelial corneal dystrophy (FECD)",
    "Guttata": "Guttata",
    "Folds": "Descemet folds",
    "PolyPleo": "Polymegathism / pleomorphism",
    "LowCD": "Low cell density",
}
SEVERITY_ORDER = {"None": 0, "Mild": 1, "Mod/Sev": 2}


def run_disease_analysis(image) -> dict:
    """Disease module of the combined /analyze endpoint: not run there (see POST /disease/analyze)."""
    raise NotImplementedError("Disease analysis runs on its own page (POST /disease/analyze).")


@dataclass
class DiseaseOutcome:
    rejected: bool          # input checks failed and the analysis was not forced
    input_check: dict
    image_quality: dict
    result: dict | None     # None when rejected


def warm_up() -> None:
    """Load the config, both models and the unusual-image reference (raises DiseaseModelNotReady)."""
    load_config()
    model.load_models()


def severities(probabilities: np.ndarray, severity_probabilities: np.ndarray, found: list[str],
               ecd: float | None) -> list[dict]:
    """notebook analyse(): severity of each detected disease group."""
    config = load_config()
    out = []
    for k, (head, diseases) in enumerate(config["severity_heads"].items()):
        if not any(c in found for c in diseases):
            continue
        if head == "FECDgroup" and config["fecd_sev_method"] == "cd_rule":
            moderate = ecd is not None and ecd < config["fecd_cd_rule_ecd_below"]
            probability, threshold, method = None, None, "cd_rule"
        else:
            probability = float(severity_probabilities[k])
            threshold = float(config["severity_thresholds"][head])
            moderate, method = probability >= threshold, "model"
        out.append({
            "group": head, "label": config["severity_head_names"].get(head, head),
            "diseases": [c for c in diseases if c in found], "grade": "Mod/Sev" if moderate else "Mild",
            "probability": probability, "threshold": threshold, "method": method,
        })
    if "Guttata" in found and "Guttata" not in config["severity_heads"]:
        out.append({"group": "Guttata", "label": "Guttata", "diseases": ["Guttata"], "grade": "Mild",
                    "probability": None, "threshold": None, "method": "not_gradable"})
    return out


def analyse(gray: np.ndarray, rgb: np.ndarray, values: dict, force: bool = False,
            include_gradcam: bool = True) -> DiseaseOutcome:
    """Checks the inputs and, unless they fail (and force is off), predicts.

    gray: 8-bit greyscale image (H, W); rgb: the same image in colour (H, W, 3), for the
    colour check; values: the five measurements by name (None = not recorded).
    """
    config = load_config()
    diseases = config["diseases"]

    prepared = model.prepare(gray)
    quality = checks.check_quality(gray)
    prediction = model.predict(prepared, model.scale_numbers(values))
    distance = model.unusual_distance(prediction.embedding)

    image_errors, image_warnings = checks.validate_image(rgb, quality, distance)
    number_errors, number_warnings = checks.validate_numbers(values)
    errors, warnings = image_errors + number_errors, image_warnings + number_warnings
    input_check = {
        "passed": not errors, "forced": bool(errors) and force,
        "errors": [asdict(e) for e in errors], "warnings": [asdict(w) for w in warnings],
    }
    image_quality = {
        "rating": quality.rating, "focus": round(quality.focus, 2),
        "focusLowLimit": round(config["quality"]["low_focus_below"], 2),
        "darkFraction": round(quality.dark, 4), "saturatedFraction": round(quality.saturated, 4),
        "contrast": round(quality.std, 2), "unusualDistance": round(distance, 4),
        "unusualWarnAbove": round(config["ood"]["warn_above"], 4),
        "unusualRejectAbove": round(config["ood"]["reject_above"], 4),
    }
    if errors and not force:
        return DiseaseOutcome(True, input_check, image_quality, None)

    P, PS = prediction.disease_probabilities, prediction.severity_probabilities
    thresholds = config["disease_thresholds"]
    found = [c for j, c in enumerate(diseases) if P[j] >= thresholds[c]]
    shap = explain.explain_numbers(values, prediction)
    findings = []
    for j, c in enumerate(diseases):
        detected = c in found
        with_cam = detected and include_gradcam
        findings.append({
            "code": c, "label": LABELS.get(c, c), "probability": float(P[j]), "threshold": float(thresholds[c]),
            "detected": detected,
            "gradcamPng": model.overlay_png(prepared, prediction.cams[j]) if with_cam else None,
            "gradcamFocus": model.gradcam_focus(prediction.cams[j]) if with_cam else None,
            "shap": shap["disease"][c],
        })
    severity = severities(P, PS, found, values.get("ECD_CD_cells_per_mm2"))
    for group in severity:
        group["shap"] = shap["severity"].get(group["group"]) if group["method"] == "model" else None
    overall = max((s["grade"] for s in severity), key=lambda s: SEVERITY_ORDER[s]) if severity else "None"
    used = model.feature_row(values)
    missing = [name for name in checks.MEASUREMENTS if values.get(name) is None]

    message = ("Research tool, not a medical diagnosis. Probabilities come from the DenseNet121 image + numbers "
               "model; a disease counts as found at or above its threshold, chosen on cross-validation.")
    if input_check["forced"]:
        message += " The inputs failed the checks and the analysis was forced: the result is NOT reliable."
    elif warnings:
        message += " Some inputs raised warnings; treat the result with caution."

    return DiseaseOutcome(False, input_check, image_quality, {
        "method": METHOD,
        "diseases": findings,
        "detected": found,
        "normal": not found,
        "severity": severity,
        "overallSeverity": overall,
        "severityProbabilities": {h: float(PS[k]) for k, h in enumerate(config["severity_heads"])},
        "measurementsUsed": used,
        "measurementsNotRecorded": missing,
        "reliable": not errors and quality.rating == "OK",
        "message": message,
    })
