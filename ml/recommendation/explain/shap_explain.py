"""SHAP explanations for the donor-tissue ML ranker.

Answers two questions:
  1. Global: which features matter most to the ranker overall?
  2. Local ("Why #1?"): why is this cornea ranked above the others for this request?

For the local answer, each candidate's SHAP values are compared with the average of
the other candidates in the same request. A positive contribution means "this is why
it ranks higher than the others"; negative means "this holds it back".

The 23 features are summed into 6 readable reasons for clinicians (grade match,
endothelium, freshness, ...). Explanations describe the model, not clinical truth:
they show what drove the ranking learned from past NEBSL allocations.
"""
import numpy as np
import pandas as pd
import shap

from recommendation.matching.features import build_features
from recommendation.matching.ranker import Ranker

# Each feature belongs to one clinician-facing reason.
REASON_OF = {
    "Grade_Gap": "grade match", "Grade_Exact": "grade match", "Grade_Below": "grade match",
    "Grade_Abs_Gap": "grade match", "Cand_Grade_Num": "grade match",
    "Grade_Abs_Gap_PoolPct": "grade match", "s_grade_fit": "grade match",
    "ECD_if_Endo": "endothelium", "Endo_Procedure": "endothelium", "Endo_Missing": "endothelium",
    "Cand_ECD_PoolPct": "endothelium", "Cand_CV_PoolPct": "endothelium",
    "Cand_HEX_PoolPct": "endothelium", "s_endothelium": "endothelium",
    "Cand_Days_In_Storage": "freshness", "Cand_Days_In_Storage_PoolPct": "freshness",
    "s_freshness": "freshness",
    "Cand_Donor_Age_PoolPct": "donor age", "s_donor_age": "donor age",
    "Cand_Death_to_Preservation_h_PoolPct": "preservation time", "s_preservation_time": "preservation time",
    "Serology_Unknown": "serology",
    # Same value for every candidate of a request, so they never change the order
    # within a request; their relative contribution is always zero.
    "Pool_Size": "request context",
}
REASONS = ["grade match", "endothelium", "freshness", "donor age",
           "preservation time", "serology"]


def shap_values(ranker: Ranker, pairs: pd.DataFrame, background: pd.DataFrame) -> pd.DataFrame:
    """SHAP value of every feature for every row of ``pairs`` (same index).

    ``background`` is the data used as the 'average candidate' (normally the
    training pairs).
    """
    X = build_features(pairs)[ranker.cols]
    if ranker.settings["model"] == "logistic":
        imputer, scaler, lr = ranker.estimator
        to_model = lambda d: scaler.transform(imputer.transform(d))  # noqa: E731
        bg = to_model(build_features(background)[ranker.cols])
        explainer = shap.LinearExplainer(lr, shap.maskers.Independent(bg, max_samples=len(bg)))
        values = explainer.shap_values(to_model(X))
    else:
        explainer = shap.TreeExplainer(ranker.estimator)
        values = explainer.shap_values(X)
    return pd.DataFrame(np.asarray(values), index=pairs.index, columns=ranker.cols)


def by_reason(values: pd.DataFrame) -> pd.DataFrame:
    """Sum feature SHAP values into the 6 clinician-facing reasons."""
    return values.T.groupby(REASON_OF).sum().T.reindex(columns=REASONS)


def relative_to_pool(reasons: pd.DataFrame, request_ids: pd.Series) -> pd.DataFrame:
    """Each candidate's reasons minus the average of its request's pool.

    Positive = pushes this cornea above the other candidates for the same request.
    """
    return reasons - reasons.groupby(request_ids).transform("mean")


def reason_text(row: pd.Series, top: int = 3, min_effect: float = 0.05) -> str:
    """Short 'Why?' text, e.g. 'grade match (+0.82); freshness (+0.31); serology (-0.20)'."""
    strongest = row[row.abs() >= min_effect].sort_values(key=abs, ascending=False).head(top)
    if strongest.empty:
        return "no single factor stands out from the other candidates"
    return "; ".join(f"{k} ({v:+.2f})" for k, v in strongest.items())


def explain_ranking(ranker: Ranker, pairs: pd.DataFrame, background: pd.DataFrame) -> pd.DataFrame:
    """Rank ``pairs`` and add a relative SHAP contribution per reason plus a text reason."""
    ranked = ranker.rank(pairs)
    rel = relative_to_pool(by_reason(shap_values(ranker, pairs, background)), pairs["Request_ID"])
    out = ranked.join(rel.add_prefix("why_"))
    out["Why"] = rel.apply(reason_text, axis=1)
    return out


def global_importance(values: pd.DataFrame, request_ids: pd.Series) -> tuple[pd.Series, pd.Series]:
    """How much each feature / reason changes the ORDER of candidates.

    Uses SHAP values relative to each request's pool, so features that are the same
    for every candidate of a request (e.g. pool size) correctly get zero.
    Returned as shares of the total (sum = 1).
    """
    rel = values - values.groupby(request_ids).transform("mean")
    feat = rel.abs().mean().sort_values(ascending=False)
    reason = by_reason(rel).abs().mean().sort_values(ascending=False)
    return feat / feat.sum(), reason / reason.sum()
