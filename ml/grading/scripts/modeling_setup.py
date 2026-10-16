"""Shared setup for the modelling notebooks (05 onwards).

Recreates the data, feature lists, holdout split, CV folds and
preprocessing defined in 04_feature_preparation.ipynb, so later
notebooks no longer depend on 04's in-memory kernel state.

Place this file in the same folder as the notebooks.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import (
    StratifiedGroupKFold,
    StratifiedKFold,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# ---------------------------------------------------------------- paths
# Resolved from this file so notebooks in any subfolder can import it.
PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
DATA_PATH = PROCESSED_DIR / "cleaned_grading_dataset.xlsx"
SPLIT_PATH = PROCESSED_DIR / "holdout_split.csv"
DONOR_FOLDS_PATH = PROCESSED_DIR / "donor_grouped_folds.csv"

# ---------------------------------------------------------------- config
TARGET = "Tissue_Grade_Clean"
CLASSES = ["A+", "A", "B"]
RANDOM_STATE = 42
TEST_SIZE = 0.20
N_SPLITS = 5

# ---------------------------------------------------------------- features
ECD_FEATURES = ["ECD_CD_cells_per_mm2"]

MORPHOLOGY_FEATURES = [
    "CV",
    "HEX_percent",
    "SD",
    "Total_Cell_Count",
    "Total_Area_um2",
]

NUMERIC_FEATURES = ECD_FEATURES + MORPHOLOGY_FEATURES

CLINICAL_BINARY_FEATURES = [
    "Stroma_Is_Clear",
    "Stroma_Is_Compact",
    "Stroma_Has_Arcus",
    "Stroma_Has_Edema",
    "Stroma_Has_Scar",
    "Epi_Has_Arcus",
    "Epi_Has_Defect",
    "Epi_Has_Exposure",
    "Epi_Has_Haze",
    "Endo_Has_Stress_Lines",
    "Endo_Has_RBC",
    "Endo_Has_Cell_Dropout",
    "Descemet_Has_Folds",
]

# Reduced set from 04 (Epi_Exposure_Location and
# Endo_Stress_Line_Amount excluded for very low category support).
CLINICAL_CATEGORICAL_FEATURES = [
    "Descemet_Fold_Severity",
    "Descemet_Fold_Relative_Number",
    "Endo_Stress_Line_Location",
    "Stroma_Arcus_Severity",
    "Epi_Exposure_Severity",
]

CLINICAL_FEATURES = CLINICAL_BINARY_FEATURES + CLINICAL_CATEGORICAL_FEATURES
ALL_FEATURES = NUMERIC_FEATURES + CLINICAL_FEATURES  # 24 features

# ---------------------------------------------------------------- checks from 04 outputs
EXPECTED_COUNTS = {"A+": 545, "A": 319, "B": 172}
EXPECTED_TEST_COUNTS = {"A+": 109, "A": 64, "B": 35}

# Tissue IDs that appeared in 04's holdout error analysis,
# used to confirm the regenerated split matches the original one.
KNOWN_TEST_IDS = [
    "NEB-2023-11-15526 R",
    "NEB-2020-09-12665 L",
    "NEB-2023-12-15605 R",
    "NEB-2025-11-17635 R",
    "NEB-2024-08-16275 L",
]


def load_labelled_data(path=DATA_PATH):
    """Load the cleaned dataset and keep rows with a valid specialist grade."""
    df = pd.read_excel(path)

    missing = [col for col in [TARGET, *ALL_FEATURES] if col not in df.columns]
    if missing:
        raise ValueError(
            f"{path} has shape {df.shape} and is missing {len(missing)} "
            f"expected columns (e.g. {missing[:5]}). The processed file is "
            "out of date: re-run 02_data_cleaning.ipynb with "
            "'Restart Kernel and Run All' to regenerate it."
        )

    labelled = df[df[TARGET].isin(CLASSES)].reset_index(drop=True)

    counts = labelled[TARGET].value_counts().to_dict()
    if counts != EXPECTED_COUNTS:
        raise ValueError(
            f"Grade counts {counts} differ from 04 ({EXPECTED_COUNTS}). "
            "Check the cleaning notebook before modelling."
        )

    return labelled


def get_holdout_split(labelled):
    """Return (train_df, test_df) using the same split as notebook 04.

    The first call recreates the split with train_test_split and saves the
    Tissue_IDs (in train_test_split's order) to SPLIT_PATH. Later calls read
    that file, so the split no longer depends on row order or random state.
    Row order is preserved because it determines the CV folds.
    """
    if SPLIT_PATH.exists():
        split = pd.read_csv(SPLIT_PATH)
    else:
        train_idx, test_idx = train_test_split(
            labelled.index,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
            stratify=labelled[TARGET],
        )
        split = pd.DataFrame({
            "Tissue_ID": np.concatenate([
                labelled.loc[train_idx, "Tissue_ID"].to_numpy(),
                labelled.loc[test_idx, "Tissue_ID"].to_numpy(),
            ]),
            "Split": ["train"] * len(train_idx) + ["test"] * len(test_idx),
        })
        split.to_csv(SPLIT_PATH, index=False)
        print(f"Saved holdout split to {SPLIT_PATH}")

    by_id = labelled.set_index("Tissue_ID", drop=False)
    train_ids = split.loc[split["Split"] == "train", "Tissue_ID"]
    test_ids = split.loc[split["Split"] == "test", "Tissue_ID"]

    train_df = by_id.loc[train_ids].reset_index(drop=True)
    test_df = by_id.loc[test_ids].reset_index(drop=True)

    # Sanity checks against notebook 04.
    assert set(train_ids).isdisjoint(test_ids), "Train/test overlap"
    assert len(train_df) + len(test_df) == len(labelled), "Rows lost in split"
    test_counts = test_df[TARGET].value_counts().to_dict()
    assert test_counts == EXPECTED_TEST_COUNTS, (
        f"Test counts {test_counts} differ from 04 ({EXPECTED_TEST_COUNTS})"
    )
    missing_known = set(KNOWN_TEST_IDS) - set(test_ids)
    assert not missing_known, (
        f"Split differs from 04: {missing_known} should be in the test set"
    )

    return train_df, test_df


def make_preprocessor(
    numeric=NUMERIC_FEATURES,
    binary=CLINICAL_BINARY_FEATURES,
    categorical=CLINICAL_CATEGORICAL_FEATURES,
    scale_numeric=True,
):
    """Build the 04 preprocessing for any subset of feature groups.

    Pass an empty list to drop a group, e.g. make_preprocessor(binary=[],
    categorical=[]) for numeric-only models. Missing clinical values are
    kept as their own category, as in 04.
    """
    transformers = []

    if numeric:
        steps = [("imputer", SimpleImputer(strategy="median"))]
        if scale_numeric:
            steps.append(("scaler", StandardScaler()))
        transformers.append(("numeric", Pipeline(steps), list(numeric)))

    if binary:
        transformers.append((
            "clinical_binary",
            Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value=-1)),
                ("encoder", OneHotEncoder(handle_unknown="ignore")),
            ]),
            list(binary),
        ))

    if categorical:
        transformers.append((
            "clinical_categorical",
            Pipeline([
                ("imputer", SimpleImputer(
                    strategy="constant", fill_value="__MISSING__"
                )),
                ("encoder", OneHotEncoder(handle_unknown="ignore")),
            ]),
            list(categorical),
        ))

    return ColumnTransformer(transformers=transformers, remainder="drop")


def make_cv():
    """The same stratified 5-fold splitter used throughout 04."""
    return StratifiedKFold(
        n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE
    )


# ---------------------------------------------------------------- donor grouping
N_REPEATS = 5


def get_donor_groups(df):
    """Infer a donor ID per tissue, aligned with df.index.

    Fellow eyes from one donor receive consecutive Tissue_Serial numbers
    with opposite eyes. Two consecutive tissues are treated as the same
    donor when they also share Donor_Age and either the cause of death
    or the death time, and their death times do not contradict each
    other. The rule errs towards grouping: merging two donors only costs
    fold balance, while missing a pair would leak a fellow eye.
    """
    d = df.sort_values("Tissue_Serial")
    prev = d.shift()

    cod = (
        d["Primary_COD"].astype(str).str.lower()
        .str.replace(r"[^a-z]", "", regex=True).str[:12]
    )
    death = d["Death_Date_Time"]
    both_death = death.notna() & prev["Death_Date_Time"].notna()
    same_death = both_death & (death == prev["Death_Date_Time"])

    same_donor = (
        (d["Tissue_Serial"].diff() == 1)
        & (d["Eye"] != prev["Eye"])
        & d["Donor_Age"].notna()
        & (d["Donor_Age"] == prev["Donor_Age"])
        & ((cod == cod.shift()) | same_death)
        & (~both_death | same_death)
    )

    donor = (~same_donor).cumsum()
    return ("D" + donor.astype(str)).reindex(df.index).rename("Donor_Group")


def make_group_cv(random_state=RANDOM_STATE):
    """Stratified 5-fold splitter that keeps each donor in one fold."""
    return StratifiedGroupKFold(
        n_splits=N_SPLITS, shuffle=True, random_state=random_state
    )


def get_donor_folds(labelled):
    """Return repeated donor-grouped fold assignments for labelled tissues.

    Columns: Tissue_ID, Donor_Group, Fold_r0 ... Fold_r{N_REPEATS-1}.
    The first call creates the folds and saves them to DONOR_FOLDS_PATH;
    later calls read that file so every model (tabular, image, hybrid)
    is evaluated on identical folds. Filter to a sub-cohort (e.g. tissues
    with images) by Tissue_ID; donors stay within one fold.
    """
    if DONOR_FOLDS_PATH.exists():
        folds = pd.read_csv(DONOR_FOLDS_PATH)
        missing = set(labelled["Tissue_ID"]) - set(folds["Tissue_ID"])
        if missing:
            raise ValueError(
                f"{len(missing)} tissues have no fold assignment; delete "
                f"{DONOR_FOLDS_PATH} to regenerate the folds."
            )
        return folds

    folds = pd.DataFrame({
        "Tissue_ID": labelled["Tissue_ID"].to_numpy(),
        "Donor_Group": get_donor_groups(labelled).to_numpy(),
    })
    for repeat in range(N_REPEATS):
        column = np.empty(len(labelled), dtype=int)
        splitter = make_group_cv(random_state=RANDOM_STATE + repeat)
        for fold, (_, test_idx) in enumerate(splitter.split(
            labelled, labelled[TARGET], groups=folds["Donor_Group"]
        )):
            column[test_idx] = fold
        folds[f"Fold_r{repeat}"] = column

    folds.to_csv(DONOR_FOLDS_PATH, index=False)
    print(f"Saved donor-grouped folds to {DONOR_FOLDS_PATH}")
    return folds


def iter_donor_folds(folds, tissue_ids, repeat=0):
    """Yield (train_idx, test_idx) positions for tissue_ids in one repeat.

    Positions refer to the order of tissue_ids, so they can index the
    feature matrix built from the same rows.
    """
    assignment = (
        folds.set_index("Tissue_ID").loc[list(tissue_ids), f"Fold_r{repeat}"]
        .to_numpy()
    )
    for fold in range(N_SPLITS):
        yield (
            np.flatnonzero(assignment != fold),
            np.flatnonzero(assignment == fold),
        )