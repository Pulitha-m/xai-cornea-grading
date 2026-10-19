"""POST /cellular/analyze: cellular analysis (ROI, cells, ECD / CV / HEX) on its own page.

Same request handling as /analyze and /disease/analyze: multipart form, safe decoding (pipelines/image/decode.py,
size / format / dimension limits), the corneal-image domain validator, the same rejection shape. The pipeline
then gets the uploaded bytes decoded as in the validated research pipeline (OpenCV, greyscale), so the served
numbers match it.
"""
import base64
import logging

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.schemas.analysis import ErrorDetail, ImageValidation
from app.schemas.cellular import CellularAnalyzeResponse, CellularRejectedResponse
from pipelines.cellular import service
from pipelines.cellular.config import CellularModelNotReady
from pipelines.image import domain
from pipelines.image.decode import ImageRejected, decode_image

logger = logging.getLogger("ml-service")

router = APIRouter(prefix="/cellular", tags=["cellular"])

MESSAGE = ("Research tool for a specialist, not a clinical measurement. Validated on 1296 × 972 images from one "
           "specular microscope: against the instrument's counts, mean cell area and CV met their targets, ECD "
           "(mean error 5.8 %) and HEX (11.6 %) did not. Check the overlays and the flagged cells.")


def rejected(status_code: int, code: str, message: str, field: str | None = None) -> JSONResponse:
    body = CellularRejectedResponse(error=ErrorDetail(code=code, field=field, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


JPEG_QUALITY = 90      # ~250 KB per 1296 x 972 overlay instead of ~2.5 MB as PNG; the numbers are unaffected


def jpeg(rgb: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", np.ascontiguousarray(rgb[..., ::-1]), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def camel(rep: dict) -> dict:
    """The research report (snake_case) -> the response fields."""
    bm = rep["biomarkers"]
    unc, ev, rel = rep["uncertainty"], rep["evidence"], rep["reliability"]
    return {
        "umPerPx": rep["um_per_px"],
        "validatedImageSize": rep["validated_image_size"],
        "biomarkers": {
            "cellCount": bm["n_cells"], "ecd": bm["ecd_cells_per_mm2"], "meanAreaUm2": bm["mean_area_um2"],
            "sdAreaUm2": bm["sd_area_um2"], "coefficientOfVariation": bm["cv_pct"], "hexagonality": bm["hex_pct"],
            "cellsWithSides": bm["n_cells_with_sides"], "meanCompactness": bm["mean_compactness"],
            "sdCompactness": bm["sd_compactness"], "cvCompactness": bm["cv_compactness_pct"],
            "areaPercentilesUm2": bm["area_percentiles_um2"], "sideDistributionPct": bm["side_distribution_pct"],
            "flaggedCells": bm["n_flagged"]},
        "roi": {"method": rep["roi"]["method"], "shareOfImage": rep["roi"]["share_of_image"],
                "shareOfLitArea": rep["roi"]["share_of_lit_area"], "qualityScore": rep["roi"]["quality_score"]},
        "qualityFlags": rep["quality_flags"],
        "reliable": rep["reliable"],
        "uncertainty": {"method": unc["method"], "ecdCi95": unc["ecd_ci95"], "cvCi95": unc["cv_ci95"],
                        "hexCi95": unc["hex_ci95"]},
        "evidence": {"mostExtremeCellsPct": ev["most_extreme_cells_pct"],
                     "theirShareOfAreaVariancePct": ev["their_share_of_area_variance_pct"]},
        "reliability": None if rel is None else {
            "rule": rel["rule"], "green": rel["green"], "yellow": rel["yellow"], "red": rel["red"],
            "medianConfidence": rel["median_confidence"]},
        "seconds": rep["seconds"],
    }


@router.post(
    "/analyze",
    response_model=CellularAnalyzeResponse,
    responses={422: {"model": CellularRejectedResponse}, 500: {"model": CellularRejectedResponse},
               503: {"model": CellularRejectedResponse}},
)
async def analyze_cellular(
    caseId: str = Form(..., min_length=1, max_length=100),
    image: UploadFile = File(...),
):
    # 1. Safe decoding (same limits as /analyze).
    data = await image.read()
    try:
        decoded = decode_image(data)
    except ImageRejected as exc:
        return rejected(422, exc.code, exc.message, "image")

    # 2. The corneal-image domain validator, as for every module.
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

    # 3. The pipeline, on the bytes decoded as in the research pipeline.
    gray = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return rejected(422, "IMAGE_DECODE_FAILED", "The image could not be read.", "image")
    try:
        outcome = service.analyse(gray, caseId)
        images = {"overlayJpeg": jpeg(outcome.images["overlay"]),
                  "cvEvidenceJpeg": jpeg(outcome.images["cv_evidence"]),
                  "reliabilityJpeg": jpeg(outcome.images["reliability"]) if "reliability" in outcome.images else None}
    except CellularModelNotReady:
        logger.exception("Cellular models unavailable")
        return rejected(503, "MODEL_NOT_READY", "The cellular analysis models are unavailable. Try again later.")
    except Exception:
        logger.exception("Cellular analysis failed")
        return rejected(500, "MODEL_INFERENCE_FAILED", "The cellular analysis could not be completed.")

    return CellularAnalyzeResponse(
        caseId=caseId,
        status="completed",
        imageValidation=ImageValidation(domainStatus=checked.status, qualityAssessed=True,
                                        width=decoded.width, height=decoded.height, format=decoded.format),
        method=service.METHOD,
        images=images,
        message=MESSAGE,
        **camel(outcome.report),
    )
