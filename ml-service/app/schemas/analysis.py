from pydantic import BaseModel, Field

# Valid ECD range (cells/mm²): ECD_MIN_EXCLUSIVE < ecd <= ECD_MAX_INCLUSIVE.
ECD_MIN_EXCLUSIVE = 0.0
ECD_MAX_INCLUSIVE = 6000.0


class ErrorDetail(BaseModel):
    code: str
    field: str | None = None
    message: str


class RejectedResponse(BaseModel):
    """Returned with HTTP 4xx/5xx when the request is refused before any analysis runs."""

    status: str = "rejected"
    error: ErrorDetail


class ImageValidation(BaseModel):
    domainStatus: str = Field(
        ...,
        description="VALID_CORNEAL_IMAGE, or UNVALIDATED_DEV_MODE when the development bypass is enabled",
    )
    qualityAssessed: bool = Field(False, description="Image quality and cell detail are not assessed by this version")
    width: int
    height: int
    format: str


class CellularResult(BaseModel):
    status: str
    error: str | None = None
    cellCount: int | None = None
    ecd: float | None = None
    coefficientOfVariation: float | None = None
    hexagonality: float | None = None


class EcdBand(BaseModel):
    lowerExclusive: float | None = None
    upperInclusive: float | None = None


class GradingResult(BaseModel):
    status: str
    error: str | None = None
    grade: str | None = None
    method: str | None = None
    ecdUsed: float | None = None
    ecdBand: EcdBand | None = None
    bandDistribution: dict[str, float] | None = Field(
        None,
        description="Recorded grades of training tissues in the same ECD band (not model confidence)",
    )
    bandTrainingTissues: int | None = None
    reviewRequired: bool | None = None
    message: str | None = None


class DiseaseResult(BaseModel):
    status: str
    error: str | None = None
    disease: str | None = None
    severity: str | None = None
    confidence: float | None = None


class RecommendationResult(BaseModel):
    status: str
    error: str | None = None
    recommendation: str | None = None
    confidence: float | None = None


class AnalyzeResponse(BaseModel):
    caseId: str
    status: str
    imageValidation: ImageValidation
    cellular: CellularResult
    grading: GradingResult
    disease: DiseaseResult
    recommendation: RecommendationResult
