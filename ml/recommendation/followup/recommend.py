"""P7: follow-up recommendation at the 12-month visit.

Turns the chosen models' outputs into what a clinician acts on:
  alert level   green / amber / red
  next visit    12 / 6 / 3 months (green / amber / red)
  actions       review prompts, not treatment instructions
  reasons       which rules fired, plus the strongest model reasons (P6)

Inputs per graft: predicted ECD at 24/36/60 months with its 80% band (P4), recalibrated
risk of graft failure and of low ECD by 12 and 24 months after the visit (P5), the
12-month ECD, cell loss by 12 months and any rejection episode by 12 months.

Rules are transparent and their thresholds live in config.yaml (followup.alerts). They
are placeholders until agreed with clinicians. A rejection episode always triggers red:
the risk model cannot learn its effect from the few early rejections in the data, and a
clinician would review it anyway.
"""
import numpy as np
import pandas as pd

from recommendation.explain import followup_explain as fx

DEFAULT_RULES = {
    "version": "placeholder-2026-10-20",
    "red": {"failure_risk_12m": 0.20, "ecd_12m_below": 750, "predicted_ecd_24m_below": 600},
    "amber": {"failure_risk_24m": 0.05, "low_ecd_risk_24m": 0.30, "ecd_60m_lower_band_below": 500,
              "loss_12m_at_least": 0.40},
    "interval_months": {"green": 12, "amber": 6, "red": 3},
}
FAILURE_ECD = 500
DISCLAIMER = "Decision support only. Follow-up decisions rest with the treating clinician."


def predictions(table: pd.DataFrame, traj: dict, risk: dict) -> pd.DataFrame:
    """Model outputs needed by the rules, one row per graft."""
    model, band = traj["model"], traj["band"]
    pred = model.predict(table)
    out = pd.DataFrame(index=table.index)
    for h in (24, 36, 60):
        lo, hi = band[h] if h in band else band[str(h)]
        out[f"ecd_{h}m"] = pred[f"ECD_{h}m"]
        out[f"ecd_{h}m_low"] = pred[f"ECD_{h}m"] * np.exp(lo)
        out[f"ecd_{h}m_high"] = pred[f"ECD_{h}m"] * np.exp(hi)
    fail = risk["models"]["graft_failure"]
    low = risk["models"]["low_ecd"]
    for tau in (12, 24):
        out[f"failure_risk_{tau}m"] = fx.risk_at(fail, table, tau)
        r = fx.risk_at(low, table, tau)
        out[f"low_ecd_risk_{tau}m"] = np.where(table["low_ecd_before_landmark"].astype(bool), 1.0, r)
    out["ecd_12m"] = table["ECD_12m"]
    out["loss_12m"] = table["loss_12m"]
    out["rejection_by_12m"] = table["rejection_by_12m"].astype(bool)
    out["already_low_ecd"] = table["low_ecd_before_landmark"].astype(bool)
    return out


def apply_rules(p: pd.DataFrame, rules: dict = DEFAULT_RULES) -> pd.DataFrame:
    """Alert level, next visit, fired rules and actions for every graft."""
    r, a = rules["red"], rules["amber"]
    red = {
        "rejection episode by 12 months": p["rejection_by_12m"],
        f"failure risk by 12 months >= {r['failure_risk_12m']:.0%}": p["failure_risk_12m"] >= r["failure_risk_12m"],
        f"12-month ECD < {r['ecd_12m_below']}": p["ecd_12m"] < r["ecd_12m_below"],
        f"predicted 24-month ECD < {r['predicted_ecd_24m_below']}": p["ecd_24m"] < r["predicted_ecd_24m_below"],
    }
    amber = {
        f"failure risk by 24 months >= {a['failure_risk_24m']:.0%}": p["failure_risk_24m"] >= a["failure_risk_24m"],
        f"low-ECD risk by 24 months >= {a['low_ecd_risk_24m']:.0%}": p["low_ecd_risk_24m"] >= a["low_ecd_risk_24m"],
        f"60-month ECD could reach {a['ecd_60m_lower_band_below']} (lower end of 80% band)":
            p["ecd_60m_low"] < a["ecd_60m_lower_band_below"],
        f"cell loss by 12 months >= {a['loss_12m_at_least']:.0%}": p["loss_12m"] >= a["loss_12m_at_least"],
        "ECD already below 1000": p["already_low_ecd"],
    }
    red_any = pd.concat(red, axis=1).any(axis=1)
    amber_any = pd.concat(amber, axis=1).any(axis=1)
    level = np.where(red_any, "red", np.where(amber_any, "amber", "green"))
    out = pd.DataFrame({"alert": level}, index=p.index)
    out["next_visit_months"] = out["alert"].map(rules["interval_months"])

    fired, actions = [], []
    for i in p.index:
        f = [k for k, s in red.items() if s[i]] + [k for k, s in amber.items() if s[i]]
        fired.append(f)
        actions.append(_actions(p.loc[i], out.loc[i, "alert"]))
    out["rules_fired"] = fired
    out["actions"] = actions
    return out


def _actions(p: pd.Series, alert: str) -> list[str]:
    acts = []
    if p["rejection_by_12m"]:
        acts.append("Review for graft rejection")
    if p["ecd_24m"] < FAILURE_ECD or p["ecd_36m"] < FAILURE_ECD:
        acts.append("Consider regraft assessment: ECD projected below 500 within 3 years")
    if alert == "red" and not acts:
        acts.append("Clinical review of endothelial function")
    if alert in ("red", "amber"):
        acts.append("Repeat specular microscopy (ECD, CV, HEX) at the next visit")
    if alert == "green":
        acts.append("Routine follow-up")
    return acts


def recommend(table: pd.DataFrame, traj: dict, risk: dict, rules: dict = DEFAULT_RULES) -> pd.DataFrame:
    p = predictions(table, traj, risk)
    return pd.concat([table[["graft_id"]], p, apply_rules(p, rules)], axis=1)


# ---------------------------------------------------------------- evaluation (outcomes are known in a simulation)
def outcomes_by_alert(rec: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """What actually happened next, per alert level (failure / low ECD within 12 and 24 months)."""
    d = rec[["alert"]].join(table[["failure_event", "failure_months_after_landmark", "low_ecd_event",
                                   "low_ecd_months_after_landmark", "low_ecd_before_landmark"]])
    rows = []
    for level in ("green", "amber", "red"):
        s = d[d["alert"] == level]
        fail = s["failure_event"].astype(bool)
        low = s["low_ecd_event"].astype(bool)
        rows.append({"alert": level, "grafts": int(len(s)), "share": len(s) / max(len(d), 1),
                     "failed_within_12m": int((fail & (s["failure_months_after_landmark"] <= 12)).sum()),
                     "failed_within_24m": int((fail & (s["failure_months_after_landmark"] <= 24)).sum()),
                     "failed_ever": int(fail.sum()),
                     "low_ecd_within_24m": int((low & (s["low_ecd_months_after_landmark"] <= 24)).sum())})
    return pd.DataFrame(rows)


def visit_burden(rec: pd.DataFrame, fixed_interval: int = 6) -> dict:
    """Visits per graft in the next year: recommended interval vs a fixed schedule."""
    per_year = (12 / rec["next_visit_months"]).mean()
    return {"recommended_visits_per_graft_year": float(per_year), "fixed_schedule_months": fixed_interval,
            "fixed_visits_per_graft_year": 12 / fixed_interval}


def safety(out: pd.DataFrame) -> dict:
    """Grafts that failed within 12 months although they were green (missed deterioration)."""
    g = out.set_index("alert").loc["green"]
    return {"green_failed_within_12m": int(g["failed_within_12m"]), "green_grafts": int(g["grafts"])}
