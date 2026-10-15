import numpy as np
import pandas as pd
import pytest

from recommendation.evaluation.metrics import random_baseline, ranking_metrics
from recommendation.matching.mcda import Weights, score


def _ranked(ranks_of_positive, pool=4):
    """One request per entry; the allocated tissue sits at the given rank."""
    rows = []
    for q, pos_rank in enumerate(ranks_of_positive):
        for r in range(1, pool + 1):
            rows.append({"Request_ID": f"Q{q}", "Rank": r, "Label_Allocated": int(r == pos_rank)})
    return pd.DataFrame(rows)


def test_perfect_ranking():
    m = ranking_metrics(_ranked([1, 1, 1]), "Rank")
    assert m["top1"] == 1.0 and m["mrr"] == 1.0 and m["ndcg@3"] == pytest.approx(1.0)


def test_known_values():
    m = ranking_metrics(_ranked([1, 2]), "Rank")
    assert m["top1"] == 0.5
    assert m["top3"] == 1.0
    assert m["mrr"] == pytest.approx((1 + 0.5) / 2)
    assert m["ndcg@3"] == pytest.approx((1 + 1 / np.log2(3)) / 2)


def test_random_baseline_top1_is_one_over_pool():
    assert random_baseline(_ranked([1, 1], pool=4))["top1"] == pytest.approx(0.25)


def _candidates(**over):
    base = {
        "Request_ID": "Q0", "Surgery_Type": "PK", "Cand_Serology_Clear": "Yes",
        "Grade_Gap": 0, "Cand_ECD": 2800.0, "Cand_CV": 35.0, "Cand_HEX": 55.0,
        "Cand_Days_In_Storage": 3, "Cand_Donor_Age": 50.0, "Cand_Death_to_Preservation_h": 3.0,
        "Label_Allocated": 0,
    }
    base.update(over)
    return base


def test_positive_serology_is_excluded():
    df = pd.DataFrame([_candidates(), _candidates(Cand_Serology_Clear="No")])
    out = score(df, Weights())
    assert out.loc[1, "Excluded"] and np.isnan(out.loc[1, "MCDA_Score"])
    assert out.loc[0, "MCDA_Rank"] == 1


def test_exact_grade_beats_lower_grade():
    df = pd.DataFrame([_candidates(Grade_Gap=-1), _candidates(Grade_Gap=0)])
    out = score(df, Weights())
    assert out.loc[1, "MCDA_Rank"] == 1


def test_endothelium_ignored_for_dalk():
    good = _candidates(Surgery_Type="DALK", Cand_ECD=3400.0, Cand_CV=26.0, Cand_HEX=68.0)
    poor = _candidates(Surgery_Type="DALK", Cand_ECD=2050.0, Cand_CV=49.0, Cand_HEX=41.0)
    out = score(pd.DataFrame([good, poor]), Weights())
    assert out.loc[0, "MCDA_Score"] == pytest.approx(out.loc[1, "MCDA_Score"])


def test_weights_load_from_default_config():
    from recommendation.config import load_config
    w = Weights(**load_config()["matching"]["weights"])
    assert sum(w.normalised().values()) == pytest.approx(1.0)


def test_env_override(monkeypatch):
    from recommendation.config import load_config
    monkeypatch.setenv("REC_SPLIT__SEED", "7")
    assert load_config()["split"]["seed"] == 7
