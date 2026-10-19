"""
Phase 1, Step 1.7 — choose images for ROI (tile-quality) labelling.

Every chosen image is cut into a fixed grid of square tiles (roi.grid_rows x
roi.grid_cols; 6 x 8 tiles of 162 px for 972 x 1296 images) and EVERY tile is
labelled good / usable / poor in the Colab labeller (data_prep/roi_labeller.py).
Labelling whole images instead of random patches gives two things at once:
  * tile labels to train the patch-quality CNN (Sub-component 3.1)  -> TRAIN images
  * a complete reference ROI map per image to measure ROI IoU        -> VAL images

Images are spread evenly over image-quality terciles (so poor tiles are not
rare) and ECD bands, one image per tissue. Test images are never used.
``roi.n_repeat`` images are shown a second time, rotated 180 deg and in the
second half of the sequence, to measure intra-rater repeatability.

Writes <annotations_dir>/roi/<round>/index.csv (the labelling order).

Usage (run from ml/cellular/; on Colab after the setup cell):
    python -m data_prep.select_roi_images            # create round
    python -m data_prep.select_roi_images --force    # replace an existing round (deletes its labels!)
"""

from __future__ import annotations

import argparse
import shutil

import numpy as np
import pandas as pd

from config import load_config

KEEP = ["image_id", "image_file", "split", "group_id", "ecd", "ecd_band", "quality_tercile"]


def add_quality_terciles(pool: pd.DataFrame, quality: pd.DataFrame | None) -> pd.DataFrame:
    """Quality tercile (low / mid / high) from the audit's image-quality score."""
    if quality is None:
        return pool.assign(quality_tercile="unknown")
    pool = pool.merge(quality[["image_id", "quality_score"]], on="image_id", how="left")
    pool["quality_tercile"] = pd.qcut(pool["quality_score"].rank(method="first"), 3,
                                      labels=["low", "mid", "high"]).astype(str)
    return pool


def choose(pool: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """n images, one per tissue, round robin over quality tercile x ECD band strata."""
    pool = pool.drop_duplicates("group_id")
    strata = {key: list(rng.permutation(g.index.to_numpy()))
              for key, g in pool.groupby(["quality_tercile", "ecd_band"])}
    picked: list[int] = []
    while len(picked) < n and any(strata.values()):
        for key in sorted(strata):
            if strata[key] and len(picked) < n:
                picked.append(strata[key].pop())
    return pool.loc[picked]


def labelling_order(chosen: pd.DataFrame, n_repeat: int, seed: int) -> pd.DataFrame:
    """
    Shuffled order; repeats are taken from the first half and mixed into the
    second half, so each repeat comes after its original and is not adjacent to it.
    """
    chosen = chosen.sample(frac=1, random_state=seed).reset_index(drop=True)
    chosen = chosen.assign(is_repeat=False, view="normal")
    half = len(chosen) // 2
    first, second = chosen.iloc[:half], chosen.iloc[half:]
    repeats = first.sample(min(n_repeat, len(first)), random_state=seed).assign(is_repeat=True, view="rot180")
    second = pd.concat([second, repeats]).sample(frac=1, random_state=seed + 1)
    order = pd.concat([first, second]).reset_index(drop=True)
    order.insert(0, "order", range(len(order)))
    return order


def main() -> None:
    ap = argparse.ArgumentParser(description="Select images for ROI tile labelling.")
    ap.add_argument("--force", action="store_true", help="replace an existing round (deletes its labels)")
    args = ap.parse_args()

    cfg = load_config()
    roi, paths = cfg["roi"], cfg["paths"]
    out_dir = paths["annotations_dir"] / "roi" / roi["round"]
    if (out_dir / "index.csv").exists() and not args.force:
        raise SystemExit(f"{out_dir} already exists (labelling may be in progress). "
                         "Use --force only if you really want to replace it - labels.csv is deleted too.")
    if out_dir.exists() and args.force:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(roi["seed"])
    man = pd.read_csv(paths["splits_dir"] / "manifest.csv")
    quality_csv = paths["outputs_dir"] / "audit" / "06_image_quality.csv"
    quality = pd.read_csv(quality_csv) if quality_csv.exists() else None
    print(f"Quality scores: {'used' if quality is not None else 'not found - stratifying by ECD only'}")

    pool = add_quality_terciles(man[man["split"].isin(["train", "val"])], quality)
    parts = [choose(pool[pool["split"] == split], roi[f"n_images_{split}"], rng)
             for split in ("train", "val")]
    order = labelling_order(pd.concat(parts)[KEEP], roi["n_repeat"], roi["seed"])
    order.to_csv(out_dir / "index.csv", index=False)

    tiles = roi["grid_rows"] * roi["grid_cols"]
    print(f"\nWrote {len(order)} images ({int(order['is_repeat'].sum())} repeats) to {out_dir / 'index.csv'}")
    print(f"Tiles to label: {len(order) * tiles}  ({tiles} per image)")
    main_rows = order[~order["is_repeat"]]
    print(main_rows.groupby(["split", "quality_tercile"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
