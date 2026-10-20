"""Export the trained ranker for the ML service.

The ML service must not depend on the research code, pandas or scikit-learn, so the
logistic-regression ranker is written out as plain numbers in JSON:

    feature list, missing-value medians, standardisation means/scales,
    coefficients, intercept, feature -> reason mapping, evaluation summary

The file holds model parameters only (23 numbers per list): no records, IDs or dates.
"""
import json
from datetime import date
from pathlib import Path

import joblib

from recommendation.explain.shap_explain import REASON_OF


def export_model(model_file: Path, out_file: Path, metrics_file: Path | None = None) -> dict:
    saved = joblib.load(model_file)
    settings, features, est = saved["settings"], saved["features"], saved["estimator"]
    if settings["model"] != "logistic":
        raise ValueError("Only the logistic-regression ranker can be exported to plain JSON.")
    imputer, scaler, lr = est

    summary = {}
    if metrics_file and metrics_file.exists():
        m = json.loads(metrics_file.read_text())
        rc = m["repeated_cv_all_requests"]
        summary = {
            "evaluation": f"{rc['repeats']}x {rc['folds']}-fold grouped CV over {rc['requests']} requests",
            "ml_top3": rc["methods"]["ML ranker"]["top3"],
            "mcda_top3": rc["methods"]["MCDA"]["top3"],
            "ml_mrr": rc["methods"]["ML ranker"]["mrr"],
            "mcda_mrr": rc["methods"]["MCDA"]["mrr"],
        }

    model = {
        "name": "matching-ranker-logistic",
        "version": date.today().isoformat(),
        "settings": settings,
        "features": list(features),
        "impute_median": [float(v) for v in imputer.statistics_],
        "mean": [float(v) for v in scaler.mean_],
        "scale": [float(v) for v in scaler.scale_],
        "coef": [float(v) for v in lr.coef_[0]],
        "intercept": float(lr.intercept_[0]),
        "reason_of": {f: REASON_OF.get(f, "other") for f in features},
        "summary": summary,
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(model, indent=2))
    return model
