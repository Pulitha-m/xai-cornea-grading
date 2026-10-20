"""Parity of the served cellular pipeline with the exported web path and the validated research pipeline.

References (written by ml/cellular/export_web.py on 3 validation images; git-ignored: patient images) in
tests/data/cellular_reference/:
  <id>.jpg / .png     the image
  <id>_web.json       the web path in Colab (same ONNX networks, same code)      -> must match closely
  <id>.json           the validated pipeline (PyTorch on GPU, TensorFlow)       -> within the measured bounds
The export measured the web path against the validated pipeline on 13 validation images: at most 1 % cells,
0.2 % ECD and CV, 0.5 % HEX (floating-point precision of the networks). The same bounds apply here.

Skipped where the reference folder or the models are absent. As a script it prints the comparison table:
    uv run python -m tests.test_cellular_parity
"""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

REF = Path(__file__).resolve().parent / "data" / "cellular_reference"
MODELS = Path(__file__).resolve().parents[1] / "models" / "cellular" / "cellular_config.json"
HEADLINE = ("n_cells", "ecd_cells_per_mm2", "cv_pct", "hex_pct")
WEB_TOL = {"n_cells": 1e-3, "ecd_cells_per_mm2": 1e-3, "cv_pct": 1e-3, "hex_pct": 1e-3}
VALIDATED_TOL = {"n_cells": 0.01, "ecd_cells_per_mm2": 0.002, "cv_pct": 0.002, "hex_pct": 0.005}


def references() -> list[tuple[str, Path]]:
    if not REF.is_dir():
        return []
    # an input image is a file with both reports next to it (the overlay PNGs of pipeline.save have none)
    return [(f.stem, f) for f in sorted(REF.iterdir())
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")
            and (REF / f"{f.stem}_web.json").exists() and (REF / f"{f.stem}.json").exists()]


def rel(a, b) -> float:
    return 0.0 if a == b else abs(a - b) / max(abs(b), 1e-9)


def compare(iid: str, path: Path) -> dict:
    from pipelines.cellular import service
    gray = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)
    out = service.analyse(gray, iid)
    served = out.report["biomarkers"]
    web = json.loads((REF / f"{iid}_web.json").read_text())["biomarkers"]
    validated = json.loads((REF / f"{iid}.json").read_text())
    row = {"image_id": iid}
    for k in HEADLINE:
        row[f"{k} served"], row[f"{k} web"], row[f"{k} validated"] = served[k], web[k], validated["biomarkers"][k]
        row[f"{k} vs web"] = rel(served[k], web[k])
        row[f"{k} vs validated"] = rel(served[k], validated["biomarkers"][k])
    npz = REF / f"{iid}_web.npz"
    if npz.exists():
        with np.load(npz) as ref:
            row["roi pixels differ (vs web)"] = int((out.roi != ref["roi"]).sum())
            row["mask pixels differ (vs web)"] = int((out.mask != ref["mask"]).sum())
    row["reliable served / validated"] = f"{out.report['reliable']} / {validated['reliable']}"
    return row


CASES = references()


@pytest.mark.skipif(not CASES or not MODELS.exists(), reason="cellular reference data or models not present")
@pytest.mark.parametrize("iid,path", CASES, ids=[c[0] for c in CASES])
def test_served_numbers_match_the_exported_and_the_validated_pipeline(iid, path):
    row = compare(iid, path)
    for k in HEADLINE:
        assert row[f"{k} vs web"] <= WEB_TOL[k], (k, row)
        assert row[f"{k} vs validated"] <= VALIDATED_TOL[k], (k, row)


if __name__ == "__main__":
    import pandas as pd
    pd.set_option("display.width", 250)
    if not CASES:
        raise SystemExit(f"no references in {REF}")
    t = pd.DataFrame([compare(i, p) for i, p in CASES]).set_index("image_id")
    print(t.T.to_string())
