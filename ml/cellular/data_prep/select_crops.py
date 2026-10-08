"""
Phase 1, Step 1.2 — select annotation crops and create draft wall masks.

Picks ``annotation.n_crops`` crops (256 x 256) from TRAIN images, one crop per
tissue, spread over ECD bands and image-quality levels, and writes for each:

    crops/<crop_id>.png         grayscale crop to annotate
    drafts/<crop_id>_walls.png  RGBA layer: classical draft walls in RED on a
                                transparent background (open as a layer in GIMP/Krita)

A subset (``annotation.n_expert_overlap``) is copied to ``expert/`` for the NEBSL
expert to correct independently (inter-annotator agreement, Step 1.6).

Also writes ``index.csv`` (one row per crop) and ``preview.png`` (all crops with
draft walls) into  <annotations_dir>/seg/<round>/ .

Window choice inside an image: candidate 256 x 256 windows lie fully inside the
analysable (well-lit) area. Most crops take a window with high cell coverage;
``challenging_share`` of them take a mid-coverage window so the U-Net also sees
harder regions (faint walls, debris, uneven lighting).

Usage (run from ml/cellular/; on Colab after the setup cell):
    python -m data_prep.select_crops            # create round
    python -m data_prep.select_crops --force    # overwrite an existing round
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm

from config import load_config
from segmentation.classical import ClassicalParams, ClassicalResult, segment

WALL_RGBA = (255, 0, 0, 255)      # red, opaque: wall pixels in the draft layer


# -----------------------------------------------------------------------------
# Which images
# -----------------------------------------------------------------------------
def choose_images(train: pd.DataFrame, quality: pd.DataFrame | None, ann: dict,
                  rng: np.random.Generator) -> pd.DataFrame:
    """Stratified pick of one image per tissue: ECD bands x quality terciles."""
    pool = train.drop_duplicates("group_id").copy()          # one capture per tissue
    if quality is not None:
        pool = pool.merge(quality[["image_id", "quality_score"]], on="image_id", how="left")
        pool["quality_tercile"] = pd.qcut(pool["quality_score"].rank(method="first"), 3,
                                          labels=["low", "mid", "high"]).astype(str)
    else:
        pool["quality_tercile"] = "unknown"

    n_total = ann["n_crops"]
    shares = pool["ecd_band"].value_counts(normalize=True)
    alloc = {b: max(ann["min_per_ecd_band"], int(round(n_total * s))) for b, s in shares.items()}
    alloc = {b: min(n, int((pool["ecd_band"] == b).sum())) for b, n in alloc.items()}
    largest = max(alloc, key=alloc.get)
    alloc[largest] += n_total - sum(alloc.values())          # make the total exact

    picks = []
    for band, n in alloc.items():
        band_pool = pool[pool["ecd_band"] == band]
        # spread evenly over quality terciles inside the band
        terciles = sorted(band_pool["quality_tercile"].unique())
        per_t = {t: n // len(terciles) for t in terciles}
        for t in terciles[: n % len(terciles)]:
            per_t[t] += 1
        for t, k in per_t.items():
            sub = band_pool[band_pool["quality_tercile"] == t]
            k = min(k, len(sub))
            picks.append(sub.sample(k, random_state=int(rng.integers(1 << 31))))
    chosen = pd.concat(picks)
    # top up if some strata were too small
    missing = n_total - len(chosen)
    if missing > 0:
        rest = pool[~pool["image_id"].isin(chosen["image_id"])]
        chosen = pd.concat([chosen, rest.sample(missing, random_state=int(rng.integers(1 << 31)))])
    return chosen.reset_index(drop=True)


def assign_within_bands(chosen: pd.DataFrame, share: float, rng: np.random.Generator) -> pd.Series:
    """
    Mark ~share of the crops 'challenging' INSIDE every ECD band, so difficulty is
    not confounded with cell density (round-1 v1 put all of them in one band).
    """
    difficulty = pd.Series("typical", index=chosen.index)
    for _, idx in chosen.groupby("ecd_band").groups.items():
        idx = list(idx)
        k = int(round(share * len(idx)))
        difficulty.loc[rng.choice(idx, size=k, replace=False)] = "challenging"
    return difficulty


def pick_expert_subset(chosen: pd.DataFrame, n: int, rng: np.random.Generator) -> set[str]:
    """
    Expert-overlap crops spread over ECD band x difficulty strata (round robin),
    so inter-annotator agreement covers easy and hard, dense and sparse cells.
    """
    strata = {key: list(rng.permutation(g["image_id"].to_numpy()))
              for key, g in chosen.groupby(["ecd_band", "difficulty"])}
    picked: list[str] = []
    while len(picked) < n and any(strata.values()):
        for key in sorted(strata):
            if strata[key] and len(picked) < n:
                picked.append(strata[key].pop())
    return set(picked)


# -----------------------------------------------------------------------------
# Where in the image
# -----------------------------------------------------------------------------
def candidate_windows(res: ClassicalResult, size: int, stride: int = 32) -> pd.DataFrame:
    """All windows fully inside the valid area, with their kept-cell coverage."""
    valid_ii = cv2.integral(res.valid.astype(np.uint8))
    cells_ii = cv2.integral((res.labels > 0).astype(np.uint8))
    h, w = res.valid.shape
    rows = []
    for y in range(0, h - size + 1, stride):
        for x in range(0, w - size + 1, stride):
            box = lambda ii: ii[y + size, x + size] - ii[y, x + size] - ii[y + size, x] + ii[y, x]
            if box(valid_ii) < size * size:                   # must be fully analysable
                continue
            rows.append({"y0": y, "x0": x, "coverage": box(cells_ii) / (size * size)})
    return pd.DataFrame(rows)


def pick_window(cands: pd.DataFrame, challenging: bool, rng: np.random.Generator) -> pd.Series:
    """Best-covered window (random among top 5), or a mid-coverage one if challenging."""
    ranked = cands.sort_values("coverage", ascending=False).reset_index(drop=True)
    if challenging:
        lo, hi = int(len(ranked) * 0.4), max(int(len(ranked) * 0.6), int(len(ranked) * 0.4) + 1)
        pool = ranked.iloc[lo:hi]
    else:
        pool = ranked.head(5)
    return pool.iloc[int(rng.integers(len(pool)))]


def walls_layer(res: ClassicalResult, y0: int, x0: int, size: int) -> np.ndarray:
    """RGBA draft layer: red 2-px walls, transparent elsewhere (cv2 order BGRA)."""
    walls = res.boundary[y0:y0 + size, x0:x0 + size].astype(np.uint8)
    walls = cv2.dilate(walls, np.ones((2, 2), np.uint8)).astype(bool)
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[walls] = WALL_RGBA
    return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)


def save_preview(index: pd.DataFrame, out_dir: Path, size: int) -> None:
    """Contact sheet of all crops with draft walls, for a quick visual check."""
    tiles = []
    for _, r in index.iterrows():
        crop = cv2.imread(str(out_dir / "crops" / f"{r['crop_id']}.png"), cv2.IMREAD_GRAYSCALE)
        layer = cv2.imread(str(out_dir / "drafts" / f"{r['crop_id']}_walls.png"), cv2.IMREAD_UNCHANGED)
        tile = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        tile[layer[..., 3] > 0] = (0, 0, 255)
        cv2.putText(tile, r["crop_id"], (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        tiles.append(tile)
    cols = 8
    while len(tiles) % cols:
        tiles.append(np.zeros((size, size, 3), np.uint8))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(str(out_dir / "preview.png"), np.vstack(rows))


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Select annotation crops and draft masks.")
    ap.add_argument("--force", action="store_true", help="overwrite an existing round")
    args = ap.parse_args()

    cfg = load_config()
    ann, paths = cfg["annotation"], cfg["paths"]
    size = ann["crop_size"]
    out_dir = paths["annotations_dir"] / "seg" / ann["round"]
    if (out_dir / "index.csv").exists() and not args.force:
        raise SystemExit(f"{out_dir} already exists (annotation may be in progress). "
                         "Use --force only if you really want to replace it.")
    if out_dir.exists() and args.force:
        shutil.rmtree(out_dir)
    for sub in ("crops", "drafts", "expert/crops", "expert/drafts", "corrected", "expert/corrected"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(ann["seed"])
    man = pd.read_csv(paths["splits_dir"] / "manifest.csv")
    train = man[man["split"] == "train"]

    quality_csv = paths["outputs_dir"] / "audit" / "06_image_quality.csv"
    quality = pd.read_csv(quality_csv) if quality_csv.exists() else None
    print(f"Quality scores: {'used' if quality is not None else 'not found - stratifying by ECD only'}")

    chosen = choose_images(train, quality, ann, rng)
    chosen["difficulty"] = assign_within_bands(chosen, ann["challenging_share"], rng)
    chosen = chosen.sample(frac=1, random_state=ann["seed"]).reset_index(drop=True)
    expert_ids = pick_expert_subset(chosen, ann["n_expert_overlap"], rng)

    draft_params = replace(ClassicalParams.from_config(cfg), h_threshold=cfg["classical"]["draft_h_threshold"])

    rows = []
    for i, r in tqdm(chosen.iterrows(), total=len(chosen), desc="Cropping"):
        img = cv2.imread(str(paths["images_dir"] / r["image_file"]), cv2.IMREAD_GRAYSCALE)
        res = segment(img, draft_params)
        cands = candidate_windows(res, size)
        if cands.empty:
            print(f"  skipped {r['image_id']}: no fully analysable {size}px window")
            continue
        win = pick_window(cands, r["difficulty"] == "challenging", rng)
        y0, x0 = int(win["y0"]), int(win["x0"])

        crop_id = f"{ann['round']}_{i:03d}"
        cv2.imwrite(str(out_dir / "crops" / f"{crop_id}.png"), img[y0:y0 + size, x0:x0 + size])
        cv2.imwrite(str(out_dir / "drafts" / f"{crop_id}_walls.png"), walls_layer(res, y0, x0, size))
        expert = r["image_id"] in expert_ids
        if expert:
            for sub, name in (("crops", f"{crop_id}.png"), ("drafts", f"{crop_id}_walls.png")):
                shutil.copy(out_dir / sub / name, out_dir / "expert" / sub / name)

        rows.append({"crop_id": crop_id, "image_id": r["image_id"], "image_file": r["image_file"],
                     "group_id": r["group_id"], "y0": y0, "x0": x0, "size": size,
                     "ecd": r["ecd"], "ecd_band": r["ecd_band"],
                     "quality_tercile": r["quality_tercile"], "difficulty": r["difficulty"],
                     "window_coverage": round(float(win["coverage"]), 3),
                     "expert_overlap": expert, "draft_h_threshold": draft_params.h_threshold})

    index = pd.DataFrame(rows)
    index.to_csv(out_dir / "index.csv", index=False)
    save_preview(index, out_dir, size)

    print(f"\nWrote {len(index)} crops to {out_dir}")
    print(index.groupby(["ecd_band", "difficulty"]).size().unstack(fill_value=0).to_string())
    print(f"Quality terciles: {index['quality_tercile'].value_counts().to_dict()}")
    print(f"Expert overlap crops: {int(index['expert_overlap'].sum())}  ->  {out_dir / 'expert'}")
    print(index[index["expert_overlap"]].groupby(["ecd_band", "difficulty"]).size().to_string())


if __name__ == "__main__":
    main()
