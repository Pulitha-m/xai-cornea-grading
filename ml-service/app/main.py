import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.analysis import (
    AnalyzeResponse,
    CellularResult,
    DiseaseResult,
    ErrorDetail,
    GradingResult,
    ImageValidation,
    RecommendationResult,
    RejectedResponse,
)
from app.routers import disease as disease_router
from app.routers import grading as grading_router
from app.routers.grading import parse_clinical_features
from pipelines.cellular.service import run_cellular_analysis
from pipelines.disease.config import DiseaseModelNotReady
from pipelines.disease.service import run_disease_analysis, warm_up as warm_up_disease
from pipelines.grading.service import run_grading_analysis
from pipelines.image.decode import ImageRejected, decode_image
from pipelines.image.domain import NON_CORNEAL, UNCERTAIN, ModelNotReady, validate_domain
from pipelines.recommendation.service import run_recommendation_analysis

logger = logging.getLogger("ml-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the disease models once; if they are unavailable, /disease/analyze answers MODEL_NOT_READY.
    try:
        warm_up_disease()
    except DiseaseModelNotReady:
        logger.exception("Disease models not loaded")
    yield


app = FastAPI(
    title="Corneal-AI ML Service",
    description="Machine learning inference service for Corneal-AI",
    version="0.2.0",
    lifespan=lifespan,
)
app.include_router(disease_router.router)
app.include_router(grading_router.router)


def rejected(status_code: int, code: str, message: str, field: str | None = None,
             errors: list[ErrorDetail] | None = None) -> JSONResponse:
    body = RejectedResponse(error=ErrorDetail(code=code, field=field, message=message), errors=errors)
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


@app.exception_handler(RequestValidationError)
def request_validation_error(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = str(first.get("loc", ["", "request"])[-1])
    if field == "image":
        return rejected(422, "IMAGE_DECODE_FAILED", "Attach a specular microscopy image.", "image")
    if field == "clinicalFeatures":
        return rejected(422, "MISSING_CLINICAL_FEATURES", "The 24 clinical features are required.", field)
    return rejected(422, "INVALID_REQUEST", "The request is missing a required field.", field)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "ml-service"}


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
    clinicalFeatures: str = Form(..., description="JSON object with the 24 model features"),
    image: UploadFile = File(...),
):
    # 1. Validate the 24 features before touching the image.
    parsed, errors = parse_clinical_features(clinicalFeatures)
    if errors:
        first = errors[0]
        return rejected(422, first.code, first.message, first.field, errors)
    feature_values, feature_warnings = parsed

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
        "grading": run_module(GradingResult, run_grading_analysis, feature_values, feature_warnings, decoded.image),
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
