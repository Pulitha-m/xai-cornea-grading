"""Request/response models for the donor-tissue ranking endpoint."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Grade = Literal["A+", "A", "B", "C"]
Indication = Literal["Fuchs/Endothelial", "Bullous keratopathy", "Failed/Re-graft", "Other"]


def warnings_field():
    return Field(default_factory=list, description="Values that are possible but unusual: check them; not a rejection")


class MatchRequestInfo(BaseModel):
    request_id: str = Field(..., description="Study code for the recipient request, e.g. Q0012")
    requested_grade: Grade
    surgery_type: str | None = Field(None, description="PK, DALK, DSEK, DMEK, Lamellar, Patch/Tectonic")
    urgency: Literal["Routine", "Emergency"] | None = None


class Candidate(BaseModel):
    record_id: str = Field(..., description="Study code for the tissue, e.g. R0233")
    grade: Grade | None = None
    ecd: float | None = Field(None, ge=0, le=5000)
    cv: float | None = Field(None, ge=0, le=100)
    hex: float | None = Field(None, ge=0, le=100)
    donor_age: float | None = Field(None, ge=0, le=100)
    death_to_preservation_h: float | None = Field(None, ge=0, le=72)
    days_in_storage: float | None = Field(None, ge=0, le=60)
    serology_clear: Literal["Yes", "No", "Unknown"] | None = "Unknown"


class WeightsIn(BaseModel):
    """Optional clinician-set weights; any field left null keeps its default."""
    grade_fit: float | None = Field(None, ge=0)
    endothelium: float | None = Field(None, ge=0)
    serology: float | None = Field(None, ge=0)
    freshness: float | None = Field(None, ge=0)
    surgery_compatibility: float | None = Field(None, ge=0)

    @model_validator(mode="after")
    def not_all_zero(self):
        values = self.model_dump().values()
        if all(v is not None for v in values) and sum(values) == 0:
            raise ValueError("at least one weight must be above 0")
        return self


class MatchRequest(BaseModel):
    request: MatchRequestInfo
    candidates: list[Candidate] = Field(..., min_length=1)
    top_k: int | None = Field(3, ge=1)
    weights: WeightsIn | None = None
    method: Literal["ml", "mcda"] | None = Field(
        "ml", description="ml = trained ranker (default), mcda = rule-based baseline")

    @model_validator(mode="after")
    def unique_tissue_ids(self):
        seen, duplicates = set(), []
        for c in self.candidates:
            key = c.record_id.strip().upper()
            if key in seen and c.record_id not in duplicates:
                duplicates.append(c.record_id)
            seen.add(key)
        if duplicates:
            raise ValueError(f"duplicate tissue ID: {', '.join(duplicates)}")
        return self


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
    warnings: list[str] = warnings_field()
    disclaimer: str = "Decision support only. The final allocation decision rests with the clinician."


# ---------------------------------------------------------------- post-transplant follow-up (12-month visit)
class FollowupVisit(BaseModel):
    """Specular microscopy at one follow-up visit."""
    ecd: float = Field(..., gt=0, le=5000, description="Endothelial cell density, cells/mm2")
    cv: float = Field(..., ge=0, le=100, description="Coefficient of variation of cell area, %")
    hex: float = Field(..., ge=0, le=100, description="Hexagonality, %")


class FollowupRequest(BaseModel):
    graft_id: str = Field(..., description="Study code for the graft, e.g. G0012")
    procedure: Literal["PK", "DSEK", "DMEK"]
    indication: Indication
    donor_age: float = Field(..., ge=0, le=100)
    baseline_ecd: float = Field(..., gt=0, le=5000, description="Donor ECD before surgery")
    baseline_cv: float = Field(..., ge=0, le=100)
    baseline_hex: float = Field(..., ge=0, le=100)
    visit_3m: FollowupVisit | None = Field(None, description="May be missing (missed visit)")
    visit_6m: FollowupVisit
    visit_12m: FollowupVisit
    rejection_by_12m: bool = Field(False, description="Any rejection episode in the first 12 months")


class PredictedEcd(BaseModel):
    months: int
    ecd: int
    low: int
    high: int


class RiskEstimate(BaseModel):
    outcome: Literal["graft_failure", "low_ecd"]
    within_months: int = Field(..., description="Months after this (12-month) visit")
    probability: float


class TrajectoryReason(BaseModel):
    reason: str
    effect_pct: float = Field(..., description="% change this reason makes to the predicted 60-month ECD")


class RiskReason(BaseModel):
    reason: str
    hazard_ratio: float = Field(..., description="> 1 raises the risk compared with the average graft")


class FollowupReasons(BaseModel):
    trajectory: list[TrajectoryReason]
    graft_failure: list[RiskReason]
    low_ecd: list[RiskReason]


class FollowupResponse(BaseModel):
    graft_id: str
    alert: Literal["green", "amber", "red"]
    next_visit_months: int
    rules_fired: list[str]
    actions: list[str] = Field(..., description="Review prompts, not treatment instructions")
    predicted_ecd: list[PredictedEcd]
    band_level: str
    risk: list[RiskEstimate]
    reasons: FollowupReasons
    counterfactuals: list[str] = Field(..., description="Descriptive: what would change the risk")
    alert_thresholds: dict[str, float] = Field(..., description="Configured alert thresholds (placeholders until agreed)")
    model_summary: dict[str, float | str] | None = Field(None, description="Evaluation numbers of the models")
    model: str
    model_version: str
    rules_version: str | None
    data_source: str
    warnings: list[str] = warnings_field()
    disclaimer: str
