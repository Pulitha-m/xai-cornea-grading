"""Tests for the model analysis (ablation, learning curve, subgroups). Made-up data only."""
from recommendation.evaluation import analysis as A
from recommendation.matching.mcda import score
from recommendation.tests.test_ranker import _pairs

SETTINGS = {"model": "logistic", "C": 1.0}


def _scored():
    p = _pairs(n_requests=30)
    p["Requested_Grade"] = "A"
    p["Request_Urgency"] = "Routine"
    return score(p)


def test_cv_ranks_has_one_row_per_request_per_repeat():
    r = A.cv_ranks(_scored(), SETTINGS, repeats=2)
    assert len(r) == 2 * 30
    assert {"ML_Rank", "MCDA_Rank", "Grade_Rank"} <= set(r.columns)


def test_ablation_has_reference_and_one_row_per_reason():
    t = A.ablation(_scored(), SETTINGS, repeats=1)
    assert "all features" in t.index
    assert t.loc["all features", "mrr_change"] == 0
    assert "without grade match" in t.index


def test_learning_curve_uses_fewer_requests():
    c = A.learning_curve(_scored(), SETTINGS, fractions=(0.5, 1.0), repeats=1)
    assert c["train_requests"].iloc[0] < c["train_requests"].iloc[1]


def test_subgroups_respect_minimum_size():
    s = _scored()
    sub = A.subgroups(s, A.cv_ranks(s, SETTINGS, repeats=1), min_requests=8)
    assert (sub["requests"] >= 8).all()
