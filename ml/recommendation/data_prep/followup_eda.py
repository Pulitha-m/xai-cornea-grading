"""P1: exploratory analysis of the post-transplant follow-up cohort.

Describes the cohort before any modelling, so later steps (P2 preprocessing, P3-P5
models) are designed around what the data actually looks like:

  1. data checks      identifiers, visit schedule, no visits after failure or censoring,
                      event flags consistent, values in plausible ranges
  2. cohort summary   grafts, visits, follow-up length, events, censoring
  3. ECD over time    median and IQR per procedure (PK / DSEK / DMEK), CV and HEX trends
  4. survival         Kaplan-Meier for graft failure and for the low-ECD event (<1000),
                      by procedure, indication and rejection, with log-rank tests
  5. visits           attendance at each scheduled visit among grafts still observed
  6. rejection        cell loss with and without a rejection episode

EDA is descriptive only: nothing here is fitted and reused by the models, so looking at
the whole cohort does not leak test information into P2-P5.

The cohort currently comes from the follow-up simulator (data_prep/followup_simulator.py,
data_source = "simulated"); every figure and the summary state the data source. The same
code runs unchanged on real follow-up data with the same columns (data_source = "nebsl").

From ml/:
    uv run python -m recommendation.main followup-eda
"""
import json
from pathlib import Path

import pandas as pd
from matplotlib.ticker import MaxNLocator

from recommendation.data_prep.eda import INK_2, MUTED, SURFACE, _figure, _save, _style, plt
from recommendation.evaluation.survival import kaplan_meier, logrank, survival_at

VISIT_MONTHS = [1, 3, 6, 12, 24, 36, 48, 60]
PROCEDURE_COLORS = {"PK": "#2a78d6", "DSEK": "#eb6834", "DMEK": "#1f9e74"}
GROUP_COLORS = ["#2a78d6", "#eb6834", "#1f9e74", "#8b5cf6"]
FAILURE_ECD = 500
LOW_ECD = 1000
PLAUSIBLE = {"ECD": (100, 4000), "CV": (15, 90), "HEX": (15, 90)}
REPORT_MONTHS = (12, 36, 60)

GRAFT_COLS = {"graft_id", "data_source", "procedure", "indication", "donor_age", "baseline_ECD",
              "baseline_CV", "baseline_HEX", "rejection_episode", "rejection_month", "graft_failed",
              "time_to_event_months", "censored", "low_ECD_event", "time_to_low_ECD_months"}
VISIT_COLS = {"graft_id", "data_source", "months_after_surgery", "ECD", "CV", "HEX",
              "rejection_before_visit", "graft_failed_by_visit"}


# ---------------------------------------------------------------- loading and checks
def load_cohort(path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Read the Grafts and Visits sheets. Returns (grafts, visits, source)."""
    grafts = pd.read_excel(path, sheet_name="Grafts")
    visits = pd.read_excel(path, sheet_name="Visits")
    missing = (GRAFT_COLS - set(grafts.columns)) | (VISIT_COLS - set(visits.columns))
    if missing:
        raise ValueError(f"cohort file is missing columns: {sorted(missing)}")
    return grafts, visits, cohort_source(grafts, visits)


def cohort_source(grafts: pd.DataFrame, visits: pd.DataFrame) -> str:
    """The cohort's data source, e.g. 'simulated' or 'nebsl'. Mixed sources are refused,
    because every result must name exactly one source."""
    sources = set(grafts["data_source"].astype(str)) | set(visits["data_source"].astype(str))
    if len(sources) != 1:
        raise ValueError(f"cohort mixes data sources {sorted(sources)}; analyse them separately")
    return sources.pop()


def validate_cohort(grafts: pd.DataFrame, visits: pd.DataFrame) -> list[dict]:
    """Data checks that must pass before the cohort is used. One dict per check."""
    g = grafts.set_index("graft_id")
    v = visits.merge(grafts[["graft_id", "graft_failed", "time_to_event_months"]], on="graft_id", how="left")
    m = v["months_after_surgery"]
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("graft IDs unique", g.index.is_unique, f"{len(g)} grafts")
    orphans = int(v["graft_failed"].isna().sum())
    add("every visit belongs to a graft", orphans == 0, f"{orphans} orphan visits")
    dup = int(visits.duplicated(["graft_id", "months_after_surgery"]).sum())
    add("one visit per graft per scheduled month", dup == 0, f"{dup} duplicates")
    off = int((~m.isin(VISIT_MONTHS)).sum())
    add("visits on the schedule (1-60 months)", off == 0, f"{off} off-schedule visits")
    after_fail = int((v["graft_failed"].astype(bool) & (m > v["time_to_event_months"])).sum())
    add("no visits after graft failure", after_fail == 0, f"{after_fail} visits")
    after_cens = int((~v["graft_failed"].astype(bool) & (m > v["time_to_event_months"] + 0.05)).sum())
    add("no visits after censoring", after_cens == 0, f"{after_cens} visits")
    flags_ok = (grafts["graft_failed"].astype(bool) != grafts["censored"].astype(bool)).all()
    add("failed and censored flags agree", flags_ok, "graft_failed == not censored")
    times_ok = (grafts["time_to_event_months"].between(0, max(VISIT_MONTHS))).all()
    add("event times within 0-60 months", times_ok, "time_to_event_months")
    for col, (lo, hi) in PLAUSIBLE.items():
        bad = int((~visits[col].between(lo, hi)).sum()) + int((~grafts[f"baseline_{col}"].between(lo, hi)).sum())
        add(f"{col} in plausible range {lo}-{hi}", bad == 0, f"{bad} values outside")
    low = grafts[grafts["low_ECD_event"].astype(bool)]
    first_low = (visits[visits["ECD"] < LOW_ECD].groupby("graft_id")["months_after_surgery"].min())
    mismatch = int((first_low.reindex(low["graft_id"]).to_numpy() != low["time_to_low_ECD_months"].to_numpy()).sum())
    add("low-ECD event = first visit with ECD < 1000", mismatch == 0, f"{mismatch} mismatches")
    rej = grafts[grafts["rejection_episode"].astype(bool)]
    add("rejection grafts have a rejection month", rej["rejection_month"].notna().all(), f"{len(rej)} grafts")
    return checks


# ---------------------------------------------------------------- descriptive tables
def cohort_summary(grafts: pd.DataFrame, visits: pd.DataFrame) -> dict:
    per_graft = visits.groupby("graft_id").size().reindex(grafts["graft_id"], fill_value=0)
    follow = grafts["time_to_event_months"]
    return {
        "grafts": int(len(grafts)),
        "visits": int(len(visits)),
        "visits_per_graft_median": float(per_graft.median()),
        "visits_per_graft_iqr": [float(per_graft.quantile(0.25)), float(per_graft.quantile(0.75))],
        "grafts_without_visits": int((per_graft == 0).sum()),
        "follow_up_months_median": float(follow.median()),
        "follow_up_months_iqr": [float(follow.quantile(0.25)), float(follow.quantile(0.75))],
        "graft_failures": int(grafts["graft_failed"].sum()),
        "censored": int(grafts["censored"].sum()),
        "low_ecd_events": int(grafts["low_ECD_event"].sum()),
        "rejection_episodes": int(grafts["rejection_episode"].sum()),
        "procedure": grafts["procedure"].value_counts().to_dict(),
        "indication": grafts["indication"].value_counts().to_dict(),
        "donor_age_median": float(grafts["donor_age"].median()),
        "baseline_ecd_median": float(grafts["baseline_ECD"].median()),
    }


def _with_baseline(grafts: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    """Visits plus a month-0 row per graft holding the donor (baseline) values."""
    base = grafts.rename(columns={"baseline_ECD": "ECD", "baseline_CV": "CV", "baseline_HEX": "HEX"})
    base = base.assign(months_after_surgery=0)[["graft_id", "months_after_surgery", "ECD", "CV", "HEX"]]
    v = pd.concat([base, visits[["graft_id", "months_after_surgery", "ECD", "CV", "HEX"]]], ignore_index=True)
    v = v.merge(grafts[["graft_id", "procedure", "indication", "rejection_episode", "baseline_ECD"]], on="graft_id")
    v["relative_loss"] = 1 - v["ECD"] / v["baseline_ECD"]
    return v


def measures_over_time(grafts: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    """Median / IQR of ECD and median loss, CV, HEX per procedure and month (0 = donor)."""
    v = _with_baseline(grafts, visits)
    agg = v.groupby(["procedure", "months_after_surgery"]).agg(
        n=("ECD", "size"),
        ecd_median=("ECD", "median"),
        ecd_q25=("ECD", lambda s: s.quantile(0.25)),
        ecd_q75=("ECD", lambda s: s.quantile(0.75)),
        loss_median=("relative_loss", "median"),
        cv_median=("CV", "median"),
        hex_median=("HEX", "median"),
    )
    return agg.reset_index()


def survival_tables(grafts: pd.DataFrame) -> dict:
    """KM survival at 12/36/60 months and log-rank tests, for both endpoints."""
    endpoints = {
        "graft_failure": ("time_to_event_months", "graft_failed"),
        "low_ecd": ("time_to_low_ECD_months", "low_ECD_event"),
    }
    out = {}
    for name, (tcol, ecol) in endpoints.items():
        t, e = grafts[tcol], grafts[ecol].astype(bool)
        km_all = kaplan_meier(t, e)
        res = {"overall": {f"S({m})": round(survival_at(km_all, m), 3) for m in REPORT_MONTHS},
               "by": {}, "logrank": {}}
        res["overall"]["events"] = int(e.sum())
        for by in ("procedure", "indication", "rejection_episode"):
            groups = {}
            for level, sub in grafts.groupby(by):
                km = kaplan_meier(sub[tcol], sub[ecol].astype(bool))
                groups[str(level)] = {"n": int(len(sub)), "events": int(sub[ecol].sum()),
                                      **{f"S({m})": round(survival_at(km, m), 3) for m in REPORT_MONTHS}}
            res["by"][by] = groups
            lr = logrank(t, e, grafts[by].astype(str))
            res["logrank"][by] = {"chi2": round(lr["chi2"], 2), "df": lr["df"], "p": round(lr["p"], 4)}
        out[name] = res
    return out


def visit_attendance(grafts: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    """Share of grafts with a recorded visit at each scheduled month, among grafts still
    under observation then (not yet failed, censored or lost to follow-up)."""
    seen = set(zip(visits["graft_id"], visits["months_after_surgery"]))
    rows = []
    for m in VISIT_MONTHS:
        eligible = grafts.loc[grafts["time_to_event_months"] >= m, "graft_id"]
        attended = sum((gid, m) in seen for gid in eligible)
        rows.append({"month": m, "under_observation": int(len(eligible)), "attended": int(attended),
                     "attendance": round(attended / len(eligible), 3) if len(eligible) else float("nan")})
    return pd.DataFrame(rows)


def rejection_effect(grafts: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    """Median relative ECD loss at each month, grafts with vs without a rejection episode."""
    v = _with_baseline(grafts, visits)
    v = v[v["months_after_surgery"] > 0]
    t = v.pivot_table(index="months_after_surgery", columns="rejection_episode",
                      values="relative_loss", aggfunc="median")
    t = t.rename(columns={False: "no_rejection", True: "rejection"})
    n = v.pivot_table(index="months_after_surgery", columns="rejection_episode",
                      values="relative_loss", aggfunc="size").rename(
        columns={False: "n_no_rejection", True: "n_rejection"})
    return t.join(n).reset_index().rename(columns={"months_after_surgery": "month"})


# ---------------------------------------------------------------- figures
SOURCE_NOTE = {"simulated": "Data source: simulated cohort (method development)"}


def _label(source: str, title: str) -> str:
    return title


def _note(fig, source: str) -> None:
    """Small data-source line at the bottom of every figure."""
    fig.text(0.01, 0.005, SOURCE_NOTE.get(source, f"Data source: {source}"), fontsize=7, color=MUTED)


def _fig_ecd(trend: pd.DataFrame, source: str, out: Path) -> str:
    fig, ax = _figure(8, 4.2)
    for proc, color in PROCEDURE_COLORS.items():
        s = trend[trend["procedure"] == proc]
        if s.empty:
            continue
        ax.fill_between(s["months_after_surgery"], s["ecd_q25"], s["ecd_q75"], color=color, alpha=0.12, linewidth=0)
        ax.plot(s["months_after_surgery"], s["ecd_median"], color=color, linewidth=2.2, marker="o",
                markersize=4, label=f"{proc} median (IQR shaded)")
    ax.axhline(LOW_ECD, color=MUTED, linewidth=1, linestyle=":")
    ax.axhline(FAILURE_ECD, color="#b3261e", linewidth=1, linestyle="--")
    ax.annotate("low ECD 1000", (0.5, LOW_ECD + 25), color=MUTED, fontsize=8, ha="left")
    ax.annotate("failure 500", (0.5, FAILURE_ECD + 25), color="#b3261e", fontsize=8, ha="left")
    _style(ax, _label(source, "ECD after keratoplasty by procedure"), "Months after surgery", "ECD (cells/mm²)")
    ax.set_xticks([0] + VISIT_MONTHS)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)
    _note(fig, source)
    return _save(fig, out, "ecd_by_procedure.png")


def _fig_km(grafts: pd.DataFrame, source: str, out: Path) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), facecolor=SURFACE, sharey=True)
    panels = [("time_to_event_months", "graft_failed", "Graft survival (failure = ECD < 500)"),
              ("time_to_low_ECD_months", "low_ECD_event", "Free of low ECD (< 1000)")]
    for ax, (tcol, ecol, title) in zip(axes, panels):
        for proc, color in PROCEDURE_COLORS.items():
            sub = grafts[grafts["procedure"] == proc]
            if sub.empty:
                continue
            km = kaplan_meier(sub[tcol], sub[ecol].astype(bool))
            ax.step(km["time"], km["survival"], where="post", color=color, linewidth=2, label=proc)
            ax.fill_between(km["time"], km["lower"], km["upper"], step="post", color=color, alpha=0.1, linewidth=0)
        _style(ax, _label(source, title) if ax is axes[0] else title, "Months after surgery",
               "Proportion" if ax is axes[0] else "")
        ax.yaxis.set_major_locator(MaxNLocator(6))
        ax.set_ylim(0, 1.02)
        ax.set_xticks([0, 12, 24, 36, 48, 60])
        ax.legend(frameon=False, fontsize=8, labelcolor=INK_2, loc="lower left")
    _note(fig, source)
    return _save(fig, out, "km_by_procedure.png")


def _fig_attendance(att: pd.DataFrame, source: str, out: Path) -> str:
    fig, ax = _figure(7, 3.6)
    bars = ax.bar(att["month"].astype(str), att["attendance"] * 100, color=GROUP_COLORS[0], width=0.6)
    for b, n in zip(bars, att["under_observation"]):
        ax.annotate(f"{b.get_height():.0f}%\nn={n}", (b.get_x() + b.get_width() / 2, b.get_height()),
                    xytext=(0, 3), textcoords="offset points", ha="center", fontsize=7, color=INK_2)
    _style(ax, _label(source, "Visit attendance among grafts still followed"), "Scheduled visit (months)", "Attended (%)")
    ax.set_ylim(0, 115)
    _note(fig, source)
    return _save(fig, out, "visit_attendance.png")


def _fig_rejection(rej: pd.DataFrame, source: str, out: Path) -> str:
    fig, ax = _figure(7, 3.8)
    for col, color, label in (("no_rejection", GROUP_COLORS[0], "no rejection"),
                              ("rejection", GROUP_COLORS[1], "rejection episode")):
        if col in rej:
            ax.plot(rej["month"], rej[col] * 100, color=color, linewidth=2.2, marker="o", markersize=4, label=label)
    _style(ax, _label(source, "Median ECD loss: rejection vs none"), "Months after surgery", "Cell loss from donor (%)")
    ax.set_xticks(VISIT_MONTHS)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK_2)
    _note(fig, source)
    return _save(fig, out, "rejection_effect.png")


# ---------------------------------------------------------------- run
def run(cohort_path, out_dir) -> dict:
    """Run every P1 analysis; write figures, followup_eda.json and followup_eda_summary.md."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    grafts, visits, source = load_cohort(cohort_path)
    checks = validate_cohort(grafts, visits)
    summary = cohort_summary(grafts, visits)
    trend = measures_over_time(grafts, visits)
    surv = survival_tables(grafts)
    att = visit_attendance(grafts, visits)
    rej = rejection_effect(grafts, visits)
    figs = [_fig_ecd(trend, source, out), _fig_km(grafts, source, out),
            _fig_attendance(att, source, out), _fig_rejection(rej, source, out)]
    res = {"source": source, "checks": checks, "all_checks_pass": all(c["ok"] for c in checks),
           "summary": summary, "survival": surv,
           "measures_over_time": trend.round(4).to_dict(orient="records"),
           "visit_attendance": att.to_dict(orient="records"),
           "rejection_effect": rej.round(4).to_dict(orient="records"), "figures": figs}
    (out / "followup_eda.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    _write_markdown(out / "followup_eda_summary.md", res, trend, att, rej)
    return res


def _md_table(df: pd.DataFrame, index: bool = True) -> str:
    """Markdown table without extra dependencies."""
    d = df.reset_index() if index else df
    fmt = lambda x: f"{x:.3f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)  # noqa: E731
    lines = ["| " + " | ".join(map(str, d.columns)) + " |", "|" + "---|" * len(d.columns)]
    lines += ["| " + " | ".join(fmt(x) for x in row) + " |" for row in d.itertuples(index=False)]
    return "\n".join(lines)


def _write_markdown(path: Path, r: dict, trend: pd.DataFrame, att: pd.DataFrame, rej: pd.DataFrame) -> None:
    s, src = r["summary"], r["source"]
    md = ["# P1 Follow-up cohort EDA", ""]
    if src == "simulated":
        md += ["Data source: simulated cohort calibrated to published studies (Lass et al. 2010; SMAS), "
               "generated by `data_prep/followup_simulator.py` for method development.", ""]
    else:
        md += [f"Data source: {src}.", ""]
    md += ["## 1. Data checks", "", "| Check | Result | Detail |", "|---|---|---|"]
    md += [f"| {c['check']} | {'pass' if c['ok'] else '**FAIL**'} | {c['detail']} |" for c in r["checks"]]
    md += ["", "## 2. Cohort", "",
           f"- Grafts: {s['grafts']}; visits: {s['visits']} "
           f"(median {s['visits_per_graft_median']:.0f} per graft, IQR {s['visits_per_graft_iqr'][0]:.0f}-"
           f"{s['visits_per_graft_iqr'][1]:.0f}); grafts with no visit: {s['grafts_without_visits']}",
           f"- Follow-up: median {s['follow_up_months_median']:.1f} months "
           f"(IQR {s['follow_up_months_iqr'][0]:.1f}-{s['follow_up_months_iqr'][1]:.1f})",
           f"- Graft failures: {s['graft_failures']}; censored: {s['censored']}; "
           f"low-ECD events: {s['low_ecd_events']}; rejection episodes: {s['rejection_episodes']}",
           "- Procedures: " + ", ".join(f"{k} {v}" for k, v in s["procedure"].items()),
           "- Indications: " + ", ".join(f"{k} {v}" for k, v in s["indication"].items()), ""]
    md += ["## 3. ECD over time (median, cells/mm²; month 0 = donor)", ""]
    piv = trend.pivot(index="months_after_surgery", columns="procedure", values="ecd_median").round(0)
    md += [_md_table(piv), ""]
    loss = trend.pivot(index="months_after_surgery", columns="procedure", values="loss_median")
    md += ["Median cell loss from donor: " + "; ".join(
        f"{p} {loss.loc[12, p]:.0%} at 12 mo, {loss.loc[60, p]:.0%} at 60 mo"
        for p in loss.columns if 12 in loss.index and 60 in loss.index), ""]
    md += ["## 4. Survival (Kaplan-Meier)", ""]
    for name, title in (("graft_failure", "Graft failure (ECD < 500)"), ("low_ecd", "Low ECD (< 1000)")):
        e = r["survival"][name]
        md += [f"### {title}", "",
               "Overall: " + ", ".join(f"{k} {v}" for k, v in e["overall"].items()), "",
               "| Group | n | events | S(12) | S(36) | S(60) |", "|---|---|---|---|---|---|"]
        for by, groups in e["by"].items():
            for lv, d in groups.items():
                md.append(f"| {by} = {lv} | {d['n']} | {d['events']} | {d['S(12)']} | {d['S(36)']} | {d['S(60)']} |")
        md += ["", "Log-rank: " + "; ".join(
            f"{by} chi2 {d['chi2']} (df {d['df']}), p {d['p']}" for by, d in e["logrank"].items()), ""]
    md += ["## 5. Visit attendance (grafts still under observation)", "", _md_table(att, index=False), ""]
    md += ["## 6. Rejection and cell loss (median relative loss)", "", _md_table(rej.round(3), index=False), ""]
    md += ["## What this means for the next steps", "",
           "- Visits are irregular (missed visits, loss to follow-up, failure stops follow-up): P2 must build "
           "sequences that allow gaps and must never use visits after the prediction time.",
           "- Censoring is common, so P5 risk models must be survival models (Cox, RSF, DeepSurv), "
           "not plain classifiers.",
           "- Procedure, indication and rejection change both the trajectory and the risk: include them as inputs.",
           "- Split by graft (P2), so no graft's visits appear in both training and test data.", ""]
    md += ["Figures: " + ", ".join(r["figures"])]
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
