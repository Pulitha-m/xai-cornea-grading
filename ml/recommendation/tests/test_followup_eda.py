"""Tests for P1 follow-up EDA and the survival helpers. Simulated / made-up data only."""
import numpy as np
import pandas as pd
import pytest

from recommendation.data_prep.followup_eda import (cohort_source, cohort_summary, run, validate_cohort,
                                                   visit_attendance)
from recommendation.data_prep.followup_simulator import simulate, write
from recommendation.evaluation.survival import kaplan_meier, logrank, survival_at


# ---- Kaplan-Meier and log-rank against hand-worked examples

def test_km_without_censoring_is_empirical_survival():
    km = kaplan_meier([1, 2, 3, 4], [True, True, True, True])
    assert km["survival"].round(3).tolist() == [1.0, 0.75, 0.5, 0.25, 0.0]


def test_km_with_censoring():
    # times 1(event) 2(censored) 3(event) 4(event): S = 1 * 3/4 * 1/2 * 0
    km = kaplan_meier([1, 2, 3, 4], [True, False, True, True])
    assert survival_at(km, 1) == pytest.approx(0.75)
    assert survival_at(km, 2.5) == pytest.approx(0.75)   # censoring does not drop the curve
    assert survival_at(km, 3) == pytest.approx(0.375)
    assert survival_at(km, 4) == pytest.approx(0.0)


def test_km_interval_contains_estimate():
    rng = np.random.default_rng(0)
    km = kaplan_meier(rng.integers(1, 60, 200), rng.random(200) < 0.4)
    assert ((km["lower"] <= km["survival"]) & (km["survival"] <= km["upper"])).all()


def test_logrank_detects_difference_and_not_noise():
    t = np.r_[np.full(30, 5), np.full(30, 50)]
    e = np.ones(60, bool)
    assert logrank(t, e, ["a"] * 30 + ["b"] * 30)["p"] < 0.001
    same = logrank(np.tile([5, 50], 30), e, ["a"] * 30 + ["b"] * 30)
    assert same["p"] > 0.5


# ---- cohort checks

def test_simulated_cohort_passes_every_check():
    g, v = simulate(200, seed=11)
    failed = [c for c in validate_cohort(g, v) if not c["ok"]]
    assert not failed, failed


def test_checks_catch_a_visit_after_failure():
    g, v = simulate(200, seed=12)
    gid, t = g.loc[g["graft_failed"], ["graft_id", "time_to_event_months"]].iloc[0]
    later = [m for m in (12, 24, 36, 48, 60) if m > t][0]
    extra = v[v["graft_id"] == gid].iloc[[-1]].assign(months_after_surgery=later)
    checks = {c["check"]: c["ok"] for c in validate_cohort(g, pd.concat([v, extra]))}
    assert checks["no visits after graft failure"] is False


def test_mixed_data_sources_are_refused():
    g, v = simulate(20, seed=13)
    g.loc[0, "data_source"] = "nebsl"
    with pytest.raises(ValueError):
        cohort_source(g, v)


def test_summary_counts_are_consistent():
    g, v = simulate(150, seed=14)
    s = cohort_summary(g, v)
    assert s["grafts"] == 150 and s["visits"] == len(v)
    assert s["graft_failures"] + s["censored"] == 150
    assert sum(s["procedure"].values()) == 150


def test_attendance_is_a_share_and_counts_only_followed_grafts():
    g, v = simulate(150, seed=15)
    att = visit_attendance(g, v)
    assert att["attendance"].between(0, 1).all()
    assert (att["attended"] <= att["under_observation"]).all()
    assert att["under_observation"].is_monotonic_decreasing


def test_run_writes_outputs_and_states_data_source(tmp_path):
    cohort = tmp_path / "cohort.xlsx"
    write(cohort, n_grafts=120, seed=16)
    res = run(cohort, tmp_path / "out")
    assert res["source"] == "simulated" and res["all_checks_pass"]
    md = (tmp_path / "out" / "followup_eda_summary.md").read_text(encoding="utf-8")
    assert "Data source: simulated cohort" in md
    for f in res["figures"]:
        assert (tmp_path / "out" / f).exists()
