"""Tests for counterfactual explanations. Small made-up data only."""
from recommendation.explain.counterfactual import counterfactuals, describe
from recommendation.matching.ranker import Ranker
from recommendation.tests.test_ranker import _pairs


def _setup():
    """Train on made-up data where fresher, better-matched corneas are chosen."""
    train = _pairs(n_requests=40)
    train["Cand_Days_In_Storage"] = [1 if lab else 8 for lab in train["Label_Allocated"]]
    ranker = Ranker({"model": "logistic", "C": 1.0}).fit(train)
    pool = _pairs(n_requests=1, seed=5)
    pool["Cand_Days_In_Storage"] = 5
    pool.loc[pool.index[0], "Cand_Days_In_Storage"] = 2   # best match, fresh -> #1
    pool.loc[pool.index[1], "Grade_Gap"] = 0.0          # same grade, but older
    pool.loc[pool.index[1], "Cand_Tissue_Grade"] = "A"
    pool.loc[pool.index[1], "Cand_ECD"] = 3300
    pool.loc[pool.index[1], "Cand_Days_In_Storage"] = 9
    return ranker, pool


def test_fresher_storage_can_make_a_cornea_first():
    ranker, pool = _setup()
    rid = pool.loc[pool.index[1], "Candidate_Record_ID"]
    cf = counterfactuals(ranker, pool, rid)
    assert cf["current_rank"] > 1
    assert any(any(c.startswith("stored") for c in o["changes"]) for o in cf["options"])
    assert all(o["new_rank"] == 1 for o in cf["options"])


def test_storage_days_never_go_below_zero():
    ranker, pool = _setup()
    rid = pool.loc[pool.index[1], "Candidate_Record_ID"]
    for o in counterfactuals(ranker, pool, rid)["options"]:
        for c in o["changes"]:
            if c.startswith("stored"):
                assert int(c.split()[1]) <= 9


def test_first_ranked_needs_no_change():
    ranker, pool = _setup()
    top = ranker.rank(pool).sort_values("ML_Rank")["Candidate_Record_ID"].iloc[0]
    cf = counterfactuals(ranker, pool, top)
    assert cf["options"] == [] and "already ranked #1" in describe(cf)


def test_positive_serology_is_never_made_eligible():
    ranker, pool = _setup()
    pool.loc[pool.index[2], "Cand_Serology_Clear"] = "No"
    rid = pool.loc[pool.index[2], "Candidate_Record_ID"]
    assert counterfactuals(ranker, pool, rid)["options"] == []


def test_describe_marks_descriptive_changes():
    cf = {"record_id": "R1", "current_rank": 3.0,
          "options": [{"changes": ["ECD 300 cells/mm2 higher"], "actionable": False}]}
    assert "[descriptive]" in describe(cf)
