"""Reading CellChek values from a report (POST /disease/read-report, pipelines/disease/report.py).

No real report is committed (they carry donor tissue IDs): the OCR test draws a synthetic
report with the CellChek layout; the parsing rules are tested on hand-made text boxes.
"""
import io

from PIL import Image, ImageDraw, ImageFont

from pipelines.disease import report
from pipelines.disease.report import Box, read_boxes

# Consistent values: 124 cells / 0.05 mm² = 2,480 cells/mm²; SD = 33 % × (10^6 / 2480) ≈ 133.
SYNTHETIC = {"ECD_CD_cells_per_mm2": 2480.0, "SD": 133.0, "CV": 33.0, "HEX_percent": 55.0, "Donor_Age": 61.0}


def synthetic_report_png() -> bytes:
    image = Image.new("RGB", (1100, 760), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)
    draw.text((15, 60), "Donor Tissue ID : TEST-0001 L", fill="black", font=font)
    draw.text((15, 140), "Age : 61", fill="black", font=font)
    draw.text((140, 140), "Eye : OD", fill="black", font=font)
    draw.rectangle((20, 260, 500, 640), fill=(90, 90, 90))           # stands in for the cell image
    rows = [("CD", "Cells/mm2", "2,480"), ("CV", "", "33"), ("HEX", "%", "55"), ("SD", "", "133"),
            ("Total Area", "um2", "50,000"), ("Total Num", "", "124")]
    for i, (label, unit, value) in enumerate(rows):
        y = 280 + 32 * i
        draw.text((540, y), label, fill="black", font=font)
        draw.text((660, y), unit, fill="black", font=font)
        draw.text((780, y), value, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def box(text, x, y, score=0.99):
    return Box(text, score, x, y, x + 10 * len(text), y + 20)


LAYOUT = [
    box("Donor Tissue ID:NEB-0000-00-00000 L", 10, 77), box("Age:59", 12, 147), box("Eye: OS", 137, 147),
    box("CD", 554, 286), box("Cells/mm2", 596, 288), box("2,016", 662, 285),
    box("CV", 553, 307), box("35", 678, 307),
    box("HEX", 548, 328), box("48", 678, 328),
    box("SD", 554, 351), box("175", 673, 350),
    box("Total Area", 529, 371), box("pm", 623, 378, 0.57), box("61,468", 666, 372),
    box("Total Num", 529, 394), box("124", 674, 394),
    box("CD-15 v 1.00", 912, 706),
]


def test_values_are_taken_from_the_number_right_of_each_label():
    values, scores, extra = read_boxes(LAYOUT)
    assert values == {"ECD_CD_cells_per_mm2": 2016, "CV": 35, "HEX_percent": 48, "SD": 175,
                      "total_num": 124, "total_area": 61468, "Donor_Age": 59}
    assert extra == {"tissue_id": "NEB-0000-00-00000 L", "eye": "OS"}


def test_unit_merged_with_value_by_ocr_is_read():
    merged = [b for b in LAYOUT if b.text not in ("Cells/mm2", "2,016")] + [box("Cells/mm2 2,016", 596, 286)]
    assert read_boxes(merged)[0]["ECD_CD_cells_per_mm2"] == 2016


def test_consistent_reading_has_no_warnings(monkeypatch):
    monkeypatch.setattr(report, "ocr_boxes", lambda gray: LAYOUT)
    result = report.read_report(synthetic_report_png())
    assert result["values"] == {"ECD_CD_cells_per_mm2": 2016, "SD": 175, "CV": 35, "HEX_percent": 48, "Donor_Age": 59}
    assert result["warnings"] == [] and result["notFound"] == []


def test_misread_digit_is_flagged_by_the_cross_checks(monkeypatch):
    misread = [box("2,916", b.x0, b.y0) if b.text == "2,016" else b for b in LAYOUT]
    monkeypatch.setattr(report, "ocr_boxes", lambda gray: misread)
    codes = {w["code"] for w in report.read_report(synthetic_report_png())["warnings"]}
    assert {"REPORT_ECD_MISMATCH", "REPORT_SD_MISMATCH"} <= codes


def test_impossible_or_unclear_values_are_not_trusted(monkeypatch):
    layout = [box("9", b.x0, b.y0) if b.text == "48" else b for b in LAYOUT]               # HEX 9 -> possible but…
    layout = [box("1750", b.x0, b.y0) if b.text == "175" else b for b in layout]          # SD 1750: impossible
    layout = [box("35", b.x0, b.y0, score=0.5) if b.text == "35" else b for b in layout]  # CV hard to read
    monkeypatch.setattr(report, "ocr_boxes", lambda gray: layout)
    result = report.read_report(synthetic_report_png())
    assert result["values"]["SD"] is None and "SD" in result["notFound"]
    codes = {(w["code"], w["field"]) for w in result["warnings"]}
    assert ("REPORT_VALUE_NOT_POSSIBLE", "SD") in codes and ("REPORT_LOW_CONFIDENCE", "CV") in codes


def test_missing_fields_are_listed_for_manual_entry(monkeypatch):
    layout = [b for b in LAYOUT if not b.text.startswith("Age")]
    monkeypatch.setattr(report, "ocr_boxes", lambda gray: layout)
    result = report.read_report(synthetic_report_png())
    assert result["notFound"] == ["Donor_Age"] and result["values"]["Donor_Age"] is None


def test_text_export_is_read():
    export = b"CorneaID : 4499\r\nDonorAge : 22\r\nEye : OD\r\n<Multi-Sample Averages>\r\n  CD  = 2632\r\n  CV  = 53\r\n" \
             b"  HEX = 45\r\n  AVE = 380\r\n  NUM = 104\r\n  AREA= 39532\r\n<G>\r\n  SD = 202\r\n"
    result = report.read_report(export)
    assert result["source"] == "text_export"
    assert result["values"] == {"ECD_CD_cells_per_mm2": 2632, "SD": 202, "CV": 53, "HEX_percent": 45, "Donor_Age": 22}
    assert result["tissueId"] == "4499" and result["eye"] == "OD"


def test_ocr_reads_a_synthetic_report_end_to_end(client):
    response = client.post("/disease/read-report", files={"report": ("report.png", synthetic_report_png(), "image/png")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "image"
    assert body["values"] == SYNTHETIC
    assert body["warnings"] == []
    assert body["eye"] == "OD"


def test_other_files_are_refused(client):
    response = client.post("/disease/read-report", files={"report": ("report.pdf", b"%PDF-1.7 ...", "application/pdf")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REPORT_UNSUPPORTED_FORMAT"


def test_blank_image_has_no_values(client):
    buffer = io.BytesIO()
    Image.new("L", (640, 480), 255).save(buffer, format="PNG")
    response = client.post("/disease/read-report", files={"report": ("blank.png", buffer.getvalue(), "image/png")})
    assert response.status_code == 422 and response.json()["error"]["code"] == "REPORT_NO_VALUES"

