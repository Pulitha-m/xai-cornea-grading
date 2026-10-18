"""Export the authoritative 24-feature tabular schema for ml-service.

The feature list, order and preprocessing come from modeling_setup.py, which
every tabular model in notebooks 05-13 used. Categories and training ranges
come from the labelled training data. Nothing is typed in by hand except
units and sources, which are documented below.

The deployed grading model (ECD threshold tree) uses only
ECD_CD_cells_per_mm2. This schema exists so that any future tabular
inference validates inputs exactly as the training pipeline expects them.

Usage (from ml/):
    .venv/Scripts/python.exe grading/scripts/export_feature_schema.py
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modeling_setup as ms  # noqa: E402

REPO_DIR = Path(__file__).resolve().parents[3]
OUT_PATH = REPO_DIR / "ml-service" / "models" / "grading_feature_schema.json"

NUMERIC_META = {
    "ECD_CD_cells_per_mm2": {"unit": "cells/mm²", "description": "Endothelial cell density", "integer": False, "max": None},
    "CV": {"unit": "%", "description": "Coefficient of variation of cell area", "integer": False, "max": None},
    "HEX_percent": {"unit": "%", "description": "Proportion of hexagonal cells", "integer": False, "max": 100},
    "SD": {"unit": "µm²", "description": "Standard deviation of cell area", "integer": False, "max": None},
    "Total_Cell_Count": {"unit": "cells", "description": "Number of cells analysed", "integer": True, "max": None},
    "Total_Area_um2": {"unit": "µm²", "description": "Total analysed area", "integer": False, "max": None},
}


def main():
    data = ms.load_labelled_data()
    features = []
    for name in ms.ALL_FEATURES:
        column = data[name]
        if name in ms.NUMERIC_FEATURES:
            meta = NUMERIC_META[name]
            values = column.dropna()
            features.append({
                "name": name, "group": "konan_measurement", "type": "number",
                "unit": meta["unit"], "description": meta["description"],
                "source": "Specular microscopy (Konan) report",
                "integer": meta["integer"],
                "valid": {"min_exclusive": 0, "max_inclusive": meta["max"]},
                "training_range": {"min": float(values.min()), "max": float(values.max())},
                "missing": "allowed: replaced by the training-fold median (SimpleImputer, strategy='median')",
            })
        elif name in ms.CLINICAL_BINARY_FEATURES:
            observed = sorted(column.dropna().unique().tolist())
            assert observed == [0.0, 1.0], f"{name} has unexpected values {observed}"
            features.append({
                "name": name, "group": "slit_lamp_finding", "type": "binary", "unit": None,
                "description": name.replace("_", " "), "source": "Slit-lamp examination (specialist)",
                "allowed": [0, 1],
                "missing": "allowed: encoded as its own category (constant -1, one-hot)",
            })
        else:
            features.append({
                "name": name, "group": "slit_lamp_finding", "type": "category", "unit": None,
                "description": name.replace("_", " "), "source": "Slit-lamp examination (specialist)",
                "allowed": sorted(column.dropna().unique().tolist()),
                "missing": "allowed: encoded as its own category ('__MISSING__', one-hot)",
            })

    # Cross-field identity verified on the training data: ECD = count / area × 10^6.
    complete = data[ms.NUMERIC_FEATURES].dropna()
    derived = complete["Total_Cell_Count"] / complete["Total_Area_um2"] * 1e6
    relative = (derived / complete["ECD_CD_cells_per_mm2"] - 1).abs()
    assert (relative < 0.01).all(), "ECD identity does not hold on training data"

    schema = {
        "schema": "grading_tabular_features",
        "version": 1,
        "source": "ml/grading/scripts/modeling_setup.py (ALL_FEATURES, make_preprocessor)",
        "feature_count": len(features),
        "order": [f["name"] for f in features],
        "features": features,
        "cross_field_checks": [{
            "rule": "ECD_CD_cells_per_mm2 ≈ Total_Cell_Count / Total_Area_um2 × 10^6 (within 1%)",
            "evidence": f"holds for all {len(complete)} labelled tissues with complete Konan measurements",
            "on_failure": "warning (values reviewed, not rejected)",
        }],
        "deployed_model_uses": ["ECD_CD_cells_per_mm2"],
        "data_sha256": hashlib.sha256(ms.DATA_PATH.read_bytes()).hexdigest(),
        "training_rows": int(len(data)),
    }
    assert schema["feature_count"] == 24 and schema["order"] == ms.ALL_FEATURES
    OUT_PATH.write_text(json.dumps(schema, indent=2, ensure_ascii=False, default=lambda o: float(o) if isinstance(o, np.floating) else o) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({schema['feature_count']} features)")


if __name__ == "__main__":
    main()
