from pydantic import BaseModel, Field

from app.schemas.analysis import ErrorDetail, ImageValidation, RejectedResponse


class InputCheck(BaseModel):
    passed: bool
    forced: bool = Field(False, description="Checks failed but the analysis was forced; the result is not reliable")
    errors: list[ErrorDetail]
    warnings: list[ErrorDetail]


class ImageQuality(BaseModel):
    rating: str = Field(..., description="OK, Low or Unusable")
    focus: float = Field(..., description="Laplacian variance at 640 × 480")
    focusLowLimit: float
    darkFraction: float
    saturatedFraction: float
    contrast: float
    unusualDistance: float = Field(..., description="kNN cosine distance to the training images (k = 5)")
    unusualWarnAbove: float
    unusualRejectAbove: float


class GradcamFocus(BaseModel):
    region: str = Field(..., description="Where the map is hottest: centre, upper/lower, left/right or a corner")
    coverage: float = Field(..., description="Share of the image at or above half the map's maximum")


class ShapValue(BaseModel):
    input: str = Field(..., description="Measurement name (ECD includes its derived ECD_Deficit)")
    value: float | None = Field(None, description="Value entered; null = not recorded")
    imputed: bool = Field(..., description="Not recorded: the training median was used, so the contribution is 0")
    contribution: float = Field(..., description="Exact Shapley value, in probability units")


class ShapExplanation(BaseModel):
    """Effect of the CellChek values on one output, with the image fixed.

    baseline + sum(contribution) = prediction. Baseline = all five values at their training median.
    """

    baseline: float
    prediction: float
    values: list[ShapValue]


class DiseaseFinding(BaseModel):
    code: str
    label: str
    probability: float = Field(..., description="Model output (mean of image and flipped image); not calibrated")
    threshold: float
    detected: bool
    gradcamPng: str | None = Field(None, description="Base64 PNG: Grad-CAM over the input image (detected only)")
    gradcamFocus: GradcamFocus | None = None
    shap: ShapExplanation | None = None


class SeverityFinding(BaseModel):
    group: str
    label: str
    diseases: list[str]
    grade: str = Field(..., description="Mild or Mod/Sev")
    probability: float | None = None
    threshold: float | None = None
    method: str
    shap: ShapExplanation | None = Field(None, description="For model-graded groups")


class DiseaseAnalyzeResponse(BaseModel):
    caseId: str
    status: str
    imageValidation: ImageValidation
    inputCheck: InputCheck
    imageQuality: ImageQuality
    method: str
    diseases: list[DiseaseFinding]
    detected: list[str]
    normal: bool
    severity: list[SeverityFinding]
    overallSeverity: str = Field(..., description="None, Mild or Mod/Sev (worst detected group)")
    severityProbabilities: dict[str, float]
    measurementsUsed: dict[str, float | None]
    measurementsNotRecorded: list[str]
    reliable: bool
    message: str


class DiseaseRejectedResponse(RejectedResponse):
    """A rejection; for failed input checks it also carries every error and warning."""

    inputCheck: InputCheck | None = None
    imageQuality: ImageQuality | None = None


class CellChekReport(BaseModel):
    """Values read from a CellChek report to pre-fill the form; the clinician checks them."""

    source: str = Field(..., description="image (OCR) or text_export")
    values: dict[str, float | None] = Field(..., description="The 5 measurements by name; null = not found")
    notFound: list[str]
    tissueId: str | None = None
    eye: str | None = None
    totalCells: float | None = None
    totalAreaUm2: float | None = None
    warnings: list[ErrorDetail]
