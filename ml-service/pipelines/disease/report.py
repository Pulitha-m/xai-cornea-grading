"""Read the CellChek values from a Konan CellChek report, to pre-fill the disease form.

Two inputs are accepted:
- a picture of the printed / exported report (JPEG or PNG): text is read with RapidOCR
  (onnxruntime, CPU) and each value is taken from the number to the right of its label
  in the "Multi-Sample Average" block (CD, CV, HEX, SD, Total Num, Total Area) and the
  header (Age, Donor Tissue ID, Eye);
- the CellChek .txt export ("CD = 2632", "DonorAge : 22"), with the patterns of
  ml/cellular/scripts/parse_report.py.

The report only fills the form: the clinician checks and may edit every value, and the
model's image is always the separately uploaded specular image, never the report's
thumbnail. Nothing is stored. Readings are cross-checked (CD = Total Num / Total Area,
SD = CV x mean cell area) so an OCR misread is flagged rather than silently used.
"""
import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from pipelines.disease.config import load_config
from pipelines.image.decode import ImageRejected, decode_image

MAX_TEXT_BYTES = 256 * 1024
LOW_OCR_SCORE = 0.8
ECD_IDENTITY_TOLERANCE = 0.03

# Form fields read from the report, with the label patterns of the report image.
LABELS = {
    "ECD_CD_cells_per_mm2": re.compile(r"^CD(\s|$)"),
    "CV": re.compile(r"^CV(\s|$)"),
    "HEX_percent": re.compile(r"^HEX(\s|%|$)"),
    "SD": re.compile(r"^SD(\s|$)"),
    "total_num": re.compile(r"^Total\s*Num", re.IGNORECASE),
    "total_area": re.compile(r"^Total\s*Area", re.IGNORECASE),
}
FIELD_LABELS = {"ECD_CD_cells_per_mm2": "ECD", "SD": "SD", "CV": "CV", "HEX_percent": "HEX %", "Donor_Age": "Donor age"}
NUMBER = re.compile(r"^\d[\d,]*(\.\d+)?$")
AGE = re.compile(r"^Age\s*[:：]?\s*(\d{1,3})?\b", re.IGNORECASE)
TISSUE = re.compile(r"Tissue\s*ID\s*[:：]?\s*(.*)$", re.IGNORECASE)
EYE = re.compile(r"^Eye\s*[:：]?\s*(OD|OS|OU)?\b", re.IGNORECASE)


class ReportUnreadable(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Box:
    text: str
    score: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@lru_cache
def ocr_engine():
    from rapidocr_onnxruntime import RapidOCR  # imported lazily: only needed when a report is read

    return RapidOCR()


def ocr_boxes(gray: np.ndarray) -> list[Box]:
    result, _ = ocr_engine()(np.stack([gray] * 3, axis=-1), use_cls=False)
    boxes = []
    for points, text, score in result or []:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        boxes.append(Box(str(text).strip(), float(score), min(xs), min(ys), max(xs), max(ys)))
    return boxes


def to_number(text: str) -> float | None:
    text = text.replace(" ", "").rstrip("%")
    if not NUMBER.match(text):
        return None
    return float(text.replace(",", ""))


def trailing_number(text: str) -> float | None:
    """A box's number: the whole text, or its last token when OCR merged unit and value ("Cells/mm2 2,480")."""
    tokens = text.split()
    return to_number(text) if to_number(text) is not None else (to_number(tokens[-1]) if len(tokens) > 1 else None)


def number_right_of(label: Box, boxes: list[Box]) -> Box | None:
    """The nearest box on the same row, to the right of the label, that ends in a number."""
    row = [b for b in boxes
           if b is not label and b.x0 > label.x0
           and abs(b.cy - label.cy) <= 0.6 * max(label.h, b.h)
           and trailing_number(b.text) is not None]
    return min(row, key=lambda b: b.x0, default=None)


def inline_number(label: Box, pattern: re.Pattern) -> float | None:
    """A number written in the label's own box, e.g. "CD 2,016" or "Age:59"."""
    rest = pattern.sub("", label.text, count=1).strip(" :：%")
    tokens = rest.split()
    return to_number(tokens[-1]) if tokens else None


def read_boxes(boxes: list[Box]) -> tuple[dict, dict, dict]:
    """(values, OCR scores, extra fields) from the text boxes of a report image."""
    values, scores, extra = {}, {}, {}
    for name, pattern in LABELS.items():
        for label in (b for b in boxes if pattern.match(b.text)):
            value = inline_number(label, pattern)
            score = label.score
            if value is None:
                found = number_right_of(label, boxes)
                if found is None:
                    continue
                value, score = trailing_number(found.text), found.score
            values[name], scores[name] = value, score
            break

    for box in boxes:
        if "Donor_Age" not in values and (m := AGE.match(box.text)):
            age = float(m.group(1)) if m.group(1) else None
            if age is None and (found := number_right_of(box, boxes)) is not None:
                age, box = trailing_number(found.text), found
            if age is not None:
                values["Donor_Age"], scores["Donor_Age"] = age, box.score
        if "tissue_id" not in extra and (m := TISSUE.search(box.text)):
            extra["tissue_id"] = m.group(1).strip() or None
        if "eye" not in extra and (m := EYE.match(box.text)) and m.group(1):
            extra["eye"] = m.group(1).upper()
    return values, scores, extra


def read_text_export(text: str) -> tuple[dict, dict, dict]:
    """The CellChek .txt export (patterns of ml/cellular/scripts/parse_report.py)."""
    def grab(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    values = {}
    for name, key in [("ECD_CD_cells_per_mm2", "CD"), ("CV", "CV"), ("HEX_percent", "HEX"), ("SD", "SD"),
                      ("total_num", "NUM"), ("total_area", "AREA")]:
        raw = grab(rf"\b{key}\s*=\s*([0-9][0-9,.]*)")
        if raw is not None and (value := to_number(raw)) is not None:
            values[name] = value
    if (age := grab(r"DonorAge\s*:\s*(\d+)")) is not None:
        values["Donor_Age"] = float(age)
    extra = {"tissue_id": grab(r"CorneaID\s*:\s*(.+)"), "eye": (grab(r"\bEye\s*:\s*(\w+)") or None)}
    return values, {name: 1.0 for name in values}, extra


def looks_like_text(data: bytes) -> str | None:
    if len(data) > MAX_TEXT_BYTES or b"\x00" in data:
        return None
    text = data.decode("utf-8", errors="ignore") or data.decode("latin-1")
    return text if re.search(r"\bCD\s*=", text) else None


def read_report(data: bytes) -> dict:
    """Values for the form, the fields not found, and warnings to show next to them."""
    try:
        decoded = decode_image(data)
        values, scores, extra = read_boxes(ocr_boxes(np.asarray(decoded.image)))
        source = "image"
    except ImageRejected as exc:
        text = looks_like_text(data)
        if text is None:
            if exc.code in ("IMAGE_TOO_LARGE", "IMAGE_DIMENSIONS_INVALID"):
                raise ReportUnreadable(exc.code, exc.message) from exc
            raise ReportUnreadable("REPORT_UNSUPPORTED_FORMAT",
                                   "Upload the CellChek report as a JPEG or PNG image, or the CellChek .txt export.") from exc
        values, scores, extra = read_text_export(text)
        source = "text_export"

    limits = load_config()["number_checks"]["limits"]
    keys = {"ECD_CD_cells_per_mm2": "ecd", "SD": "sd", "CV": "cv", "HEX_percent": "hex_pct", "Donor_Age": "age"}
    warnings = []
    form = {}
    for name, key in keys.items():
        value = values.get(name)
        lo, hi = limits[key]
        if value is not None and not lo <= value <= hi:
            warnings.append({"code": "REPORT_VALUE_NOT_POSSIBLE", "field": name,
                             "message": f"{FIELD_LABELS[name]} was read as {value:g}, which is not possible; enter it by hand."})
            value = None
        elif value is not None and scores.get(name, 1.0) < LOW_OCR_SCORE:
            warnings.append({"code": "REPORT_LOW_CONFIDENCE", "field": name,
                             "message": f"{FIELD_LABELS[name]} ({value:g}) was hard to read; check it against the report."})
        form[name] = value

    ecd, sd, cv = form["ECD_CD_cells_per_mm2"], form["SD"], form["CV"]
    num, area = values.get("total_num"), values.get("total_area")
    if ecd and num and area:
        derived = num / (area / 1e6)
        if abs(ecd / derived - 1) > ECD_IDENTITY_TOLERANCE:
            warnings.append({"code": "REPORT_ECD_MISMATCH", "field": "ECD_CD_cells_per_mm2",
                             "message": f"ECD {ecd:g} does not match Total Num / Total Area ({derived:.0f}); "
                                        "check ECD, Total Num and Total Area on the report."})
    if ecd and sd and cv:
        expected = cv / 100 * 1e6 / ecd
        if abs(sd / expected - 1) > load_config()["number_checks"]["sd_consistency_tolerance"]:
            warnings.append({"code": "REPORT_SD_MISMATCH", "field": "SD",
                             "message": f"SD {sd:g} does not match ECD and CV (expected about {expected:.0f}); "
                                        "check SD, ECD and CV on the report."})

    found = {k: v for k, v in form.items() if v is not None}
    if not found:
        raise ReportUnreadable("REPORT_NO_VALUES",
                               "No CellChek values could be read from this file. Enter them by hand.")
    return {
        "source": source,
        "values": form,
        "notFound": [k for k, v in form.items() if v is None],
        "tissueId": extra.get("tissue_id"),
        "eye": extra.get("eye"),
        "totalCells": num,
        "totalAreaUm2": area,
        "warnings": warnings,
    }
