"""Survival-analysis helpers: Kaplan-Meier estimate and log-rank test.

Small, dependency-free versions (numpy + scipy) so the follow-up EDA (P1) and the risk
models (P5) use the same, tested code.

Times are in months. ``event`` is True when the event (e.g. graft failure) was observed
and False when the graft was censored (lost to follow-up or still functioning at the
data cutoff). A graft censored at the same time as an event is still counted at risk at
that time (the usual convention).
"""
import numpy as np
import pandas as pd
from scipy.stats import chi2


def kaplan_meier(time, event) -> pd.DataFrame:
    """Kaplan-Meier survival with a 95% pointwise interval (Greenwood variance).

    Returns one row per distinct event time (plus time 0): time, at_risk, events,
    survival, lower, upper.
    """
    t = np.asarray(time, dtype=float)
    e = np.asarray(event, dtype=bool)
    if len(t) != len(e):
        raise ValueError("time and event must have the same length")
    rows = [{"time": 0.0, "at_risk": int(len(t)), "events": 0, "survival": 1.0, "lower": 1.0, "upper": 1.0}]
    s, greenwood = 1.0, 0.0
    for u in np.unique(t[e]):
        n = int((t >= u).sum())
        d = int(((t == u) & e).sum())
        s *= 1 - d / n
        if n > d:
            greenwood += d / (n * (n - d))
        se = s * np.sqrt(greenwood)
        rows.append({"time": float(u), "at_risk": n, "events": d, "survival": s,
                     "lower": max(0.0, s - 1.96 * se), "upper": min(1.0, s + 1.96 * se)})
    return pd.DataFrame(rows)


def survival_at(km: pd.DataFrame, t: float) -> float:
    """Survival probability at time t from a kaplan_meier() table (step function)."""
    return float(km.loc[km["time"] <= t, "survival"].iloc[-1])


def logrank(time, event, group) -> dict:
    """k-group log-rank test of equal survival curves.

    Returns chi2, df, p and the observed / expected events per group.
    """
    t = np.asarray(time, dtype=float)
    e = np.asarray(event, dtype=bool)
    g = np.asarray(group)
    levels = list(pd.unique(g))
    k = len(levels)
    if k < 2:
        raise ValueError("log-rank needs at least two groups")
    observed, expected = np.zeros(k), np.zeros(k)
    var = np.zeros((k, k))
    for u in np.unique(t[e]):
        at = t >= u
        n = at.sum()
        d = ((t == u) & e).sum()
        n_j = np.array([(at & (g == lv)).sum() for lv in levels], dtype=float)
        d_j = np.array([((t == u) & e & (g == lv)).sum() for lv in levels], dtype=float)
        observed += d_j
        expected += d * n_j / n
        if n > 1:
            var += d * (n - d) / (n - 1) * (np.diag(n_j / n) - np.outer(n_j, n_j) / n ** 2)
    diff = (observed - expected)[:-1]
    stat = float(diff @ np.linalg.pinv(var[:-1, :-1]) @ diff)
    return {"chi2": stat, "df": k - 1, "p": float(chi2.sf(stat, k - 1)),
            "groups": {str(lv): {"observed": int(o), "expected": round(float(x), 2)}
                       for lv, o, x in zip(levels, observed, expected)}}


# ---------------------------------------------------------------- metrics for risk models
def censoring_km(time, event) -> pd.DataFrame:
    """Kaplan-Meier of the censoring distribution G(t) (censoring treated as the 'event')."""
    return kaplan_meier(time, ~np.asarray(event, dtype=bool))


def _G(cens_km: pd.DataFrame, t, eps: float = 0.05) -> np.ndarray:
    """G(t-) from a censoring KM table, floored at eps to keep IPCW weights bounded."""
    times, surv = cens_km["time"].to_numpy(), cens_km["survival"].to_numpy()
    idx = np.searchsorted(times, np.asarray(t, dtype=float), side="left") - 1
    return np.maximum(surv[np.clip(idx, 0, None)], eps)


def concordance_index(time, event, risk) -> float:
    """Harrell's C: share of comparable pairs where the earlier event has the higher risk."""
    t, e, r = (np.asarray(x, dtype=float) for x in (time, event, risk))
    e = e.astype(bool)
    num = den = 0.0
    for i in np.where(e)[0]:
        later = t > t[i]
        den += later.sum()
        num += (r[i] > r[later]).sum() + 0.5 * (r[i] == r[later]).sum()
    return float(num / den) if den else float("nan")


def cumulative_dynamic_auc(time, event, risk, tau: float, cens_km: pd.DataFrame) -> float:
    """Time-dependent AUC at tau (Uno-style IPCW): events by tau vs grafts still event-free after tau."""
    t, e, r = np.asarray(time, float), np.asarray(event, bool), np.asarray(risk, float)
    cases = e & (t <= tau)
    controls = t > tau
    if not cases.any() or not controls.any():
        return float("nan")
    w = 1 / _G(cens_km, t[cases])
    rc, rk = r[cases][:, None], r[controls][None, :]
    score = ((rc > rk) + 0.5 * (rc == rk)).mean(axis=1)
    return float((w * score).sum() / w.sum())


def brier_score(time, event, surv_at_tau, tau: float, cens_km: pd.DataFrame) -> float:
    """IPCW Brier score at tau for predicted survival probabilities S(tau | x) (Graf et al.)."""
    t, e, s = np.asarray(time, float), np.asarray(event, bool), np.asarray(surv_at_tau, float)
    died = e & (t <= tau)
    alive = t > tau
    loss = np.zeros(len(t))
    loss[died] = s[died] ** 2 / _G(cens_km, t[died])
    loss[alive] = (1 - s[alive]) ** 2 / _G(cens_km, np.full(alive.sum(), tau))
    return float(loss.mean())
