"""
Phase 0, Step 0.6 — integrity tests for the frozen data manifest and split.

These guard the assumptions every later phase relies on:
  * every tissue belongs to exactly one split (no train/test leakage)
  * only ``included`` rows carry a split; excluded / review rows never do
  * the test set is exactly the frozen one recorded in split_summary.json
  * split proportions match config.yaml
  * the calibration set is green-grade only
  * every referenced image exists (skipped when the images are not present)

Run from ml/cellular/:
    python -m pytest            # all tests
    python -m pytest -v         # one line per test
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from config import load_config
# Aliased: a name starting with "test_" would be collected by pytest as a test.
from data_prep.build_manifest import MANIFEST_COLUMNS
from data_prep.build_manifest import test_set_hash as compute_test_hash

VALID_SPLITS = {"train", "calibration", "val", "test"}
SHARE_TOLERANCE = 0.03     # allowed absolute deviation from the configured split share


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def manifest(cfg):
    path = cfg["paths"]["splits_dir"] / "manifest.csv"
    if not path.exists():
        pytest.fail(f"{path} not found - run `python -m data_prep.build_manifest` first.")
    # keep_default_na=False: an empty split stays "" instead of becoming NaN
    return pd.read_csv(path, keep_default_na=False, na_values=[""],
                       dtype={"split": str, "group_id": str, "status": str})


@pytest.fixture(scope="module")
def summary(cfg):
    return json.loads((cfg["paths"]["splits_dir"] / "split_summary.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def assigned(manifest):
    """Rows that belong to a split."""
    return manifest[manifest["split"].notna()]


# -----------------------------------------------------------------------------
# Structure
# -----------------------------------------------------------------------------
def test_manifest_has_expected_columns(manifest):
    missing = set(MANIFEST_COLUMNS) - set(manifest.columns)
    assert not missing, f"manifest.csv is missing columns: {sorted(missing)}"


def test_image_ids_are_unique(manifest):
    dupes = manifest.loc[manifest["image_id"].duplicated(), "image_id"].tolist()
    assert not dupes, f"duplicate image_id values: {dupes[:5]}"


def test_split_labels_are_valid(assigned):
    unknown = set(assigned["split"]) - VALID_SPLITS
    assert not unknown, f"unknown split labels: {unknown}"


# -----------------------------------------------------------------------------
# Split assignment rules
# -----------------------------------------------------------------------------
def test_every_included_row_has_a_split(manifest):
    inc = manifest[manifest["status"] == "included"]
    without = inc[inc["split"].isna()]
    assert without.empty, f"{len(without)} included rows have no split, e.g. {without['image_id'].head(3).tolist()}"


def test_only_included_rows_have_a_split(manifest):
    leaked = manifest[(manifest["status"] != "included") & manifest["split"].notna()]
    assert leaked.empty, f"non-included rows were given a split: {leaked['image_id'].head(3).tolist()}"


def test_no_tissue_in_more_than_one_split(assigned):
    per_group = assigned.groupby("group_id")["split"].nunique()
    leaking = per_group[per_group > 1]
    assert leaking.empty, f"{len(leaking)} tissues appear in several splits, e.g. {leaking.index[:3].tolist()}"


def test_calibration_is_green_grade_only(assigned):
    cal = assigned[assigned["split"] == "calibration"]
    assert not cal.empty, "calibration split is empty"
    non_green = cal[cal["grade"].astype(str).str.lower() != "green"]
    assert non_green.empty, f"non-green calibration images: {non_green['image_id'].tolist()}"


# -----------------------------------------------------------------------------
# Frozen test set and proportions
# -----------------------------------------------------------------------------
def test_test_set_matches_frozen_hash(manifest, summary):
    assert compute_test_hash(manifest.fillna({"split": ""})) == summary["test_hash_sha256"], (
        "the test set in manifest.csv differs from the frozen one in split_summary.json")


def test_summary_counts_match_manifest(assigned, summary):
    for name, info in summary["splits"].items():
        assert (assigned["split"] == name).sum() == info["images"], f"count mismatch for split '{name}'"


def test_split_shares_match_config(assigned, cfg):
    s = cfg["split"]
    expected = {
        "train": s["train"] - s["calibration_from_train"],
        "calibration": s["calibration_from_train"],
        "val": s["val"],
        "test": s["test"],
    }
    shares = assigned["split"].value_counts(normalize=True)
    for name, target in expected.items():
        actual = float(shares.get(name, 0.0))
        assert abs(actual - target) <= SHARE_TOLERANCE, (
            f"{name}: share {actual:.3f} vs target {target:.3f} (tolerance ±{SHARE_TOLERANCE})")


# -----------------------------------------------------------------------------
# Data on disk
# -----------------------------------------------------------------------------
def test_assigned_images_exist(assigned, cfg):
    images_dir = cfg["paths"]["images_dir"]
    if not images_dir.exists():
        pytest.skip(f"images not available at {images_dir}")
    missing = [f for f in assigned["image_file"] if not (images_dir / f).exists()]
    assert not missing, f"{len(missing)} images referenced by the split are missing, e.g. {missing[:3]}"
