"""P5 experiment: compare risk models for graft failure and low ECD, pick one each, test once.

Order (each step only uses the data it is allowed to):
  1. tuning         Cox ridge penalties and gradient-boosting settings chosen by repeated CV
                    on training grafts only (DeepSurv uses fixed, documented settings and
                    early stopping inside its own training data)
  2. comparison     Cox (clinical inputs), Cox (all inputs), gradient-boosted Cox and
                    DeepSurv scored by the same 5x repeated 5-fold CV over training +
                    validation grafts; Kaplan-Meier (no inputs) as the floor
  3. choice         highest CV C-index; a simpler model within 0.01 wins (simplest first)
  4. test           chosen model and the clinical Cox model fitted on training + validation,
                    scored once on the untouched test grafts
  5. calibration    out-of-fold predicted 24-month risk vs observed (Kaplan-Meier) risk in
                    five groups of predicted risk
  6. recalibration  the calibration slope of the out-of-fold score is reported (1 = well
                    scaled). The risk percentages are then corrected by a monotone (isotonic)
                    map from predicted to observed (Kaplan-Meier) risk at 12 / 24 / 36 months,
                    learnt from out-of-fold predictions on training + validation grafts in ten
                    risk groups. The map never changes the ranking, so C-index and SHAP reasons
                    are unchanged. Checked before / after on the test grafts and on a separate
                    simulated cohort of 3,000 grafts (enough events)
  7. final models   refitted on all grafts with their preprocessing and recalibration, saved
"""
import numpy as np
import pandas as pd

from recommendation.data_prep.followup_dataset import FollowupPreprocessor
from recommendation.evaluation import followup_eval as fe
from recommendation.evaluation.survival import kaplan_meier, survival_at
from recommendation.risk.cox import CoxPH
from recommendation.risk.models import DeepSurv, GradientBoostedCox

# Clinical inputs for the small Cox model (procedure PK is the reference level).
COX_CLINICAL = ["ECD_12m", "loss_12m", "log_ecd_slope_3_12", "rejection_by_12m", "donor_age",
                "procedure=DMEK", "procedure=DSEK"]
COX_PENALTIES = (0.1, 1.0, 10.0)
GBC_GRID = [dict(num_leaves=4, n_estimators=100), dict(num_leaves=4, n_estimators=250),
            dict(num_leaves=7, n_estimators=150)]
TIE_MARGIN = 0.01
EXTERNAL_COHORT = (3000, 202)          # size and seed of the separate simulated check cohort
CAL_TIME = 24
CAL_GROUPS = 5

COX_CLIN, COX_ALL, GBC, DSV = ("Cox, clinical inputs", "Cox, all inputs", GradientBoostedCox.name, DeepSurv.name)
ORDER = [COX_CLIN, COX_ALL, GBC, DSV]          # simplest first


def tune(train: pd.DataFrame, seed: int = 42) -> dict:
    """Settings chosen on training grafts only (graft-failure endpoint)."""
    def best(options, factory, feats):
        scores = {i: fe.cv_risk(lambda o=o: factory(o), train, "graft_failure", feats, repeats=2, seed=seed)["c_index"]
                  for i, o in enumerate(options)}
        return options[max(scores, key=scores.get)]

    return {"cox_clinical_penalty": best(list(COX_PENALTIES), lambda p: CoxPH(penalty=p), COX_CLINICAL),
            "cox_all_penalty": best(list(COX_PENALTIES), lambda p: CoxPH(penalty=p), None),
            "gbc": best(GBC_GRID, lambda p: GradientBoostedCox(**p, seed=seed), None)}


def candidates(settings: dict, seed: int = 42) -> dict:
    """name -> (factory, feature list or None for all inputs)."""
    return {COX_CLIN: (lambda: CoxPH(penalty=settings["cox_clinical_penalty"]), COX_CLINICAL),
            COX_ALL: (lambda: CoxPH(penalty=settings["cox_all_penalty"]), None),
            GBC: (lambda: GradientBoostedCox(**settings["gbc"], seed=seed), None),
            DSV: (lambda: DeepSurv(seed=seed), None)}


def choose(cv: dict) -> str:
    best = max(cv[n]["c_index"] for n in ORDER)
    return next(n for n in ORDER if cv[n]["c_index"] >= best - TIE_MARGIN)


def fit_with_preprocessing(factory, rows: pd.DataFrame, endpoint: str, features=None) -> dict:
    """Preprocessor + model fitted on the given grafts (used for test fits and final models)."""
    tcol, ecol = fe.ENDPOINTS[endpoint]
    rows = fe.endpoint_rows(rows, endpoint)
    pre = FollowupPreprocessor().fit(rows)
    cols = features or pre.feature_names
    model = factory()
    model.features = list(cols)
    model.fit(pre.transform(rows)[cols].to_numpy(), rows[tcol], rows[ecol].astype(bool))
    return {"preprocessor": pre, "features": cols, "model": model, "endpoint": endpoint}


def oof_survival(factory, table: pd.DataFrame, endpoint: str, features=None, tau=CAL_TIME, seed=42) -> pd.DataFrame:
    """Out-of-fold S(tau) for every graft (one repeat of 5-fold CV)."""
    tcol, ecol = fe.ENDPOINTS[endpoint]
    rows = fe.endpoint_rows(table, endpoint)
    parts = []
    for _, tr, te in fe.folds(rows, k=5, repeats=1, seed=seed):
        fitted = fit_with_preprocessing(factory, rows.loc[tr], endpoint, features)
        X = fitted["preprocessor"].transform(rows.loc[te])[fitted["features"]].to_numpy()
        parts.append(pd.DataFrame({"time": rows.loc[te, tcol], "event": rows.loc[te, ecol].astype(bool),
                                   "surv": fitted["model"].predict_survival(X, tau),
                                   "lp": fitted["model"].predict_risk(X)}, index=te))
    return pd.concat(parts)


def calibration(oof: pd.DataFrame, tau=CAL_TIME, groups=CAL_GROUPS) -> list[dict]:
    """Predicted vs Kaplan-Meier observed risk by tau, in groups of predicted risk."""
    risk = 1 - oof["surv"]
    bins = pd.qcut(risk.rank(method="first"), groups, labels=False)
    rows = []
    for g in range(groups):
        sel = oof[bins == g]
        km = kaplan_meier(sel["time"], sel["event"])
        rows.append({"group": g + 1, "n": int(len(sel)), "events": int(sel["event"].sum()),
                     "predicted_risk": float((1 - sel["surv"]).mean()),
                     "observed_risk": float(1 - survival_at(km, tau))})
    return rows


RECAL_GROUPS = 10


class Recalibrated:
    """A fitted risk model whose risk percentages pass through a monotone map per time point
    (predicted -> observed). The score (predict_risk) and its coefficients are unchanged."""

    def __init__(self, base, maps: dict):
        self.base, self.maps = base, maps            # tau -> (x points, y points), increasing
        self.features = getattr(base, "features", [])

    @property
    def coef(self):                                  # linear models: exact SHAP still works
        return np.asarray(self.base.coef)

    def predict_risk(self, X):
        return self.base.predict_risk(X)

    def predict_survival(self, X, tau):
        s = self.base.predict_survival(X, tau)
        if tau not in self.maps:
            return s
        x, y = self.maps[tau]
        return 1 - np.interp(1 - s, x, y)


def risk_maps(oof_by_tau: dict) -> dict:
    """Isotonic map from predicted to Kaplan-Meier observed risk for each time point."""
    from sklearn.isotonic import IsotonicRegression

    maps = {}
    for tau, oof in oof_by_tau.items():
        cal = calibration(oof, tau, RECAL_GROUPS)
        px = np.array([0.0] + [c["predicted_risk"] for c in cal] + [1.0])
        py = np.array([0.0] + [c["observed_risk"] for c in cal] + [1.0])
        w = np.array([1.0] + [c["n"] for c in cal] + [1.0])
        iso = IsotonicRegression(y_min=0, y_max=1, increasing=True).fit(px, py, sample_weight=w)
        maps[tau] = (px.tolist(), iso.predict(px).tolist())
    return maps


def calibration_slope(oof: pd.DataFrame) -> float:
    """Unpenalised one-input Cox model of the out-of-fold score: ideal value 1."""
    m = CoxPH(penalty=1e-6).fit(oof[["lp"]].to_numpy(), oof["time"], oof["event"])
    return float(m.coef[0])


def recalibrate(fitted: dict, maps: dict) -> dict:
    return {**fitted, "model": Recalibrated(fitted["model"], maps), "uncalibrated_model": fitted["model"]}


def _calibration_on(fitted: dict, rows: pd.DataFrame) -> list:
    tcol, ecol = fe.ENDPOINTS[fitted["endpoint"]]
    rows = fe.endpoint_rows(rows, fitted["endpoint"])
    X = fitted["preprocessor"].transform(rows)[fitted["features"]].to_numpy()
    oof = pd.DataFrame({"time": rows[tcol], "event": rows[ecol].astype(bool),
                        "surv": fitted["model"].predict_survival(X, CAL_TIME)})
    return calibration(oof)


def calibration_gap(cal: list) -> float:
    """Mean absolute gap between predicted and observed risk across the groups."""
    return float(np.mean([abs(c["predicted_risk"] - c["observed_risk"]) for c in cal]))


def external_cohort():
    from recommendation.data_prep.followup_dataset import landmark_table
    from recommendation.data_prep.followup_simulator import simulate

    g, v = simulate(*EXTERNAL_COHORT)
    return landmark_table(g, v)


def run(table: pd.DataFrame, seed: int = 42) -> dict:
    train = table[table["split"] == "train"]
    dev = table[table["split"] != "test"]
    test = table[table["split"] == "test"]
    settings = tune(train, seed)
    cands = candidates(settings, seed)
    ext = external_cohort()

    results, finals = {}, {}
    for endpoint in fe.ENDPOINTS:
        cv = {"Kaplan-Meier (no inputs)": fe.cv_risk(fe.KaplanMeierRisk, dev, endpoint, seed=seed)}
        cv.update({n: fe.cv_risk(f, dev, endpoint, feats, seed=seed) for n, (f, feats) in cands.items()})
        chosen = choose(cv)
        test_scores = {n: fe.score_risk(cands[n][0], dev, test, endpoint, cands[n][1])
                       for n in dict.fromkeys([chosen, COX_CLIN])}
        factory, feats = cands[chosen]
        oof_by_tau = {tau: oof_survival(factory, dev, endpoint, feats, tau=tau, seed=seed) for tau in fe.RISK_TIMES}
        oof = oof_by_tau[CAL_TIME]
        cal = calibration(oof)
        slope = calibration_slope(oof)
        maps = risk_maps(oof_by_tau)

        # before / after recalibration, model fitted on training + validation grafts
        dev_fit = fit_with_preprocessing(factory, dev, endpoint, feats)
        dev_recal = recalibrate(dev_fit, maps)
        recal = {"slope": slope}
        for where, rows in (("test", test), ("external_simulated_cohort", ext)):
            before, after = _calibration_on(dev_fit, rows), _calibration_on(dev_recal, rows)
            recal[where] = {"gap_before": calibration_gap(before), "gap_after": calibration_gap(after),
                            "before": before, "after": after}

        final = fit_with_preprocessing(factory, table, endpoint, feats)
        finals[endpoint] = {"name": chosen, **recalibrate(final, maps)}
        results[endpoint] = {"cv": cv, "chosen": chosen, "test": test_scores, "calibration_24m": cal,
                             "recalibration": recal}
    return {"settings": settings, "tie_margin": TIE_MARGIN, "endpoints": results,
            "risk_times_after_landmark": list(fe.RISK_TIMES), "final_models": finals}
