"""Train and export the application grading model (ECD threshold tree).

Rebuilds the model selected in 13_nested_tuning_model_selection.ipynb:
a depth-2 decision tree on ECD alone, fitted on non-2023, image-matched
tissues with an ECD value (cohort K3 in RESULTS.md). Exports it as a small
JSON spec that ml-service can evaluate without scikit-learn, plus a golden
test file of predictions made by the fitted scikit-learn tree.

The spec contains only cut points and per-band grade counts; no
tissue-level data is written.

Usage (from ml/):
    .venv/Scripts/python.exe grading/scripts/train_grading_model.py
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modeling_setup as ms  # noqa: E402

ECD = "ECD_CD_cells_per_mm2"
REVIEW_IDS = ["NEB-2024-08-16259 R", "NEB-2025-09-17471 R"]
TREE_PARAMS = dict(
    max_depth=2, min_samples_leaf=10, class_weight="balanced",
    criterion="gini", random_state=ms.RANDOM_STATE,
)
EXPECTED = {"tissues": 470, "grades": {"A+": 244, "A": 159, "B": 67}}
VALID_RANGE = {"min_exclusive": 0.0, "max_inclusive": 6000.0}

REPO_DIR = Path(__file__).resolve().parents[3]
IMAGE_MANIFEST = ms.PROCESSED_DIR.parent.parent / "image" / "data" / "processed" / "clean_image_manifest.csv"
SELECTION_PATH = ms.PROCESSED_DIR / "selected_grading_model.json"
SPEC_PATH = REPO_DIR / "ml-service" / "models" / "grading_ecd_tree.json"
GOLDEN_PATH = REPO_DIR / "ml-service" / "tests" / "fixtures" / "grading_golden.json"


def normalize_id(value):
    return " ".join(str(value).split()).replace("NEB- ", "NEB-").casefold()


def load_training_tissues():
    """K3 tissues (non-2023, image-matched) with an ECD value."""
    labelled = ms.load_labelled_data()
    manifest = pd.read_csv(IMAGE_MANIFEST)
    manifest_ids = set(manifest["Tissue_ID"].map(normalize_id)) - {normalize_id(i) for i in REVIEW_IDS}

    year = labelled["Tissue_ID"].str.extract(r"NEB-\s*(\d{4})")[0].astype("Int64")
    keep = (
        labelled["Tissue_ID"].map(normalize_id).isin(manifest_ids)
        & year.notna() & (year != 2023)
        & labelled[ECD].notna()
    )
    tissues = labelled[keep.to_numpy()]

    found = {"tissues": len(tissues), "grades": tissues[ms.TARGET].value_counts().to_dict()}
    if found != EXPECTED:
        raise ValueError(f"Training cohort {found} differs from the selected model's cohort {EXPECTED}")
    return tissues


def tree_to_bands(tree, X, y):
    """Convert a single-feature tree into contiguous ECD bands, lowest first."""
    t = tree.tree_
    leaf_of = tree.apply(X)
    bands = []

    def walk(node, lower, upper):
        if t.children_left[node] == -1:
            counts = pd.Series(y[leaf_of == node]).value_counts()
            bands.append({
                "lower_exclusive": lower,
                "upper_inclusive": upper,
                "grade": str(tree.classes_[np.argmax(t.value[node][0])]),
                "training_counts": {g: int(counts.get(g, 0)) for g in ms.CLASSES},
            })
            return
        threshold = float(t.threshold[node])
        walk(t.children_left[node], lower, threshold)   # x <= threshold
        walk(t.children_right[node], threshold, upper)  # x > threshold

    walk(0, None, None)
    return sorted(bands, key=lambda b: -np.inf if b["lower_exclusive"] is None else b["lower_exclusive"])


def predict_from_bands(bands, values):
    out = []
    for v in values:
        band = next(
            b for b in bands
            if (b["lower_exclusive"] is None or v > b["lower_exclusive"])
            and (b["upper_inclusive"] is None or v <= b["upper_inclusive"])
        )
        out.append(band["grade"])
    return np.array(out)


def main():
    tissues = load_training_tissues()
    X = tissues[[ECD]].to_numpy(dtype=float)
    y = tissues[ms.TARGET].to_numpy()

    tree = DecisionTreeClassifier(**TREE_PARAMS).fit(X, y)
    bands = tree_to_bands(tree, X, y)
    cut_points = [b["upper_inclusive"] for b in bands if b["upper_inclusive"] is not None]

    # The spec must reproduce the fitted tree exactly on the training data.
    assert np.array_equal(predict_from_bands(bands, X[:, 0]), tree.predict(X)), "Spec disagrees with tree"

    data_sha256 = hashlib.sha256(ms.DATA_PATH.read_bytes()).hexdigest()
    if SELECTION_PATH.exists():
        selection = json.loads(SELECTION_PATH.read_text())
        assert selection["model"] == "ecd_tree", "Notebook 13 did not select the ECD tree"
        assert selection["cut_points"] == cut_points, "Cut points differ from notebook 13"
        assert selection["data_sha256"] == data_sha256, "Dataset differs from the one used in notebook 13"

    spec = {
        "model": "ecd_threshold_tree",
        "spec_version": 1,
        "feature": "ecd_cells_per_mm2",
        "decision_rule": "A value v falls in the band with lower_exclusive < v <= upper_inclusive (null = unbounded).",
        "cut_points": cut_points,
        "bands": bands,
        "valid_range": VALID_RANGE,
        "training_ecd_range": {"min": float(X.min()), "max": float(X.max())},
        "intended_use": (
            "Decision support for donor cornea grading. The grade is based on ECD only; slit-lamp "
            "findings and other morphology are not considered and may justify a lower grade. "
            "A specialist must confirm every grade."
        ),
        "training": {
            "cohort": "Non-2023, image-matched tissues with ECD (K3 with ECD, RESULTS.md)",
            "tissues": int(len(tissues)),
            "params": TREE_PARAMS,
            "selected_by": "ml/grading/notebooks/images/13_nested_tuning_model_selection.ipynb",
            "data_sha256": data_sha256,
            "scikit_learn_version": sklearn.__version__,
            "exported_on": date.today().isoformat(),
        },
    }
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(json.dumps(spec, indent=2) + "\n")

    # Golden predictions from the fitted scikit-learn tree on synthetic ECD values:
    # a regular grid plus values at and around each cut point. No tissue-level data.
    probes = {float(v) for v in np.arange(500, 4501, 25)}
    for c in cut_points:
        probes |= {c - 1, c - 0.01, c, c + 0.01, c + 1}
    probes = sorted(probes)
    golden = {
        "source": "scikit-learn DecisionTreeClassifier fitted by train_grading_model.py",
        "data_sha256": data_sha256,
        "cases": [
            {"ecd": v, "grade": str(g)}
            for v, g in zip(probes, tree.predict(np.array(probes).reshape(-1, 1)))
        ],
    }
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2) + "\n")

    print(f"Trained on {len(tissues)} tissues; cut points {cut_points}")
    for b in bands:
        print(f"  ({b['lower_exclusive']}, {b['upper_inclusive']}] -> {b['grade']}  {b['training_counts']}")
    print(f"Wrote {SPEC_PATH}")
    print(f"Wrote {GOLDEN_PATH} ({len(golden['cases'])} cases)")


if __name__ == "__main__":
    main()
