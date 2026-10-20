"""One report with the output of every stage of the post-transplant (Part B) work.

Same style as the matching stage report (stage_report.py), for supervisors, panels and the
thesis. It reads the saved results of each step instead of retraining, so it takes seconds:

  1. Follow-up cohort        data checks, ECD over time, survival, visits     (followup-eda)
  2. Landmark dataset        12-month design, graft split, leakage checks     (followup-data)
  3. Baselines               trajectory and risk baselines                     (followup-baselines)
  4. Trajectory models       gradient boosting vs LSTM, learning curve, test  (trajectory)
  5. Risk models             Cox vs boosted Cox vs DeepSurv, calibration       (risk)
  6. Explanations            SHAP reasons, counterfactuals, sanity checks      (followup-explain)
  7. Follow-up recommendation  alert, next visit, what happened next          (followup)
  8. Robustness              conclusions under other simulation settings      (followup-robustness)

A stage whose results are missing is listed with the command that creates them. The report
states the data source. It is written to outputs/report/ (git-ignored).

From ml/:
    uv run python -m recommendation.main followup-report
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

from recommendation.reporting.stage_report import CSS, _img, _kpis, _section, _table

STAGES = [
    ("followup_eda/followup_eda.json", "followup-eda"),
    ("followup_baselines/baselines.json", "followup-baselines"),
    ("trajectory/trajectory_results.json", "trajectory"),
    ("risk/risk_results.json", "risk"),
    ("followup_explain/followup_explanations.json", "followup-explain"),
    ("followup/followup_recommendations.json", "followup"),
    ("robustness/robustness_results.json", "followup-robustness"),
]


def _load(outputs: Path, rel: str):
    p = outputs / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _missing(n: int, title: str, command: str) -> str:
    return _section(n, title, "Not available yet.",
                    f'<p class="note">Run <code>uv run python -m recommendation.main {command}</code> first.</p>')


def _checks_html(checks: list[dict]) -> str:
    rows = "".join(f'<li><span class="{"pass" if c["ok"] else "fail"}">{"pass" if c["ok"] else "FAIL"}</span> '
                   f'{c["check"]} ({c["detail"]})</li>' for c in checks)
    return f"<ul>{rows}</ul>"


def build_followup_report(cfg: dict) -> tuple[Path, list[str]]:
    paths = cfg["paths"]
    outputs = Path(paths["outputs"])
    r = {cmd: _load(outputs, rel) for rel, cmd in STAGES}
    log, parts = [], []

    eda = r["followup-eda"]
    source = (eda or {}).get("source", "unknown")

    # 1. cohort
    if eda:
        s = eda["summary"]
        body = _kpis([("grafts", str(s["grafts"])), ("visits", f"{s['visits']:,}"),
                      ("median follow-up (months)", f"{s['follow_up_months_median']:.1f}"),
                      ("graft failures", str(s["graft_failures"])), ("low-ECD events", str(s["low_ecd_events"])),
                      ("rejection episodes", str(s["rejection_episodes"]))])
        body += "<h3>Data checks</h3>" + _checks_html(eda["checks"])
        trend = pd.DataFrame(eda["measures_over_time"]).pivot(index="months_after_surgery", columns="procedure",
                                                              values="ecd_median")
        trend.index.name = "months"
        body += "<h3>Median ECD by procedure (cells/mm²; month 0 = donor)</h3>" + _table(trend, fmt="{:.0f}")
        body += '<div class="grid2">' + _img(outputs / "followup_eda" / "ecd_by_procedure.png") + \
            _img(outputs / "followup_eda" / "km_by_procedure.png") + "</div>"
        parts.append(_section(1, "Follow-up cohort", "What the follow-up data looks like and whether it is valid.", body))
        log.append(f"Stage 1 cohort: {s['grafts']} grafts, {s['visits']} visits, checks pass: {eda['all_checks_pass']}")
    else:
        parts.append(_missing(1, "Follow-up cohort", "followup-eda"))

    # 2. landmark dataset
    try:
        from recommendation.data_prep.followup_dataset import leakage_checks, load
        from recommendation.data_prep.followup_eda import load_cohort

        table, pre = load(paths["followup_dataset"], Path(paths["models"]) / "followup_preprocessor.json")
        _, visits, _ = load_cohort(paths["followup_cohort"])
        split = table.groupby("split").agg(grafts=("graft_id", "size"), failures=("failure_event", "sum"),
                                           low_ecd_events=("low_ecd_event", "sum")).reindex(["train", "val", "test"])
        split.index.name = "split"
        body = (f'<p class="what">Prediction at the 12-month visit from donor values and the 3/6/12-month visits; '
                f'{len(pre.feature_names)} inputs; targets ECD at 24/36/60 months and failure / low ECD afterwards.</p>'
                + _table(split.astype(float), fmt="{:.0f}") + "<h3>Leakage checks</h3>"
                + _checks_html(leakage_checks(table, pre, visits)))
        parts.append(_section(2, "Landmark dataset", "Graft-level split; preprocessing fitted on training grafts only.", body))
        log.append(f"Stage 2 dataset: {len(table)} grafts, {len(pre.feature_names)} inputs")
    except FileNotFoundError:
        parts.append(_missing(2, "Landmark dataset", "followup-data"))

    # 3. baselines
    b = r["followup-baselines"]
    if b:
        traj = pd.DataFrame({n: {h: d["repeated_cv"][h]["mae"] for h in ("24m", "36m", "60m", "all")}
                             for n, d in b["trajectory"].items()}).T
        traj.index.name = "baseline (MAE, cells/mm²)"
        risk = pd.DataFrame({f"{n} [{ep}]": {k: d["repeated_cv"][k] for k in ("c_index", "auc_24m", "brier_24m")}
                             for ep, models in b["risk"].items() for n, d in models.items()}).T
        risk.index.name = "baseline [endpoint]"
        parts.append(_section(3, "Baselines", "The simple methods every model must beat (repeated CV; test untouched).",
                              _table(traj, fmt="{:.0f}") + _table(risk)))
        log.append("Stage 3 baselines")
    else:
        parts.append(_missing(3, "Baselines", "followup-baselines"))

    # 4. trajectory
    t = r["trajectory"]
    if t:
        cv = pd.DataFrame({n: {h: c[h]["mae"] for h in ("24m", "36m", "60m", "all")} for n, c in t["cv"].items()}).T
        cv.index.name = "model (MAE, cells/mm²)"
        test = pd.DataFrame({n: {h: d["errors"][h]["mae"] for h in ("24m", "36m", "60m", "all")}
                             for n, d in t["test"].items()}).T
        test.index.name = "test grafts (used once)"
        cov = t["test"][t["chosen"]].get("band_coverage", {})
        curve = pd.DataFrame(t["learning_curve"]).groupby(["train_grafts", "model"])["mae_all"].mean().unstack() \
            if t["learning_curve"] else pd.DataFrame()
        body = (_kpis([("chosen model", t["chosen"]), ("best baseline", t["best_baseline"])])
                + _table(cv, highlight=t["chosen"], fmt="{:.0f}") + _table(test, fmt="{:.0f}")
                + f'<p class="what">{t["band_level"]} band coverage on test: '
                + ", ".join(f'{h} {d["coverage"]:.0%}' for h, d in cov.items()) + "</p>")
        if not curve.empty:
            curve.index.name = "training grafts"
            body += "<h3>Learning curve (separate simulated cohort)</h3>" + _table(curve, fmt="{:.0f}") \
                + _img(outputs / "trajectory" / "learning_curve.png")
        parts.append(_section(4, "Trajectory models", "Predicted ECD at 24/36/60 months; a simpler model wins near-ties.",
                              body))
        log.append(f"Stage 4 trajectory: chosen {t['chosen']}")
    else:
        parts.append(_missing(4, "Trajectory models", "trajectory"))

    # 5. risk
    rk = r["risk"]
    if rk:
        body = ""
        for ep, e in rk["endpoints"].items():
            cv = pd.DataFrame(e["cv"]).T[["c_index", "auc_12m", "auc_24m", "auc_36m", "brier_24m"]]
            cv.index.name = f"{ep.replace('_', ' ')} (repeated CV)"
            rc = e["recalibration"]
            body += _table(cv, highlight=e["chosen"]) + (
                f'<p class="what">Chosen: <b>{e["chosen"]}</b>. Calibration slope {rc["slope"]:.2f}; mean gap '
                f'predicted vs observed 24-month risk: test {rc["test"]["gap_before"]:.3f} → {rc["test"]["gap_after"]:.3f}, '
                f'separate cohort {rc["external_simulated_cohort"]["gap_before"]:.3f} → '
                f'{rc["external_simulated_cohort"]["gap_after"]:.3f} (isotonic recalibration).</p>')
        body += _img(outputs / "risk" / "calibration_24m.png")
        parts.append(_section(5, "Risk models", "Graft failure and low ECD after the 12-month visit; rejection can only "
                                                "raise risk (clinical sign constraint).", body))
        log.append("Stage 5 risk: " + ", ".join(f"{ep} {e['chosen']}" for ep, e in rk["endpoints"].items()))
    else:
        parts.append(_missing(5, "Risk models", "risk"))

    # 6. explanations
    x = r["followup-explain"]
    if x:
        imp = pd.DataFrame(x["global_importance"])
        imp = (imp / imp.sum() * 100)
        imp.index.name = "reason (% of mean |SHAP|)"
        ex = "".join(f'<li><b>{e["graft"]}</b> ({e["procedure"]}, 12-month ECD {e["ECD_12m"]:.0f}): predicted '
                     f'60-month ECD {e["predicted_ECD_60m"]}; {e["why_trajectory"]}</li>' for e in x["examples"])
        parts.append(_section(6, "Explanations", "SHAP reasons (exact for Cox), descriptive counterfactuals, sanity checks.",
                              _checks_html(x["checks"]) + _table(imp, fmt="{:.0f}") + f"<ul>{ex}</ul>"
                              + _img(outputs / "followup_explain" / "followup_reason_importance.png")))
        log.append(f"Stage 6 explanations: checks pass {x['all_checks_pass']}")
    else:
        parts.append(_missing(6, "Explanations", "followup-explain"))

    # 7. recommendation
    f = r["followup"]
    if f:
        body = f'<p class="what">Rules version {f["rules"].get("version")} (placeholder thresholds until agreed with clinicians).</p>'
        for where, e in f["evaluation"].items():
            df = pd.DataFrame(e["by_alert"]).set_index("alert")[["grafts", "share", "failed_within_12m",
                                                                 "failed_within_24m", "low_ecd_within_24m"]]
            df.index.name = where.replace("_", " ")
            body += _table(df.astype(float), fmt="{:.2f}") + (
                f'<p class="what">Missed deterioration: {e["safety"]["green_failed_within_12m"]} of '
                f'{e["safety"]["green_grafts"]} green grafts failed within 12 months. Visits per graft next year: '
                f'{e["visits"]["recommended_visits_per_graft_year"]:.2f} recommended vs '
                f'{e["visits"]["fixed_visits_per_graft_year"]:.2f} on a fixed 6-monthly schedule.</p>')
        parts.append(_section(7, "Follow-up recommendation", "Alert level and next visit at the 12-month visit; "
                                                             "outcomes are known in the simulation.", body))
        log.append("Stage 7 recommendation")
    else:
        parts.append(_missing(7, "Follow-up recommendation", "followup"))

    # 8. robustness
    rb = r["followup-robustness"]
    if rb:
        df = pd.DataFrame(rb["scenarios"]).T[["grafts", "failures", "trajectory_mae_baseline", "trajectory_mae_gbm",
                                              "gbm_gain_pct", "graft_failure_cox_c_index",
                                              "graft_failure_deepsurv_c_index", "low_ecd_cox_c_index",
                                              "low_ecd_deepsurv_c_index", "literature_patterns_met"]]
        df.index.name = "scenario"
        body = _table(df, fmt="{:.3f}") + (
            f'<p class="what">Gradient boosting beats the best baseline in {rb["gbm_beats_baseline_in"]} scenarios; '
            f'Cox is as good as DeepSurv (within 0.01 C-index or better) in {rb["cox_as_good_as_deepsurv_in"]}.</p>')
        parts.append(_section(8, "Robustness", "Do the conclusions hold when the simulation assumptions change?", body))
        log.append(f"Stage 8 robustness: GBM beats baseline {rb['gbm_beats_baseline_in']}, "
                   f"Cox as good as DeepSurv {rb['cox_as_good_as_deepsurv_in']}")
    else:
        parts.append(_missing(8, "Robustness", "followup-robustness"))

    note = ("Data source: simulated post-transplant cohort calibrated to published studies (method development); "
            "NEBSL follow-up records were not available. The pipeline is data-agnostic and will be rerun on real "
            "follow-up data." if source == "simulated" else f"Data source: {source}.")
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>Part B stage report</title><style>{CSS}</style>"
            f"</head><body><main><h1>Post-transplant follow-up: stage report</h1>"
            f"<p class='sub'>iTRUST Member 4 · generated {date.today().isoformat()}</p>"
            f"<p class='note'>{note}</p>{''.join(parts)}</main></body></html>")
    out = outputs / "report" / "followup_report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out, log
