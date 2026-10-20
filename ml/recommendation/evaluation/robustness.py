"""Robustness of the post-transplant conclusions to the simulation assumptions.

The follow-up cohort is simulated, so its parameters are assumptions. This reruns the core
P4 / P5 comparisons on cohorts simulated under different assumptions and checks whether the
conclusions hold:

  trajectory   does gradient boosting still beat the best simple baseline (population decay)?
  risk         is the simple Cox model (clinical inputs) still as good as DeepSurv
               (C-index within the 0.01 near-tie margin, or better)?

Scenarios: the reference settings with three other random seeds, slower and faster chronic
cell loss (x0.7 / x1.3), and more missed visits and loss to follow-up. Each cohort is built
exactly like the main one (landmark table, graft-level split) and scored by repeated CV over
its training + validation grafts. Model settings are the ones chosen in P4 / P5, not re-tuned,
so this tests the conclusions rather than running a new search.
"""
import copy

import numpy as np
import pandas as pd

from recommendation.data_prep.followup_dataset import landmark_table, split_grafts
from recommendation.data_prep.followup_simulator import PARAMS, simulate, validate
from recommendation.evaluation import followup_eval as fe
from recommendation.risk.cox import CoxPH
from recommendation.risk.experiment import COX_CLINICAL, TIE_MARGIN
from recommendation.risk.models import DeepSurv
from recommendation.trajectory.baselines import PopulationDecay
from recommendation.trajectory.models import GradientBoosting


def _scaled_decline(p: dict, factor: float) -> dict:
    q = copy.deepcopy(p)
    for d in q["decline"].values():
        d["k2"] *= factor
    return q


def scenarios() -> dict:
    """name -> (simulator parameters, seed)."""
    more_missing = copy.deepcopy(PARAMS)
    more_missing["missed_visit_prob"] = 0.30
    more_missing["dropout_per_year"] = 0.16
    return {
        "reference (seed 42)": (PARAMS, 42),
        "reference, seed 1": (PARAMS, 1),
        "reference, seed 2": (PARAMS, 2),
        "reference, seed 3": (PARAMS, 3),
        "slower cell loss (x0.7)": (_scaled_decline(PARAMS, 0.7), 42),
        "faster cell loss (x1.3)": (_scaled_decline(PARAMS, 1.3), 42),
        "more missed visits / drop-out": (more_missing, 42),
    }


def cohort(p: dict, seed: int, n_grafts: int = 500) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Landmark table with a graft-level split, plus the literature pattern checks."""
    g, v = simulate(n_grafts, seed=seed, p=p)
    checks = validate(g, v, p)
    t = landmark_table(g, v)
    t["split"] = split_grafts(t, seed=seed).to_numpy()
    return t, checks


def evaluate(table: pd.DataFrame, gbm_params: dict, cox_penalty: float, repeats: int = 2, seed: int = 42,
             deepsurv=None) -> dict:
    dev = table[table["split"] != "test"]
    base = fe.cv_trajectory(PopulationDecay, dev, repeats=repeats, seed=seed)["all"]["mae"]
    gbm = fe.cv_trajectory(lambda: GradientBoosting(**gbm_params, seed=seed), dev, repeats=repeats, seed=seed)["all"]["mae"]
    deepsurv = deepsurv or (lambda: DeepSurv(seed=seed))
    risk = {}
    for endpoint in fe.ENDPOINTS:
        cox = fe.cv_risk(lambda: CoxPH(penalty=cox_penalty), dev, endpoint, COX_CLINICAL, repeats=repeats, seed=seed)
        ds = fe.cv_risk(deepsurv, dev, endpoint, None, repeats=repeats, seed=seed)
        risk[endpoint] = {"cox_c_index": cox["c_index"], "deepsurv_c_index": ds["c_index"]}
    return {
        "grafts": int(len(table)), "failures": int(table["failure_event"].sum()),
        "trajectory_mae_baseline": base, "trajectory_mae_gbm": gbm,
        "gbm_beats_baseline": bool(gbm < base), "gbm_gain_pct": float((base - gbm) / base * 100),
        **{f"{ep}_{k}": v for ep, d in risk.items() for k, v in d.items()},
        "cox_as_good_as_deepsurv": bool(all(d["cox_c_index"] >= d["deepsurv_c_index"] - TIE_MARGIN for d in risk.values())),
    }


def run(gbm_params: dict, cox_penalty: float, repeats: int = 2, n_grafts: int = 500, which=None) -> dict:
    rows = {}
    for name, (p, seed) in scenarios().items():
        if which and name not in which:
            continue
        table, checks = cohort(p, seed, n_grafts)
        res = evaluate(table, gbm_params, cox_penalty, repeats=repeats, seed=seed)
        res["literature_patterns_met"] = f"{int(checks['ok'].sum())}/{len(checks)}"
        rows[name] = res
    df = pd.DataFrame(rows).T
    return {
        "scenarios": rows,
        "gbm_beats_baseline_in": f"{int(df['gbm_beats_baseline'].sum())}/{len(df)}",
        "cox_as_good_as_deepsurv_in": f"{int(df['cox_as_good_as_deepsurv'].sum())}/{len(df)}",
        "gbm_gain_pct_range": [float(np.min(df["gbm_gain_pct"])), float(np.max(df["gbm_gain_pct"]))],
        "settings": {"gbm": gbm_params, "cox_clinical_penalty": cox_penalty, "repeats": repeats, "n_grafts": n_grafts},
    }
