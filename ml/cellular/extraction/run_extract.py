"""
Phase 3, Step 3.7 — cell extraction on the full validation images.

Uses the masks the Phase 2 full-image check already saved
(<outputs_dir>/seg/full_<split>/<run>/masks/, same illumination mask for every
run), so no GPU is needed. For every image: the per-cell table and an image
summary (cells, mean area in px, CV, HEX %, compactness; with and without
flagged cells). --compare relates the summaries to Konan (rank correlations;
areas stay in pixels until the Phase 4 scale).

Outputs: <outputs_dir>/extraction/full_<split>/<run>/cells/<image_id>.csv,
         summary.csv, comparison printed, figures/<image_id>.png (cells coloured
         by side count)

Usage (from ml/cellular/; CPU is enough):
    python -m extraction.run_extract
    python -m extraction.run_extract --compare
    python -m extraction.run_extract --figure "<image_id>" ...
"""

from __future__ import annotations

import argparse
import time

import cv2
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import load_config
from data_prep.check_annotations import IGNORE
from extraction.cells import ExtractionParams, extract_cells, instances_from_mask, overlay_sides, summarise_cells
from segmentation.infer_full import images_of, run_root


def paths(cfg: dict, run: str, split: str, norm: str):
    """Masks from segmentation.infer_full (same --norm) and the matching extraction folder."""
    seg = run_root(cfg, split, norm, run) / run / "masks"
    suffix = "" if (norm == "image" or run == "classical") else "_litnorm"
    out = cfg["paths"]["outputs_dir"] / "extraction" / f"full_{split}{suffix}" / run
    return seg, out


def extract_all(cfg: dict, run: str, split: str, norm: str) -> None:
    p = ExtractionParams.from_config(cfg)
    seg, out = paths(cfg, run, split, norm)
    (out / "cells").mkdir(parents=True, exist_ok=True)
    rows, t0 = [], time.time()
    images = images_of(cfg, split)
    for i, r in enumerate(images.itertuples(index=False), 1):
        mask = cv2.imread(str(seg / f"{r.image_id}.png"), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            print(f"  missing mask: {r.image_id} - run segmentation.infer_full --run {run} first")
            continue
        df, _, _ = extract_cells(instances_from_mask(mask), mask != IGNORE, p)
        df.to_csv(out / "cells" / f"{r.image_id}.csv", index=False)
        rows.append({"image_id": r.image_id, **summarise_cells(df)})
        if i % 25 == 0 or i == len(images):
            print(f"  {i}/{len(images)} images, {(time.time() - t0) / i:.1f} s/image", flush=True)
    pd.DataFrame(rows).to_csv(out / "summary.csv", index=False)
    print(f"Results: {out}")


def open_sensitivity(cfg: dict, run: str, split: str, norm: str, limits: list[float]) -> None:
    """Sensitivity analysis only (decision rule stays max_open_fraction): HEX % vs Konan when the
    open-ring limit is relaxed. Recomputed from the stored raw side counts, no re-extraction."""
    _, out = paths(cfg, run, split, norm)
    ref = images_of(cfg, split).set_index("image_id")["hex"]
    rows = []
    for t in limits:
        hex_pct, known = {}, []
        for f in sorted((out / "cells").glob("*.csv")):
            df = pd.read_csv(f)
            s = df.loc[df["open_fraction"] <= t, "sides_raw"]
            hex_pct[f.stem] = 100 * (s == 6).mean() if len(s) else np.nan
            known.append(len(s) / max(len(df), 1))
        h = pd.Series(hex_pct).dropna()
        k = ref.loc[h.index]
        rows.append({"max_open_fraction": t, "share of cells with sides": np.median(known),
                     "rho HEX": spearmanr(h, k).correlation, "HEX mean (ours)": h.mean(),
                     "HEX mean (Konan)": k.mean(), "HEX MAE (points)": (h - k).abs().mean()})
    official = cfg["extraction"]["max_open_fraction"]
    print(f"Open-ring sensitivity (official limit {official}; for interpretation only):")
    print(pd.DataFrame(rows).set_index("max_open_fraction").round(3).to_string())


def compare(cfg: dict, run: str, split: str, norm: str) -> None:
    _, out = paths(cfg, run, split, norm)
    ref = images_of(cfg, split)[["image_id", "hex", "cv", "mean_area", "num_cells", "ecd_band"]]
    s = pd.read_csv(out / "summary.csv").merge(ref, on="image_id")
    print(f"{run}: {len(s)} {split} images; median per image: {s['n_cells'].median():.0f} complete cells, "
          f"{s['n_sides_known'].median():.0f} with a side count, {s['n_flagged'].median():.0f} flagged")
    rows = []
    for suffix, label in (("", "all complete cells"), ("_unflagged", "without flagged cells")):
        rows.append({"cells": label,
                     "rho HEX": spearmanr(s[f"hex_pct{suffix}"], s["hex"]).correlation,
                     "HEX mean (Konan)": s["hex"].mean(), "HEX mean (ours)": s[f"hex_pct{suffix}"].mean(),
                     "HEX MAE (points)": (s[f"hex_pct{suffix}"] - s["hex"]).abs().mean(),
                     "rho CV": spearmanr(s[f"cv_area_pct{suffix}"], s["cv"]).correlation,
                     "CV MAE (points)": (s[f"cv_area_pct{suffix}"] - s["cv"]).abs().mean(),
                     "rho mean area": spearmanr(s[f"mean_area_px{suffix}"], s["mean_area"]).correlation})
    pd.set_option("display.width", 220)
    print(pd.DataFrame(rows).set_index("cells").round(3).to_string())
    print("\nBy ECD band (all complete cells): " + "; ".join(
        f"{b}: rho HEX {spearmanr(g['hex_pct'], g['hex']).correlation:.2f}, "
        f"rho CV {spearmanr(g['cv_area_pct'], g['cv']).correlation:.2f} (n={len(g)})"
        for b, g in s.groupby("ecd_band")))


def figure(cfg: dict, run: str, split: str, norm: str, image_ids: list[str]) -> None:
    p = ExtractionParams.from_config(cfg)
    seg, out = paths(cfg, run, split, norm)
    man = images_of(cfg, split).set_index("image_id")
    (out / "figures").mkdir(parents=True, exist_ok=True)
    for iid in image_ids:
        img = cv2.imread(str(cfg["paths"]["images_dir"] / man.loc[iid, "image_file"]), cv2.IMREAD_GRAYSCALE)
        mask = cv2.imread(str(seg / f"{iid}.png"), cv2.IMREAD_GRAYSCALE)
        df, _, complete = extract_cells(instances_from_mask(mask), mask != IGNORE, p)
        view = overlay_sides(img, complete, df)
        sm = summarise_cells(df)
        cv2.putText(view, f"{run}: HEX {sm['hex_pct']:.0f}% (Konan {man.loc[iid, 'hex']:.0f}%), "
                          f"CV {sm['cv_area_pct']:.0f}% (Konan {man.loc[iid, 'cv']:.0f}%), {sm['n_cells']} cells",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(view, "sides: <=4 purple, 5 orange, 6 green, 7 blue, >=8 red, unknown grey",
                    (10, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imwrite(str(out / "figures" / f"{iid}.png"), view)
        print(f"Figure: {out / 'figures' / f'{iid}.png'}")


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Cell extraction on full validation images.")
    ap.add_argument("--run", default=cfg["extraction"]["run"])
    ap.add_argument("--split", default="val", choices=["val"], help="test stays frozen until Phase 7")
    ap.add_argument("--norm", default="lit", choices=["lit", "image"],
                    help="which segmentation masks: lit-area normalisation (default) or the first run")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--open-sensitivity", type=float, nargs="+", metavar="LIMIT",
                    help="sensitivity analysis: HEX % with other open-ring limits")
    ap.add_argument("--figure", nargs="+", metavar="IMAGE_ID")
    args = ap.parse_args()
    if args.compare:
        compare(cfg, args.run, args.split, args.norm)
    elif args.open_sensitivity:
        open_sensitivity(cfg, args.run, args.split, args.norm, args.open_sensitivity)
    elif args.figure:
        figure(cfg, args.run, args.split, args.norm, args.figure)
    else:
        extract_all(cfg, args.run, args.split, args.norm)


if __name__ == "__main__":
    main()
