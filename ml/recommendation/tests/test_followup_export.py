"""The exported follow-up models must give the same results in the ML service as in the research code.

Uses a small simulated cohort and quickly fitted models. The parity checks run when the
ml-service folder is present (it is, in the team repo); otherwise they are skipped.
"""
import importlib
import json
import math
import sys
from pathlib import Path

import joblib
import numpy as np
import pytest

from recommendation.data_prep.followup_dataset import landmark_table, split_grafts
from recommendation.data_prep.followup_simulator import simulate
from recommendation.explain import followup_explain as fx
from recommendation.followup import recommend as R
from recommendation.followup.export import export_followup
from recommendation.risk import experiment as rx
from recommendation.risk.cox import CoxPH
from recommendation.trajectory.experiment import band_from_residuals, oof_log_residuals
from recommendation.trajectory.models import GradientBoosting

ML_SERVICE = Path(__file__).resolve().parents[3] / "ml-service"


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("followup_export")
    g, v = simulate(500, seed=61)
    t = landmark_table(g, v)
    t["split"] = split_grafts(t, seed=0).to_numpy()
    gbm = lambda: GradientBoosting(n_estimators=60)                   # noqa: E731
    traj = {"name": GradientBoosting.name, "model": gbm().fit(t),
            "band": band_from_residuals(oof_log_residuals(gbm, t)), "band_level": "10-90%"}
    cox = lambda: CoxPH(penalty=1.0)                                  # noqa: E731
    risk = {}
    for ep in ("graft_failure", "low_ecd"):
        maps = rx.risk_maps({tau: rx.oof_survival(cox, t, ep, rx.COX_CLINICAL, tau=tau) for tau in (12, 24, 36)})
        risk[ep] = {"name": "Cox, clinical inputs",
                    **rx.recalibrate(rx.fit_with_preprocessing(cox, t, ep, rx.COX_CLINICAL), maps)}
    joblib.dump(traj, tmp / "followup_trajectory.joblib")
    joblib.dump({"source": "simulated", "models": risk}, tmp / "followup_risk.joblib")
    model = export_followup(tmp, t, tmp / "followup.json")
    return t, traj, {"models": risk}, model, tmp / "followup.json"


def _serving():
    sys.path.insert(0, str(ML_SERVICE))
    try:
        return importlib.import_module("pipelines.recommendation.followup")
    finally:
        sys.path.pop(0)


def _request(r) -> dict:
    def visit(m):
        e = getattr(r, f"ECD_{m}m")
        if isinstance(e, float) and math.isnan(e):
            return None
        return {"ecd": e, "cv": getattr(r, f"CV_{m}m"), "hex": getattr(r, f"HEX_{m}m")}

    return {"procedure": r.procedure, "indication": r.indication, "donor_age": r.donor_age,
            "baseline_ecd": r.baseline_ECD, "baseline_cv": r.baseline_CV, "baseline_hex": r.baseline_HEX,
            "visit_3m": visit(3), "visit_6m": visit(6), "visit_12m": visit(12),
            "rejection_by_12m": bool(r.rejection_by_12m)}


def test_export_has_parameters_only(bundle):
    *_, path = bundle
    text = path.read_text()
    data = json.loads(text)
    assert set(data) == {"name", "version", "data_source", "landmark_month", "horizons", "trajectory", "risk",
                         "rules", "summary"}
    assert "graft_id" not in text and "G0001" not in text


@pytest.mark.skipif(not ML_SERVICE.exists(), reason="ml-service folder not found")
def test_ml_service_matches_research_predictions_risks_and_alerts(bundle):
    t, traj, risk, model, _ = bundle
    serving = _serving()
    rec = R.recommend(t, traj, risk)
    for r in t.head(120).itertuples():
        out = serving.recommend_followup(_request(r), model)
        res = rec.loc[r.Index]
        served_ecd = {p["months"]: p for p in out["predicted_ecd"]}
        for h in (24, 36, 60):
            assert abs(served_ecd[h]["ecd"] - res[f"ecd_{h}m"]) <= 0.5               # rounded to whole cells
        risks = {(x["outcome"], x["within_months"]): x["probability"] for x in out["risk"]}
        assert abs(risks[("graft_failure", 24)] - res["failure_risk_24m"]) < 1e-3
        assert abs(risks[("low_ecd", 24)] - res["low_ecd_risk_24m"]) < 1e-3
        assert out["alert"] == res["alert"] and out["next_visit_months"] == res["next_visit_months"]


@pytest.mark.skipif(not ML_SERVICE.exists(), reason="ml-service folder not found")
def test_ml_service_reasons_match_research_shap(bundle):
    t, traj, risk, model, _ = bundle
    serving = _serving()
    research = fx.trajectory_shap(traj["model"], t.head(20))["reasons"]
    for r in t.head(20).itertuples():
        served = {x["reason"]: x["effect_pct"] for x in serving.trajectory_reasons(model, serving.landmark_row(_request(r)))}
        for reason, pct in served.items():
            assert abs(pct - round((math.exp(research.loc[r.Index, reason]) - 1) * 100, 1)) <= 0.11
    fail = risk["models"]["graft_failure"]
    contrib = fx.risk_contributions(fail, t.head(20), fx.fe_rows(t, "graft_failure"))["reasons"]
    for r in t.head(20).itertuples():
        served = serving.risk_reasons(model["risk"]["graft_failure"], serving.landmark_row(_request(r)))
        for x in served:
            assert abs(x["hazard_ratio"] - round(float(np.exp(contrib.loc[r.Index, x["reason"]])), 2)) <= 0.011
