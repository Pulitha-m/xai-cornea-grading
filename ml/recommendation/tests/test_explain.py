"""Tests for SHAP explanations of the ranker. Small made-up data only."""
import numpy as np
import pytest

from recommendation.explain.shap_explain import (
    REASONS, by_reason, explain_ranking, global_importance, reason_text, shap_values,
)
from recommendation.matching.ranker import Ranker
from recommendation.tests.test_ranker import _pairs


@pytest.fixture(scope="module")
def fitted():
    pairs = _pairs()
    return Ranker({"model": "logistic", "C": 1.0}).fit(pairs), pairs


def test_shap_values_add_up_to_score_differences(fitted):
    """Linear SHAP is exact: within a request, SHAP differences = score differences."""
    ranker, pairs = fitted
    values = shap_values(ranker, pairs, background=pairs)
    score = ranker.score(pairs)
    q = pairs["Request_ID"] == pairs["Request_ID"].iloc[0]
    shap_diff = values[q].sum(axis=1).to_numpy()
    assert np.allclose(shap_diff - shap_diff.mean(), score[q] - score[q].mean(), atol=1e-6)


def test_reasons_and_text(fitted):
    ranker, pairs = fitted
    out = explain_ranking(ranker, pairs, background=pairs)
    assert {f"why_{r}" for r in REASONS} <= set(out.columns)
    top = out[out["ML_Rank"] == 1].iloc[0]
    assert "grade match" in top["Why"] or "endothelium" in top["Why"]


def test_pool_constant_features_get_no_importance(fitted):
    ranker, pairs = fitted
    feat, reason = global_importance(shap_values(ranker, pairs, pairs), pairs["Request_ID"])
    assert feat["Pool_Size"] == pytest.approx(0, abs=1e-9)
    assert reason.sum() == pytest.approx(1)


def test_reason_text_handles_no_strong_factor():
    import pandas as pd
    assert "no single factor" in reason_text(pd.Series({"grade match": 0.01}))


def test_by_reason_keeps_all_reasons(fitted):
    ranker, pairs = fitted
    assert list(by_reason(shap_values(ranker, pairs, pairs)).columns) == REASONS
