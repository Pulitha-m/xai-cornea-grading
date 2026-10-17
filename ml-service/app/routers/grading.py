"""POST /grading/analyze: donor cornea grading on its own page.

Same request handling as /analyze (app/main.py): the 24 features are validated
before the image is touched, then safe decoding and the corneal-image domain
validator. Unlike /analyze, a grading failure is not folded into a "partial"
result: it is returned as a rejection, since grading is the only module here.
"""
import json
import logging

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.schemas.analysis import ErrorDetail, ImageValidation, RejectedResponse
from app.schemas.grading import GradingAnalyzeResponse
from pipelines.grading.feature_schema import load_schema, validate_features
from pipelines.grading.hybrid import HybridModelNotReady
from pipelines.grading.service import run_grading_analysis
from pipelines.image import domain
from pipelines.image.decode import ImageRejected, decode_image

logger = logging.getLogger("ml-service")

router = APIRouter(prefix="/grading", tags=["grading"])


def rejected(status_code: int, code: str, message: str, field: str | None = None,
             errors: list[ErrorDetail] | None = None) -> JSONResponse:
    body = RejectedResponse(error=ErrorDetail(code=code, field=field, message=message), errors=errors)
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


def parse_clinical_features(raw: str):
    """The clinicalFeatures form field: a JSON object with all 24 features (null = not recorded)."""
    try:
        payload = json.loads(raw, parse_constant=lambda c: float(c))  # NaN/Infinity reach the validator
    except json.JSONDecodeError:
        return None, [ErrorDetail(code="FEATURE_SCHEMA_MISMATCH", field="clinicalFeatures",
                                  message="Clinical features must be a JSON object.")]
    result = validate_features(payload)
    if not result.ok:
        return None, [ErrorDetail(code=e.code, field=e.field, message=e.message) for e in result.errors]
    values = dict(zip(load_schema()["order"], result.values))
    warnings = [{"code": w.code, "field": w.field, "message": w.message} for w in result.warnings]
    return (values, warnings), None


@router.post(
    "/analyze",
    response_model=GradingAnalyzeResponse,
    responses={422: {"model": RejectedResponse}, 500: {"model": RejectedResponse}, 503: {"model": RejectedResponse}},
)
async def analyze_grading(
    caseId: str = Form(..., min_length=1, max_length=100),
    clinicalFeatures: str = Form(..., description="JSON object with the 24 model features"),
    image: UploadFile = File(...),
):
    # 1. The 24 features before touching the image.
    parsed, errors = parse_clinical_features(clinicalFeatures)
    if errors:
        first = errors[0]
        return rejected(422, first.code, first.message, first.field, errors)
    values, feature_warnings = parsed

    # 2. Safe decoding (same limits as /analyze).
    try:
        decoded = decode_image(await image.read())
    except ImageRejected as exc:
        return rejected(422, exc.code, exc.message, "image")

    # 3. The corneal-image domain validator, as for every module.
    try:
        checked = domain.validate_domain(decoded.image)
    except domain.ModelNotReady:
        logger.exception("Domain validator unavailable")
        return rejected(503, "MODEL_NOT_READY", "Image validation is unavailable. Try again later.", "image")
    if checked.status == domain.NON_CORNEAL:
        return rejected(422, "INVALID_IMAGE_DOMAIN",
                        "Upload a specular microscopy image showing corneal endothelial cells.", "image")
    if checked.status == domain.UNCERTAIN:
        return rejected(422, "CORNEAL_IMAGE_UNCERTAIN",
                        "The image could not be confirmed as a specular microscopy image of the corneal "
                        "endothelium. Check the image and upload it again.", "image")

    # 4. The hybrid model; it fails closed, so no grade is ever given without it.
    try:
        result = run_grading_analysis(values, feature_warnings, decoded.image, explain=True)
    except HybridModelNotReady:
        logger.exception("Hybrid grading model unavailable")
        return rejected(503, "MODEL_NOT_READY", "The grading model is unavailable. Try again later.")
    except Exception:
        logger.exception("Grading failed")
        return rejected(500, "MODEL_INFERENCE_FAILED", "The grading could not be completed. Try again later.")

    return GradingAnalyzeResponse(
        caseId=caseId,
        imageValidation=ImageValidation(domainStatus=checked.status, width=decoded.width,
                                        height=decoded.height, format=decoded.format),
        featuresUsed=values,
        **result,
    )
