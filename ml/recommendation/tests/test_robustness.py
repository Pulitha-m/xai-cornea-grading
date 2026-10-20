"""Tests for the robustness check. Small simulated cohorts, short training."""
import numpy as np

from recommendation.data_prep.followup_simulator import PARAMS
from recommendation.evaluation import robustness as rb
from recommendation.risk.models import DeepSurv


def test_scenarios_change_only_what_they_say():
    sc = rb.scenarios()
    assert sc["reference (seed 42)"] == (PARAMS, 42)
    slow, _ = sc["slower cell loss (x0.7)"]
    assert all(np.isclose(slow["decline"][k]["k2"], PARAMS["decline"][k]["k2"] * 0.7) for k in PARAMS["decline"])
    assert slow["missed_visit_prob"] == PARAMS["missed_visit_prob"]
    missing, _ = sc["more missed visits / drop-out"]
    assert missing["missed_visit_prob"] > PARAMS["missed_visit_prob"]
    assert PARAMS["decline"]["PK"]["k2"] == 0.13            # the reference settings are never modified


def test_faster_cell_loss_gives_lower_ecd_and_more_failures():
    slow, _ = rb.cohort(rb.scenarios()["slower cell loss (x0.7)"][0], seed=5, n_grafts=400)
    fast, _ = rb.cohort(rb.scenarios()["faster cell loss (x1.3)"][0], seed=5, n_grafts=400)
    assert fast["ECD_36m"].median() < slow["ECD_36m"].median()
    assert fast["failure_event"].mean() >= slow["failure_event"].mean()


def test_evaluate_returns_the_comparisons():
    table, checks = rb.cohort(PARAMS, seed=7, n_grafts=400)
    res = rb.evaluate(table, {"num_leaves": 4, "n_estimators": 60}, cox_penalty=1.0, repeats=1,
                      deepsurv=lambda: DeepSurv(epochs=40))
    assert res["trajectory_mae_gbm"] > 0 and res["trajectory_mae_baseline"] > 0
    for ep in ("graft_failure", "low_ecd"):
        assert 0 <= res[f"{ep}_cox_c_index"] <= 1 and 0 <= res[f"{ep}_deepsurv_c_index"] <= 1
    assert isinstance(res["gbm_beats_baseline"], bool) and isinstance(res["cox_as_good_as_deepsurv"], bool)
    assert {"pattern", "ok"} <= set(checks.columns)
