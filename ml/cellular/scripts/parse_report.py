"""
Parse Konan CellChek D exported report (.txt) into a structured dict.

Handles the key-value export format, e.g. 4499T.txt:
    CorneaID : 4499
    DonorAge : 22
    <Multi-Sample Averages>
      CD  = 2632
      CV  = 53
      HEX = 45
      AVE = 380
      NUM = 104
      AREA= 39532
    <G>
      SD = 202
"""
import re
from pathlib import Path


# Map the raw Konan keys to our canonical column names.
FIELD_MAP = {
    "CD":   "ecd",        # endothelial cell density, cells/mm^2
    "CV":   "cv",         # coefficient of variation, %
    "HEX":  "hex",        # hexagonality, %
    "SD":   "sd",         # std dev of cell area, um^2
    "AVE":  "mean_area",  # mean cell area, um^2
    "NUM":  "num_cells",  # number of analysed cells
    "AREA": "area_um2",   # total analysed area, um^2 (= sum of cell areas)
}


def _grab(pattern, text, cast=str, default=None):
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return default
    try:
        return cast(m.group(1).strip())
    except (ValueError, AttributeError):
        return default


def parse_report(path):
    """Parse a single Konan .txt report. Returns a flat dict."""
    text = Path(path).read_text(errors="ignore")

    rec = {"source_file": Path(path).name}

    # --- metadata ---
    rec["cornea_id"] = _grab(r"CorneaID\s*:\s*(.+)", text)
    rec["donor_age"] = _grab(r"DonorAge\s*:\s*(\d+)", text, int)
    rec["eye"]       = _grab(r"\bEye\s*:\s*(\w+)", text)
    rec["date"]      = _grab(r"Date\s*:\s*(.+)", text)
    rec["tech"]      = _grab(r"TechName\s*:\s*(.+)", text)
    rec["comments"]  = _grab(r"Comments\s*:\s*(.+)", text)

    # Konan reliability grade: the single-letter section tag <G>/<Y>/<R>
    grade = _grab(r"<([GYR])>", text)
    rec["grade"] = {"G": "green", "Y": "yellow", "R": "red"}.get(grade, grade)

    # Acquisition year comes from the measurement Date (the NEB-YYYY- prefix is a
    # tissue catalogue number, not the acquisition year, so Date is authoritative).
    yr = _grab(r"Date\s*:\s*\d+/\d+/(\d{4})", text) or _grab(r"NEB-(\d{4})-", text)
    rec["year"] = int(yr) if yr else None

    # --- measured biomarkers ---
    # Accept both "CD = 2632" and "CD  = 2,632"
    for raw_key, col in FIELD_MAP.items():
        val = _grab(rf"\b{raw_key}\s*=\s*([0-9,.\-]+)", text, default=None)
        if val is not None:
            val = val.replace(",", "")
            try:
                rec[col] = float(val) if ("." in val) else int(val)
            except ValueError:
                rec[col] = None
        else:
            rec.setdefault(col, None)

    # --- cross-check: Konan's CD should equal NUM / AREA(mm^2) ---
    if rec.get("num_cells") and rec.get("area_um2"):
        derived = rec["num_cells"] / (rec["area_um2"] / 1_000_000.0)
        rec["ecd_check"] = round(derived, 1)
    else:
        rec["ecd_check"] = None

    return rec


if __name__ == "__main__":
    import sys, json
    for p in sys.argv[1:]:
        print(json.dumps(parse_report(p), indent=2, ensure_ascii=False))

