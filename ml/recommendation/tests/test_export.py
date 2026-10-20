"""The exported model must give the same scores in the ML service as in the research code.

Uses small made-up data. The parity check runs when the ml-service folder is present
(it is, in the team repo); otherwise it is skipped.
"""
import importlib
import json
import math
import sys
from pathlib import Path

import joblib
import numpy as np
import pytest

from recommendation.matching.export import export_model
from recommendation.matching.features import FEATURES
from recommendation.matching.ranker import Ranker
from recommendation.tests.test_ranker import _pairs

ML_SERVICE = Path(__file__).resolve().parents[3] / "ml-service"


@pytest.fixture()
def exported(tmp_path):
    pairs = _pairs(n_requests=30)
    pairs["Requested_Grade"] = "A"
    ranker = Ranker({"model": "logistic", "C": 1.0}).fit(pairs)
    joblib.dump({"settings": ranker.settings, "features": FEATURES, "estimator": ranker.estimator},
                tmp_path / "m.joblib")
    model = export_model(tmp_path / "m.joblib", tmp_path / "m.json")
    return ranker, pairs, model, tmp_path / "m.json"


def test_export_has_parameters_only(exported):
    _, _, model, path = exported
    data = json.loads(path.read_text())
    assert data["features"] == FEATURES
    assert all(len(data[k]) == len(FEATURES) for k in ["impute_median", "mean", "scale", "coef"])
    assert set(data) == {"name", "version", "settings", "features", "impute_median", "mean",
                         "scale", "coef", "intercept", "reason_of", "summary"}


@pytest.mark.skipif(not ML_SERVICE.exists(), reason="ml-service folder not found")
def test_ml_service_scores_match_research_code(exported):
    ranker, pairs, model, _ = exported
    sys.path.insert(0, str(ML_SERVICE))
    try:
        serving = importlib.import_module("pipelines.recommendation.ml_ranker")
    finally:
        sys.path.pop(0)

    def none(v):
        return None if isinstance(v, float) and math.isnan(v) else v

    for rid, pool in pairs.groupby("Request_ID"):
        request = {"requested_grade": "A", "surgery_type": pool["Surgery_Type"].iloc[0]}
        cands = [{"record_id": r.Candidate_Record_ID, "grade": r.Cand_Tissue_Grade, "ecd": none(r.Cand_ECD),
                  "cv": none(r.Cand_CV), "hex": none(r.Cand_HEX), "donor_age": r.Cand_Donor_Age,
                  "death_to_preservation_h": r.Cand_Death_to_Preservation_h,
                  "days_in_storage": float(r.Cand_Days_In_Storage), "serology_clear": r.Cand_Serology_Clear}
                 for r in pool.itertuples()]
        served, _ = serving.scores(model, request, cands)
        assert np.allclose(served, ranker.score(pool), atol=1e-9)
