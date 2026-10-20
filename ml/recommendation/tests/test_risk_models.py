"""Tests for P5 risk models and selection logic. Made-up / simulated data only."""
import pickle

import numpy as np
import pandas as pd
import torch

from recommendation.data_prep.followup_dataset import landmark_table, split_grafts
from recommendation.data_prep.followup_simulator import simulate
from recommendation.evaluation.survival import concordance_index
from recommendation.risk import experiment
from recommendation.risk.models import DeepSurv, GradientBoostedCox, _cox_grad_hess, _neg_partial_loglik


def _xy(n=500, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 3))
    t = np.ceil(rng.exponential(10 / np.exp(1.2 * x[:, 0] - 0.8 * x[:, 1])))   # discrete times -> ties
    e = rng.random(n) < 0.7
    return x, t, e


def test_boosting_gradient_matches_the_cox_loss_with_ties():
    rng = np.random.default_rng(1)
    n = 30
    f, t, e = rng.normal(size=n), rng.integers(1, 5, n).astype(float), rng.random(n) < 0.6

    def loss(v):
        return float(_neg_partial_loglik(torch.tensor(v), torch.tensor(t), torch.tensor(e, dtype=torch.float64))) * e.sum()

    g, h = _cox_grad_hess(f, t, e)
    num = np.array([(loss(f + 1e-6 * np.eye(n)[i]) - loss(f - 1e-6 * np.eye(n)[i])) / 2e-6 for i in range(n)])
    assert np.allclose(g, num, atol=1e-5)
    assert (h > 0).all()


def test_models_learn_a_known_signal():
    x, t, e = _xy()
    for model in (GradientBoostedCox(n_estimators=100), DeepSurv(epochs=200)):
        m = model.fit(x[:350], t[:350], e[:350])
        assert concordance_index(t[350:], e[350:], m.predict_risk(x[350:])) > 0.65


def test_survival_is_a_probability_that_falls_over_time():
    x, t, e = _xy()
    for model in (GradientBoostedCox(n_estimators=50), DeepSurv(epochs=100)):
        m = model.fit(x, t, e)
        early, late = m.predict_survival(x[:20], 2), m.predict_survival(x[:20], 15)
        assert ((0 <= late) & (late <= early) & (early <= 1)).all()


def test_deepsurv_reproducible_and_survives_save_load():
    x, t, e = _xy(300)
    a = DeepSurv(epochs=80, seed=5).fit(x, t, e)
    b = DeepSurv(epochs=80, seed=5).fit(x, t, e)
    assert np.allclose(a.predict_risk(x), b.predict_risk(x))
    c = pickle.loads(pickle.dumps(a))
    assert np.allclose(a.predict_risk(x), c.predict_risk(x))


def test_choice_prefers_simpler_model_within_margin():
    cv = {n: {"c_index": 0.80} for n in experiment.ORDER}
    cv[experiment.DSV]["c_index"] = 0.805                         # within 0.01: simpler wins
    assert experiment.choose(cv) == experiment.COX_CLIN
    cv[experiment.DSV]["c_index"] = 0.85
    assert experiment.choose(cv) == experiment.DSV


def test_calibration_groups_cover_every_graft():
    rng = np.random.default_rng(2)
    oof = pd.DataFrame({"time": rng.integers(1, 40, 200), "event": rng.random(200) < 0.3,
                        "surv": rng.uniform(0.5, 1, 200)})
    cal = experiment.calibration(oof)
    assert sum(c["n"] for c in cal) == 200 and len(cal) == experiment.CAL_GROUPS
    preds = [c["predicted_risk"] for c in cal]
    assert preds == sorted(preds)                                 # groups ordered by predicted risk


def test_final_model_carries_its_own_preprocessing():
    g, v = simulate(300, seed=7)
    t = landmark_table(g, v)
    t["split"] = split_grafts(t, seed=0).to_numpy()
    fitted = experiment.fit_with_preprocessing(lambda: GradientBoostedCox(n_estimators=30), t, "low_ecd")
    X = fitted["preprocessor"].transform(t.iloc[:5])[fitted["features"]].to_numpy()
    s = fitted["model"].predict_survival(X, 24)
    assert len(s) == 5 and ((0 <= s) & (s <= 1)).all()


def test_rejection_coefficient_cannot_be_protective():
    from recommendation.risk.cox import CoxPH

    rng = np.random.default_rng(9)
    x = rng.normal(size=(300, 2))
    x[:, 1] = (rng.random(300) < 0.05).astype(float)          # rare rejection flag
    t = rng.exponential(1 / np.exp(x[:, 0] - 1.5 * x[:, 1]))  # data suggest a protective effect
    e = np.ones(300, bool)
    free = CoxPH(penalty=0.01).fit(x, t, e)
    bounded = CoxPH(penalty=0.01, features=["ECD_12m", "rejection_by_12m"]).fit(x, t, e)
    assert free.coef[1] < 0 and bounded.coef[1] >= 0


def test_isotonic_recalibration_keeps_ranking_and_moves_risk_towards_observed():
    from recommendation.risk.cox import CoxPH

    x, t, e = _xy(800, seed=4)
    base = CoxPH(penalty=50.0).fit(x[:400], t[:400], e[:400])          # heavy shrinkage -> miscalibrated
    oof = pd.DataFrame({"time": t[400:], "event": e[400:], "surv": base.predict_survival(x[400:], 10),
                        "lp": base.predict_risk(x[400:])})
    model = experiment.Recalibrated(base, experiment.risk_maps({10: oof}))
    assert np.array_equal(np.argsort(model.predict_risk(x)), np.argsort(base.predict_risk(x)))
    s_b, s_m = base.predict_survival(x[400:], 10), model.predict_survival(x[400:], 10)
    assert ((0 <= s_m) & (s_m <= 1)).all()
    assert np.all(np.diff((1 - s_m)[np.argsort(1 - s_b)]) >= -1e-12)    # monotone in the original risk
    gap = lambda s: experiment.calibration_gap(experiment.calibration(oof.assign(surv=s)))  # noqa: E731
    assert gap(s_m) <= gap(s_b)
