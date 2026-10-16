"""Command-line entry point for the recommendation module.

From ml/:
    uv run python -m recommendation.main matching
    uv run python -m recommendation.main matching --config my_config.yaml --no-rebuild
    uv run python -m recommendation.main ranker
"""
import argparse

import pandas as pd

from recommendation import pipeline
from recommendation.config import load_config

TASKS = {
    "matching": pipeline.run_matching,
    "ranker": pipeline.run_ranker,
    "trajectory": pipeline.run_trajectory,
    "risk": pipeline.run_risk,
    "followup": pipeline.run_followup,
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Recommendation module pipelines")
    ap.add_argument("task", choices=TASKS)
    ap.add_argument("--config", default=None, help="path to a config.yaml (default: module config)")
    ap.add_argument("--no-rebuild", action="store_true", help="reuse the processed dataset if present")
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
    else:
        TASKS[a.task](cfg)


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
