"""End-to-end pipelines for the recommendation module.

Implemented:
    run_matching   build matching dataset -> MCDA ranking -> evaluation

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


def run_trajectory(cfg: dict):
    raise NotImplementedError("Needs recipient follow-up visits (ECD/CV/HEX over time).")


def run_risk(cfg: dict):
    raise NotImplementedError("Needs recipient follow-up visits and the low-ECD endpoint definition.")


def run_followup(cfg: dict):
    raise NotImplementedError("Needs trajectory/risk outputs and clinician follow-up decisions.")
