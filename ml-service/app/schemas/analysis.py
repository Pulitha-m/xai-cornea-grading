from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    image_url: str = Field(..., description="URL of the corneal image")
    case_id: str = Field(..., description="Case identifier")


class CellularResult(BaseModel):
    status: str
    error: str | None = None
    cell_count: int | None = None
    ecd: float | None = None
    coefficient_of_variation: float | None = None
    hexagonality: float | None = None


class GradingResult(BaseModel):
    status: str
    error: str | None = None
    grade: str | None = None
    confidence: float | None = None


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
    case_id: str
    status: str
    cellular: CellularResult
    grading: GradingResult
    disease: DiseaseResult
    recommendation: RecommendationResult