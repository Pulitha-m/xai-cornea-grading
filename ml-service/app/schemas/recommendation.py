"""Request/response models for the donor-tissue ranking endpoint."""
from typing import Literal

from pydantic import BaseModel, Field

Grade = Literal["A+", "A", "B", "C"]


class MatchRequestInfo(BaseModel):
    request_id: str = Field(..., description="Study code for the recipient request, e.g. Q0012")
    requested_grade: Grade
    surgery_type: str | None = Field(None, description="PK, DALK, DSEK, DMEK, Lamellar, Patch/Tectonic")
    urgency: Literal["Routine", "Emergency"] | None = None


class Candidate(BaseModel):
    record_id: str = Field(..., description="Study code for the tissue, e.g. R0233")
    grade: Grade | None = None
    ecd: float | None = Field(None, ge=0)
    cv: float | None = Field(None, ge=0)
    hex: float | None = Field(None, ge=0, le=100)
    donor_age: float | None = Field(None, ge=0)
    death_to_preservation_h: float | None = Field(None, ge=0)
    days_in_storage: float | None = Field(None, ge=0)
    serology_clear: Literal["Yes", "No", "Unknown"] | None = "Unknown"


class WeightsIn(BaseModel):
    """Optional clinician-set weights; any field left null keeps its default."""
    grade_fit: float | None = Field(None, ge=0)
    endothelium: float | None = Field(None, ge=0)
    serology: float | None = Field(None, ge=0)
    freshness: float | None = Field(None, ge=0)
    surgery_compatibility: float | None = Field(None, ge=0)


class MatchRequest(BaseModel):
    request: MatchRequestInfo
    candidates: list[Candidate] = Field(..., min_length=1)
    top_k: int | None = Field(3, ge=1)
    weights: WeightsIn | None = None
    method: Literal["ml", "mcda"] | None = Field(
        "ml", description="ml = trained ranker (default), mcda = rule-based baseline")


class ReasonEffect(BaseModel):
    reason: str
    effect: float = Field(..., description="+ pushes this cornea above the other candidates")


class RankedCandidate(BaseModel):
    rank: int = Field(..., description="Rank by the method used (1 = best)")
    record_id: str
    grade: str | None
    ml_score: float | None = Field(None, description="Trained-ranker score (higher = better)")
    match_score: float = Field(..., description="MCDA score 0-1, shown for comparison")
    mcda_rank: int | None = None
    grade_gap: int | None
    criterion_scores: dict[str, float]
    reasons: list[str] = Field(..., description="MCDA: two strongest criteria")
    why: list[ReasonEffect] = Field(default_factory=list, description="ML: effect of each reason vs the pool")
    why_text: str | None = None
    counterfactual: str | None = Field(None, description="Smallest realistic change that would make it #1")
    flags: list[str]


class ExcludedCandidate(BaseModel):
    record_id: str
    reason: str


class MatchResponse(BaseModel):
    request_id: str
    ranked: list[RankedCandidate]
    excluded: list[ExcludedCandidate]
    weights_used: dict[str, float]
    endothelium_considered: bool
    method_used: str = "mcda"
    model: str = "mcda-baseline-v1"
    model_summary: dict[str, float | str] | None = None
    disclaimer: str = "Decision support only. The final allocation decision rests with the clinician."
