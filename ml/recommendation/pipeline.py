"""End-to-end pipelines for the recommendation module.

Implemented:
    run_matching   build matching dataset -> MCDA ranking -> evaluation
    run_ranker     train the ML ranker on the same split and compare it with MCDA

Planned (need recipient follow-up data from NEBSL):
    run_trajectory, run_risk, run_followup
"""
import json
from pathlib import Path

import pandas as pd

from recommendation.data_prep.build_matching_dataset import build
from recommendation.evaluation.metrics import compare
from recommendation.evaluation.split import grouped_split
from recommendation.matching.mcda import Weights, score


def run_matching(cfg: dict, rebuild: bool = True) -> dict:
    paths, split, m = cfg["paths"], cfg["split"], cfg["matching"]

    dataset = Path(paths["matching_dataset"])
    if rebuild or not dataset.exists():
        dataset.parent.mkdir(parents=True, exist_ok=True)
        build(paths["raw_workbook"], str(dataset), storage_days=m["storage_days"])
    pairs = pd.read_excel(dataset, sheet_name="Ranking_Pairs")

    weights = Weights(**m["weights"])
    scored = score(pairs, weights)
    _, test = grouped_split(scored, group_col=split["group_col"],
                            test_size=split["test_size"], seed=split["seed"])

    results = {
        "weights_version": m["weights_version"],
        "weights": weights.normalised(),
        "split": split,
        "all_requests": compare(scored).round(4).to_dict(orient="index"),
        "test_requests": compare(test).round(4).to_dict(orient="index"),
    }
    out = Path(paths["outputs"]) / "matching"
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(results, indent=2))
    return results


def run_ranker(cfg: dict) -> dict:
    """Select, train and evaluate the ML ranker; save the model and its metrics.

    Three evaluations, all by whole requests:
      1. held-out test requests (same 80/20 split as MCDA)
      2. repeated 5-fold grouped CV over all requests, with a bootstrap interval
      3. time-based: train on requests up to 2024, test on 2025
    """
    import joblib

    from recommendation.evaluation.metrics import grade_only_rank, random_baseline, ranking_metrics
    from recommendation.matching.features import FEATURES
    from recommendation.matching.ranker import Ranker, repeated_cv_comparison, select

    paths, split, m = cfg["paths"], cfg["split"], cfg["matching"]
    seed = split["seed"]
    pairs = pd.read_excel(paths["matching_dataset"], sheet_name="Ranking_Pairs")
    scored = score(pairs, Weights(**m["weights"]))
    train, test = grouped_split(scored, group_col=split["group_col"],
                                test_size=split["test_size"], seed=seed)

    # 1. choose the model on training requests only, then test once
    best, cv_table = select(train, seed=seed)
    model = Ranker(best).fit(train, seed)
    test = model.rank(test)
    held_out = compare(test).round(4).to_dict(orient="index")
    held_out["ML ranker"] = {k: round(v, 4) for k, v in ranking_metrics(test, "ML_Rank").items()}

    # 2. repeated grouped CV over all requests
    repeated = repeated_cv_comparison(scored, best, seed=seed)

    # 3. time-based check
    year = pd.to_datetime(scored["Request_Date"]).dt.year
    early, late = scored[year <= 2024], scored[year == 2025].copy()
    late = Ranker(best).fit(early, seed).rank(late)
    late["Grade_Rank"] = grade_only_rank(late)
    time_split = {
        "train_requests": int(early["Request_ID"].nunique()),
        "Random (expected)": {k: round(v, 4) for k, v in random_baseline(late).items()},
        "Grade-only rule": {k: round(v, 4) for k, v in ranking_metrics(late, "Grade_Rank").items()},
        "MCDA": {k: round(v, 4) for k, v in ranking_metrics(late, "MCDA_Rank").items()},
        "ML ranker": {k: round(v, 4) for k, v in ranking_metrics(late, "ML_Rank").items()},
    }

    # final model for the app: trained on all requests
    final = Ranker(best).fit(scored, seed)
    models = Path(paths["models"])
    models.mkdir(parents=True, exist_ok=True)
    joblib.dump({"settings": best, "features": FEATURES, "estimator": final.estimator},
                models / "matching_ranker.joblib")

    weights = final.weights()
    results = {
        "selected_model": best,
        "model_selection_cv": cv_table.assign(settings=cv_table["settings"].astype(str))
                                      .to_dict(orient="records"),
        "held_out_test": held_out,
        "repeated_cv_all_requests": repeated,
        "time_split_2024_to_2025": time_split,
        "feature_weights": None if weights is None else weights.round(4).to_dict(),
    }
    out = Path(paths["outputs"]) / "matching"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ranker_metrics.json").write_text(json.dumps(results, indent=2, default=str))
    return results


def run_trajectory(cfg: dict):
    raise NotImplementedError("Needs recipient follow-up visits (ECD/CV/HEX over time).")


def run_risk(cfg: dict):
    raise NotImplementedError("Needs recipient follow-up visits and the low-ECD endpoint definition.")


def run_followup(cfg: dict):
    raise NotImplementedError("Needs trajectory/risk outputs and clinician follow-up decisions.")
