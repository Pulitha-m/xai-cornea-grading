"""Train and export the hybrid grading model (24 features + image) for ml-service.

Deployment decision (2026-10-16, project owner): serve the hybrid model as the
application grade, with the ECD threshold tree shown alongside as a reference.
This overrides notebook 13's selection rule, under which the ECD tree was
selected. In notebook 13 the tuned hybrid was not better than the ECD tree
(macro F1 -0.003, Holm p = 1.00) or the tuned tabular model (-0.012, Holm
p = 1.00); see ANALYSIS_PLAN.md, Amendment 2.

Model: the "tuned hybrid" arm of notebook 13.
- Tabular branch: modeling_setup.make_preprocessor() on the 24 features.
- Image branch: 2048-d ResNet-50 (ImageNet IMAGENET1K_V2) embeddings of the
  full-resolution greyscale image (notebook 07), StandardScaler + PCA(k).
- Random Forest, n_estimators=300, random_state=42. k and the forest settings are
  chosen by the same 3-fold donor-grouped inner CV and grid as notebook 13, run
  once on all primary-cohort tissues (protocol Section 6).
- Training data: the 551 non-2023, image-matched tissues (primary cohort K3), with
  the cached embeddings the research used.

Outputs (ml-service/models/):
- grading_hybrid_rf.joblib   fitted scikit-learn pipeline (needs scikit-learn 1.9.1)
- grading_hybrid_rf.json     metadata: features, classes, setting, backbone, evaluation
- ../tests/fixtures/hybrid_golden.json  predictions on synthetic inputs, for parity tests

With --onnx-embeddings FILE.npz (tissue_ids, embeddings computed by the exported ONNX
backbone with ml-service preprocessing), the script also records how often the
served backbone's embeddings change the model's prediction for training tissues.

Usage (from ml/):
    .venv/Scripts/python.exe grading/scripts/train_hybrid_grading_model.py \
        --backbone ../ml-service/models/grading_backbone/resnet50_backbone.onnx [--onnx-embeddings FILE.npz]
"""
import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modeling_setup as ms  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ml-service" / "scripts"))
from backbone_check import reference, verify_and_record  # noqa: E402

SEED = ms.RANDOM_STATE
REVIEW_IDS = ["NEB-2024-08-16259 R", "NEB-2025-09-17471 R"]
MANIFEST = ms.PROCESSED_DIR.parent.parent / "image" / "data" / "processed" / "clean_image_manifest.csv"
REPO_DIR = Path(__file__).resolve().parents[3]
EMBEDDING_PATH = ms.PROCESSED_DIR.parent.parent / "image" / "data" / "processed" / "embeddings" / "resnet50_imagenet_fullres.npz"
MODEL_DIR = REPO_DIR / "ml-service" / "models"
GOLDEN_PATH = REPO_DIR / "ml-service" / "tests" / "fixtures" / "hybrid_golden.json"

# Same grid and tie-break order as notebook 13 (fewer/larger first; first maximum wins).
TAB_GRID = [
    {"min_samples_leaf": leaf, "max_depth": depth, "max_features": features, "class_weight": weight}
    for leaf in [5, 2, 1]
    for depth in [15, None]
    for features in ["sqrt", 0.3]
    for weight in ["balanced", None]
]

PCA_GRID = [8, 16, 32]
EMBEDDING_DIM = 2048
EMBEDDING_COLUMNS = [f"emb_{i}" for i in range(EMBEDDING_DIM)]
TRAINING_IMAGE_SIZE = [1296, 972]  # width, height of every training image (greyscale JPEG)

# Nested-CV performance of this arm on the 470 primary-cohort tissues with ECD (notebook 13).
NESTED_CV = {
    "source": "13_nested_tuning_model_selection.ipynb (25 donor-grouped outer folds, 3-fold inner tuning)",
    "macro_f1": "0.793 ± 0.047", "balanced_accuracy": "0.775 ± 0.050", "accuracy": "0.797 ± 0.040",
    "grade_b_recall": "0.789 ± 0.130",
    "vs_ecd_tree_macro_f1": "−0.003 [−0.034, +0.029], Holm p = 1.00 (not significant)",
    "vs_tuned_tabular_macro_f1": "−0.012 [−0.045, +0.022], Holm p = 1.00 (not significant)",
}


def normalize_id(value):
    return " ".join(str(value).split()).replace("NEB- ", "NEB-").casefold()


def load_cohort():
    labelled = ms.load_labelled_data()
    labelled["Donor_Group"] = ms.get_donor_groups(labelled)
    manifest_ids = set(pd.read_csv(MANIFEST)["Tissue_ID"].map(normalize_id)) - {normalize_id(i) for i in REVIEW_IDS}
    year = labelled["Tissue_ID"].str.extract(r"NEB-\s*(\d{4})")[0].astype("Int64")
    keep = labelled["Tissue_ID"].map(normalize_id).isin(manifest_ids) & year.notna() & (year != 2023)
    cohort = labelled[keep.to_numpy()].reset_index(drop=True)
    assert len(cohort) == 551 and cohort["Donor_Group"].nunique() == 312, "Primary cohort differs from notebook 13"
    return cohort


def synthetic_inputs(cohort):
    """Plausible but synthetic feature rows (no tissue's values), including missing values."""
    rng = np.random.default_rng(SEED)
    rows = []
    for i in range(60):
        row = {}
        for f in ms.NUMERIC_FEATURES:
            lo, hi = cohort[f].min(), cohort[f].max()
            row[f] = None if i % 11 == 0 else float(round(rng.uniform(lo, hi)))
        for f in ms.CLINICAL_BINARY_FEATURES:
            row[f] = None if i % 7 == 0 else int(rng.integers(0, 2))
        for f in ms.CLINICAL_CATEGORICAL_FEATURES:
            options = sorted(cohort[f].dropna().unique().tolist())
            row[f] = None if i % 3 == 0 else str(rng.choice(options))
        rows.append(row)
    rows.append({f: None for f in ms.ALL_FEATURES})  # everything "not recorded"
    return rows


def to_frame(rows):
    """The exact dtypes used in training: float for Konan and binary features, str for categories."""
    frame = pd.DataFrame(rows, columns=ms.ALL_FEATURES)
    for f in ms.NUMERIC_FEATURES + ms.CLINICAL_BINARY_FEATURES:
        frame[f] = pd.to_numeric(frame[f], errors="raise").astype("float64")
    for f in ms.CLINICAL_CATEGORICAL_FEATURES:
        frame[f] = frame[f].astype("str").where(frame[f].notna(), np.nan).astype("str")
    return frame


def make_pipeline(n_components, setting):
    features = ColumnTransformer([
        ("tabular", ms.make_preprocessor(), ms.ALL_FEATURES),
        ("image", Pipeline([
            ("scaler", StandardScaler()),
            ("pca", PCA(n_components=n_components, random_state=SEED)),
        ]), EMBEDDING_COLUMNS),
    ], remainder="drop")
    return Pipeline([
        ("features", features),
        ("classifier", RandomForestClassifier(n_estimators=300, random_state=SEED, n_jobs=-1, **setting)),
    ])


def tune(X, y, groups):
    """Notebook 13's inner tuning: fit the preprocessor once per (fold, k), then every forest setting."""
    candidates = [(k, s) for k in PCA_GRID for s in TAB_GRID]
    scores = np.zeros((3, len(candidates)))
    splitter = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED)
    for i, (tr, va) in enumerate(splitter.split(X, y, groups=groups)):
        for k in PCA_GRID:
            pre = make_pipeline(k, TAB_GRID[0]).named_steps["features"].fit(X.iloc[tr], y[tr])
            Z_tr, Z_va = pre.transform(X.iloc[tr]), pre.transform(X.iloc[va])
            for j, (kk, setting) in enumerate(candidates):
                if kk != k:
                    continue
                forest = RandomForestClassifier(n_estimators=300, random_state=SEED, n_jobs=-1, **setting)
                pred = forest.fit(Z_tr, y[tr]).predict(Z_va)
                scores[i, j] = f1_score(y[va], pred, labels=ms.CLASSES, average="macro", zero_division=0)
    mean = scores.mean(axis=0)
    best = int(np.argmax(mean))  # first maximum = notebook 13's tie-break order
    return candidates[best], float(mean[best])


def with_embeddings(tabular: pd.DataFrame, embeddings: np.ndarray) -> pd.DataFrame:
    return pd.concat([tabular.reset_index(drop=True), pd.DataFrame(embeddings, columns=EMBEDDING_COLUMNS)], axis=1)


def synthetic_embedding(seed: int) -> np.ndarray:
    """Deterministic non-negative vector shaped like pooled ResNet features (not from any image)."""
    return np.random.default_rng(seed).exponential(0.45, EMBEDDING_DIM)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", type=Path, required=True, help="exported ONNX backbone (for its SHA-256)")
    parser.add_argument("--onnx-embeddings", type=Path, help="embeddings of training images from the ONNX backbone")
    args = parser.parse_args()

    cohort = load_cohort()
    cached = np.load(EMBEDDING_PATH, allow_pickle=True)
    row_of = {t: i for i, t in enumerate(cached["tissue_ids"])}
    embeddings = cached["embeddings"][[row_of[t] for t in cohort["Tissue_ID"]]]
    X = with_embeddings(cohort[ms.ALL_FEATURES], embeddings)
    y = cohort[ms.TARGET].to_numpy()

    (n_components, setting), inner_f1 = tune(X, y, cohort["Donor_Group"].to_numpy())
    model = make_pipeline(n_components, setting).fit(X, y)
    print(f"Selected PCA {n_components}, {setting} (inner-CV macro F1 {inner_f1:.4f})")

    # The inference-time frame builder must reproduce training predictions exactly.
    tabular = to_frame(cohort[ms.ALL_FEATURES].astype(object).where(cohort[ms.ALL_FEATURES].notna(), None)
                       .to_dict(orient="records"))
    rebuilt = with_embeddings(tabular, embeddings.astype(np.float32))
    assert np.array_equal(model.predict(rebuilt), model.predict(X)), "Inference dtypes do not match training"
    assert np.allclose(model.predict_proba(rebuilt), model.predict_proba(X)), "Inference dtypes do not match training"

    parity = None
    if args.onnx_embeddings:
        served = np.load(args.onnx_embeddings, allow_pickle=True)
        served_of = {t: i for i, t in enumerate(served["tissue_ids"])}
        served_emb = served["embeddings"][[served_of[t] for t in cohort["Tissue_ID"]]]
        rel = np.linalg.norm(served_emb - embeddings, axis=1) / np.linalg.norm(embeddings, axis=1)
        X_served = with_embeddings(cohort[ms.ALL_FEATURES], served_emb)
        same = model.predict(X_served) == model.predict(X)
        prob_diff = np.abs(model.predict_proba(X_served) - model.predict_proba(X)).max()
        parity = {
            "tissues": int(len(cohort)),
            "max_relative_l2_difference": round(float(rel.max()), 5),
            "same_prediction": int(same.sum()),
            "max_probability_difference": round(float(prob_diff), 4),
            "note": "Training embeddings were computed with PyTorch (notebook 07); the service uses the "
                    "ONNX export on CPU. Counts compare the fitted model's predictions on the 551 training "
                    "tissues with each set of embeddings.",
        }
        print(f"Backbone parity: {parity['same_prediction']}/{len(cohort)} same prediction, "
              f"max probability difference {parity['max_probability_difference']}, "
              f"max relative embedding difference {parity['max_relative_l2_difference']}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "grading_hybrid_rf.joblib"
    joblib.dump(model, model_path, compress=3)
    meta = {
        "model": "hybrid_random_forest_24_resnet50",
        "version": 1,
        "features": ms.ALL_FEATURES,
        "embedding_columns": EMBEDDING_DIM,
        "classes": [str(c) for c in model.classes_],
        "setting": {"pca_components": n_components, **setting, "n_estimators": 300, "random_state": SEED},
        "inner_cv_macro_f1": round(inner_f1, 4),
        "backbone": {
            "file": "grading_backbone/resnet50_backbone.onnx",
            "sha256": hashlib.sha256(args.backbone.read_bytes()).hexdigest(),
            "source": "torchvision ResNet-50, IMAGENET1K_V2, fc removed (scripts/export_grading_backbone.py)",
            "preprocessing": "8-bit greyscale at full resolution, /255, repeated to 3 channels, "
                             "ImageNet mean/std normalisation (notebook 07)",
            "training_image_size": TRAINING_IMAGE_SIZE,
            # Exports verify against this output, not the bytes (ml-service/scripts/backbone_check.py).
            "reference": reference(args.backbone),
            "parity_with_training_embeddings": parity,
        },
        "training": {
            "cohort": "Primary cohort K3: non-2023, image-matched tissues (RESULTS.md)",
            "tissues": int(len(cohort)), "donors": int(cohort["Donor_Group"].nunique()),
            "grades": {str(k): int(v) for k, v in cohort[ms.TARGET].value_counts().items()},
            "data_sha256": hashlib.sha256(ms.DATA_PATH.read_bytes()).hexdigest(),
            "embeddings_sha256": hashlib.sha256(EMBEDDING_PATH.read_bytes()).hexdigest(),
            "versions": {"scikit_learn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__},
            "trained_on": date.today().isoformat(),
        },
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "evaluation": NESTED_CV,
        "probability_note": "predict_proba is the share of trees voting for each grade. It has not been "
                            "calibrated and must not be presented as a confidence.",
        "deployment_note": "Served as the application grade by project decision; notebook 13's rule had "
                           "selected the ECD tree, and the hybrid was not better than it or than the tuned "
                           "tabular model. See ANALYSIS_PLAN.md, Amendment 2.",
    }
    (MODEL_DIR / "grading_hybrid_rf.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    verify_and_record(args.backbone, meta["backbone"]["reference"])  # lets the local service load this backbone

    inputs = synthetic_inputs(cohort)
    seeds = [1000 + i for i in range(len(inputs))]
    frame = with_embeddings(to_frame(inputs), np.stack([synthetic_embedding(s) for s in seeds]).astype(np.float32))
    golden = {
        "model_sha256": meta["model_sha256"],
        "embedding": "numpy default_rng(seed).exponential(0.45, 2048), cast to float32",
        "cases": [
            {"features": row, "embedding_seed": seed, "grade": str(g),
             "probabilities": {str(c): round(float(p), 6) for c, p in zip(model.classes_, probs)}}
            for row, seed, g, probs in zip(inputs, seeds, model.predict(frame), model.predict_proba(frame))
        ],
    }
    GOLDEN_PATH.write_text(json.dumps(golden, indent=1) + "\n")
    print(f"Wrote {model_path} ({model_path.stat().st_size / 1e6:.1f} MB), metadata and {len(inputs)} golden cases")


if __name__ == "__main__":
    main()
