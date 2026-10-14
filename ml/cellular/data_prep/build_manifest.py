"""
Phase 0, Steps 0.3 + 0.4 — build the data manifest and the frozen split.

What it does
------------
1. Joins every image file in ``images_dir`` with the Konan ground-truth xlsx.
2. Checks each image (opens, expected size, not blank) and records simple
   intensity statistics for the later data audit.
3. Assigns one ``status`` per row, with the reason, so every exclusion is logged:
       excluded:no_ground_truth   image has no ground-truth row
       excluded:missing_image     ground-truth row whose image file is absent
       excluded:unreadable        image cannot be opened
       excluded:wrong_size        image is not width x height from config.yaml
       excluded:blank             image is (almost) empty / black
       excluded:invalid_gt        ECD, CV, HEX or cell count missing or zero
       review:needs_review        matched by serial only (kept out of splits)
       included                   usable for training / validation
4. Adds Konan self-consistency flags (kept, never dropped).
5. Makes a tissue-level, ECD-stratified split of the ``included`` rows:
       train / val / test, plus a small ``calibration`` set taken from train
       (used ONLY for the um/pixel estimate in Phase 4).
6. Freezes the test set: its SHA-256 hash is stored in split_summary.json and
   the script refuses to write a different test set unless ``--force`` is given.

Later phases must READ ``splits/manifest.csv`` and never re-split.

Outputs (in ``splits_dir``)
---------------------------
    manifest.csv         one row per image / ground-truth row
    split_summary.json   counts, biomarker means per split, seed, test hash

Usage (run from ml/cellular/)
-----------------------------
    python -m data_prep.build_manifest              # build and write
    python -m data_prep.build_manifest --dry-run    # print summary only
    python -m data_prep.build_manifest --force      # allow a new test set
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from PIL import Image
from sklearn.model_selection import StratifiedGroupKFold
from tqdm import tqdm

from config import ensure_output_dirs, load_config
from scripts.match_images import extract_key  # existing helper, reused unchanged

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

# An image whose mean or contrast is below these is treated as a failed capture.
BLANK_MEAN_THRESHOLD = 5.0
BLANK_STD_THRESHOLD = 2.0

# Konan consistency tolerances (flags only).
ECD_CHECK_TOL = 0.02      # |ecd - ecd_check| / ecd
ECD_AREA_TOL = 0.03       # |ecd - 1e6/mean_area| / ecd
CV_POINTS_TOL = 3.0       # |cv - 100*sd/mean_area| in percentage points

GROUPING_NOTE = (
    "Tissues are grouped by tissue serial number (5-digit serials) or by the "
    "normalised cornea ID (other formats). Whether both eyes of one donor share "
    "a serial is unconfirmed, so two eyes of the same donor could fall into "
    "different splits. Confirm with NEBSL and rebuild with --force before "
    "training if needed."
)

MANIFEST_COLUMNS = [
    "image_id", "image_file", "cornea_id", "group_id", "eye", "year", "grade",
    "donor_age", "ecd", "cv", "hex", "sd", "mean_area", "num_cells", "area_um2",
    "ecd_check", "needs_review", "dup_same_tissue", "match_method",
    "img_width", "img_height", "img_mean", "img_std",
    "status", "flags", "ecd_band", "split",
]


# -----------------------------------------------------------------------------
# Loading
# -----------------------------------------------------------------------------
def _to_bool(series: pd.Series) -> pd.Series:
    """Normalise 0/1, True/False and 'yes'/'no' columns to booleans."""
    return series.astype(str).str.strip().str.lower().isin(["1", "1.0", "true", "yes"])


def load_ground_truth(xlsx_path: Path) -> pd.DataFrame:
    """Read the Konan ground-truth workbook and normalise key columns."""
    gt = pd.read_excel(xlsx_path)
    gt["image_filename"] = gt["image_filename"].astype(str).str.strip()
    gt["needs_review"] = _to_bool(gt.get("needs_review", pd.Series(False, index=gt.index)))
    gt["dup_same_tissue"] = _to_bool(gt.get("dup_same_tissue", pd.Series(False, index=gt.index)))

    # Guard against the same image appearing twice in the workbook.
    gt["duplicate_gt_row"] = gt.duplicated("image_filename", keep="first")
    return gt


def list_images(images_dir: Path) -> list[str]:
    """Return sorted image filenames (not paths) in ``images_dir``."""
    return sorted(
        p.name for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


# -----------------------------------------------------------------------------
# Per-image checks
# -----------------------------------------------------------------------------
def inspect_image(path: Path) -> dict:
    """Open one image and return size + intensity statistics (or an error)."""
    try:
        with Image.open(path) as im:
            width, height = im.size
            arr = np.asarray(im.convert("L"), dtype=np.float32)
        return {"img_width": width, "img_height": height,
                "img_mean": round(float(arr.mean()), 2),
                "img_std": round(float(arr.std()), 2), "readable": True}
    except Exception:  # corrupt / truncated file
        return {"img_width": np.nan, "img_height": np.nan,
                "img_mean": np.nan, "img_std": np.nan, "readable": False}


# -----------------------------------------------------------------------------
# Grouping, status and flags
# -----------------------------------------------------------------------------
def tissue_group_id(cornea_id: str) -> str:
    """
    Key that keeps all captures of one tissue together.

    5-digit NEB-style serials are unique across the dataset, so they are used
    directly (this also survives typos in the ID prefix). Short serials (e.g.
    'HSEB-23-02' -> '23') could clash between ID series, so those keep their
    full normalised ID instead.
    """
    serial, _eye = extract_key(str(cornea_id))
    if serial and len(serial) == 5:
        return f"S{serial}"
    eye_stripped = re.sub(r"\s*[LR]\s*$", "", str(cornea_id).strip(), flags=re.I)
    return "ID-" + re.sub(r"[^A-Za-z0-9]", "", eye_stripped).upper()


def assign_status(row: pd.Series, cfg: dict) -> str:
    """Return the status for one merged row (first matching rule wins)."""
    if row["_merge"] == "left_only":
        return "excluded:no_ground_truth"
    if row["_merge"] == "right_only":
        return "excluded:missing_image"
    if not row["readable"]:
        return "excluded:unreadable"
    if (row["img_width"], row["img_height"]) != (cfg["image"]["width"], cfg["image"]["height"]):
        return "excluded:wrong_size"
    if row["img_mean"] < BLANK_MEAN_THRESHOLD or row["img_std"] < BLANK_STD_THRESHOLD:
        return "excluded:blank"
    for col in ("ecd", "cv", "hex", "num_cells"):
        if pd.isna(row[col]) or row[col] <= 0:
            return "excluded:invalid_gt"
    if row["needs_review"]:
        return "review:needs_review"
    return "included"


def consistency_flags(row: pd.Series) -> str:
    """Semicolon-separated Konan consistency flags (empty string if none)."""
    flags = []
    ecd, mean_area, sd, cv = row["ecd"], row["mean_area"], row["sd"], row["cv"]
    if pd.notna(ecd) and ecd > 0:
        if pd.notna(row["ecd_check"]) and abs(ecd - row["ecd_check"]) / ecd > ECD_CHECK_TOL:
            flags.append("ecd_vs_num_area")
        if pd.notna(mean_area) and mean_area > 0 and abs(ecd - 1e6 / mean_area) / ecd > ECD_AREA_TOL:
            flags.append("ecd_vs_mean_area")
    if pd.notna(cv) and pd.notna(sd) and pd.notna(mean_area) and mean_area > 0:
        if abs(cv - 100.0 * sd / mean_area) > CV_POINTS_TOL:
            flags.append("cv_vs_sd_mean")
    if row.get("dup_same_tissue"):
        flags.append("dup_same_tissue")
    if row.get("duplicate_gt_row"):
        flags.append("duplicate_gt_row")
    if pd.notna(row.get("year")) and not (2018 <= row["year"] <= 2026):
        flags.append("year_out_of_range")
    return ";".join(flags)


def ecd_band(ecd: float, bins: list[float]) -> str:
    """Label an ECD value with its stratification band, e.g. '2000-2800'."""
    if pd.isna(ecd):
        return ""
    edges = [-np.inf, *bins, np.inf]
    i = int(np.digitize(ecd, bins))
    lo, hi = edges[i], edges[i + 1]
    if np.isinf(lo):
        return f"<{int(hi)}"
    if np.isinf(hi):
        return f">{int(lo)}"
    return f"{int(lo)}-{int(hi)}"


# -----------------------------------------------------------------------------
# Splitting
# -----------------------------------------------------------------------------
def _hold_out_fold(df: pd.DataFrame, fraction: float, seed: int) -> pd.Index:
    """
    Take one fold of a StratifiedGroupKFold as a held-out set of roughly
    ``fraction`` of ``df``: groups never straddle folds and every fold has a
    similar ECD-band mix.
    """
    n_splits = max(2, round(1.0 / fraction))
    sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    _, held_idx = next(sgkf.split(df, df["ecd_band"], groups=df["group_id"]))
    return df.index[held_idx]


def make_splits(manifest: pd.DataFrame, split_cfg: dict) -> pd.Series:
    """Return a split label for every row ('' for rows not included)."""
    seed = split_cfg["seed"]
    split = pd.Series("", index=manifest.index, dtype=object)
    inc = manifest[manifest["status"] == "included"]
    n_total = len(inc)

    # 1) Test set from all included rows.
    test_idx = _hold_out_fold(inc, split_cfg["test"], seed)
    split.loc[test_idx] = "test"

    # 2) Validation set from what is left, sized relative to the full dataset.
    rest = inc.drop(index=test_idx)
    val_fraction_of_rest = split_cfg["val"] * n_total / len(rest)
    val_idx = _hold_out_fold(rest, val_fraction_of_rest, seed)
    split.loc[val_idx] = "val"
    split.loc[rest.index.difference(val_idx)] = "train"

    # 3) Calibration set: whole green-grade tissues moved out of train.
    train = manifest.loc[split == "train"]
    green_groups = (train.groupby("group_id")["grade"]
                    .apply(lambda g: (g.astype(str).str.lower() == "green").all()))
    candidates = list(green_groups[green_groups].index)
    rng = np.random.default_rng(seed)
    rng.shuffle(candidates)
    target = round(split_cfg["calibration_from_train"] * n_total)
    chosen, n_chosen = [], 0
    for gid in candidates:
        if n_chosen >= target:
            break
        chosen.append(gid)
        n_chosen += int((train["group_id"] == gid).sum())
    split.loc[train.index[train["group_id"].isin(chosen)]] = "calibration"
    return split


def test_set_hash(manifest: pd.DataFrame) -> str:
    """SHA-256 of the sorted test image IDs — the fingerprint of the frozen test set."""
    ids = sorted(manifest.loc[manifest["split"] == "test", "image_id"].astype(str))
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def summarise(manifest: pd.DataFrame, cfg: dict) -> dict:
    """Build the split_summary.json content."""
    inc = manifest[manifest["split"] != ""]
    per_split = {}
    for name, g in inc.groupby("split"):
        per_split[name] = {
            "images": int(len(g)),
            "tissues": int(g["group_id"].nunique()),
            "share": round(len(g) / len(inc), 4),
            "ecd_band_counts": {k: int(v) for k, v in g["ecd_band"].value_counts().sort_index().items()},
            "grade_counts": {str(k): int(v) for k, v in g["grade"].value_counts().items()},
            "mean": {c: round(float(g[c].mean()), 2) for c in ("ecd", "cv", "hex", "mean_area", "num_cells")},
        }
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": cfg["split"]["seed"],
        "ratios": {k: cfg["split"][k] for k in ("train", "val", "test", "calibration_from_train")},
        "stratified_by": f"ECD band, bins {cfg['split']['stratify_ecd_bins']}",
        "grouped_by": "group_id (tissue)",
        "grouping_limitation": GROUPING_NOTE,
        "sklearn_version": sklearn.__version__,
        "status_counts": {k: int(v) for k, v in manifest["status"].value_counts().items()},
        "flag_counts": {k: int(v) for k, v in manifest["flags"].str.split(";").explode()
                        .loc[lambda s: s != ""].value_counts().items()},
        "splits": per_split,
        "test_hash_sha256": test_set_hash(manifest),
    }


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def build(cfg: dict) -> pd.DataFrame:
    """Create the full manifest DataFrame (no files written)."""
    paths = cfg["paths"]
    images_dir = paths["images_dir"]

    gt = load_ground_truth(paths["ground_truth_xlsx"])
    gt = gt[~gt["duplicate_gt_row"]] if gt["duplicate_gt_row"].any() else gt
    files = pd.DataFrame({"image_file": list_images(images_dir)})

    merged = files.merge(gt, left_on="image_file", right_on="image_filename",
                         how="outer", indicator=True)
    merged["image_file"] = merged["image_file"].fillna(merged["image_filename"])

    # Inspect every image that exists on disk.
    stats = []
    for _, row in tqdm(merged.iterrows(), total=len(merged), desc="Checking images"):
        if row["_merge"] == "right_only":
            stats.append({"img_width": np.nan, "img_height": np.nan,
                          "img_mean": np.nan, "img_std": np.nan, "readable": False})
        else:
            stats.append(inspect_image(images_dir / row["image_file"]))
    merged = pd.concat([merged.reset_index(drop=True), pd.DataFrame(stats)], axis=1)

    # Rows without ground truth have NaN in these boolean columns; `.eq(True)`
    # maps True -> True and NaN/False -> False without pandas' downcast warning.
    for col in ("needs_review", "dup_same_tissue", "duplicate_gt_row"):
        merged[col] = merged[col].eq(True)

    merged["image_id"] = merged["image_file"].map(lambda f: Path(f).stem)
    merged["cornea_id"] = merged["matched_cornea_id"]
    merged["group_id"] = merged["cornea_id"].map(
        lambda c: tissue_group_id(c) if pd.notna(c) else "")
    merged["status"] = merged.apply(assign_status, axis=1, cfg=cfg)
    merged["flags"] = merged.apply(consistency_flags, axis=1)
    merged["ecd_band"] = merged["ecd"].map(
        lambda v: ecd_band(v, cfg["split"]["stratify_ecd_bins"]))

    merged["split"] = make_splits(merged, cfg["split"])
    return merged[MANIFEST_COLUMNS].sort_values("image_file").reset_index(drop=True)


def print_report(manifest: pd.DataFrame, summary: dict) -> None:
    """Human-readable summary for the notebook / terminal."""
    print(f"\nRows in manifest: {len(manifest)}")
    print("Status:")
    for k, v in summary["status_counts"].items():
        print(f"  {k:28s} {v:5d}")
    print("Consistency flags:", summary["flag_counts"] or "none")
    print("\nSplit        images  tissues  share   mean ECD   mean CV  mean HEX")
    for name in ("train", "calibration", "val", "test"):
        s = summary["splits"].get(name)
        if s:
            m = s["mean"]
            print(f"  {name:11s} {s['images']:6d}  {s['tissues']:7d}  {s['share']:.3f}  "
                  f"{m['ecd']:8.1f}  {m['cv']:8.1f}  {m['hex']:8.1f}")
    # Leakage check: a tissue must belong to exactly one split.
    inc = manifest[manifest["split"] != ""]
    leaks = inc.groupby("group_id")["split"].nunique().gt(1).sum()
    print(f"\nTissues in more than one split (must be 0): {leaks}")
    print(f"Test-set hash: {summary['test_hash_sha256'][:16]}...")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print the summary, write nothing")
    ap.add_argument("--force", action="store_true", help="allow overwriting a frozen, different test set")
    args = ap.parse_args()

    cfg = load_config()
    manifest = build(cfg)
    summary = summarise(manifest, cfg)
    print_report(manifest, summary)

    if args.dry_run:
        print("\nDry run - nothing written.")
        return

    splits_dir = cfg["paths"]["splits_dir"]
    summary_path = splits_dir / "split_summary.json"
    manifest_path = splits_dir / "manifest.csv"

    # Freeze guard: never silently replace an existing test set.
    if summary_path.exists() and not args.force:
        old_hash = json.loads(summary_path.read_text(encoding="utf-8")).get("test_hash_sha256")
        if old_hash and old_hash != summary["test_hash_sha256"]:
            raise SystemExit(
                "Refusing to overwrite: the new test set differs from the frozen one in "
                f"{summary_path}. Re-run with --force only if you intend to replace it.")

    ensure_output_dirs(cfg)
    manifest.to_csv(manifest_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote {manifest_path}\nWrote {summary_path}")


if __name__ == "__main__":
    main()
