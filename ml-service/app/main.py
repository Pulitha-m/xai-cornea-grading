import logging
import math

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.analysis import (
    ECD_MAX_INCLUSIVE,
    ECD_MIN_EXCLUSIVE,
    AnalyzeResponse,
    CellularResult,
    DiseaseResult,
    ErrorDetail,
    GradingResult,
    ImageValidation,
    RecommendationResult,
    RejectedResponse,
)
from pipelines.cellular.service import run_cellular_analysis
from pipelines.disease.service import run_disease_analysis
from pipelines.grading.service import run_grading_analysis
from pipelines.image.decode import ImageRejected, decode_image
from pipelines.image.domain import NON_CORNEAL, UNCERTAIN, ModelNotReady, validate_domain
from pipelines.recommendation.service import run_recommendation_analysis

logger = logging.getLogger("ml-service")

app = FastAPI(
    title="Corneal-AI ML Service",
    description="Machine learning inference service for Corneal-AI",
    version="0.2.0",
)


def rejected(status_code: int, code: str, message: str, field: str | None = None) -> JSONResponse:
    body = RejectedResponse(error=ErrorDetail(code=code, field=field, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump())


@app.exception_handler(RequestValidationError)
def request_validation_error(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = str(first.get("loc", ["", "request"])[-1])
    if field == "image":
        return rejected(422, "IMAGE_DECODE_FAILED", "Attach a specular microscopy image.", "image")
    return rejected(422, "INVALID_REQUEST", "The request is missing a required field.", field)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "ml-service"}


def parse_ecd(raw: str | None) -> float | None:
    """Optional ECD form field. Blank means not recorded; anything else must be a valid number."""
    if raw is None or raw.strip() == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ValueError("INVALID_FEATURE_TYPE") from None
    if not math.isfinite(value):
        raise ValueError("INVALID_FEATURE_TYPE")
    if not ECD_MIN_EXCLUSIVE < value <= ECD_MAX_INCLUSIVE:
        raise ValueError("FEATURE_OUT_OF_RANGE")
    return value


def run_module(result_type, runner, *args):
    """Run one module; a missing or failing module never hides the others' real results."""
    try:
        data = runner(*args)
        return result_type(**({"status": "completed"} | data))
    except NotImplementedError as exc:
        return result_type(status="not_implemented", error=str(exc))
    except Exception:
        logger.exception("Module %s failed", result_type.__name__)
        return result_type(status="failed", error="The module could not complete the analysis.")


@app.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={422: {"model": RejectedResponse}, 503: {"model": RejectedResponse}},
)
async def analyze(
    caseId: str = Form(..., min_length=1, max_length=100),
    ecd: str | None = Form(None),
    image: UploadFile = File(...),
):
    # 1. Cheap input checks before touching the image.
    try:
        ecd_value = parse_ecd(ecd)
    except ValueError as exc:
        message = (
            "ECD must be a number."
            if str(exc) == "INVALID_FEATURE_TYPE"
            else f"ECD must be greater than {ECD_MIN_EXCLUSIVE:g} and at most {ECD_MAX_INCLUSIVE:g} cells/mm²."
        )
        return rejected(422, str(exc), message, "ecd")

    # 2. Decode the actual image bytes safely.
    try:
        decoded = decode_image(await image.read())
    except ImageRejected as exc:
        return rejected(422, exc.code, exc.message, "image")

    # 3. Domain validation before any analysis module runs.
    try:
        domain = validate_domain(decoded.image)
    except ModelNotReady:
        logger.exception("Domain validator unavailable")
        return rejected(503, "MODEL_NOT_READY", "Image validation is unavailable. Try again later.", "image")

    if domain.status == NON_CORNEAL:
        return rejected(422, "INVALID_IMAGE_DOMAIN",
                        "Upload a specular microscopy image showing corneal endothelial cells.", "image")
    if domain.status == UNCERTAIN:
        return rejected(422, "CORNEAL_IMAGE_UNCERTAIN",
                        "The image could not be confirmed as a specular microscopy image of the corneal "
                        "endothelium. Check the image and upload it again.", "image")

    # 4. Independent analysis modules.
    modules = {
        "cellular": run_module(CellularResult, run_cellular_analysis, decoded.image),
        "grading": run_module(GradingResult, run_grading_analysis, ecd_value),
        "disease": run_module(DiseaseResult, run_disease_analysis, decoded.image),
        "recommendation": run_module(RecommendationResult, run_recommendation_analysis, decoded.image),
    }
    overall = "completed" if all(m.status == "completed" for m in modules.values()) else "partial"

    return AnalyzeResponse(
        caseId=caseId,
        status=overall,
        imageValidation=ImageValidation(
            domainStatus=domain.status, width=decoded.width, height=decoded.height, format=decoded.format
        ),
        **modules,
    )
