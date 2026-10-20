"""Export the post-transplant models for the ML service (P8).

The ML service must not depend on the research code, LightGBM or torch, so everything the
12-month-visit recommendation needs is written as plain numbers in one JSON file:

  trajectory  preprocessing (medians, means, scales, category levels), the gradient-boosting
              trees as flat arrays (split feature, threshold, children, leaf / node values,
              node counts for SHAP) and the 80% band
  risk        per endpoint: preprocessing, Cox coefficients, Breslow baseline hazard,
              isotonic recalibration maps (12 / 24 / 36 months) and the population mean of
              each input (for exact per-patient reasons)
  rules       the alert thresholds from config.yaml (followup.alerts)
  summary     evaluation numbers from P4 / P5

The file holds model parameters and aggregate statistics only: no records, IDs or dates
other than the version date.
"""
import json
from datetime import date
from pathlib import Path

import joblib
import numpy as np

from recommendation.evaluation.followup_eval import endpoint_rows
from recommendation.followup.recommend import DEFAULT_RULES


def _flat_tree(node: dict) -> dict:
    """LightGBM nested tree -> flat arrays (node 0 = root). Leaves have feature -1."""
    arrays = {k: [] for k in ("feature", "threshold", "left", "right", "default_left", "value", "count")}

    def visit(n):
        i = len(arrays["feature"])
        for k in arrays:
            arrays[k].append(None)
        if "leaf_value" in n:
            arrays["feature"][i], arrays["threshold"][i] = -1, 0.0
            arrays["left"][i] = arrays["right"][i] = -1
            arrays["default_left"][i] = True
            arrays["value"][i], arrays["count"][i] = float(n["leaf_value"]), int(n.get("leaf_count", 0))
            return i
        if n.get("decision_type", "<=") != "<=":
            raise ValueError("only numerical '<=' splits are supported")
        arrays["feature"][i], arrays["threshold"][i] = int(n["split_feature"]), float(n["threshold"])
        arrays["default_left"][i] = bool(n.get("default_left", True))
        arrays["value"][i], arrays["count"][i] = float(n.get("internal_value", 0.0)), int(n.get("internal_count", 0))
        arrays["left"][i] = visit(n["left_child"])
        arrays["right"][i] = visit(n["right_child"])
        return i

    visit(node)
    return arrays


def trajectory_part(saved: dict) -> dict:
    model = saved["model"]
    if type(model).__name__ != "GradientBoosting":
        raise ValueError(f"export supports the gradient-boosting trajectory model, not {saved['name']}")
    dump = model.model.booster_.dump_model()
    return {"name": saved["name"], "preprocessor": model.pre.to_dict(),
            "features": model.pre.feature_names + ["years_ahead"],
            "trees": [_flat_tree(t["tree_structure"]) for t in dump["tree_info"]],
            "band_log_quantiles": {str(h): list(v) for h, v in saved["band"].items()},
            "band_level": saved["band_level"]}


def risk_part(fitted: dict, table) -> dict:
    model = fitted["model"]                         # Recalibrated(CoxPH)
    base = model.base
    if type(base).__name__ != "CoxPH":
        raise ValueError(f"export supports Cox risk models, not {fitted['name']}")
    rows = endpoint_rows(table, fitted["endpoint"])
    X = fitted["preprocessor"].transform(rows)[fitted["features"]]
    return {"name": fitted["name"], "preprocessor": fitted["preprocessor"].to_dict(),
            "features": list(fitted["features"]), "coef": np.asarray(base.coef).tolist(),
            "base_times": np.asarray(base.base_times).tolist(), "base_cumhaz": np.asarray(base.base_cumhaz).tolist(),
            "maps": {str(tau): [list(x), list(y)] for tau, (x, y) in model.maps.items()},
            "reference_mean": X.mean().tolist()}


def export_followup(models_dir: Path, table, out_file: Path, rules: dict | None = None,
                    outputs_dir: Path | None = None) -> dict:
    traj = joblib.load(models_dir / "followup_trajectory.joblib")
    risk = joblib.load(models_dir / "followup_risk.joblib")
    summary = {}
    if outputs_dir is not None:
        tj, rk = outputs_dir / "trajectory" / "trajectory_results.json", outputs_dir / "risk" / "risk_results.json"
        if tj.exists():
            t = json.loads(tj.read_text())
            summary["trajectory_cv_mae_all"] = round(t["cv"][t["chosen"]]["all"]["mae"], 1)
            summary["best_baseline_cv_mae_all"] = round(t["cv"][t["best_baseline"]]["all"]["mae"], 1)
        if rk.exists():
            r = json.loads(rk.read_text())
            for ep, e in r["endpoints"].items():
                summary[f"{ep}_cv_c_index"] = round(e["cv"][e["chosen"]]["c_index"], 3)
    bundle = {
        "name": "followup-12m-visit",
        "version": date.today().isoformat(),
        "data_source": str(table["data_source"].iloc[0]),
        "landmark_month": 12,
        "horizons": [24, 36, 60],
        "trajectory": trajectory_part(traj),
        "risk": {ep: risk_part(f, table) for ep, f in risk["models"].items()},
        "rules": rules or DEFAULT_RULES,
        "summary": summary,
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(bundle), encoding="utf-8")
    return bundle
