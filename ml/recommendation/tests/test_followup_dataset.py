"""Tests for P2: landmark dataset, graft split, train-only preprocessing. Simulated data only."""
import numpy as np
import pandas as pd

from recommendation.data_prep.followup_dataset import (HORIZONS, LANDMARK, FollowupPreprocessor, build, landmark_table,
                                                       leakage_checks, load, split_grafts)
from recommendation.data_prep.followup_simulator import simulate, write


def _table(n=300, seed=21):
    g, v = simulate(n, seed=seed)
    t = landmark_table(g, v)
    t["split"] = split_grafts(t, seed=0).to_numpy()
    return g, v, t


def test_landmark_keeps_only_grafts_alive_and_seen_at_12_months():
    g, v, t = _table()
    assert (t["failure_months_after_landmark"] > 0).all()
    seen = set(v.loc[v["months_after_surgery"] == LANDMARK, "graft_id"])
    assert set(t["graft_id"]) <= seen


def test_inputs_never_use_later_visits():
    g, v, t = _table()
    # change every visit after month 12; the inputs must not move
    v2 = v.astype({"ECD": float, "CV": float, "HEX": float})
    v2.loc[v2["months_after_surgery"] > LANDMARK, ["ECD", "CV", "HEX"]] *= 0.5
    t2 = landmark_table(g, v2)
    pre = FollowupPreprocessor()
    cols = [c for c in pre.numeric]
    pd.testing.assert_frame_equal(t[cols].reset_index(drop=True), t2[cols].reset_index(drop=True))
    assert not t2[[f"ECD_{h}m" for h in HORIZONS]].equals(t[[f"ECD_{h}m" for h in HORIZONS]])


def test_rejection_after_12_months_is_not_an_input():
    g, v, _ = _table()
    late = g["graft_id"].iloc[0]
    g2 = g.copy()
    g2.loc[g2["graft_id"] == late, ["rejection_episode", "rejection_month"]] = [True, 30.0]
    t = landmark_table(g2, v)
    if late in set(t["graft_id"]):
        assert t.loc[t["graft_id"] == late, "rejection_by_12m"].iloc[0] == 0


def test_split_is_by_graft_and_covers_everyone():
    _, _, t = _table()
    assert t["graft_id"].is_unique
    assert set(t["split"]) == {"train", "val", "test"}
    share = t["split"].value_counts(normalize=True)
    assert 0.6 < share["train"] < 0.8


def test_preprocessor_fitted_on_train_only():
    _, _, t = _table()
    train = t[t["split"] == "train"]
    pre = FollowupPreprocessor().fit(train)
    X = pre.transform(train)
    assert np.allclose(X[pre.numeric].mean(), 0, atol=1e-9)
    # changing test rows must not change the fitted values
    t2 = t.copy()
    t2.loc[t2["split"] == "test", "baseline_ECD"] = 9999
    pre2 = FollowupPreprocessor().fit(t2[t2["split"] == "train"])
    assert pre2.means == pre.means and pre2.medians == pre.medians


def test_unseen_category_and_missing_values_are_handled():
    _, _, t = _table()
    pre = FollowupPreprocessor().fit(t[t["split"] == "train"])
    row = t.iloc[[0]].copy()
    row["procedure"] = "NEW_PROCEDURE"
    row["ECD_3m"] = np.nan
    X = pre.transform(row)
    assert not X.isna().any().any()
    assert X.filter(like="procedure=").sum(axis=1).iloc[0] == 0


def test_leakage_checks_all_pass():
    g, v, t = _table()
    pre = FollowupPreprocessor().fit(t[t["split"] == "train"])
    failed = [c for c in leakage_checks(t, pre, v) if not c["ok"]]
    assert not failed, failed


def test_build_and_load_round_trip(tmp_path):
    cohort = tmp_path / "cohort.xlsx"
    write(cohort, n_grafts=300, seed=22)
    res = build(cohort, tmp_path / "landmark.xlsx", tmp_path / "pre.json")
    assert res["all_checks_pass"] and res["source"] == "simulated"
    table, pre = load(tmp_path / "landmark.xlsx", tmp_path / "pre.json")
    assert len(pre.transform(table).columns) == len(res["features"])
