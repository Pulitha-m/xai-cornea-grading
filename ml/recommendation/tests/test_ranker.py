"""Tests for the ML ranker features and model. Small made-up data only."""
import numpy as np
import pandas as pd

from recommendation.matching.features import FEATURES, NOT_FEATURES, build_features
from recommendation.matching.ranker import Ranker


def _pairs(n_requests=30, pool=6, seed=0):
    """Made-up requests where the allocated cornea is always the exact grade match
    with the highest ECD, so a working ranker should learn to put it first."""
    rng = np.random.default_rng(seed)
    rows = []
    for q in range(n_requests):
        gaps = rng.choice([-1, 0, 1], size=pool)
        gaps[0] = 0
        ecd = rng.uniform(2000, 3000, size=pool)
        ecd[0] = 3400
        for i in range(pool):
            rows.append({
                "Request_ID": f"Q{q:03d}", "Candidate_Record_ID": f"R{q:03d}{i}",
                "Surgery_Type": "PK", "Cand_Serology_Clear": "Yes",
                "Cand_Tissue_Grade": {-1: "B", 0: "A", 1: "A+"}[gaps[i]],
                "Grade_Gap": float(gaps[i]), "Cand_ECD": ecd[i], "Cand_CV": 35.0, "Cand_HEX": 55.0,
                "Cand_Days_In_Storage": int(rng.integers(0, 14)), "Cand_Donor_Age": 55.0,
                "Cand_Death_to_Preservation_h": 2.0, "Label_Allocated": int(i == 0),
            })
    return pd.DataFrame(rows)


def test_features_have_fixed_columns_and_no_leakage():
    X = build_features(_pairs(3))
    assert list(X.columns) == FEATURES
    assert not set(X.columns) & NOT_FEATURES


def test_pool_percentiles_are_within_each_request():
    X = build_features(_pairs(2))
    assert X["Cand_ECD_PoolPct"].between(0, 1).all()
    assert X["Pool_Size"].eq(6).all()


def test_logistic_ranker_learns_the_pattern():
    pairs = _pairs()
    ranked = Ranker({"model": "logistic", "C": 1.0}).fit(pairs).rank(pairs)
    top = ranked[ranked["Label_Allocated"] == 1]["ML_Rank"]
    assert (top == 1).mean() > 0.9


def test_positive_serology_is_never_ranked():
    pairs = _pairs(5)
    pairs.loc[pairs.index[1], "Cand_Serology_Clear"] = "No"
    ranked = Ranker({"model": "logistic", "C": 1.0}).fit(pairs).rank(pairs)
    assert np.isnan(ranked.loc[pairs.index[1], "ML_Rank"])


def test_lightgbm_ranker_runs():
    pairs = _pairs()
    ranked = Ranker({"model": "lightgbm", "num_leaves": 3, "n_estimators": 50}).fit(pairs).rank(pairs)
    assert ranked["ML_Rank"].notna().all()
