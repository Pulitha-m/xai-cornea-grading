"""Shared evaluation for the post-transplant models (P3 baselines, P4 trajectory, P5 risk).

Every model is scored the same way, so results are comparable across steps:
  validation     fit on the training grafts, score on the validation grafts
  repeated CV    5-fold CV repeated over training + validation grafts (stratified by
                 failure), because the validation set alone has few failures
The test grafts are not used here; they are scored once, for the chosen models only.

Preprocessing is refitted inside every training fold, so no fold sees statistics from
the grafts it is scored on.
"""
import numpy as np
import pandas as pd

from recommendation.data_prep.followup_dataset import FollowupPreprocessor
from recommendation.evaluation.survival import (brier_score, censoring_km, concordance_index,
                                                cumulative_dynamic_auc, kaplan_meier, survival_at)
from recommendation.trajectory.baselines import forecast_errors

RISK_TIMES = (12, 24, 36)          # months after the 12-month landmark (= 24, 36, 48 after surgery)
BRIER_TIME = 24
ENDPOINTS = {
    "graft_failure": ("failure_months_after_landmark", "failure_event"),
    "low_ecd": ("low_ecd_months_after_landmark", "low_ecd_event"),
}


def endpoint_rows(table: pd.DataFrame, endpoint: str) -> pd.DataFrame:
    """Grafts at risk for an endpoint (low ECD excludes grafts that already had it by month 12)."""
    if endpoint == "low_ecd":
        return table[~table["low_ecd_before_landmark"].astype(bool)]
    return table


def folds(table: pd.DataFrame, k: int = 5, repeats: int = 5, seed: int = 42):
    """(repeat, train_index, test_index) for repeated stratified K-fold by graft."""
    strata = table["failure_event"].astype(int).to_numpy()
    for rep in range(repeats):
        rng = np.random.default_rng(seed + rep)
        fold_of = np.empty(len(table), dtype=int)
        for s in np.unique(strata):
            idx = np.where(strata == s)[0]
            rng.shuffle(idx)
            fold_of[idx] = np.arange(len(idx)) % k
        for f in range(k):
            yield rep, table.index[fold_of != f], table.index[fold_of == f]


# ---------------------------------------------------------------- trajectory
def score_trajectory(model_factory, train: pd.DataFrame, test: pd.DataFrame) -> dict:
    model = model_factory().fit(train)
    return forecast_errors(test, model.predict(test))


def cv_trajectory(model_factory, table: pd.DataFrame, k=5, repeats=5, seed=42) -> dict:
    rows = [score_trajectory(model_factory, table.loc[tr], table.loc[te]) for _, tr, te in folds(table, k, repeats, seed)]
    keys = rows[0].keys()
    return {key: {"mae": float(np.nanmean([r[key]["mae"] for r in rows])),
                  "rmse": float(np.nanmean([r[key]["rmse"] for r in rows])),
                  "mae_sd": float(np.nanstd([r[key]["mae"] for r in rows]))} for key in keys}


# ---------------------------------------------------------------- risk
class KaplanMeierRisk:
    """No-input baseline: every graft gets the training Kaplan-Meier curve."""
    name = "Kaplan-Meier (no inputs)"
    uses_features = False

    def fit(self, X, time, event):
        self.km = kaplan_meier(time, event)
        return self

    def predict_risk(self, X):
        return np.zeros(len(X))

    def predict_survival(self, X, tau):
        return np.full(len(X), survival_at(self.km, tau))


def score_risk(model_factory, train: pd.DataFrame, test: pd.DataFrame, endpoint: str, features=None) -> dict:
    tcol, ecol = ENDPOINTS[endpoint]
    train, test = endpoint_rows(train, endpoint), endpoint_rows(test, endpoint)
    pre = FollowupPreprocessor().fit(train)
    cols = features or pre.feature_names
    Xtr, Xte = pre.transform(train)[cols].to_numpy(), pre.transform(test)[cols].to_numpy()
    model = model_factory()
    model.features = list(cols)                     # lets models apply clinical sign constraints
    model.fit(Xtr, train[tcol], train[ecol].astype(bool))
    t, e = test[tcol].to_numpy(), test[ecol].astype(bool).to_numpy()
    risk = model.predict_risk(Xte)
    g = censoring_km(train[tcol], train[ecol].astype(bool))
    out = {"n": int(len(test)), "events": int(e.sum()), "c_index": concordance_index(t, e, risk)}
    for tau in RISK_TIMES:
        out[f"auc_{tau}m"] = cumulative_dynamic_auc(t, e, risk, tau, g)
    out[f"brier_{BRIER_TIME}m"] = brier_score(t, e, model.predict_survival(Xte, BRIER_TIME), BRIER_TIME, g)
    return out


def cv_risk(model_factory, table: pd.DataFrame, endpoint: str, features=None, k=5, repeats=5, seed=42) -> dict:
    rows = [score_risk(model_factory, table.loc[tr], table.loc[te], endpoint, features)
            for _, tr, te in folds(table, k, repeats, seed)]
    keys = [k_ for k_ in rows[0] if k_ not in ("n", "events")]
    out = {key: float(np.nanmean([r[key] for r in rows])) for key in keys}
    out["c_index_sd"] = float(np.nanstd([r["c_index"] for r in rows]))
    return out
