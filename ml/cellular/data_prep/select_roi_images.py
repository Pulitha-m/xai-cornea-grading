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

Round 2 (Phase 6, config roi.round2): more TRAIN tissues only, none used in
round 1, with extra weight on lower image quality (roi.round2.tercile_share)
so more artefacts (glare, folds, dim strips, blur) are labelled; within a
tercile, round robin over ECD bands. roi.round2.n_repeat round-1 TRAIN images
are shown again (rotated 180 deg) to check that grading has not drifted since
round 1. The round-1 validation reference maps are not changed.

Writes <annotations_dir>/roi/<round>/index.csv (the labelling order).

Usage (run from ml/cellular/; on Colab after the setup cell):
    python -m data_prep.select_roi_images                   # create round 1
    python -m data_prep.select_roi_images --round round2    # create round 2
    python -m data_prep.select_roi_images --force           # replace an existing round (deletes its labels!)
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


def choose_weighted(pool: pd.DataFrame, n: int, shares: dict[str, float],
                    rng: np.random.Generator) -> pd.DataFrame:
    """n images, one per tissue: quota per quality tercile (shares), round robin over ECD bands
    inside each tercile. A tercile with too few images passes its remainder to the others."""
    pool = pool.drop_duplicates("group_id")
    quota = {t: int(round(n * s)) for t, s in shares.items()}
    quota[max(shares, key=shares.get)] += n - sum(quota.values())      # rounding remainder
    parts = []
    for t in shares:
        got = choose(pool[pool["quality_tercile"] == t], quota[t], rng)
        parts.append(got)
    picked = pd.concat(parts)
    if len(picked) < n:                                                  # top up from what is left
        picked = pd.concat([picked, choose(pool.drop(picked.index), n - len(picked), rng)])
    return picked


def labelling_order_round2(new: pd.DataFrame, repeats: pd.DataFrame, seed: int) -> pd.DataFrame:
    """New images shuffled; the repeats (earlier-round images, rot180) mixed into the second half."""
    new = new.sample(frac=1, random_state=seed).reset_index(drop=True).assign(is_repeat=False, view="normal")
    half = len(new) // 2
    second = pd.concat([new.iloc[half:], repeats.assign(is_repeat=True, view="rot180")])
    order = pd.concat([new.iloc[:half], second.sample(frac=1, random_state=seed + 1)]).reset_index(drop=True)
    order.insert(0, "order", range(len(order)))
    return order


def select_round2(cfg: dict, pool: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    r2 = cfg["roi"]["round2"]
    round1 = pd.read_csv(cfg["paths"]["annotations_dir"] / "roi" / cfg["roi"]["round"] / "index.csv")
    used = set(round1["group_id"])
    fresh = pool[(pool["split"] == "train") & ~pool["group_id"].isin(used)]
    new = choose_weighted(fresh, r2["n_images_train"], r2["tercile_share"], rng)
    old_train = round1[(round1["split"] == "train") & ~round1["is_repeat"].astype(bool)]
    repeats = old_train.sample(min(r2["n_repeat"], len(old_train)), random_state=r2["seed"])
    return labelling_order_round2(new[KEEP], repeats[KEEP], r2["seed"])


def main() -> None:
    ap = argparse.ArgumentParser(description="Select images for ROI tile labelling.")
    ap.add_argument("--round", default=None, help="round to create (default: roi.round = round1)")
    ap.add_argument("--force", action="store_true", help="replace an existing round (deletes its labels)")
    args = ap.parse_args()

    cfg = load_config()
    roi, paths = cfg["roi"], cfg["paths"]
    rnd = args.round or roi["round"]
    if rnd != roi["round"] and rnd not in roi:
        raise SystemExit(f"No settings for '{rnd}' in config roi:")
    out_dir = paths["annotations_dir"] / "roi" / rnd
    if (out_dir / "index.csv").exists() and not args.force:
        raise SystemExit(f"{out_dir} already exists (labelling may be in progress). "
                         "Use --force only if you really want to replace it - labels.csv is deleted too.")
    if out_dir.exists() and args.force:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    man = pd.read_csv(paths["splits_dir"] / "manifest.csv")
    quality_csv = paths["outputs_dir"] / "audit" / "06_image_quality.csv"
    quality = pd.read_csv(quality_csv) if quality_csv.exists() else None
    print(f"Quality scores: {'used' if quality is not None else 'not found - stratifying by ECD only'}")

    # terciles over the same train + val pool as round 1, so 'low' means the same in every round
    pool = add_quality_terciles(man[man["split"].isin(["train", "val"])], quality)
    if rnd == roi["round"]:
        rng = np.random.default_rng(roi["seed"])
        parts = [choose(pool[pool["split"] == split], roi[f"n_images_{split}"], rng)
                 for split in ("train", "val")]
        order = labelling_order(pd.concat(parts)[KEEP], roi["n_repeat"], roi["seed"])
    else:
        order = select_round2(cfg, pool, np.random.default_rng(roi[rnd]["seed"]))
    order.to_csv(out_dir / "index.csv", index=False)

    tiles = roi["grid_rows"] * roi["grid_cols"]
    print(f"\nWrote {len(order)} images ({int(order['is_repeat'].sum())} repeats) to {out_dir / 'index.csv'}")
    print(f"Tiles to label: {len(order) * tiles}  ({tiles} per image)")
    main_rows = order[~order["is_repeat"]]
    print(main_rows.groupby(["split", "quality_tercile"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
