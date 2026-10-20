"""P6: explanations for the chosen post-transplant models (trajectory and risk).

  Why this prediction?
    trajectory   SHAP values of the gradient-boosting model for the 60-month ECD
                 prediction (log-ratio scale), summed into clinical reasons and shown as
                 the % change each reason makes to the predicted ECD
    risk         for the Cox model SHAP is exact: coefficient x (input - population mean);
                 summed into the same reasons and shown as hazard ratios

  What would change it? (counterfactuals, descriptive)
    the smallest change in the 12-month ECD (derived inputs recomputed) or the absence of
    a rejection episode that would bring the 24-month risk under its alert threshold, or
    keep the 60-month ECD at or above 1000. These describe the model; the 12-month ECD is
    a measurement, not something a clinician can set, so they are not treatment advice.

  Sanity checks
    explanations add up to the prediction; higher 12-month ECD -> higher predicted ECD and
    lower risk; counterfactuals really cross the threshold when applied.
"""
import numpy as np
import pandas as pd

from recommendation.data_prep.followup_dataset import add_derived

RISK_TAU = 24                                   # months after the 12-month visit
RISK_THRESHOLDS = {"graft_failure": 0.10, "low_ecd": 0.30}
TARGET_ECD_60 = 1000
ECD_STEP, ECD_MAX_STEPS = 100, 15
REASONS = ["12-month ECD", "early cell loss", "cell shape (CV/HEX)", "donor", "procedure", "indication",
           "rejection", "missed visit"]


def reason_of(feature: str) -> str | None:
    if feature.endswith("_missing"):
        return "missed visit"
    if feature == "years_ahead":
        return None
    if feature.startswith("ECD_12m"):
        return "12-month ECD"
    if feature in ("loss_12m", "log_ecd_slope_3_12") or feature.startswith(("ECD_3m", "ECD_6m")):
        return "early cell loss"
    if feature.startswith(("CV_", "HEX_", "baseline_CV", "baseline_HEX")):
        return "cell shape (CV/HEX)"
    if feature in ("donor_age", "baseline_ECD"):
        return "donor"
    if feature.startswith("procedure="):
        return "procedure"
    if feature.startswith("indication="):
        return "indication"
    if feature == "rejection_by_12m":
        return "rejection"
    return None


def _group(values: pd.DataFrame) -> pd.DataFrame:
    """Sum per-feature contributions into clinical reasons."""
    cols = {c: reason_of(c) for c in values.columns}
    out = pd.DataFrame(0.0, index=values.index, columns=REASONS)
    for c, r in cols.items():
        if r:
            out[r] += values[c]
    return out


# ---------------------------------------------------------------- trajectory (gradient boosting)
def _trajectory_X(model, t: pd.DataFrame, horizon: int = 60) -> pd.DataFrame:
    return model.pre.transform(t).assign(years_ahead=(horizon - 12) / 12)


def trajectory_shap(model, t: pd.DataFrame, horizon: int = 60) -> dict:
    import shap

    X = _trajectory_X(model, t, horizon)
    explainer = shap.TreeExplainer(model.model.booster_)
    phi = pd.DataFrame(explainer.shap_values(X), index=t.index, columns=X.columns)
    raw = model.model.predict(X, raw_score=True)
    base = float(np.ravel(explainer.expected_value)[0])
    return {"phi": phi, "reasons": _group(phi), "base": base, "raw": raw,
            "additivity_error": float(np.abs(base + phi.sum(axis=1) - raw).max())}


def predicted_ecd(model, t: pd.DataFrame, horizon: int = 60) -> pd.Series:
    return model.predict(t)[f"ECD_{horizon}m"]


# ---------------------------------------------------------------- risk (Cox)
def risk_scores(fitted: dict, t: pd.DataFrame) -> pd.DataFrame:
    return fitted["preprocessor"].transform(t)[fitted["features"]]


def risk_contributions(fitted: dict, t: pd.DataFrame, reference: pd.DataFrame) -> dict:
    """Exact SHAP for a linear Cox model: coef * (x - mean of the reference population)."""
    X, ref = risk_scores(fitted, t), risk_scores(fitted, reference).mean()
    coef = pd.Series(fitted["model"].coef, index=fitted["features"])
    phi = (X - ref) * coef
    lp = X.to_numpy() @ coef.to_numpy()
    return {"phi": phi, "reasons": _group(phi), "base": float(ref.to_numpy() @ coef.to_numpy()),
            "additivity_error": float(np.abs(phi.sum(axis=1) + ref.to_numpy() @ coef.to_numpy() - lp).max())}


def risk_at(fitted: dict, t: pd.DataFrame, tau: float = RISK_TAU) -> np.ndarray:
    return 1 - fitted["model"].predict_survival(risk_scores(fitted, t).to_numpy(), tau)


# ---------------------------------------------------------------- counterfactuals
def _with_ecd12(row: pd.DataFrame, ecd12: float) -> pd.DataFrame:
    r = row.copy()
    r["ECD_12m"] = ecd12
    return add_derived(r)


def risk_counterfactual(fitted: dict, row: pd.DataFrame, endpoint: str) -> dict:
    thr = RISK_THRESHOLDS[endpoint]
    now = float(risk_at(fitted, row)[0])
    if now <= thr:
        return {"risk_now": now, "threshold": thr, "text": None}
    options = []
    ecd = float(row["ECD_12m"].iloc[0])
    for k in range(1, ECD_MAX_STEPS + 1):
        new = _with_ecd12(row, ecd + k * ECD_STEP)
        r = float(risk_at(fitted, new)[0])
        if r <= thr:
            options.append((f"12-month ECD {ecd + k * ECD_STEP:.0f} instead of {ecd:.0f}", r))
            break
    if float(row["rejection_by_12m"].iloc[0]) == 1:
        new = row.copy()
        new["rejection_by_12m"] = 0.0
        r = float(risk_at(fitted, new)[0])
        if r <= thr:
            options.append(("no rejection episode by 12 months", r))
    text = ("; or ".join(f"{o} (risk {r:.0%})" for o, r in options) if options
            else f"no single realistic change brings it under {thr:.0%}")
    return {"risk_now": now, "threshold": thr, "options": options,
            "text": f"risk would be under {thr:.0%} with: {text} [descriptive]"}


def trajectory_counterfactual(model, row: pd.DataFrame) -> dict:
    now = float(predicted_ecd(model, row).iloc[0])
    if now >= TARGET_ECD_60:
        return {"ecd60_now": now, "text": None}
    ecd = float(row["ECD_12m"].iloc[0])
    for k in range(1, ECD_MAX_STEPS + 1):
        new = _with_ecd12(row, ecd + k * ECD_STEP)
        p = float(predicted_ecd(model, new).iloc[0])
        if p >= TARGET_ECD_60:
            return {"ecd60_now": now, "text": f"60-month ECD would reach {TARGET_ECD_60} if the 12-month ECD were "
                                              f"{ecd + k * ECD_STEP:.0f} instead of {ecd:.0f} [descriptive]"}
    return {"ecd60_now": now, "text": f"no 12-month ECD within +{ECD_STEP * ECD_MAX_STEPS} keeps it at {TARGET_ECD_60}"}


# ---------------------------------------------------------------- sanity checks
def sanity_checks(traj_model, risk_models: dict, table: pd.DataFrame, traj_expl: dict, risk_expl: dict) -> list:
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("trajectory explanation adds up to the prediction", traj_expl["additivity_error"] < 1e-6,
        f"max error {traj_expl['additivity_error']:.1e}")
    for ep, e in risk_expl.items():
        add(f"{ep}: risk explanation adds up to the prediction", e["additivity_error"] < 1e-9,
            f"max error {e['additivity_error']:.1e}")
    higher = table.copy()
    higher["ECD_12m"] = higher["ECD_12m"] + 200
    add_derived(higher)
    up = (predicted_ecd(traj_model, higher) > predicted_ecd(traj_model, table)).mean()
    add("higher 12-month ECD -> higher predicted 60-month ECD", up >= 0.9, f"{up:.0%} of grafts")
    for ep, fitted in risk_models.items():
        rows = table if ep != "low_ecd" else table[~table["low_ecd_before_landmark"].astype(bool)]
        hi = higher.loc[rows.index]
        down = (risk_at(fitted, hi) <= risk_at(fitted, rows)).mean()
        add(f"{ep}: higher 12-month ECD -> lower risk", down >= 0.9, f"{down:.0%} of grafts")
        rej = rows.copy()
        rej["rejection_by_12m"] = 1.0
        more = (risk_at(fitted, rej) >= risk_at(fitted, rows.assign(rejection_by_12m=0.0))).mean()
        add(f"{ep}: rejection episode -> higher risk", more >= 0.9,
            f"{more:.0%} of grafts (only {int(table['rejection_by_12m'].sum())} grafts had rejection by 12 months)")
    return checks


# ---------------------------------------------------------------- run
def run(table: pd.DataFrame, traj: dict, risk: dict, n_examples: int = 3) -> dict:
    traj_model, risk_models = traj["model"], {ep: f for ep, f in risk["models"].items()}
    t_expl = trajectory_shap(traj_model, table)
    r_expl = {ep: risk_contributions(f, fe_rows(table, ep), fe_rows(table, ep)) for ep, f in risk_models.items()}

    global_imp = {"trajectory_60m_ECD": (t_expl["reasons"].abs().mean()).round(4).to_dict()}
    for ep, e in r_expl.items():
        global_imp[f"risk_{ep}"] = (e["reasons"].abs().mean()).round(4).to_dict()

    # examples from the test grafts: highest failure risk, a middle one, and one with a rejection
    test = table[table["split"] == "test"]
    fail = risk_models["graft_failure"]
    r_test = pd.Series(risk_at(fail, test), index=test.index).sort_values()
    picks = [r_test.index[-1], r_test.index[len(r_test) // 2]]
    rej = test.index[test["rejection_by_12m"] == 1]
    picks += [i for i in rej if i not in picks][:1]
    examples = [example(table.loc[[i]], traj_model, risk_models, t_expl, r_expl) for i in picks[:n_examples]]

    checks = sanity_checks(traj_model, risk_models, table, t_expl, r_expl)
    return {"global_importance": global_imp, "examples": examples, "checks": checks,
            "all_checks_pass": all(c["ok"] for c in checks), "risk_thresholds_24m": RISK_THRESHOLDS,
            "trajectory_model": traj["name"], "risk_models": {ep: f["name"] for ep, f in risk_models.items()}}


def fe_rows(table: pd.DataFrame, endpoint: str) -> pd.DataFrame:
    from recommendation.evaluation.followup_eval import endpoint_rows

    return endpoint_rows(table, endpoint)


def example(row: pd.DataFrame, traj_model, risk_models: dict, t_expl: dict, r_expl: dict) -> dict:
    i = row.index[0]
    ecd60 = float(predicted_ecd(traj_model, row).iloc[0])
    tr = t_expl["reasons"].loc[i]
    top_t = tr.reindex(tr.abs().sort_values(ascending=False).index)[:3]
    out = {"graft": str(row["graft_id"].iloc[0]), "procedure": str(row["procedure"].iloc[0]),
           "ECD_12m": float(row["ECD_12m"].iloc[0]), "predicted_ECD_60m": round(ecd60),
           "why_trajectory": "; ".join(f"{k} ({np.exp(v) - 1:+.0%} on ECD)" for k, v in top_t.items() if abs(v) > 0.005),
           "trajectory_counterfactual": trajectory_counterfactual(traj_model, row)["text"]}
    for ep, fitted in risk_models.items():
        if ep == "low_ecd" and bool(row["low_ecd_before_landmark"].iloc[0]):
            out[ep] = {"note": "already below 1000 by 12 months"}
            continue
        reasons = r_expl[ep]["reasons"]
        rr = reasons.loc[i] if i in reasons.index else pd.Series(dtype=float)
        top = rr.reindex(rr.abs().sort_values(ascending=False).index)[:3]
        cf = risk_counterfactual(fitted, row, ep)
        out[ep] = {"risk_24m": round(cf["risk_now"], 3),
                   "why": "; ".join(f"{k} (hazard x{np.exp(v):.2f})" for k, v in top.items() if abs(v) > 0.01),
                   "counterfactual": cf["text"]}
    return out
