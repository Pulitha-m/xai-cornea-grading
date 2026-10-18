"""POST /disease/analyze: v2 disease detection and severity grading on its own page.

Same request handling as /analyze (app/main.py): multipart form, safe decoding, the
corneal-image domain validator, and the same rejection shape. Then the disease
pipeline's own input checks (notebook 10); errors reject the request unless `force`.
"""
import io
import json
import logging

import numpy as np
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps

from app.schemas.analysis import ErrorDetail, ImageValidation
from app.schemas.disease import DiseaseAnalyzeResponse, DiseaseRejectedResponse
from pipelines.disease import service
from pipelines.disease.checks import MEASUREMENTS, is_number
from pipelines.disease.config import DiseaseModelNotReady
from pipelines.image import domain
from pipelines.image.decode import ImageRejected, decode_image

logger = logging.getLogger("ml-service")

router = APIRouter(prefix="/disease", tags=["disease"])


def rejected(status_code: int, code: str, message: str, field: str | None = None,
             errors: list[ErrorDetail] | None = None, **extra) -> JSONResponse:
    body = DiseaseRejectedResponse(error=ErrorDetail(code=code, field=field, message=message), errors=errors, **extra)
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


def parse_measurements(raw: str):
    """The measurements form field: a JSON object with the 5 CellChek values (null = not recorded, never 0)."""
    try:
        payload = json.loads(raw, parse_constant=lambda c: float(c))
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        return None, [ErrorDetail(code="FEATURE_SCHEMA_MISMATCH", field="measurements",
                                  message="Measurements must be a JSON object.")]
    errors = [ErrorDetail(code="FEATURE_SCHEMA_MISMATCH", field=name, message=f"{name} is missing.")
              for name in MEASUREMENTS if name not in payload]
    errors += [ErrorDetail(code="FEATURE_SCHEMA_MISMATCH", field=name, message=f"{name} is not a known measurement.")
               for name in payload if name not in MEASUREMENTS]
    values = {}
    for name in MEASUREMENTS:
        value = payload.get(name)
        if value is not None and not is_number(value):
            errors.append(ErrorDetail(code="INVALID_FEATURE_TYPE", field=name,
                                      message=f"{MEASUREMENTS[name][1]} must be a number, or blank if unknown."))
        values[name] = None if value is None else float(value) if is_number(value) else None
    return (None, errors) if errors else (values, None)


@router.post(
    "/analyze",
    response_model=DiseaseAnalyzeResponse,
    responses={422: {"model": DiseaseRejectedResponse}, 503: {"model": DiseaseRejectedResponse}},
)
async def analyze_disease(
    caseId: str = Form(..., min_length=1, max_length=100),
    measurements: str = Form(..., description="JSON object: ECD_CD_cells_per_mm2, SD, CV, HEX_percent, Donor_Age"),
    force: bool = Form(False, description="Predict even if the input checks fail (result marked not reliable)"),
    image: UploadFile = File(...),
):
    # 1. Measurements before touching the image.
    values, errors = parse_measurements(measurements)
    if errors:
        first = errors[0]
        return rejected(422, first.code, first.message, first.field, errors)

    # 2. Safe decoding (same limits as /analyze).
    data = await image.read()
    try:
        decoded = decode_image(data)
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

    # 4. Disease pipeline: its input checks, then the models.
    with Image.open(io.BytesIO(data)) as source:
        rgb = np.asarray(ImageOps.exif_transpose(source).convert("RGB"))
    try:
        outcome = service.analyse(np.asarray(decoded.image), rgb, values, force=force)
    except DiseaseModelNotReady:
        logger.exception("Disease model unavailable")
        return rejected(503, "MODEL_NOT_READY", "The disease model is unavailable. Try again later.")

    if outcome.rejected:
        issues = [ErrorDetail(**e) for e in outcome.input_check["errors"]]
        return rejected(422, "INPUT_CHECK_FAILED",
                        "The inputs did not pass the checks, so no result was produced. Correct them, or run "
                        "the analysis anyway (the result is then marked as not reliable).",
                        issues[0].field, issues, inputCheck=outcome.input_check, imageQuality=outcome.image_quality)

    return DiseaseAnalyzeResponse(
        caseId=caseId,
        status="completed",
        imageValidation=ImageValidation(domainStatus=checked.status, qualityAssessed=True,
                                        width=decoded.width, height=decoded.height, format=decoded.format),
        inputCheck=outcome.input_check,
        imageQuality=outcome.image_quality,
        **outcome.result,
    )
