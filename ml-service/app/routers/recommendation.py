"""Donor-tissue ranking endpoint (recommendation module, Member 4).

method="ml" (default) ranks with the trained model and adds "Why?" reasons and a
counterfactual for each cornea; MCDA scores are always included for comparison.
If no trained model is installed, it falls back to MCDA.
"""
from fastapi import APIRouter

from app.schemas.recommendation import MatchRequest, MatchResponse
from pipelines.recommendation.engine import Weights, rank
from pipelines.recommendation.ml_ranker import rank_ml

router = APIRouter(prefix="/recommendation", tags=["recommendation"])


@router.post("/match", response_model=MatchResponse)
def match(body: MatchRequest) -> MatchResponse:
    given = body.weights.model_dump(exclude_none=True) if body.weights else {}
    request = body.request.model_dump()
    candidates = [c.model_dump() for c in body.candidates]
    mcda = rank(request=request, candidates=candidates, weights=Weights(**given), top_k=None)

    ml = rank_ml(request, candidates, top_k=body.top_k) if body.method != "mcda" else None
    if ml is None:
        ranked = mcda["ranked"][: body.top_k] if body.top_k else mcda["ranked"]
        for r in ranked:
            r["mcda_rank"] = r["rank"]
        method = "mcda" if body.method == "mcda" else "mcda (ML model not installed)"
        return MatchResponse(request_id=body.request.request_id, ranked=ranked, excluded=mcda["excluded"],
                             weights_used=mcda["weights_used"],
                             endothelium_considered=mcda["endothelium_considered"], method_used=method)

    by_id = {r["record_id"]: r for r in mcda["ranked"]}
    ranked = []
    for r in ml["ranked"]:
        m = by_id[r["record_id"]]
        ranked.append({**r, "match_score": m["match_score"], "mcda_rank": m["rank"],
                       "grade_gap": m["grade_gap"], "criterion_scores": m["criterion_scores"],
                       "reasons": m["reasons"]})
    return MatchResponse(request_id=body.request.request_id, ranked=ranked, excluded=ml["excluded"],
                         weights_used=mcda["weights_used"], endothelium_considered=mcda["endothelium_considered"],
                         method_used="ml", model=ml["model"], model_summary=ml["model_summary"] or None)
