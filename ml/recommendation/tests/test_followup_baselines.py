"""Tests for P3: survival metrics, Cox model, trajectory baselines, shared evaluation. Made-up data only."""
import numpy as np
import pandas as pd
import pytest

from recommendation.data_prep.followup_dataset import FollowupPreprocessor, landmark_table, split_grafts
from recommendation.data_prep.followup_simulator import simulate
from recommendation.evaluation import followup_eval as fe
from recommendation.evaluation.survival import (brier_score, censoring_km, concordance_index,
                                                cumulative_dynamic_auc)
from recommendation.risk.cox import CoxPH
from recommendation.trajectory.baselines import BASELINES, LastValue, PopulationDecay, forecast_errors


def _table(n=400, seed=31):
    g, v = simulate(n, seed=seed)
    t = landmark_table(g, v)
    t["split"] = split_grafts(t, seed=0).to_numpy()
    return t


# ---- metrics against hand-worked cases

def test_c_index_perfect_reversed_and_random():
    t, e = [1, 2, 3, 4], [1, 1, 1, 1]
    assert concordance_index(t, e, [4, 3, 2, 1]) == 1.0
    assert concordance_index(t, e, [1, 2, 3, 4]) == 0.0
    assert concordance_index(t, e, [0, 0, 0, 0]) == 0.5


def test_c_index_ignores_pairs_that_are_not_comparable():
    # graft 2 censored at 1 is not comparable with the later event; only (1,3) and (1,...) count
    assert concordance_index([2, 1, 5], [1, 0, 0], [3, 9, 1]) == 1.0


def test_auc_and_brier_without_censoring():
    t = np.array([1, 2, 10, 12])
    e = np.array([1, 1, 1, 1], bool)
    g = censoring_km(t, e)                                   # no censoring -> G = 1
    assert cumulative_dynamic_auc(t, e, [4, 3, 2, 1], 5, g) == 1.0
    # perfect survival predictions give Brier 0; the opposite gives 1
    assert brier_score(t, e, [0, 0, 1, 1], 5, g) == pytest.approx(0.0)
    assert brier_score(t, e, [1, 1, 0, 0], 5, g) == pytest.approx(1.0)


# ---- Cox model

def test_cox_recovers_direction_of_effect():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(400, 2))
    t = rng.exponential(1 / np.exp(1.0 * x[:, 0]))          # x0 raises hazard, x1 no effect
    e = np.ones(400, bool)
    m = CoxPH(penalty=0.01).fit(x, t, e)
    assert m.coef[0] > 0.7 and abs(m.coef[1]) < 0.2
    s5, s50 = m.predict_survival(x[:5], 0.1), m.predict_survival(x[:5], 2.0)
    assert ((0 <= s50) & (s50 <= s5) & (s5 <= 1)).all()     # survival falls over time


def test_stronger_penalty_shrinks_coefficients():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(200, 3))
    t = rng.exponential(1 / np.exp(x[:, 0]))
    e = rng.random(200) < 0.8
    small, big = CoxPH(penalty=0.01).fit(x, t, e), CoxPH(penalty=100).fit(x, t, e)
    assert np.abs(big.coef).sum() < np.abs(small.coef).sum()


# ---- trajectory baselines

def test_baselines_predict_every_horizon_from_month_12_inputs():
    t = _table()
    train = t[t["split"] == "train"]
    for cls in BASELINES:
        p = cls().fit(train).predict(t)
        assert list(p.columns) == ["ECD_24m", "ECD_36m", "ECD_60m"]
        assert p.notna().all().all() and (p > 0).all().all()


def test_last_value_is_flat_and_decay_declines():
    t = _table()
    lv = LastValue().fit(t).predict(t)
    assert (lv["ECD_60m"] == t["ECD_12m"]).all()
    pd_ = PopulationDecay().fit(t[t["split"] == "train"]).predict(t)
    assert (pd_["ECD_60m"] < pd_["ECD_24m"]).all()


def test_forecast_errors_on_known_values():
    tab = pd.DataFrame({"ECD_24m": [1000, np.nan], "ECD_36m": [900, 800], "ECD_60m": [np.nan, np.nan]})
    pred = pd.DataFrame({"ECD_24m": [1100, 5], "ECD_36m": [900, 900], "ECD_60m": [1, 1]})
    e = forecast_errors(tab, pred)
    assert e["24m"] == {"n": 1, "mae": 100.0, "rmse": 100.0}
    assert e["36m"]["mae"] == 50.0 and e["60m"]["n"] == 0
    assert e["all"]["n"] == 3


# ---- shared evaluation

def test_folds_never_put_a_graft_in_train_and_test():
    t = _table(200)
    seen = {}
    for rep, tr, te in fe.folds(t, k=5, repeats=2):
        assert not set(tr) & set(te)
        seen.setdefault(rep, []).extend(te)
    for rep, idx in seen.items():
        assert sorted(idx) == sorted(t.index)                # each graft tested once per repeat


def test_low_ecd_endpoint_excludes_grafts_already_low():
    t = _table()
    rows = fe.endpoint_rows(t, "low_ecd")
    assert not rows["low_ecd_before_landmark"].any()
    assert len(fe.endpoint_rows(t, "graft_failure")) == len(t)


def test_risk_scoring_runs_and_cox_beats_no_input_baseline():
    t = _table(600, seed=33)
    tr, te = t[t["split"] == "train"], t[t["split"] != "train"]
    km = fe.score_risk(fe.KaplanMeierRisk, tr, te, "low_ecd")
    cox = fe.score_risk(lambda: CoxPH(penalty=1.0), tr, te, "low_ecd")
    assert km["c_index"] == 0.5
    assert cox["c_index"] > 0.6
    assert 0 <= cox["brier_24m"] <= 1


def test_preprocessor_refit_inside_folds_uses_fold_train_only():
    t = _table(200)
    rep, tr, te = next(fe.folds(t, k=5, repeats=1))
    pre = FollowupPreprocessor().fit(t.loc[tr])
    assert pre.medians["ECD_12m"] == pytest.approx(t.loc[tr, "ECD_12m"].median())
