"""Simulated post-transplant follow-up cohort (simulation study for method development).

Every follow-up value produced here is simulated; rows carry data_source = "simulated".

Purpose: let the trajectory (LSTM), risk (DeepSurv) and follow-up modules be built
and tested before real NEBSL / hospital follow-up data arrives. When real data
arrives it must use the same columns, and every reported result must say which
data it came from.

How a graft is simulated
  baseline   donor ECD / CV / HEX / age drawn from the distribution of real NEBSL
             donor exams (no real record is copied: values are re-sampled with noise)
  decline    two-component exponential cell loss (Armitage et al.): a fast early
             phase after surgery, then a slow chronic phase
               ECD(t) = ECD0 * [a * exp(-k1 t) + (1 - a) * exp(-k2 t)],  t in years
  modifiers  a minority "failing course" (steep early + fast chronic loss),
             procedure (DMEK/DSEK lose more early than PK), indication (failed
             graft / bullous keratopathy lose faster), older donor (slightly faster),
             immune rejection episodes (sudden drop + faster chronic loss)
  CV / HEX   polymegethism and pleomorphism worsen as cells are lost
  visits     1, 3, 6, 12, 24, 36, 48, 60 months, with date jitter, missed visits,
             loss to follow-up and administrative censoring
  outcome    graft failure when ECD < 500 cells/mm2 (endothelial decompensation)

Pattern targets (see PARAMS["targets"]) come from the literature and are checked by
`validate()`; they are approximate and the parameters are assumptions, which must be
stated in any write-up.
"""
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

PARAMS = {
    "visit_months": [1, 3, 6, 12, 24, 36, 48, 60],
    "procedures": {"PK": 0.60, "DSEK": 0.25, "DMEK": 0.15},
    # fast-phase fraction a and rate k1 (/yr); chronic rate k2 (/yr): medians per procedure
    "decline": {
        "PK":   {"a": 0.10, "k1": 3.0, "k2": 0.13},
        "DSEK": {"a": 0.25, "k1": 3.0, "k2": 0.10},
        "DMEK": {"a": 0.28, "k1": 3.0, "k2": 0.08},
    },
    "indications": {"Fuchs/Endothelial": 0.45, "Bullous keratopathy": 0.25,
                    "Failed/Re-graft": 0.15, "Other": 0.15},
    "indication_k2_factor": {"Fuchs/Endothelial": 1.0, "Bullous keratopathy": 1.25,
                             "Failed/Re-graft": 1.6, "Other": 1.1},
    "donor_age_k2_per_10y": 0.04,         # +4% chronic loss rate per 10 years over 60
    "between_graft_sd": 0.35,             # log-normal spread of k2 between grafts
    # a minority of grafts follow a "failing" course: steep early loss (CDS: ~27% at 6 months
    # in grafts that later failed vs ~7% in clear grafts) and fast chronic loss
    "failing_course_prob": 0.10,
    "failing_course": {"a": 0.30, "k2_factor": 3.5},
    "rejection_5y_prob": {"PK": 0.15, "DSEK": 0.08, "DMEK": 0.02},
    "rejection_drop": (0.15, 0.35),       # fraction of cells lost at a rejection episode
    "rejection_k2_factor": 1.5,
    "failure_ecd": 500,
    "low_ecd": 1000,                      # risk-model endpoint: first measured ECD below this
    "measurement_sd": {"ECD": 0.05, "CV": 2.5, "HEX": 3.0},   # ECD relative, CV/HEX absolute
    "cv_per_loss": 12.0,                  # CV rises ~12 points at 100% loss
    "hex_per_loss": -15.0,                # HEX falls ~15 points at 100% loss
    "missed_visit_prob": 0.15,
    "dropout_per_year": 0.08,
    "surgery_window": ("2020-01-01", "2025-12-31"),
    "data_cutoff": "2026-09-30",
    # literature targets used by validate(): (lower, upper) median relative ECD loss
    "targets": {
        "PK_loss_6m": (0.05, 0.20),       # CDS: ~7% (clear grafts) to 27% (failing) at 6 months
        "PK_loss_12m": (0.10, 0.45),      # other series: up to 30-50% in year 1
        "PK_loss_60m": (0.45, 0.75),      # SMAS: ~69-75% loss at 5 years
        "failure_5y": (0.05, 0.20),       # CDS: 5-year graft failure in the order of 10%
        "EK_loss_6m": (0.15, 0.40),       # EK: higher early loss than PK (assumption, check refs)
    },
}

# Real NEBSL donor exam summary (cleaned tissue table, EDA): used only to shape the
# baseline distribution. Means/SDs, not records.
DATA_SOURCE = "simulated"

DONOR_BASELINE = {"ECD": (2650.6, 455.6, 2000, 3600),   # mean, sd, clip low, clip high
                  "CV": (38.3, 5.2, 25, 55),
                  "HEX": (53.7, 6.5, 35, 72),
                  "Donor_Age": (59.8, 10.7, 18, 78)}


@dataclass
class Graft:
    graft_id: str
    procedure: str
    indication: str
    donor_age: float
    ecd0: float
    cv0: float
    hex0: float
    surgery_date: date


def _baseline(rng, n):
    out = {}
    for k, (m, sd, lo, hi) in DONOR_BASELINE.items():
        out[k] = np.clip(rng.normal(m, sd, n), lo, hi)
    # ECD and HEX are mildly positively related, CV negatively, in donor corneas
    z = (out["ECD"] - 2650) / 455
    out["CV"] = np.clip(out["CV"] - 1.5 * z, 25, 55)
    out["HEX"] = np.clip(out["HEX"] + 1.5 * z, 35, 72)
    return out


def _true_ecd(g: Graft, t_years: np.ndarray, rng, p=PARAMS):
    d = p["decline"][g.procedure]
    k2 = d["k2"] * p["indication_k2_factor"][g.indication]
    k2 *= 1 + p["donor_age_k2_per_10y"] * max(0.0, (g.donor_age - 60) / 10)
    k2 *= float(np.exp(rng.normal(0, p["between_graft_sd"])))
    a = float(np.clip(rng.normal(d["a"], 0.05), 0.02, 0.6))
    failing_course = rng.random() < p["failing_course_prob"]
    if failing_course:
        a = max(a, float(np.clip(rng.normal(p["failing_course"]["a"], 0.05), 0.15, 0.6)))
        k2 *= p["failing_course"]["k2_factor"]
    ecd = g.ecd0 * (a * np.exp(-d["k1"] * t_years) + (1 - a) * np.exp(-k2 * t_years))

    # immune rejection: at most one episode in 5 years
    rejection_at = None
    if rng.random() < p["rejection_5y_prob"][g.procedure]:
        rejection_at = float(rng.uniform(0.25, 5.0))
        drop = rng.uniform(*p["rejection_drop"])
        after = t_years >= rejection_at
        extra = np.exp(-(p["rejection_k2_factor"] - 1) * k2 * (t_years - rejection_at))
        ecd = np.where(after, ecd * (1 - drop) * extra, ecd)
    return ecd, rejection_at


def simulate(n_grafts: int = 500, seed: int = 42, p=PARAMS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (grafts, visits): one row per graft, one row per follow-up visit."""
    rng = np.random.default_rng(seed)
    base = _baseline(rng, n_grafts)
    procs = list(p["procedures"])
    inds = list(p["indications"])
    start, end = (date.fromisoformat(s) for s in p["surgery_window"])
    cutoff = date.fromisoformat(p["data_cutoff"])

    grafts, visits = [], []
    for i in range(n_grafts):
        g = Graft(
            graft_id=f"G{i + 1:04d}",
            procedure=str(rng.choice(procs, p=list(p["procedures"].values()))),
            indication=str(rng.choice(inds, p=list(p["indications"].values()))),
            donor_age=round(float(base["Donor_Age"][i])),
            ecd0=round(float(base["ECD"][i])), cv0=round(float(base["CV"][i]), 1),
            hex0=round(float(base["HEX"][i]), 1),
            surgery_date=start + timedelta(days=int(rng.integers(0, (end - start).days))),
        )
        months = np.array(p["visit_months"], dtype=float)
        t = months / 12
        ecd_true, rejection_at = _true_ecd(g, t, rng, p)

        # follow-up ends at the data cutoff or when the patient is lost to follow-up
        max_months = (cutoff - g.surgery_date).days / 30.44
        lost_after = rng.exponential(12 / p["dropout_per_year"])
        observed_until = min(max_months, lost_after)

        failed_at, low_at = None, None
        for m, true in zip(months, ecd_true):
            if m > observed_until or (failed_at is not None and m > failed_at):
                break   # follow-up stops at the data cutoff, loss to follow-up or graft failure
            if failed_at is None and true < p["failure_ecd"]:
                failed_at = m
            if rng.random() < p["missed_visit_prob"] and m not in (6, 12):
                continue
            loss = 1 - true / g.ecd0
            ecd = true * (1 + rng.normal(0, p["measurement_sd"]["ECD"]))
            cv = g.cv0 + p["cv_per_loss"] * loss + rng.normal(0, p["measurement_sd"]["CV"])
            hx = g.hex0 + p["hex_per_loss"] * loss + rng.normal(0, p["measurement_sd"]["HEX"])
            if low_at is None and ecd < p["low_ecd"]:
                low_at = m
            visit_date = g.surgery_date + timedelta(days=int(m * 30.44 + rng.integers(-14, 15)))
            visits.append({
                "graft_id": g.graft_id, "months_after_surgery": int(m), "visit_date": visit_date,
                "ECD": round(float(max(ecd, 150))), "CV": round(float(np.clip(cv, 20, 80)), 1),
                "HEX": round(float(np.clip(hx, 20, 80)), 1),
                "rejection_before_visit": bool(rejection_at is not None and rejection_at * 12 <= m),
                "graft_failed_by_visit": bool(failed_at is not None and failed_at <= m),
            })
            if failed_at is not None:
                break

        event_months = failed_at if failed_at is not None else min(observed_until, months[-1])
        grafts.append({
            "graft_id": g.graft_id, "procedure": g.procedure, "indication": g.indication,
            "donor_age": g.donor_age, "baseline_ECD": g.ecd0, "baseline_CV": g.cv0,
            "baseline_HEX": g.hex0, "surgery_date": g.surgery_date,
            "rejection_episode": rejection_at is not None,
            "rejection_month": None if rejection_at is None else round(rejection_at * 12, 1),
            "graft_failed": failed_at is not None,
            "time_to_event_months": round(float(event_months), 1),
            "censored": failed_at is None,
            "low_ECD_event": low_at is not None,
            "time_to_low_ECD_months": round(float(low_at if low_at is not None else
                                                  min(observed_until, months[-1])), 1),
        })

    gdf, vdf = pd.DataFrame(grafts), pd.DataFrame(visits)
    gdf.insert(1, "data_source", DATA_SOURCE)
    vdf.insert(1, "data_source", DATA_SOURCE)
    return gdf, vdf


def validate(grafts: pd.DataFrame, visits: pd.DataFrame, p=PARAMS) -> pd.DataFrame:
    """Compare simulated median ECD loss with the literature targets."""
    v = visits.merge(grafts[["graft_id", "procedure", "baseline_ECD"]], on="graft_id")
    v["loss"] = 1 - v["ECD"] / v["baseline_ECD"]

    def med(proc, month):
        sel = v[(v["months_after_surgery"] == month) & v["procedure"].isin(proc)]
        return float(sel["loss"].median()) if len(sel) else float("nan")

    # Kaplan-Meier estimate of graft failure by 60 months (handles censoring)
    surv, t = 1.0, grafts["time_to_event_months"]
    for m in sorted(t[grafts["graft_failed"]].unique()):
        at_risk = (t >= m).sum()
        events = ((t == m) & grafts["graft_failed"]).sum()
        if m <= 60 and at_risk:
            surv *= 1 - events / at_risk
    got = {"PK_loss_6m": med(["PK"], 6), "PK_loss_12m": med(["PK"], 12),
           "PK_loss_60m": med(["PK"], 60), "failure_5y": 1 - surv,
           "EK_loss_6m": med(["DSEK", "DMEK"], 6)}
    rows = [{"pattern": k, "simulated_median": round(got[k], 3), "target_low": lo, "target_high": hi,
             "ok": lo <= got[k] <= hi} for k, (lo, hi) in p["targets"].items()]
    return pd.DataFrame(rows)


README = [
    ("Data source", "Simulated cohort (data_source = simulated). Follow-up values are generated by "
                    "data_prep/followup_simulator.py, not recorded at patient visits; report results as a "
                    "simulation study."),
    ("Purpose", "Develop and test the trajectory, risk and follow-up models before real follow-up data "
                "arrives (simulation study)."),
    ("Baseline", "Donor ECD/CV/HEX/age re-sampled from the distribution (mean, SD) of real NEBSL donor "
                 "exams; no real record is copied."),
    ("Decline model", "Two-component exponential endothelial cell loss (Armitage et al.), with procedure, "
                      "indication, donor-age and rejection effects; parameters are assumptions."),
    ("Failure", "Graft failure when true ECD < 500 cells/mm2."),
    ("Low-ECD endpoint", "First measured ECD < 1000 cells/mm2 (event for the risk model)."),
    ("Sources for pattern targets", "Lass et al., Arch Ophthalmol 2010 (Cornea Donor Study); SMAS; "
                                    "see validate() in followup_simulator.py."),
]


def write(out_file, n_grafts: int = 500, seed: int = 42) -> dict:
    grafts, visits = simulate(n_grafts, seed)
    checks = validate(grafts, visits)
    with pd.ExcelWriter(out_file, engine="openpyxl") as xw:
        pd.DataFrame(README, columns=["Item", "Value"]).to_excel(xw, sheet_name="README", index=False)
        grafts.to_excel(xw, sheet_name="Grafts", index=False)
        visits.to_excel(xw, sheet_name="Visits", index=False)
        checks.to_excel(xw, sheet_name="Pattern_checks", index=False)
        pd.DataFrame({"parameter": list(PARAMS), "value": [str(v) for v in PARAMS.values()]}) \
            .to_excel(xw, sheet_name="Parameters", index=False)
    return {"grafts": len(grafts), "visits": len(visits), "failed": int(grafts["graft_failed"].sum()),
            "rejections": int(grafts["rejection_episode"].sum()),
            "low_ecd": int(grafts["low_ECD_event"].sum()), "checks": checks}


def plot(xlsx, out_dir) -> str:
    """Median ECD over time per procedure, with 20 example grafts behind it."""
    from pathlib import Path

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    g = pd.read_excel(xlsx, sheet_name="Grafts")
    v = pd.read_excel(xlsx, sheet_name="Visits").merge(g[["graft_id", "procedure", "baseline_ECD"]], on="graft_id")
    base = g.assign(months_after_surgery=0, ECD=g["baseline_ECD"])[["graft_id", "procedure", "months_after_surgery", "ECD"]]
    v = pd.concat([base, v[["graft_id", "procedure", "months_after_surgery", "ECD"]]])
    colors = {"PK": "#2a78d6", "DSEK": "#eb6834", "DMEK": "#1f9e74"}
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for gid in g["graft_id"].head(20):
        s = v[v["graft_id"] == gid].sort_values("months_after_surgery")
        ax.plot(s["months_after_surgery"], s["ECD"], color="#c3c2b7", linewidth=0.8, zorder=1)
    for proc, color in colors.items():
        m = v[v["procedure"] == proc].groupby("months_after_surgery")["ECD"].median()
        ax.plot(m.index, m.values, color=color, linewidth=2.4, marker="o", label=f"{proc} (median)", zorder=3)
    ax.axhline(500, color="#b3261e", linewidth=1, linestyle="--")
    ax.annotate("failure threshold 500", (61, 520), color="#b3261e", fontsize=8, ha="right")
    ax.set_title("Endothelial cell density after keratoplasty", loc="left",
                 fontsize=11, fontweight="bold", color="#0b0b0b")
    fig.text(0.01, 0.01, "Data source: simulated cohort (method development)", fontsize=7, color="#898781")
    ax.set_xlabel("Months after surgery", color="#52514e")
    ax.set_ylabel("ECD (cells/mm²)", color="#52514e")
    ax.set_xticks([0, 1, 3, 6, 12, 24, 36, 48, 60])
    ax.tick_params(colors="#898781", length=0)
    ax.grid(axis="y", color="#e1e0d9")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=9, labelcolor="#52514e")
    fig.tight_layout()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "simulated_trajectories.png"
    fig.savefig(path, dpi=150, facecolor="#fcfcfb")
    plt.close(fig)
    return str(path)
