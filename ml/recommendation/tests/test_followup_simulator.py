"""Tests for the follow-up simulator."""
from recommendation.data_prep.followup_simulator import simulate, validate


def test_every_row_records_its_data_source():
    g, v = simulate(100, seed=1)
    assert (g["data_source"] == "simulated").all() and (v["data_source"] == "simulated").all()
    assert g["graft_id"].str.fullmatch(r"G\d{4}").all()


def test_same_seed_gives_same_data():
    a, _ = simulate(50, seed=3)
    b, _ = simulate(50, seed=3)
    assert a.equals(b)


def test_patterns_match_literature_targets():
    g, v = simulate(500, seed=42)
    checks = validate(g, v)
    assert checks["ok"].all(), checks


def test_no_visits_after_graft_failure():
    g, v = simulate(300, seed=5)
    failed = g[g["graft_failed"]].set_index("graft_id")["time_to_event_months"]
    for gid, t in failed.items():
        assert v.loc[v["graft_id"] == gid, "months_after_surgery"].max() <= t


def test_ecd_declines_on_average():
    g, v = simulate(300, seed=6)
    first, last = v.groupby("graft_id")["ECD"].first(), v.groupby("graft_id")["ECD"].last()
    assert (last <= first).mean() > 0.8
