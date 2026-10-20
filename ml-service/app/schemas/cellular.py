from pydantic import BaseModel, Field

from app.schemas.analysis import ImageValidation, RejectedResponse


class CellularBiomarkers(BaseModel):
    cellCount: int = Field(..., description="Complete cells measured (not touching the image border or unanalysable area)")
    ecd: float | None = Field(None, description="Endothelial cell density, cells/mm² (= 10⁶ / mean cell area)")
    meanAreaUm2: float | None = None
    sdAreaUm2: float | None = Field(None, description="Population SD of the cell area, µm²")
    coefficientOfVariation: float | None = Field(None, description="CV of the cell area, % (polymegathism)")
    hexagonality: float | None = Field(None, description="% six-sided cells among cells with a side count (HEX)")
    cellsWithSides: int = Field(..., description="Cells with a side count (fully surrounded by other cells)")
    meanCompactness: float | None = Field(None, description="4πA/P², 1 = circle, 0.907 = regular hexagon")
    sdCompactness: float | None = None
    cvCompactness: float | None = Field(None, description="CV of the compactness within the image, %")
    areaPercentilesUm2: dict[str, float | None]
    sideDistributionPct: dict[str, float | None] = Field(..., description="Share of cells with ≤4, 5, 6, 7, ≥8 sides, %")
    flaggedCells: int = Field(..., description="Implausibly small (< 0.25 × median) or large (> 3 × median) cells; kept")


class CellularRoi(BaseModel):
    method: str
    shareOfImage: float
    shareOfLitArea: float = Field(..., description="Share of the illuminated area judged analysable")
    qualityScore: float = Field(..., description="Mean P(analysable) over the illuminated area")


class QualityFlag(BaseModel):
    level: str = Field(..., description="error (biomarkers not reliable) or warning (check)")
    code: str
    message: str


class CellularUncertainty(BaseModel):
    method: str
    ecdCi95: list[float | None]
    cvCi95: list[float | None]
    hexCi95: list[float | None]


class CellularEvidence(BaseModel):
    mostExtremeCellsPct: float
    theirShareOfAreaVariancePct: float | None = Field(None, description="Share of the cell-area variance (drives CV)")


class CellularReliability(BaseModel):
    rule: str
    green: int
    yellow: int
    red: int
    medianConfidence: float | None = None


class CellularImages(BaseModel):
    overlayJpeg: str = Field(..., description="Base64 JPEG: ROI (cyan), measured cells coloured by side count")
    reliabilityJpeg: str | None = Field(None, description="Base64 JPEG: cells green / yellow / red")
    cvEvidenceJpeg: str = Field(..., description="Base64 JPEG: cells by area vs the median; most extreme outlined")


class CellularAnalyzeResponse(BaseModel):
    caseId: str
    status: str
    imageValidation: ImageValidation
    method: str
    umPerPx: float = Field(..., description="Calibrated scale (Phase 4 / 6), µm per pixel")
    validatedImageSize: bool = Field(..., description="False if the image size differs from the validated 1296 × 972")
    biomarkers: CellularBiomarkers
    roi: CellularRoi
    qualityFlags: list[QualityFlag]
    reliable: bool = Field(..., description="False if a quality flag of level 'error' was raised")
    uncertainty: CellularUncertainty
    evidence: CellularEvidence
    reliability: CellularReliability | None = None
    images: CellularImages
    seconds: float
    message: str


class CellularRejectedResponse(RejectedResponse):
    pass
