"""Shared setup for the cleaned viva notebooks (notebooks_cleaned/).

Notebooks images/06-15 each re-declared the same cohort code, model settings
and paired statistics. The cleaned notebooks import one copy from here.
Every definition reproduces the original code exactly, including row order,
because Random Forest results depend on it.

Nothing in this module writes files.
"""
import hashlib
import inspect
import os
from pathlib import Path

# joblib worker processes do not inherit the notebook's warning filters; without this they
# print a scikit-learn UserWarning on every fit (notebook 13's file once grew to 87 MB).
os.environ.setdefault("PYTHONWARNINGS", "ignore::UserWarning")

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    cohen_kappa_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

import modeling_setup as ms

# ---------------------------------------------------------------- paths
GRADING_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = GRADING_DIR.parents[1]
PROCESSED_DIR = ms.PROCESSED_DIR
IMAGE_DATA_DIR = GRADING_DIR / "image" / "data" / "processed"
IMAGE_DIR = IMAGE_DATA_DIR / "images"
MANIFEST_PATH = IMAGE_DATA_DIR / "clean_image_manifest.csv"
EMBEDDING_PATH = IMAGE_DATA_DIR / "embeddings" / "resnet50_imagenet_fullres.npz"
SHARED_SPLIT_PATH = IMAGE_DATA_DIR / "splits" / "multimodal_shared_split.csv"
DEPLOYED_MODEL_DIR = REPO_DIR / "ml-service" / "models"

# ---------------------------------------------------------------- config
SEED = ms.RANDOM_STATE
ECD = "ECD_CD_cells_per_mm2"
CLASSES = list(ms.CLASSES)
ORDINAL = ["B", "A", "A+"]  # kappa weights follow this order
REVIEW_IDS = ["NEB-2024-08-16259 R", "NEB-2025-09-17471 R"]  # two image files per ID, contents differ
EMBEDDING_COLUMNS = [f"emb_{i}" for i in range(2048)]

# Random Forest tuned in notebook 05 (non-grouped CV); used unchanged in notebooks 06-12.
NB05_RF_PARAMS = dict(
    n_estimators=300, max_depth=15, min_samples_split=5, min_samples_leaf=1,
    max_features="sqrt", class_weight="balanced", random_state=SEED, n_jobs=-1,
)
# Depth-2 ECD threshold tree fixed in notebook 11 and never tuned.
TREE_PARAMS = dict(
    max_depth=2, min_samples_leaf=10, class_weight="balanced",
    criterion="gini", random_state=SEED,
)

EXPECTED = {
    "K2": {"tissues": 1009, "donors": 770},
    "K3": {"tissues": 551, "donors": 312},
    "K4": {"tissues": 470, "donors": 280, "grades": {"A+": 244, "A": 159, "B": 67}},
}


def normalize_id(value):
    """Tissue ID as used to match the image manifest (whitespace and case normalised)."""
    return " ".join(str(value).split()).replace("NEB- ", "NEB-").casefold()


def sha256(path, length=16):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:length]


def show_source(*objects):
    """Print the source of shared functions, so their code is visible in the notebook."""
    for obj in objects:
        print(inspect.getsource(obj))


# ---------------------------------------------------------------- cohorts
def _manifest():
    manifest = pd.read_csv(MANIFEST_PATH)
    manifest["Match_ID"] = manifest["Tissue_ID"].map(normalize_id)
    return manifest[~manifest["Match_ID"].isin({normalize_id(i) for i in REVIEW_IDS})]


def image_cohort():
    """K2: labelled tissues with a usable image (notebooks 07-08), with donor folds."""
    labelled = ms.load_labelled_data()
    folds = ms.get_donor_folds(labelled)
    labelled["Match_ID"] = labelled["Tissue_ID"].map(normalize_id)
    cohort = (
        labelled
        .merge(_manifest()[["Match_ID", "Selected_Image"]], on="Match_ID", how="inner", validate="one_to_one")
        .merge(folds, on="Tissue_ID", how="left", validate="one_to_one")
        .reset_index(drop=True)
    )
    assert {"tissues": len(cohort), "donors": cohort["Donor_Group"].nunique()} == EXPECTED["K2"], "K2 differs"
    return cohort, folds


def primary_cohort():
    """K3: K2 tissues whose Tissue_ID year is not 2023 (notebooks 09-15), with donor folds.

    Returns (cohort, folds, has_ecd); has_ecd marks the K4 evaluation tissues.
    """
    labelled = ms.load_labelled_data()
    folds = ms.get_donor_folds(labelled)
    labelled["Match_ID"] = labelled["Tissue_ID"].map(normalize_id)
    labelled["Year"] = labelled["Tissue_ID"].str.extract(r"NEB-\s*(\d{4})")[0].astype("Int64")
    with_image = labelled.merge(_manifest()[["Match_ID"]], on="Match_ID", how="inner", validate="one_to_one")
    cohort = (
        with_image[with_image["Year"].notna() & (with_image["Year"] != 2023)]
        .merge(folds, on="Tissue_ID", how="left", validate="one_to_one")
        .reset_index(drop=True)
    )
    has_ecd = cohort[ECD].notna().to_numpy()
    evaluation = cohort[has_ecd]
    assert {"tissues": len(cohort), "donors": cohort["Donor_Group"].nunique()} == EXPECTED["K3"], "K3 differs"
    assert {
        "tissues": len(evaluation), "donors": evaluation["Donor_Group"].nunique(),
        "grades": {k: int(v) for k, v in evaluation[ms.TARGET].value_counts().items()},
    } == EXPECTED["K4"], "K4 differs"
    return cohort, folds, has_ecd


def feature_matrix(cohort):
    """24 recorded features plus the cached 2048-d ResNet-50 embedding, aligned by Tissue_ID."""
    cached = np.load(EMBEDDING_PATH, allow_pickle=True)
    row_of = {tissue_id: i for i, tissue_id in enumerate(cached["tissue_ids"])}
    missing = [t for t in cohort["Tissue_ID"] if t not in row_of]
    assert not missing, f"{len(missing)} tissues have no cached embedding"
    embeddings = cached["embeddings"][[row_of[t] for t in cohort["Tissue_ID"]]]
    X = pd.concat([
        cohort[ms.ALL_FEATURES].reset_index(drop=True),
        pd.DataFrame(embeddings, columns=EMBEDDING_COLUMNS),
    ], axis=1)
    return X, cohort[ms.TARGET].to_numpy(), cohort["Donor_Group"].to_numpy()


def mean_fold_sizes(folds, tissue_ids):
    """Mean (train, test) sizes over the 25 folds, for the corrected t-test."""
    sizes = [
        (len(train), len(test))
        for repeat in range(ms.N_REPEATS)
        for train, test in ms.iter_donor_folds(folds, tissue_ids, repeat)
    ]
    return tuple(np.mean(sizes, axis=0))


# ---------------------------------------------------------------- models
def preprocessor(n_components=None, tabular=True, scale_components=False):
    """Tabular branch (ms.make_preprocessor) and/or image branch (scale -> PCA [-> scale])."""
    branches = []
    if tabular:
        branches.append(("tabular", ms.make_preprocessor(), ms.ALL_FEATURES))
    if n_components:
        steps = [("scaler", StandardScaler()), ("pca", PCA(n_components=n_components, random_state=SEED))]
        if scale_components:  # notebook 14 candidates only
            steps.append(("pca_scaler", StandardScaler()))
        branches.append(("image", Pipeline(steps), EMBEDDING_COLUMNS))
    return ColumnTransformer(branches, remainder="drop")


def rf_pipeline(n_components=None, tabular=True, **rf_params):
    """Random Forest on the tabular and/or image branches (notebook 05 settings unless overridden)."""
    params = {**NB05_RF_PARAMS, **rf_params}
    return Pipeline([
        ("features", preprocessor(n_components, tabular)),
        ("classifier", RandomForestClassifier(**params)),
    ])


def ecd_pipeline(classifier):
    """ECD as the only input, passed through unchanged (ECD tree and ECD-only Random Forest)."""
    return Pipeline([
        ("features", ColumnTransformer([("ecd", "passthrough", [ECD])], remainder="drop")),
        ("classifier", classifier),
    ])


def ecd_tree():
    return ecd_pipeline(DecisionTreeClassifier(**TREE_PARAMS))


def ecd_rule(values):
    """The eye bank's ECD grading rule: B below 2250, A from 2250 to below 2500, A+ from 2500 (cells/mm²).

    Reported descriptively, without tests: no written copy of the criteria was in the repository
    when notebooks 08-11 were run, so they compared models against an ECD tree fitted in training folds.
    """
    return np.where(values >= 2500, "A+", np.where(values >= 2250, "A", "B"))


# ---------------------------------------------------------------- metrics
def macro_f1(true, pred):
    return f1_score(true, pred, labels=CLASSES, average="macro", zero_division=0)


def recall_b(true, pred):
    return recall_score(true, pred, labels=["B"], average="macro", zero_division=0)


def kappa(true, pred):
    return cohen_kappa_score(true, pred, labels=ORDINAL, weights="quadratic")


METRICS = {
    "Macro F1": macro_f1,
    "Balanced accuracy": balanced_accuracy_score,
    "Accuracy": accuracy_score,
    "Recall B": recall_b,
}
METRICS_WITH_KAPPA = {**METRICS, "Kappa (quadratic)": kappa}


def per_grade(true, predictions):
    """Per-grade precision and recall for each model's predictions (pooled over repeats)."""
    return pd.concat({
        name: pd.DataFrame({
            "Precision": precision_score(true, pred, labels=CLASSES, average=None, zero_division=0),
            "Recall": recall_score(true, pred, labels=CLASSES, average=None, zero_division=0),
        }, index=CLASSES)
        for name, pred in predictions.items()
    }, axis=1)


def summarise(fold_scores, models, metrics, by="Model"):
    """Fold-level mean ± SD over the 25 folds, one row per model."""
    grouped = fold_scores.groupby(by)[list(metrics)]
    mean, sd = grouped.mean().reindex(models), grouped.std().reindex(models)
    return pd.DataFrame({m: [f"{a:.3f} ± {b:.3f}" for a, b in zip(mean[m], sd[m])] for m in metrics}, index=models)


# ---------------------------------------------------------------- paired statistics
def corrected_ttest(differences, n_train, n_test):
    """Corrected repeated-CV t-test (Nadeau & Bengio, 2003; Bouckaert & Frank, 2004).

    The variance of the 25 paired fold differences is inflated by n_test / n_train
    because training sets overlap across folds; df = 24. Returns mean, CI low,
    CI high, t and p. Undefined fold values (grade B recall in a subgroup fold
    without grade B tissues, notebook 08) are dropped first.
    """
    d = np.asarray(differences, dtype=float)
    d = d[~np.isnan(d)]
    n = len(d)
    se = np.sqrt((1 / n + n_test / n_train) * d.var(ddof=1))
    t = d.mean() / se if se > 0 else 0.0
    p = 2 * stats.t.sf(abs(t), df=n - 1)
    half = stats.t.ppf(0.975, df=n - 1) * se
    return d.mean(), d.mean() - half, d.mean() + half, t, p


def holm(p_values):
    """Holm step-down adjustment."""
    p_values = np.asarray(p_values, dtype=float)
    order = np.argsort(p_values)
    adjusted = np.empty_like(p_values)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (len(p_values) - rank) * p_values[idx])
        adjusted[idx] = min(running, 1.0)
    return adjusted


def paired_comparisons(fold_scores, comparisons, metrics, n_train, n_test, primary="Macro F1", by="Model"):
    """Paired fold-level differences for {ID: (model, baseline)}, Holm across the primary metric."""
    wide = fold_scores.pivot_table(index=["Repeat", "Fold"], columns=by, values=list(metrics))
    rows = []
    for label, (model, baseline) in comparisons.items():
        for metric in metrics:
            d = wide[(metric, model)] - wide[(metric, baseline)]
            mean, low, high, t, p = corrected_ttest(d, n_train, n_test)
            rows.append({
                "ID": label, "Comparison": f"{model} − {baseline}", "Metric": metric,
                "Model": wide[(metric, model)].mean(), "Baseline": wide[(metric, baseline)].mean(),
                "Difference": mean, "CI low": low, "CI high": high, "t": t, "p": p,
                "Folds improved": f"{(d > 0).sum()}/{len(d)}",
            })
    results = pd.DataFrame(rows)
    mask = results["Metric"] == primary
    results["p (Holm)"] = np.nan
    results.loc[mask, "p (Holm)"] = holm(results.loc[mask, "p"])
    return results


def verdict(difference, p):
    if p < 0.05:
        return "Improved" if difference > 0 else "Worse"
    return "Inconclusive"
