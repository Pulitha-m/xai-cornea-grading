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
    uv run python -m recommendation.main simulate   # SYNTHETIC follow-up dataset (simulation study)
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
    ap.add_argument("--n", type=int, default=500, help="simulate: number of synthetic grafts")
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

        from recommendation.data_prep.synthetic_followup import plot, write

        root = Path(cfg["paths"]["raw_workbook"]).parent.parent / "synthetic"
        root.mkdir(parents=True, exist_ok=True)
        out = root / "followup_SYNTHETIC.xlsx"
        res = write(out, a.n, a.seed)
        fig = plot(out, Path(cfg["paths"]["outputs"]) / "synthetic")
        print("\n*** SYNTHETIC DATA: simulated follow-up, not patient data ***")
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
