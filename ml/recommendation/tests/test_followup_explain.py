"""Tests for P6 explanations and counterfactuals. Simulated data, small models."""
import numpy as np
import pytest

from recommendation.data_prep.followup_dataset import landmark_table, split_grafts
from recommendation.data_prep.followup_simulator import simulate
from recommendation.explain import followup_explain as fx
from recommendation.risk.cox import CoxPH
from recommendation.risk.experiment import COX_CLINICAL, fit_with_preprocessing
from recommendation.trajectory.models import GradientBoosting


@pytest.fixture(scope="module")
def fitted():
    g, v = simulate(500, seed=51)
    t = landmark_table(g, v)
    t["split"] = split_grafts(t, seed=0).to_numpy()
    traj = GradientBoosting(n_estimators=80).fit(t)
    risk = {ep: fit_with_preprocessing(lambda: CoxPH(penalty=1.0), t, ep, COX_CLINICAL)
            for ep in ("graft_failure", "low_ecd")}
    return t, traj, risk


def test_reason_mapping_covers_every_input(fitted):
    t, traj, _ = fitted
    for f in traj.pre.feature_names:
        assert fx.reason_of(f) in fx.REASONS, f
    assert fx.reason_of("years_ahead") is None


def test_trajectory_shap_adds_up(fitted):
    t, traj, _ = fitted
    e = fx.trajectory_shap(traj, t.iloc[:50])
    assert e["additivity_error"] < 1e-6
    assert list(e["reasons"].columns) == fx.REASONS


def test_cox_contributions_are_exact(fitted):
    t, _, risk = fitted
    e = fx.risk_contributions(risk["graft_failure"], t.iloc[:40], t)
    assert e["additivity_error"] < 1e-9


def test_risk_counterfactual_really_crosses_the_threshold(fitted):
    t, _, risk = fitted
    fail = risk["graft_failure"]
    r = fx.risk_at(fail, t)
    high = t.iloc[[int(np.argmax(r))]]
    cf = fx.risk_counterfactual(fail, high, "graft_failure")
    assert cf["risk_now"] > fx.RISK_THRESHOLDS["graft_failure"]
    if cf["options"] and cf["options"][0][0].startswith("12-month ECD"):
        new_ecd = float(cf["options"][0][0].split()[2])
        changed = fx._with_ecd12(high, new_ecd)
        assert fx.risk_at(fail, changed)[0] <= fx.RISK_THRESHOLDS["graft_failure"]
        assert "[descriptive]" in cf["text"]


def test_no_counterfactual_for_low_risk_grafts(fitted):
    t, _, risk = fitted
    fail = risk["graft_failure"]
    low = t.iloc[[int(np.argmin(fx.risk_at(fail, t)))]]
    assert fx.risk_counterfactual(fail, low, "graft_failure")["text"] is None


def test_changing_ecd12_recomputes_derived_inputs(fitted):
    t, _, _ = fitted
    row = t.iloc[[0]]
    new = fx._with_ecd12(row, float(row["ECD_12m"].iloc[0]) + 300)
    assert new["loss_12m"].iloc[0] < row["loss_12m"].iloc[0]
    assert new["log_ecd_slope_3_12"].iloc[0] > row["log_ecd_slope_3_12"].iloc[0]


def test_example_has_reasons_and_risks(fitted):
    t, traj, risk = fitted
    te = fx.trajectory_shap(traj, t)
    re = {ep: fx.risk_contributions(f, fx.fe_rows(t, ep), fx.fe_rows(t, ep)) for ep, f in risk.items()}
    i = t.index[~t["low_ecd_before_landmark"].astype(bool)][0]
    ex = fx.example(t.loc[[i]], traj, risk, te, re)
    assert ex["predicted_ECD_60m"] > 0 and "risk_24m" in ex["graft_failure"] and "risk_24m" in ex["low_ecd"]
