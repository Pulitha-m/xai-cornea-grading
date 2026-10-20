"""P4 experiment: compare trajectory models, pick one, test it once, save it.

Order (each step only uses the data it is allowed to):
  1. tuning         gradient-boosting settings chosen by repeated CV on training grafts only
  2. comparison     every model (4 baselines, gradient boosting, LSTM) scored by the same
                    5x repeated 5-fold CV over training + validation grafts
  3. learning curve each model trained on 50 ... 2,000 grafts from a separate, larger
                    simulated cohort and scored on 1,500 held-out grafts of that cohort:
                    how much data does each model need?
  4. choice         lowest CV error; a simpler model wins if it is within 2% (simplest first)
  5. test           the chosen model and the best baseline are fitted on training +
                    validation grafts and scored once on the untouched test grafts
  6. uncertainty    an 80% band from out-of-fold CV residuals (split-conformal style),
                    with its coverage checked on the test grafts
  7. final model    refitted on all grafts and saved for P6-P8
"""
import numpy as np
import pandas as pd

from recommendation.data_prep.followup_dataset import HORIZONS, landmark_table
from recommendation.evaluation import followup_eval as fe
from recommendation.trajectory.baselines import (LastValue, MixedEffects, OwnTrendDecay, PopulationDecay,
                                                 forecast_errors)
from recommendation.trajectory.models import GradientBoosting, LSTMTrajectory

# simplest first: used to break near-ties in favour of the simpler model
ORDER = [LastValue, PopulationDecay, OwnTrendDecay, MixedEffects, GradientBoosting, LSTMTrajectory]
GBM_GRID = [dict(num_leaves=4, n_estimators=200), dict(num_leaves=7, n_estimators=300),
            dict(num_leaves=15, n_estimators=300)]
TIE_MARGIN = 0.02
CURVE_SIZES = (50, 100, 250, 500, 1000, 2000)
BAND = (0.10, 0.90)


def tune_gbm(train: pd.DataFrame, seed: int = 42) -> dict:
    scores = {}
    for i, params in enumerate(GBM_GRID):
        res = fe.cv_trajectory(lambda p=params: GradientBoosting(**p, seed=seed), train, repeats=2, seed=seed)
        scores[i] = res["all"]["mae"]
    best = min(scores, key=scores.get)
    return {"selected": GBM_GRID[best], "cv_mae_by_setting": {str(GBM_GRID[i]): round(v, 1) for i, v in scores.items()}}


def factories(gbm_params: dict, seed: int = 42) -> dict:
    return {LastValue.name: LastValue, PopulationDecay.name: PopulationDecay, OwnTrendDecay.name: OwnTrendDecay,
            MixedEffects.name: MixedEffects,
            GradientBoosting.name: lambda: GradientBoosting(**gbm_params, seed=seed),
            LSTMTrajectory.name: lambda: LSTMTrajectory(seed=seed)}


def choose(cv: dict) -> str:
    """Lowest CV MAE; a simpler model within TIE_MARGIN of the best is preferred."""
    best = min(cv.values(), key=lambda r: r["all"]["mae"])["all"]["mae"]
    for cls in ORDER:
        if cv[cls.name]["all"]["mae"] <= best * (1 + TIE_MARGIN):
            return cls.name
    raise RuntimeError("no model chosen")


def oof_log_residuals(factory, table: pd.DataFrame, seed: int = 42) -> np.ndarray:
    """Out-of-fold log(true / predicted) per horizon (one repeat of 5-fold CV)."""
    res = {h: [] for h in HORIZONS}
    for _, tr, te in fe.folds(table, k=5, repeats=1, seed=seed):
        pred = factory().fit(table.loc[tr]).predict(table.loc[te])
        for h in HORIZONS:
            r = np.log(table.loc[te, f"ECD_{h}m"] / pred[f"ECD_{h}m"]).dropna()
            res[h].extend(r.tolist())
    return {h: np.array(v) for h, v in res.items()}


def band_from_residuals(resid: dict) -> dict:
    return {h: (float(np.quantile(r, BAND[0])), float(np.quantile(r, BAND[1]))) for h, r in resid.items()}


def band_coverage(table: pd.DataFrame, pred: pd.DataFrame, band: dict) -> dict:
    out = {}
    for h in HORIZONS:
        y = table[f"ECD_{h}m"]
        ok = y.notna()
        lo, hi = pred[f"ECD_{h}m"] * np.exp(band[h][0]), pred[f"ECD_{h}m"] * np.exp(band[h][1])
        out[f"{h}m"] = {"n": int(ok.sum()),
                        "coverage": float(((y[ok] >= lo[ok]) & (y[ok] <= hi[ok])).mean()) if ok.any() else float("nan")}
    return out


def learning_curve(facts: dict, n_cohort: int = 6000, n_eval: int = 1500, repeats: int = 2, seed: int = 101) -> list:
    """Train on growing subsets of a separate simulated cohort, score on its held-out grafts."""
    from recommendation.data_prep.followup_simulator import simulate

    g, v = simulate(n_cohort, seed=seed)
    big = landmark_table(g, v).reset_index(drop=True)
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(big))
    evaluation, pool = big.iloc[order[:n_eval]], big.iloc[order[n_eval:]]
    rows = []
    for n in CURVE_SIZES:
        if n > len(pool):
            break
        for rep in range(repeats):
            sub = pool.sample(n, random_state=seed + rep)
            for name, f in facts.items():
                if name == LastValue.name:
                    continue
                err = forecast_errors(evaluation, f().fit(sub).predict(evaluation))
                rows.append({"train_grafts": n, "repeat": rep, "model": name, "mae_all": err["all"]["mae"],
                             "mae_60m": err["60m"]["mae"]})
    return rows


def run(table: pd.DataFrame, seed: int = 42, with_curve: bool = True) -> dict:
    train = table[table["split"] == "train"]
    dev = table[table["split"] != "test"]
    test = table[table["split"] == "test"]

    tuning = tune_gbm(train, seed)
    facts = factories(tuning["selected"], seed)
    cv = {name: fe.cv_trajectory(f, dev, seed=seed) for name, f in facts.items()}
    chosen = choose(cv)
    best_baseline = min((c.name for c in ORDER[:4]), key=lambda n: cv[n]["all"]["mae"])

    resid = oof_log_residuals(facts[chosen], dev, seed)
    band = band_from_residuals(resid)
    test_scores = {}
    for name in dict.fromkeys([chosen, best_baseline]):
        model = facts[name]().fit(dev)
        pred = model.predict(test)
        test_scores[name] = {"errors": forecast_errors(test, pred)}
        if name == chosen:
            test_scores[name]["band_coverage"] = band_coverage(test, pred, band)

    final = facts[chosen]().fit(table)          # all grafts, for the app (after the test is done)
    curve = learning_curve(facts, seed=seed + 59) if with_curve else []
    return {"tuning": tuning, "cv": cv, "chosen": chosen, "best_baseline": best_baseline,
            "tie_margin": TIE_MARGIN, "test": test_scores, "band_log_residual_quantiles": band,
            "band_level": f"{int(BAND[0] * 100)}-{int(BAND[1] * 100)}%", "learning_curve": curve,
            "final_model": final}
