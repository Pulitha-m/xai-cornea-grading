from pydantic import BaseModel, Field

from app.schemas.analysis import EcdReference, FeatureWarning, ImageValidation


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
