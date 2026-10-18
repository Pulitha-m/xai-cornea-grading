"""Parity of the served v2 disease pipeline with the evaluated notebook models.

Runs pipelines/disease on the test images in ml/disease-new/data/test_images/ with their
CellChek values from the features CSV, through the same decoding as the endpoint
(pipelines/image/decode.py), and compares with the saved test predictions:
test_predictions_all.csv (P_Fus_*) and test_predictions_severity.csv (PSev_*).
The largest difference must be below 0.01 (notebook 10, Step 9).

The data is git-ignored, so the test is skipped where it is absent. As a script it
prints the comparison table:
    uv run python -m tests.test_disease_parity
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
DATA_CANDIDATES = [REPO / "ml" / "disease-new" / "data", REPO / "ml" / "disease - new" / "data"]
DATA = next((p for p in DATA_CANDIDATES if (p / "test_images").is_dir()), DATA_CANDIDATES[0])
MODEL_DIR = REPO / "ml-service" / "models" / "disease_v2"
TOLERANCE = 0.01
MEASUREMENT_COLUMNS = ["ECD_CD_cells_per_mm2", "SD", "CV", "HEX_percent", "Donor_Age"]
REQUIRED = [DATA / "test_images", DATA / "Final_Features_MultiLabel_updated.csv",
            DATA / "test_predictions_all.csv", DATA / "test_predictions_severity.csv",
            MODEL_DIR / "corneal_config.json"]


def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def short_key(s) -> str | None:
    m = re.search(r"(\d{4,6})[\s_\-]*([LR])(?![A-Z])", str(s).upper())
    return f"{m.group(1)}{m.group(2)}" if m else None


def tissue_for(image: Path, tissue_ids: list[str]) -> str | None:
    """Notebook matching: normalised name, else unambiguous tissue number + eye."""
    stem = image.stem
    exact = [t for t in tissue_ids if norm(t) == norm(stem)]
    if exact:
        return exact[0]
    key = short_key(stem)
    by_key = [t for t in tissue_ids if key and short_key(t) == key]
    return by_key[0] if len(by_key) == 1 else None


def parity_table() -> pd.DataFrame:
    from pipelines.disease import service
    from pipelines.disease.config import load_config
    from pipelines.image.decode import decode_image

    config = load_config()
    diseases, heads = config["diseases"], list(config["severity_heads"])
    features = pd.read_csv(DATA / "Final_Features_MultiLabel_updated.csv").set_index("Tissue_ID")
    saved_d = pd.read_csv(DATA / "test_predictions_all.csv").set_index("Tissue_ID")
    saved_s = pd.read_csv(DATA / "test_predictions_severity.csv").set_index("Tissue_ID")
    test_ids = list(saved_d.index)

    rows = []
    for path in sorted((DATA / "test_images").iterdir()):
        tissue = tissue_for(path, test_ids)
        if tissue is None:
            continue
        decoded = decode_image(path.read_bytes())
        gray = np.asarray(decoded.image)
        rgb = np.repeat(gray[:, :, np.newaxis], 3, axis=2)
        r = features.loc[tissue]
        values = {c: None if pd.isna(r[c]) else float(r[c]) for c in MEASUREMENT_COLUMNS}
        outcome = service.analyse(gray, rgb, values, force=True, include_gradcam=False)
        result = outcome.result
        probs = {d["code"]: d["probability"] for d in result["diseases"]}
        d_diff = max(abs(probs[c] - saved_d.loc[tissue, f"P_Fus_{c}"]) for c in diseases)
        s_diff = max(abs(result["severityProbabilities"][h] - saved_s.loc[tissue, f"PSev_{h}"]) for h in heads)
        saved_found = [c for c in diseases if saved_d.loc[tissue, f"Pred_Fus_{c}"] == 1]
        rows.append({
            "Tissue_ID": tissue, "Label": saved_d.loc[tissue, "Combination"],
            "Found (served)": ", ".join(result["detected"]) or "Normal",
            "Same found as notebook": result["detected"] == saved_found,
            "Overall severity": result["overallSeverity"],
            "max diff disease prob": d_diff, "max diff severity prob": s_diff,
            "checks passed": outcome.input_check["passed"],
        })
    return pd.DataFrame(rows)


@pytest.mark.skipif(not all(p.exists() for p in REQUIRED), reason="disease test data or models not available")
def test_served_pipeline_reproduces_notebook_predictions():
    table = parity_table()
    assert len(table) >= 5, "fewer than 5 test images matched a test Tissue_ID"
    worst = table[["max diff disease prob", "max diff severity prob"]].max().max()
    assert worst < TOLERANCE, f"max difference {worst:.4f} >= {TOLERANCE}\n{table.to_string()}"
    assert table["Same found as notebook"].all(), table.to_string()


if __name__ == "__main__":
    missing = [str(p) for p in REQUIRED if not p.exists()]
    if missing:
        sys.exit(f"Missing: {missing}")
    table = parity_table()
    pd.set_option("display.width", 220)
    print(table.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    worst = table[["max diff disease prob", "max diff severity prob"]].max().max()
    print(f"\nmax difference {worst:.4f}:", "PASS" if worst < TOLERANCE else "FAIL")
