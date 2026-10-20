"""Serving version of the post-transplant follow-up recommendation (12-month visit).

Mirrors ml/recommendation (P2 preprocessing, P4 trajectory, P5 risk, P6 reasons,
P7 rules) using only numpy, from the parameters exported by
`python -m recommendation.main followup-export` into
ml-service/models/recommendation_followup.json. For one graft it returns:

  predicted ECD   at 24 / 36 / 60 months with an 80% band (gradient-boosting trees)
  risk            graft failure and ECD < 1000 within 12 / 24 months of this visit
                  (Cox model + isotonic recalibration)
  alert           green / amber / red, next visit in 12 / 6 / 3 months, review prompts
  reasons         rules that fired, the strongest model reasons and a descriptive
                  counterfactual

Keep this file in step with the research code: the parity test in
ml/recommendation/tests/test_followup_export.py compares both on many grafts.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

# Team convention: trained model files live in ml-service/models/
MODEL_FILE = Path(__file__).resolve().parents[2] / "models" / "recommendation_followup.json"
LANDMARK = 12
INPUT_MONTHS = (3, 6, 12)
HORIZONS = (24, 36, 60)
LOW_ECD = 1000
FAILURE_ECD = 500
RISK_THRESHOLDS = {"graft_failure": 0.10, "low_ecd": 0.30}       # counterfactual targets (as in P6)
ECD_STEP, ECD_MAX_STEPS = 100, 15
REASONS = ["12-month ECD", "early cell loss", "cell shape (CV/HEX)", "donor", "procedure", "indication",
           "rejection", "missed visit"]
DISCLAIMER = "Decision support only. Follow-up decisions rest with the treating clinician."
NAN = float("nan")


@lru_cache(maxsize=1)
def load_model(path: str = str(MODEL_FILE)) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ---------------------------------------------------------------- inputs (P2)
def landmark_row(req: dict) -> dict:
    """Request -> the landmark inputs used by the models (derived inputs recomputed)."""
    row = {"procedure": req["procedure"], "indication": req["indication"],
           "donor_age": float(req["donor_age"]), "baseline_ECD": float(req["baseline_ecd"]),
           "baseline_CV": float(req["baseline_cv"]), "baseline_HEX": float(req["baseline_hex"]),
           "rejection_by_12m": 1.0 if req.get("rejection_by_12m") else 0.0}
    for m in INPUT_MONTHS:
        visit = req.get(f"visit_{m}m") or {}
        for k in ("ECD", "CV", "HEX"):
            v = visit.get(k.lower())
            row[f"{k}_{m}m"] = NAN if v is None else float(v)
    return add_derived(row)


def add_derived(row: dict) -> dict:
    row["loss_12m"] = 1 - row["ECD_12m"] / row["baseline_ECD"]
    first, first_month = (row["ECD_3m"], 3) if not math.isnan(row["ECD_3m"]) else (row["ECD_6m"], 6)
    row["log_ecd_slope_3_12"] = (math.log(row["ECD_12m"]) - math.log(first)) / ((LANDMARK - first_month) / 12)
    return row


def already_low(row: dict) -> bool:
    return any(not math.isnan(row[f"ECD_{m}m"]) and row[f"ECD_{m}m"] < LOW_ECD for m in INPUT_MONTHS)


def transform(pre: dict, row: dict) -> dict:
    """FollowupPreprocessor.transform for one row: name -> scaled value."""
    out = {}
    for c in pre["numeric"]:
        v = row[c]
        v = pre["medians"][c] if v is None or (isinstance(v, float) and math.isnan(v)) else v
        out[c] = (v - pre["means"][c]) / pre["stds"][c]
    for c in pre["flag_cols"]:
        v = row[c]
        out[f"{c}_missing"] = 1.0 if v is None or (isinstance(v, float) and math.isnan(v)) else 0.0
    for c in pre["categorical"]:
        for lv in pre["levels"][c]:
            out[f"{c}={lv}"] = 1.0 if str(row[c]) == lv else 0.0
    return out


# ---------------------------------------------------------------- trajectory (P4)
def _tree_value(tree: dict, x: list) -> float:
    i = 0
    while tree["feature"][i] != -1:
        v = x[tree["feature"][i]]
        go_left = tree["default_left"][i] if math.isnan(v) else v <= tree["threshold"][i]
        i = tree["left"][i] if go_left else tree["right"][i]
    return tree["value"][i]


def _trajectory_x(traj: dict, row: dict, horizon: int) -> list:
    z = transform(traj["preprocessor"], row)
    return [z[f] for f in traj["features"][:-1]] + [(horizon - LANDMARK) / 12]


def predict_ecd(model: dict, row: dict) -> dict:
    traj = model["trajectory"]
    out = {}
    for h in HORIZONS:
        ratio = sum(_tree_value(t, _trajectory_x(traj, row, h)) for t in traj["trees"])
        lo, hi = traj["band_log_quantiles"][str(h)]
        ecd = row["ECD_12m"] * math.exp(ratio)
        out[h] = {"ecd": ecd, "low": ecd * math.exp(lo), "high": ecd * math.exp(hi)}
    return out


def trajectory_reasons(model: dict, row: dict, horizon: int = 60) -> list[dict]:
    """SHAP of the 60-month prediction per clinical reason (% effect on predicted ECD)."""
    explainer = _shap_explainer(model["trajectory"])
    if explainer is None:                                 # reasons are optional; predictions are not
        return []
    traj = model["trajectory"]
    phi = explainer.shap_values(np.array([_trajectory_x(traj, row, horizon)]))[0]
    by = _group(dict(zip(traj["features"], phi)))
    return [{"reason": k, "effect_pct": round((math.exp(v) - 1) * 100, 1)}
            for k, v in sorted(by.items(), key=lambda kv: -abs(kv[1])) if abs(v) > 0.005][:3]


_EXPLAINERS: dict = {}


def _shap_explainer(traj: dict):
    """TreeSHAP over the exported trees (built once per loaded model)."""
    key = id(traj)
    if key not in _EXPLAINERS:
        try:
            import shap
        except ImportError:
            return None
        trees = [{"children_left": np.array(t["left"]), "children_right": np.array(t["right"]),
                  "children_default": np.where(np.array(t["default_left"]), np.array(t["left"]),
                                               np.array(t["right"])),
                  "features": np.array(t["feature"]), "thresholds": np.array(t["threshold"]),
                  "values": np.array(t["value"]).reshape(-1, 1), "node_sample_weight": np.array(t["count"], float)}
                 for t in traj["trees"]]
        _EXPLAINERS.clear()
        _EXPLAINERS[key] = shap.TreeExplainer({"trees": trees, "base_offset": 0.0})
    return _EXPLAINERS[key]


# ---------------------------------------------------------------- risk (P5)
def _risk_x(part: dict, row: dict) -> list:
    z = transform(part["preprocessor"], row)
    return [z[f] for f in part["features"]]


def predict_risk(part: dict, row: dict, tau: int) -> float:
    lp = sum(c * x for c, x in zip(part["coef"], _risk_x(part, row)))
    times = part["base_times"]
    idx = int(np.searchsorted(times, tau, side="right")) - 1
    h0 = part["base_cumhaz"][idx] if idx >= 0 else 0.0
    raw = 1 - math.exp(-h0 * math.exp(lp))
    x, y = part["maps"][str(tau)]
    return float(np.interp(raw, x, y))


def risk_reasons(part: dict, row: dict) -> list[dict]:
    """Exact SHAP of the Cox score: coef x (input - population mean), as hazard ratios."""
    phi = {f: c * (x - m) for f, c, x, m in zip(part["features"], part["coef"], _risk_x(part, row),
                                                  part["reference_mean"])}
    by = _group(phi)
    return [{"reason": k, "hazard_ratio": round(math.exp(v), 2)}
            for k, v in sorted(by.items(), key=lambda kv: -abs(kv[1])) if abs(v) > 0.01][:3]


def risk_counterfactual(part: dict, row: dict, endpoint: str, tau: int = 24) -> str | None:
    thr = RISK_THRESHOLDS[endpoint]
    if predict_risk(part, row, tau) <= thr:
        return None
    options = []
    for k in range(1, ECD_MAX_STEPS + 1):
        new = add_derived({**row, "ECD_12m": row["ECD_12m"] + k * ECD_STEP})
        r = predict_risk(part, new, tau)
        if r <= thr:
            options.append(f"12-month ECD {new['ECD_12m']:.0f} instead of {row['ECD_12m']:.0f} (risk {r:.0%})")
            break
    if row["rejection_by_12m"] == 1:
        r = predict_risk(part, {**row, "rejection_by_12m": 0.0}, tau)
        if r <= thr:
            options.append(f"no rejection episode by 12 months (risk {r:.0%})")
    text = "; or ".join(options) if options else f"no single realistic change brings it under {thr:.0%}"
    return f"risk would be under {thr:.0%} with: {text} [descriptive]"


# ---------------------------------------------------------------- reasons mapping (as in P6)
def reason_of(feature: str) -> str | None:
    if feature.endswith("_missing"):
        return "missed visit"
    if feature == "years_ahead":
        return None
    if feature.startswith("ECD_12m"):
        return "12-month ECD"
    if feature in ("loss_12m", "log_ecd_slope_3_12") or feature.startswith(("ECD_3m", "ECD_6m")):
        return "early cell loss"
    if feature.startswith(("CV_", "HEX_", "baseline_CV", "baseline_HEX")):
        return "cell shape (CV/HEX)"
    if feature in ("donor_age", "baseline_ECD"):
        return "donor"
    if feature.startswith("procedure="):
        return "procedure"
    if feature.startswith("indication="):
        return "indication"
    if feature == "rejection_by_12m":
        return "rejection"
    return None


def _group(phi: dict) -> dict:
    out = {r: 0.0 for r in REASONS}
    for f, v in phi.items():
        r = reason_of(f)
        if r:
            out[r] += float(v)
    return out


# ---------------------------------------------------------------- rules (P7)
def apply_rules(p: dict, rules: dict) -> dict:
    r, a = rules["red"], rules["amber"]
    red = [("rejection episode by 12 months", p["rejection_by_12m"]),
           (f"failure risk by 12 months >= {r['failure_risk_12m']:.0%}", p["failure_risk_12m"] >= r["failure_risk_12m"]),
           (f"12-month ECD < {r['ecd_12m_below']}", p["ecd_12m"] < r["ecd_12m_below"]),
           (f"predicted 24-month ECD < {r['predicted_ecd_24m_below']}", p["ecd_24m"] < r["predicted_ecd_24m_below"])]
    amber = [(f"failure risk by 24 months >= {a['failure_risk_24m']:.0%}", p["failure_risk_24m"] >= a["failure_risk_24m"]),
             (f"low-ECD risk by 24 months >= {a['low_ecd_risk_24m']:.0%}", p["low_ecd_risk_24m"] >= a["low_ecd_risk_24m"]),
             (f"60-month ECD could reach {a['ecd_60m_lower_band_below']} (lower end of 80% band)",
              p["ecd_60m_low"] < a["ecd_60m_lower_band_below"]),
             (f"cell loss by 12 months >= {a['loss_12m_at_least']:.0%}", p["loss_12m"] >= a["loss_12m_at_least"]),
             ("ECD already below 1000", p["already_low_ecd"])]
    fired = [k for k, hit in red + amber if hit]
    level = "red" if any(h for _, h in red) else "amber" if any(h for _, h in amber) else "green"
    acts = []
    if p["rejection_by_12m"]:
        acts.append("Review for graft rejection")
    if p["ecd_24m"] < FAILURE_ECD or p["ecd_36m"] < FAILURE_ECD:
        acts.append("Consider regraft assessment: ECD projected below 500 within 3 years")
    if level == "red" and not acts:
        acts.append("Clinical review of endothelial function")
    if level in ("red", "amber"):
        acts.append("Repeat specular microscopy (ECD, CV, HEX) at the next visit")
    if level == "green":
        acts.append("Routine follow-up")
    return {"alert": level, "next_visit_months": int(rules["interval_months"][level]),
            "rules_fired": fired, "actions": acts}


# ---------------------------------------------------------------- one graft
def recommend_followup(req: dict, model: dict | None = None) -> dict:
    model = model or load_model()
    if model is None:
        raise FileNotFoundError("recommendation_followup.json is not installed")
    row = landmark_row(req)
    ecd = predict_ecd(model, row)
    fail, low = model["risk"]["graft_failure"], model["risk"]["low_ecd"]
    is_low = already_low(row)
    risk = {"graft_failure": {f"{t}m": predict_risk(fail, row, t) for t in (12, 24)},
            "low_ecd": {f"{t}m": 1.0 if is_low else predict_risk(low, row, t) for t in (12, 24)}}
    p = {"rejection_by_12m": row["rejection_by_12m"] == 1, "ecd_12m": row["ECD_12m"], "loss_12m": row["loss_12m"],
         "already_low_ecd": is_low, "failure_risk_12m": risk["graft_failure"]["12m"],
         "failure_risk_24m": risk["graft_failure"]["24m"], "low_ecd_risk_24m": risk["low_ecd"]["24m"],
         "ecd_24m": ecd[24]["ecd"], "ecd_36m": ecd[36]["ecd"], "ecd_60m_low": ecd[60]["low"]}
    decision = apply_rules(p, model["rules"])
    counterfactuals = [c for c in (risk_counterfactual(fail, row, "graft_failure"),
                                   None if is_low else risk_counterfactual(low, row, "low_ecd")) if c]
    return {
        **decision,
        "predicted_ecd": [{"months": h, "ecd": round(v["ecd"]), "low": round(v["low"]), "high": round(v["high"])}
                          for h, v in ecd.items()],
        "band_level": model["trajectory"]["band_level"],
        "risk": [{"outcome": o, "within_months": int(k[:-1]), "probability": round(v, 3)}
                 for o, d in risk.items() for k, v in d.items()],
        "reasons": {"trajectory": trajectory_reasons(model, row),
                    "graft_failure": risk_reasons(fail, row),
                    "low_ecd": [] if is_low else risk_reasons(low, row)},
        "counterfactuals": counterfactuals,
        "model": model["name"], "model_version": model["version"],
        "rules_version": model["rules"].get("version"),
        "data_source": model["data_source"],
        "disclaimer": DISCLAIMER,
    }
