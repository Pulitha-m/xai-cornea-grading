from pydantic import BaseModel, Field

from app.schemas.analysis import EcdReference, FeatureWarning, ImageValidation


class FeatureContribution(BaseModel):
    name: str
    value: float | int | str | None = Field(..., description="As given to the model; null = not recorded")
    contribution: float = Field(..., description="SHAP value for the explained grade's share of tree votes")


class ImageAttributionMap(BaseModel):
    method: str
    supportingPng: str | None = Field(None, description="Base64 PNG: regions that raised the grade's share of votes")
    opposingPng: str | None = Field(None, description="Base64 PNG: regions that lowered it")
    supportingTotal: float = Field(..., description="Sum of the map's positive part (each PNG is scaled to its own maximum)")
    opposingTotal: float = Field(..., description="Sum of the map's negative part (<= 0)")
    localisedShare: float = Field(..., description="Share of the image's |SHAP| that the map localises")


class GradingExplanation(BaseModel):
    """TreeSHAP of the predicted grade; baseline + all contributions = prediction (share of tree votes)."""

    method: str
    explainedGrade: str
    baseline: float = Field(..., description="Training average share of trees voting for this grade")
    prediction: float
    features: list[FeatureContribution] = Field(..., description="The 24 inputs, largest |contribution| first")
    imageContribution: float
    imageMap: ImageAttributionMap | None = Field(None, description="Null if the backbone has no feature-map output")
    message: str


class GradingAnalyzeResponse(BaseModel):
    """POST /grading/analyze: the hybrid model's grade with the ECD rule as a reference."""

    caseId: str
    status: str
    imageValidation: ImageValidation
    grade: str
    method: str
    modelProbabilities: dict[str, float] = Field(
        ...,
        description="Share of trees voting for each grade; not calibrated, not a confidence",
    )
    featuresUsed: dict[str, float | int | str | None] = Field(
        ...,
        description="The validated 24 features as given to the model (null = not recorded)",
    )
    featuresNotRecorded: list[str]
    warnings: list[FeatureWarning]
    ecdReference: EcdReference
    reviewRequired: bool
    message: str
    explanation: GradingExplanation | None = Field(None, description="Null if the explanation could not be computed")
