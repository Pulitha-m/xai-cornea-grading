"""Command-line entry point for the recommendation module.

From ml/:
    uv run python -m recommendation.main matching
    uv run python -m recommendation.main matching --config my_config.yaml --no-rebuild
    uv run python -m recommendation.main ranker
    uv run python -m recommendation.main explain
    uv run python -m recommendation.main analysis   # ablation, learning curve, subgroups, errors
    uv run python -m recommendation.main counterfactual  # "what would make this cornea #1?"
    uv run python -m recommendation.main report     # every stage -> one HTML page
    uv run python -m recommendation.main export     # trained ranker -> ml-service JSON
    uv run python -m recommendation.main pack       # workbook for the NEBSL clinician meeting
    uv run python -m recommendation.main ahp        # weights from the filled AHP sheet (--apply to save)
    uv run python -m recommendation.main simulate   # simulated follow-up cohort (simulation study)
    uv run python -m recommendation.main followup-eda   # P1: describe the follow-up cohort
    uv run python -m recommendation.main followup-data  # P2: landmark dataset, split, preprocessing
    uv run python -m recommendation.main followup-baselines  # P3: trajectory and risk baselines
    uv run python -m recommendation.main trajectory     # P4: GBM / LSTM vs baselines, learning curve
    uv run python -m recommendation.main risk           # P5: Cox / boosted Cox / DeepSurv, calibration
    uv run python -m recommendation.main followup-explain  # P6: SHAP reasons and counterfactuals
    uv run python -m recommendation.main followup       # P7: alert, next visit, review prompts
    uv run python -m recommendation.main followup-export  # P8: follow-up models -> ml-service JSON
"""
import argparse

import pandas as pd

from recommendation import pipeline
from recommendation.config import load_config

TASKS = {
    "matching": pipeline.run_matching,
    "ranker": pipeline.run_ranker,
    "explain": pipeline.run_explain,
    "analysis": pipeline.run_analysis,
    "counterfactual": pipeline.run_counterfactual,
    "report": None,
    "export": None,
    "pack": None,
    "ahp": None,
    "simulate": None,
    "followup-eda": pipeline.run_followup_eda,
    "followup-data": pipeline.run_followup_dataset,
    "followup-baselines": pipeline.run_followup_baselines,
    "followup-explain": pipeline.run_followup_explain,
    "followup-export": None,
    "trajectory": pipeline.run_trajectory,
    "risk": pipeline.run_risk,
    "followup": pipeline.run_followup,
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Recommendation module pipelines")
    ap.add_argument("task", choices=TASKS)
    ap.add_argument("--config", default=None, help="path to a config.yaml (default: module config)")
    ap.add_argument("--no-rebuild", action="store_true", help="reuse the processed dataset if present")
    ap.add_argument("--out", default=None, help="export: where to write the model JSON")
    ap.add_argument("--file", default=None, help="ahp: filled meeting-pack workbook")
    ap.add_argument("--apply", action="store_true", help="ahp: write the weights into config.yaml")
    ap.add_argument("--n", type=int, default=500, help="simulate: number of simulated grafts")
    ap.add_argument("--seed", type=int, default=42, help="simulate: random seed")
    a = ap.parse_args()

    cfg = load_config(a.config)
    if a.task == "matching":
        res = pipeline.run_matching(cfg, rebuild=not a.no_rebuild)
        print(f"\nWeights ({res['weights_version']}):", res["weights"])
        for name in ("all_requests", "test_requests"):
            print(f"\n{name.replace('_', ' ').title()}:")
            print(pd.DataFrame(res[name]).T.to_string(float_format="{:.3f}".format))
        print(f"\nSaved: {cfg['paths']['outputs']}/matching/metrics.json")
    elif a.task == "ranker":
        res = pipeline.run_ranker(cfg)
        _print_ranker(res, cfg)
    elif a.task == "simulate":
        from pathlib import Path

        from recommendation.data_prep.followup_simulator import plot, write

        out = Path(cfg["paths"]["followup_cohort"])
        out.parent.mkdir(parents=True, exist_ok=True)
        res = write(out, a.n, a.seed)
        fig = plot(out, Path(cfg["paths"]["outputs"]) / "simulation")
        print("\nData source: simulated cohort (method development)")
        print(f"Grafts {res['grafts']}, visits {res['visits']}, failed {res['failed']}, "
              f"rejection episodes {res['rejections']}, low-ECD events {res['low_ecd']}")
        print("\nPattern checks against the literature:")
        print(res["checks"].to_string(index=False))
        print(f"\nSaved: {out}\nChart: {fig}")
    elif a.task == "pack":
        from pathlib import Path

        from recommendation.reporting.meeting_pack import build_pack

        out = Path(cfg["paths"]["outputs"]) / "review" / "nebsl_meeting_pack.xlsx"
        counts = build_pack(cfg["paths"]["raw_workbook"], out)
        print("\nMeeting pack sheets (rows):")
        for k, v in counts.items():
            print(f"   {k:<18} {v}")
        print(f"\nSaved: {out}")
        print("Contains NEBSL Tissue_IDs: keep it on this laptop / with NEBSL. Do not email or commit it.")
    elif a.task == "ahp":
        from datetime import date
        from pathlib import Path

        from recommendation.config import MODULE_DIR
        from recommendation.matching.ahp import apply_to_config, combine, matrix, read_form, weights_and_cr

        form = Path(a.file) if a.file else Path(cfg["paths"]["outputs"]) / "review" / "nebsl_meeting_pack.xlsx"
        sets = read_form(form)
        mats = []
        print()
        for k, answers in enumerate(sets, start=1):
            m = matrix(answers)
            mats.append(m)
            w, cr = weights_and_cr(m)
            ok = "consistent" if cr < 0.10 else "INCONSISTENT: ask to revisit some answers"
            print(f"Clinician {k}: CR {cr:.3f} ({ok})")
            print("   " + ", ".join(f"{c} {v:.3f}" for c, v in w.items()))
        w, cr = weights_and_cr(combine(mats))
        print(f"\nCombined ({len(sets)} clinician{'s' if len(sets) > 1 else ''}): CR {cr:.3f}")
        for c, v in w.items():
            print(f"   {c:<18} {v:.3f}")
        if a.apply:
            if cr >= 0.10:
                print("\nNot applied: combined CR is 0.10 or more.")
            else:
                version = f"ahp-{date.today().isoformat()}-n{len(sets)}"
                apply_to_config(Path(a.config) if a.config else MODULE_DIR / "config.yaml", w, version)
                print(f"\nSaved to config.yaml as weights_version {version}")
    elif a.task == "export":
        from pathlib import Path

        from recommendation.matching.export import export_model

        repo_root = Path(__file__).resolve().parents[2]
        out = Path(a.out) if a.out else repo_root / "ml-service" / "models" / "recommendation_ranker.json"
        model = export_model(Path(cfg["paths"]["models"]) / "matching_ranker.joblib", out,
                             Path(cfg["paths"]["outputs"]) / "matching" / "ranker_metrics.json")
        print(f"\nExported {model['name']} ({model['version']}): {len(model['features'])} features")
        if model["summary"]:
            s = model["summary"]
            print(f"  {s['evaluation']}: top-3 ML {s['ml_top3']:.3f} vs MCDA {s['mcda_top3']:.3f}")
        print(f"Saved: {out}")
    elif a.task == "counterfactual":
        _print_counterfactual(pipeline.run_counterfactual(cfg), cfg)
    elif a.task == "analysis":
        _print_analysis(pipeline.run_analysis(cfg), cfg)
    elif a.task == "report":
        from recommendation.reporting.stage_report import build_report

        path, log = build_report(cfg)
        print()
        for line in log:
            print(" OK", line)
        print(f"\nReport: {path}")
    elif a.task == "followup-export":
        from pathlib import Path

        from recommendation.data_prep.followup_dataset import load
        from recommendation.followup.export import export_followup

        repo_root = Path(__file__).resolve().parents[2]
        out = Path(a.out) if a.out else repo_root / "ml-service" / "models" / "recommendation_followup.json"
        models = Path(cfg["paths"]["models"])
        table, _ = load(cfg["paths"]["followup_dataset"], models / "followup_preprocessor.json")
        b = export_followup(models, table, out, cfg["followup"].get("alerts"), Path(cfg["paths"]["outputs"]))
        print(f"\nExported {b['name']} ({b['version']}, data source: {b['data_source']})")
        print(f"  trajectory: {b['trajectory']['name']}, {len(b['trajectory']['trees'])} trees, "
              f"{len(b['trajectory']['features'])} inputs")
        for ep, r in b["risk"].items():
            print(f"  risk {ep}: {r['name']}, {len(r['features'])} inputs, recalibrated at {sorted(r['maps'])} months")
        print(f"  rules: {b['rules'].get('version')}; summary: {b['summary']}")
        print(f"Saved: {out} ({out.stat().st_size / 1024:.0f} KB)")
    elif a.task == "followup":
        _print_followup(pipeline.run_followup(cfg), cfg)
    elif a.task == "followup-explain":
        _print_followup_explain(pipeline.run_followup_explain(cfg), cfg)
    elif a.task == "risk":
        _print_risk(pipeline.run_risk(cfg), cfg)
    elif a.task == "trajectory":
        _print_trajectory(pipeline.run_trajectory(cfg), cfg)
    elif a.task == "followup-baselines":
        _print_followup_baselines(pipeline.run_followup_baselines(cfg), cfg)
    elif a.task == "followup-data":
        _print_followup_data(pipeline.run_followup_dataset(cfg))
    elif a.task == "followup-eda":
        _print_followup_eda(pipeline.run_followup_eda(cfg), cfg)
    elif a.task == "explain":
        res = pipeline.run_explain(cfg)
        _print_explain(res, cfg)
    else:
        TASKS[a.task](cfg)


def _print_counterfactual(res: dict, cfg: dict) -> None:
    print("\n1. What would make each cornea #1? (held-out test requests)")
    for ex in res["examples"]:
        print(f"\n   {ex['request']} (actually allocated: {ex['allocated']})")
        for line in ex["lines"]:
            print(f"     {line}")
    s = res["summary"]
    print(f"\n2. Allocated cornea vs model #1, all {s['requests']} requests:")
    for k, v in s["outcome"].items():
        print(f"   {k:<26} {v:>4}")
    print("\n   Actionable changes that would have been enough:")
    for k, v in s["actionable_kinds"].items():
        print(f"   {k:<26} {v:>4}")
    if s["median_days_fewer"] is not None:
        print(f"   median days fewer in storage needed: {s['median_days_fewer']:.0f}")
    out = f"{cfg['paths']['outputs']}/explain"
    print(f"\nSaved: {out}/counterfactuals.md, {out}/counterfactuals.json")


def _print_analysis(res: dict, cfg: dict) -> None:
    abl = pd.DataFrame(res["ablation"]).T
    print("\n1. Ablation (remove one factor at a time):")
    print(abl[["top3", "mrr", "mrr_change"]].to_string(
        formatters={"top3": "{:.3f}".format, "mrr": "{:.3f}".format, "mrr_change": "{:+.3f}".format}))
    curve = pd.DataFrame(res["learning_curve"]).set_index("train_requests")
    print("\n2. Learning curve (does more data help?):")
    print(curve[["ml_top3", "ml_mrr", "mcda_mrr"]].to_string(float_format="{:.3f}".format))
    sub = pd.DataFrame(res["subgroups"]).set_index(["subgroup", "level"])
    print("\n3. Subgroups (ML vs MCDA):")
    print(sub[["requests", "ml_top3", "mcda_top3", "ml_mrr", "mcda_mrr"]].to_string(float_format="{:.3f}".format))
    e = res["errors"]
    print(f"\n4. Errors: allocated cornea ranked below #5 in {e['missed']} of {e['requests']} requests "
          f"({e['missed_share']:.0%}). In those requests:")
    print(pd.DataFrame(e["comparison"]).T.to_string(float_format="{:.2f}".format))
    out = f"{cfg['paths']['outputs']}/analysis"
    print(f"\nSaved: {out}/analysis_summary.md, {out}/ablation.png, {out}/learning_curve.png")


def _print_explain(res: dict, cfg: dict) -> None:
    print("\n1. What changes the order of candidates (share of |SHAP|, relative to each pool):")
    for k, v in res["reason_importance"].items():
        print(f"   {k:<18} {v:>5.0%}  {'#' * round(v * 50)}")
    print("\n2. Why #1? Examples from held-out test requests:")
    for ex in res["examples"]:
        print(f"\n   {ex['request']}: wants {ex['requested_grade']}, {ex['surgery']}, {ex['pool']} candidates"
              f" (allocated cornea ranked #{ex['allocated_rank']:.0f})")
        for c in ex["top3"]:
            tag = "  <- allocated" if c["Label_Allocated"] == 1 else ""
            print(f"     #{c['ML_Rank']:.0f} {c['Candidate_Record_ID']} grade {c['Cand_Tissue_Grade']}, "
                  f"{c['Cand_Days_In_Storage']} d in storage: {c['Why']}{tag}")
    out = f"{cfg['paths']['outputs']}/explain"
    print(f"\nSaved: {out}/shap_summary.md, {out}/shap_global_reasons.png, {out}/explanations.xlsx")


def _print_followup(res: dict, cfg: dict) -> None:
    print(f"\nData source: {res['source']}. Rules {res['rules'].get('version')} (placeholder thresholds)")
    for where, e in res["evaluation"].items():
        print(f"\n== What happened next, {where.replace('_', ' ')}:")
        print(pd.DataFrame(e["by_alert"]).set_index("alert").to_string(formatters={"share": "{:.0%}".format}))
        s, vb = e["safety"], e["visits"]
        print(f"   missed deterioration: {s['green_failed_within_12m']} of {s['green_grafts']} green grafts failed within 12 months")
        print(f"   visits per graft next year: {vb['recommended_visits_per_graft_year']:.2f} recommended vs "
              f"{vb['fixed_visits_per_graft_year']:.2f} fixed {vb['fixed_schedule_months']}-monthly")
    print("\n== Example test grafts")
    for x in res["examples"]:
        print(f"\n   {x['graft']}: {x['alert'].upper()}, next visit in {x['next_visit_months']} months "
              f"(12-month ECD {x['ecd_12m']:.0f})")
        print("     predicted ECD (80% band): " + "; ".join(f"{h} m {v[1]} ({v[0]}-{v[2]})" for h, v in x["predicted_ecd"].items()))
        print(f"     risk by 24 months: failure {x['failure_risk_24m']:.0%}, ECD<1000 {x['low_ecd_risk_24m']:.0%}")
        print(f"     why: {', '.join(x['rules_fired']) or 'no alert rule fired'}")
        if x["model_reasons"]:
            print(f"     model reasons: {x['model_reasons']}")
        print("     suggested: " + "; ".join(x["actions"]))
    out = f"{cfg['paths']['outputs']}/followup"
    print(f"\n{res['disclaimer']}")
    print(f"Saved: {out}/followup_summary.md, {out}/followup_recommendations.json")


def _print_followup_explain(res: dict, cfg: dict) -> None:
    print(f"\nData source: {res['source']}")
    print("\n1. Sanity checks:")
    for c in res["checks"]:
        print(f"   {'ok  ' if c['ok'] else 'FAIL'} {c['check']:<58} {c['detail']}")
    print("\n2. What drives the predictions (share of mean |SHAP|):")
    for name, vals in res["global_importance"].items():
        s = pd.Series(vals)
        s = (s / s.sum() * 100).sort_values(ascending=False)
        print(f"   {name:<24} " + ", ".join(f"{k} {v:.0f}%" for k, v in s.items() if v >= 1))
    print("\n3. Example test grafts:")
    for e in res["examples"]:
        print(f"\n   {e['graft']} ({e['procedure']}, 12-month ECD {e['ECD_12m']:.0f})")
        print(f"     predicted 60-month ECD {e['predicted_ECD_60m']}: {e['why_trajectory']}")
        if e["trajectory_counterfactual"]:
            print(f"       {e['trajectory_counterfactual']}")
        for ep in ("graft_failure", "low_ecd"):
            d = e[ep]
            if "note" in d:
                print(f"     {ep}: {d['note']}")
                continue
            print(f"     {ep} risk {d['risk_24m']:.0%}: {d['why']}")
            if d["counterfactual"]:
                print(f"       {d['counterfactual']}")
    out = f"{cfg['paths']['outputs']}/followup_explain"
    print(f"\nAll checks pass: {res['all_checks_pass']}")
    print(f"Saved: {out}/followup_explain_summary.md, {out}/followup_explanations.json, "
          f"{out}/followup_reason_importance.png")


def _print_risk(res: dict, cfg: dict) -> None:
    print(f"\nData source: {res['source']}")
    print(f"Settings (CV on training grafts): {res['settings']}")
    for endpoint, e in res["endpoints"].items():
        print(f"\n== {endpoint.replace('_', ' ')} (times = months after the 12-month visit)")
        print("Repeated CV:")
        rows = {n: {k: c[k] for k in ("c_index", "auc_12m", "auc_24m", "auc_36m", "brier_24m")}
                for n, c in e["cv"].items()}
        print(pd.DataFrame(rows).T.to_string(float_format="{:.3f}".format))
        print(f"   Chosen: {e['chosen']}")
        print("Test grafts (used once):")
        rows = {n: {k: c[k] for k in ("events", "c_index", "auc_24m", "brier_24m")} for n, c in e["test"].items()}
        print(pd.DataFrame(rows).T.to_string(float_format="{:.3f}".format))
        cal = pd.DataFrame(e["calibration_24m"]).set_index("group")
        print("Calibration at 24 months (out-of-fold): predicted vs observed risk")
        print(cal[["n", "events", "predicted_risk", "observed_risk"]].to_string(float_format="{:.3f}".format))
        rc = e["recalibration"]
        print(f"Calibration slope {rc['slope']:.2f} (1 = well scaled). Isotonic recalibration, "
              "mean gap predicted vs observed:")
        for where in ("test", "external_simulated_cohort"):
            print(f"   {where:<27} before {rc[where]['gap_before']:.3f}  after {rc[where]['gap_after']:.3f}")
        after = pd.DataFrame(rc["external_simulated_cohort"]["after"]).set_index("group")
        print("   external cohort after recalibration (predicted vs observed):")
        print(after[["n", "predicted_risk", "observed_risk"]].to_string(float_format="{:.3f}".format))
    out = f"{cfg['paths']['outputs']}/risk"
    print(f"\nSaved: {out}/risk_summary.md, {out}/risk_results.json, {out}/calibration_24m.png")
    print(f"Models: {cfg['paths']['models']}/followup_risk.joblib")


def _print_trajectory(res: dict, cfg: dict) -> None:
    print(f"\nData source: {res['source']}")
    print(f"\n1. Gradient-boosting settings (CV on training grafts): {res['tuning']['selected']}")
    print("\n2. Repeated CV, MAE of predicted ECD (cells/mm2):")
    rows = {n: {h: c[h]["mae"] for h in ("24m", "36m", "60m", "all")} for n, c in res["cv"].items()}
    print(pd.DataFrame(rows).T.to_string(float_format="{:.0f}".format))
    print(f"   Chosen: {res['chosen']}   (best baseline: {res['best_baseline']})")
    print("\n3. Test grafts (used once), MAE:")
    rows = {n: {h: d["errors"][h]["mae"] for h in ("24m", "36m", "60m", "all")} for n, d in res["test"].items()}
    print(pd.DataFrame(rows).T.to_string(float_format="{:.0f}".format))
    cov = res["test"][res["chosen"]].get("band_coverage", {})
    print(f"   {res['band_level']} band coverage on test: " + ", ".join(f"{h} {d['coverage']:.0%}" for h, d in cov.items()))
    if res["learning_curve"]:
        curve = pd.DataFrame(res["learning_curve"]).groupby(["train_grafts", "model"])["mae_all"].mean().unstack()
        print("\n4. Learning curve (MAE, separate simulated cohort):")
        print(curve.to_string(float_format="{:.0f}".format))
    out = f"{cfg['paths']['outputs']}/trajectory"
    print(f"\nSaved: {out}/trajectory_summary.md, {out}/trajectory_results.json, {out}/learning_curve.png")
    print(f"Model: {cfg['paths']['models']}/followup_trajectory.joblib")


def _print_followup_baselines(res: dict, cfg: dict) -> None:
    print(f"\nData source: {res['source']}. Train {res['train_grafts']} grafts, validation "
          f"{res['validation_grafts']}, repeated CV over {res['cv_grafts']}; test {res['test_grafts_untouched']} untouched.")
    print("\n1. Trajectory baselines: MAE of predicted ECD (cells/mm2), repeated CV")
    rows = {n: {h: d["repeated_cv"][h]["mae"] for h in ("24m", "36m", "60m", "all")}
            for n, d in res["trajectory"].items()}
    print(pd.DataFrame(rows).T.to_string(float_format="{:.0f}".format))
    for endpoint, models in res["risk"].items():
        print(f"\n2. Risk baselines, {endpoint.replace('_', ' ')} (repeated CV; times = months after 12-month visit)")
        rows = {n: {k: d["repeated_cv"][k] for k in ("c_index", "auc_12m", "auc_24m", "auc_36m", "brier_24m")}
                for n, d in models.items()}
        print(pd.DataFrame(rows).T.to_string(float_format="{:.3f}".format))
    out = f"{cfg['paths']['outputs']}/followup_baselines"
    print(f"\nSaved: {out}/baselines_summary.md, {out}/baselines.json")


def _print_followup_data(res: dict) -> None:
    s = res["summary"]
    print(f"\nData source: {res['source']}")
    print(f"Design: predict at month {s['landmark_month']} from visits {s['input_months']}; "
          f"ECD targets at {s['horizons']} months; {s['n_features']} model inputs")
    print("\n1. Split by graft:")
    print(pd.DataFrame(s["splits"]).T.to_string())
    if s["missing_inputs"]:
        print("\n2. Missing inputs (imputed with the training median, flagged): " +
              ", ".join(f"{k} {v}" for k, v in s["missing_inputs"].items()))
    print("\n3. Leakage checks:")
    for c in res["checks"]:
        print(f"   {'ok  ' if c['ok'] else 'FAIL'} {c['check']:<54} {c['detail']}")
    print(f"\nAll checks pass: {res['all_checks_pass']}")
    print(f"Saved: {res['dataset']}\nPreprocessor: {res['preprocessor']}")


def _print_followup_eda(res: dict, cfg: dict) -> None:
    src, s = res["source"], res["summary"]
    print(f"\nData source: {src}")
    print("\n1. Data checks:")
    for c in res["checks"]:
        print(f"   {'ok  ' if c['ok'] else 'FAIL'} {c['check']:<44} {c['detail']}")
    print(f"\n2. Cohort: {s['grafts']} grafts, {s['visits']} visits "
          f"(median {s['visits_per_graft_median']:.0f} per graft), median follow-up {s['follow_up_months_median']:.1f} months")
    print(f"   failures {s['graft_failures']}, censored {s['censored']}, low-ECD events {s['low_ecd_events']}, "
          f"rejection episodes {s['rejection_episodes']}")
    trend = pd.DataFrame(res["measures_over_time"])
    print("\n3. Median ECD (cells/mm2), month 0 = donor:")
    print(trend.pivot(index="months_after_surgery", columns="procedure", values="ecd_median").to_string(
        float_format="{:.0f}".format))
    for name, title in (("graft_failure", "graft failure"), ("low_ecd", "low ECD (<1000)")):
        e = res["survival"][name]
        print(f"\n4. Kaplan-Meier, {title}: " + ", ".join(f"{k} {v}" for k, v in e["overall"].items()))
        for by, d in e["logrank"].items():
            groups = ", ".join(f"{lv} {g['S(60)']}" for lv, g in e["by"][by].items())
            print(f"   by {by:<17} S(60): {groups}   log-rank p {d['p']:.4f}")
    att = pd.DataFrame(res["visit_attendance"])
    print("\n5. Visit attendance among grafts still followed: " + ", ".join(
        f"{m} mo {a:.0%}" for m, a in zip(att["month"], att["attendance"])))
    rej = pd.DataFrame(res["rejection_effect"]).set_index("month")
    if {"rejection", "no_rejection"} <= set(rej.columns):
        print("\n6. Median cell loss, rejection vs none: " + ", ".join(
            f"{m} mo {r:.0%} vs {n:.0%}" for m, r, n in zip(rej.index, rej["rejection"], rej["no_rejection"])
            if m in (12, 36, 60)))
    out = f"{cfg['paths']['outputs']}/followup_eda"
    print(f"\nAll checks pass: {res['all_checks_pass']}")
    print(f"Saved: {out}/followup_eda_summary.md, {out}/followup_eda.json, figures: {', '.join(res['figures'])}")


def _print_ranker(res: dict, cfg: dict) -> None:
    cols = ["top1", "top3", "mrr"]
    print("\n1. Model selection (5-fold grouped CV on training requests):")
    for r in res["model_selection_cv"]:
        print(f"   {r['settings']:<62} MRR {r['cv_mrr']:.3f}  top3 {r['cv_top3']:.3f}")
    print(f"   Selected: {res['selected_model']}")

    print("\n2. Held-out test requests:")
    print(pd.DataFrame(res["held_out_test"]).T[["requests"] + cols].to_string(float_format="{:.3f}".format))

    rc = res["repeated_cv_all_requests"]
    print(f"\n3. All {rc['requests']} requests, {rc['repeats']}x {rc['folds']}-fold grouped CV:")
    print(pd.DataFrame(rc["methods"]).T[cols].to_string(float_format="{:.3f}".format))
    for metric, d in rc["difference"].items():
        lo, hi = d["ci95"]
        print(f"   ML - MCDA {metric}: {d['ml_minus_mcda']:+.3f}  (95% CI {lo:+.3f} to {hi:+.3f})")

    ts = res["time_split_2024_to_2025"]
    print(f"\n4. Time split (train up to 2024: {ts['train_requests']} requests, test 2025):")
    rows = {k: v for k, v in ts.items() if isinstance(v, dict)}
    print(pd.DataFrame(rows).T[["requests"] + cols].to_string(float_format="{:.3f}".format))

    if res["feature_weights"]:
        print("\n5. Strongest features (+ pushes a cornea up the list):")
        for k, v in list(res["feature_weights"].items())[:8]:
            print(f"   {k:<38} {v:+.3f}")
    print(f"\nSaved: {cfg['paths']['outputs']}/matching/ranker_metrics.json")
    print(f"Model: {cfg['paths']['models']}/matching_ranker.joblib")


if __name__ == "__main__":
    main()
