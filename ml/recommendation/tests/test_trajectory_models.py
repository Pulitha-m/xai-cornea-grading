"""Tests for P4 trajectory models and the selection logic. Simulated data only, short training."""
import pickle

import numpy as np
import pandas as pd

from recommendation.data_prep.followup_dataset import HORIZONS, LANDMARK, landmark_table, split_grafts
from recommendation.data_prep.followup_simulator import simulate
from recommendation.trajectory import experiment
from recommendation.trajectory.baselines import LastValue, PopulationDecay, forecast_errors
from recommendation.trajectory.models import GradientBoosting, LSTMTrajectory


def _table(n=400, seed=41):
    g, v = simulate(n, seed=seed)
    t = landmark_table(g, v)
    t["split"] = split_grafts(t, seed=0).to_numpy()
    return g, v, t


def test_gbm_and_lstm_predict_positive_declining_ecd():
    _, _, t = _table()
    train = t[t["split"] == "train"]
    for model in (GradientBoosting(n_estimators=50), LSTMTrajectory(epochs=60)):
        p = model.fit(train).predict(t)
        assert list(p.columns) == [f"ECD_{h}m" for h in HORIZONS]
        assert p.notna().all().all() and (p > 0).all().all()
        assert (p["ECD_60m"] < t["ECD_12m"]).mean() > 0.9      # cells keep being lost


def test_models_ignore_visits_after_month_12():
    g, v, t = _table()
    train = t[t["split"] == "train"]
    m = GradientBoosting(n_estimators=50).fit(train)
    v2 = v.astype({"ECD": float})
    v2.loc[v2["months_after_surgery"] > LANDMARK, "ECD"] *= 0.3
    t2 = landmark_table(g, v2)
    assert np.allclose(m.predict(t).to_numpy(), m.predict(t2).to_numpy())


def test_test_rows_do_not_change_a_fitted_model():
    _, _, t = _table()
    train = t[t["split"] == "train"]
    a = GradientBoosting(n_estimators=50).fit(train).predict(train)
    t2 = t.copy()
    t2.loc[t2["split"] == "test", "ECD_24m"] = 1.0
    b = GradientBoosting(n_estimators=50).fit(t2[t2["split"] == "train"]).predict(train)
    assert np.allclose(a.to_numpy(), b.to_numpy())


def test_lstm_is_reproducible_and_survives_save_load():
    _, _, t = _table(250)
    train = t[t["split"] == "train"]
    a = LSTMTrajectory(epochs=40, seed=3).fit(train)
    b = LSTMTrajectory(epochs=40, seed=3).fit(train)
    assert np.allclose(a.predict(t).to_numpy(), b.predict(t).to_numpy())
    c = pickle.loads(pickle.dumps(a))
    assert np.allclose(a.predict(t).to_numpy(), c.predict(t).to_numpy())


def test_learned_models_beat_carrying_the_last_value_forward():
    _, _, t = _table(600, seed=42)
    train, val = t[t["split"] == "train"], t[t["split"] != "train"]
    last = forecast_errors(val, LastValue().fit(train).predict(val))["all"]["mae"]
    gbm = forecast_errors(val, GradientBoosting(n_estimators=100).fit(train).predict(val))["all"]["mae"]
    assert gbm < last


def test_choice_prefers_simpler_model_within_margin():
    cv = {c.name: {"all": {"mae": 100.0}} for c in experiment.ORDER}
    cv[experiment.LSTMTrajectory.name]["all"]["mae"] = 99.0        # 1% better: not enough
    cv[experiment.LastValue.name]["all"]["mae"] = 300.0
    assert experiment.choose(cv) == PopulationDecay.name
    cv[experiment.LSTMTrajectory.name]["all"]["mae"] = 80.0        # clearly better
    assert experiment.choose(cv) == experiment.LSTMTrajectory.name


def test_band_coverage_matches_its_level_on_the_calibration_data():
    rng = np.random.default_rng(0)
    resid = {h: rng.normal(0, 0.1, 2000) for h in HORIZONS}
    band = experiment.band_from_residuals(resid)
    pred = pd.DataFrame({f"ECD_{h}m": np.full(2000, 1000.0) for h in HORIZONS})
    truth = pd.DataFrame({f"ECD_{h}m": 1000.0 * np.exp(resid[h]) for h in HORIZONS})
    cov = experiment.band_coverage(truth, pred, band)
    assert all(abs(d["coverage"] - 0.8) < 0.02 for d in cov.values())
