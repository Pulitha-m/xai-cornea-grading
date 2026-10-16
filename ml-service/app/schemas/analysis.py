from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    imageUrl: str = Field(..., description="URL of the corneal image")
    caseId: str = Field(..., description="Case identifier")
    ecd: float | None = Field(
        None,
        gt=0,
        le=6000,
        description="Endothelial cell density (cells/mm²) from the specular microscopy report",
    )


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
    cellular: CellularResult
    grading: GradingResult
    disease: DiseaseResult
    recommendation: RecommendationResult