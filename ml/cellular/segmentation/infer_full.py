"""
Phase 2, Step 2.7 — the finalists on FULL validation images vs Konan
(the pre-registered secondary selection criterion, config seg_models.full_image).

For every included image of the split (default: val, 197 images; never test):
  1. segment the whole 1296 x 972 image with a run:
       classical               Phase 1 baseline (reference)
       cellpose_finetune_flat  final model from segmentation/train_final.py
       stardist_finetune_flat  final model from segmentation/train_final.py
  2. keep only the illuminated area — the SAME illumination mask (classical
     flatten_illumination) for every run, so all are measured on the same pixels;
  3. measure complete cells (not touching the image border or the dark area)
     with centre-line area (segmentation/metrics.tessellated_cells):
     cell count, mean cell area (px), CV of cell area (%).
Then --compare relates each run to Konan per image. Konan measures ~110 cells in
an operator-chosen region, the runs measure the whole lit area, so the primary
criterion is scale-free and rank-based: Spearman(mean cell area, Konan mean area).
ECD from the PRELIMINARY scale (scale.um_per_px_prelim) is reported for
orientation only; the real scale is calibrated in Phase 4.

Outputs: <outputs_dir>/seg/full_<split>/<run>/masks/<image_id>.png (0 interior /
1 wall / 2 ignore), measures.csv; comparison.csv; figures/.

Usage (from ml/cellular/; Colab GPU runtime after the setup cell):
    python -m segmentation.infer_full --run classical
    python -m segmentation.infer_full --run cellpose_finetune_flat
    python -m segmentation.infer_full --run stardist_finetune_flat
    python -m segmentation.infer_full --compare
    python -m segmentation.infer_full --figure "<image_id>" ...
Images already processed are skipped (re-run after a disconnect).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import load_config
from data_prep.check_annotations import IGNORE, INTERIOR, WALL
from segmentation.classical import ClassicalParams, flatten_illumination, segment
from segmentation.metrics import tessellated_cells
from segmentation.postprocess import instances_to_mask
from segmentation.preprocess import Preprocessor
from segmentation.train_final import final_dir

RUNS = ("classical", "cellpose_finetune_flat", "stardist_finetune_flat")
NORMS = ("lit", "image")


def run_root(cfg: dict, split: str, norm: str, run: str) -> Path:
    """Output folder of a run. The classical method does not depend on the model normalisation."""
    base = cfg["paths"]["outputs_dir"] / "seg" / f"full_{split}"
    return base if (run == "classical" or norm == "image") else base.with_name(f"full_{split}_litnorm")


def normalise_lit(x: np.ndarray, lit: np.ndarray, pmin: float, pmax: float) -> np.ndarray:
    """Percentile normalisation over the LIT tissue only, clipped to 0..1 (dark area -> 0).
    Training crops were fully lit, so this reproduces their normalisation on full images;
    whole-image percentiles are pulled down by the dark area (the original 'image' mode)."""
    lo, hi = np.percentile(x[lit], [pmin, pmax]) if lit.any() else (0.0, 1.0)
    out = np.clip((x - lo) / (hi - lo + 1e-6), 0, 1).astype(np.float32)
    out[~lit] = 0
    return out


def make_predictor(cfg: dict, run: str, norm: str = "lit"):
    """Return f(uint8 image) -> mask (0 interior / 1 wall / 2 ignore) for this run.
    norm = 'lit'   : model input normalised over the lit tissue (consistent with training; default)
           'image' : the models' own whole-image normalisation (first step 2.7 run, kept for comparison)"""
    params = ClassicalParams.from_config(cfg)
    lit = lambda img: flatten_illumination(img, params)[1]

    if run == "classical":
        def f(img):
            res = segment(img, params)
            mask = np.where(res.boundary > 0, WALL, INTERIOR).astype(np.uint8)
            mask[~res.valid] = IGNORE
            return mask
        return f

    info = json.loads((final_dir(cfg, run) / "final.json").read_text())
    pre = Preprocessor(cfg, info["preprocess"])
    if run.startswith("cellpose"):
        from segmentation.run_cellpose import load_model
        model, diameter = load_model(info["model_path"]), cfg["seg_models"]["cellpose"]["diameter"]
        if norm == "lit":                                   # Cellpose's own default percentiles: 1 / 99
            instances = lambda x, m: model.eval(normalise_lit(x, m, 1, 99), diameter=diameter, normalize=False)[0]
        else:
            instances = lambda x, m: model.eval(x, diameter=diameter)[0]
    else:
        from segmentation.run_stardist import to_input
        from stardist.models import StarDist2D
        model_dir = Path(info["model_dir"])
        model = StarDist2D(None, name=model_dir.name, basedir=str(model_dir.parent))
        if norm == "lit":                                   # same percentiles as training (to_input: 1 / 99.8)
            instances = lambda x, m: model.predict_instances(normalise_lit(x, m, 1, 99.8))[0]
        else:
            instances = lambda x, m: model.predict_instances(to_input(x))[0]

    def f(img):
        m = lit(img)
        mask = instances_to_mask(instances(pre(img), m))
        mask[~m] = IGNORE
        return mask
    return f


def measure(mask: np.ndarray, um_per_px: float) -> dict:
    """Complete cells with centre-line area."""
    areas = np.bincount(tessellated_cells(mask).ravel())[1:]
    areas = areas[areas > 0].astype(float)
    mean = areas.mean() if len(areas) else float("nan")
    return {"n_cells": int(len(areas)), "mean_area_px": mean,
            "cv_area_pct": 100 * areas.std() / mean if len(areas) > 1 else float("nan"),
            "ecd_prelim": 1e6 / (mean * um_per_px ** 2) if len(areas) else float("nan"),
            "lit_share": float((mask != IGNORE).mean())}


def images_of(cfg: dict, split: str) -> pd.DataFrame:
    man = pd.read_csv(cfg["paths"]["splits_dir"] / "manifest.csv")
    return man[(man["split"] == split) & (man["status"] == "included")].reset_index(drop=True)


def run_images(cfg: dict, run: str, split: str, norm: str) -> None:
    out = run_root(cfg, split, norm, run) / run
    (out / "masks").mkdir(parents=True, exist_ok=True)
    meas_csv = out / "measures.csv"
    done = pd.read_csv(meas_csv) if meas_csv.exists() else pd.DataFrame(columns=["image_id"])
    todo = images_of(cfg, split)
    todo = todo[~todo["image_id"].isin(done["image_id"])]
    if todo.empty:
        print(f"{run}: all images done already ({out})")
        return
    predict = make_predictor(cfg, run, norm)
    um = cfg["scale"]["um_per_px_prelim"]
    t0, rows = time.time(), []
    for i, r in enumerate(todo.itertuples(index=False), 1):
        img = cv2.imread(str(cfg["paths"]["images_dir"] / r.image_file), cv2.IMREAD_GRAYSCALE)
        t = time.time()
        mask = predict(img)
        rows.append({"image_id": r.image_id, "seconds": round(time.time() - t, 2), **measure(mask, um)})
        cv2.imwrite(str(out / "masks" / f"{r.image_id}.png"), mask)
        if i % 20 == 0 or i == len(todo):          # save progress regularly (resume after a disconnect)
            pd.concat([done, pd.DataFrame(rows)]).to_csv(meas_csv, index=False)
            print(f"  {run}: {i}/{len(todo)} images, {(time.time() - t0) / i:.1f} s/image", flush=True)


def spearman(a: pd.Series, b: pd.Series) -> float:
    return float(spearmanr(a, b).correlation)


def compare(cfg: dict, split: str, norm: str) -> None:
    fi = cfg["seg_models"]["full_image"]
    out_root = run_root(cfg, split, norm, RUNS[1])
    print(f"Model input normalisation: {norm}  ({out_root})")
    ref = images_of(cfg, split)[["image_id", "ecd", "cv", "mean_area", "num_cells", "ecd_band"]]
    meas = {r: run_root(cfg, split, norm, r) / r / "measures.csv" for r in RUNS}
    runs = {r: pd.read_csv(p).merge(ref, on="image_id") for r, p in meas.items() if p.exists()}
    if not runs:
        print("No runs measured yet.")
        return

    ok = {r: set(df.loc[df["n_cells"] >= fi["min_cells"], "image_id"]) for r, df in runs.items()}
    common = set.intersection(*ok.values())
    rows = []
    for r, df in runs.items():
        c = df[df["image_id"].isin(common)]
        rows.append({"run": r, "images": len(df), "failures (<min_cells)": len(df) - len(ok[r]),
                     "rho_mean_area": spearman(c["mean_area_px"], c["mean_area"]),
                     "rho_cv": spearman(c["cv_area_pct"], c["cv"]),
                     "cv_mae": (c["cv_area_pct"] - c["cv"]).abs().mean(),
                     "ecd_prelim_mape_%": (100 * (c["ecd_prelim"] - c["ecd"]).abs() / c["ecd"]).mean(),
                     "ecd_prelim_bias_%": (100 * (c["ecd_prelim"] - c["ecd"]) / c["ecd"]).median(),
                     "median_cells": c["n_cells"].median(),
                     "s_per_image": df["seconds"].median()})
    table = pd.DataFrame(rows).set_index("run")
    table.to_csv(out_root / "comparison.csv")
    pd.set_option("display.width", 220)
    print(f"Full {split} images vs Konan - {len(common)} images measured by every run "
          f"(>= {fi['min_cells']} complete cells):")
    print(table.round(3).to_string())
    print("\nrho = Spearman rank correlation; ECD uses the PRELIMINARY scale (orientation only).")
    allruns = pd.concat(runs, names=["run"]).reset_index(level=0)
    for band, g in allruns[allruns["image_id"].isin(common)].groupby("ecd_band"):
        n = g["image_id"].nunique()
        print(f"  ECD band {band} (n={n}{', too few to interpret' if n < 20 else ''}): " + ", ".join(
            f"{r} rho {spearman(gg['mean_area_px'], gg['mean_area']):.2f}" for r, gg in g.groupby("run")))

    finalists = [r for r in RUNS[1:] if r in runs]
    if len(finalists) == 2:
        a, b = (runs[r].set_index("image_id").loc[sorted(common)] for r in finalists)
        rng = np.random.default_rng(fi["seed"])
        idx = np.arange(len(a))
        diffs = []
        for _ in range(fi["n_bootstrap"]):
            s = rng.choice(idx, size=len(idx), replace=True)
            diffs.append(spearman(a["mean_area_px"].iloc[s], a["mean_area"].iloc[s])
                         - spearman(b["mean_area_px"].iloc[s], b["mean_area"].iloc[s]))
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        d = table.loc[finalists[0], "rho_mean_area"] - table.loc[finalists[1], "rho_mean_area"]
        print(f"\nPaired bootstrap ({fi['n_bootstrap']}x): rho({finalists[0]}) - rho({finalists[1]}) = "
              f"{d:+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}]")
        if lo > 0 or hi < 0:
            winner = finalists[0] if d > 0 else finalists[1]
            print(f"DECISION (pre-registered): {winner} - CI excludes 0.")
        else:
            print("DECISION (pre-registered): tie (CI includes 0) -> stardist_finetune_flat "
                  "(simpler, smaller, faster).")


def figure(cfg: dict, split: str, norm: str, image_ids: list[str]) -> None:
    man = images_of(cfg, split).set_index("image_id")
    fig_dir = run_root(cfg, split, norm, RUNS[1]) / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    for iid in image_ids:
        img = cv2.imread(str(cfg["paths"]["images_dir"] / man.loc[iid, "image_file"]), cv2.IMREAD_GRAYSCALE)
        tiles = []
        for run in RUNS:
            mask = cv2.imread(str(run_root(cfg, split, norm, run) / run / "masks" / f"{iid}.png"),
                              cv2.IMREAD_GRAYSCALE)
            view = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            if mask is not None:
                view[mask == WALL] = (0, 0, 255)
                view[mask == IGNORE] = (0.4 * view[mask == IGNORE]).astype(np.uint8)
            view = cv2.resize(view, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA)
            cv2.putText(view, run if mask is not None else f"{run} (n/a)", (8, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            tiles.append(view)
        cv2.imwrite(str(fig_dir / f"{iid}.png"), np.hstack(tiles))
        print(f"Figure: {fig_dir / f'{iid}.png'}  (Konan ECD {man.loc[iid, 'ecd']:.0f})")


def main() -> None:
    cfg = load_config()
    fi = cfg["seg_models"]["full_image"]
    ap = argparse.ArgumentParser(description="Full-image check of the finalists against Konan.")
    ap.add_argument("--run", choices=RUNS, help="segment all images of the split with this run")
    ap.add_argument("--compare", action="store_true", help="compare measured runs with Konan")
    ap.add_argument("--figure", nargs="+", metavar="IMAGE_ID", help="side-by-side overlays")
    ap.add_argument("--split", default=fi["split"], choices=["val", "calibration"],
                    help="calibration: Phase 4 scale only; test stays frozen until Phase 7")
    ap.add_argument("--norm", default="lit", choices=NORMS,
                    help="model input normalisation: lit tissue only (default) or whole image (first run)")
    args = ap.parse_args()

    if args.run:
        run_images(cfg, args.run, args.split, args.norm)
    elif args.compare:
        compare(cfg, args.split, args.norm)
    elif args.figure:
        figure(cfg, args.split, args.norm, args.figure)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
