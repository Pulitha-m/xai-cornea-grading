"""
Phase 2 — classical baseline on the shared folds, comparison table, statistics
and figures for ALL segmentation runs.

Every run lives in <outputs_dir>/seg/<run>/ with scores.csv (one row per crop)
and masks/<crop_id>.png, whatever the model type, so this script treats the
classical method, the smp models, nnU-Net, Cellpose and StarDist the same way.

Statistics (on crops scored by every run): Friedman test across runs, then
paired Wilcoxon signed-rank tests of each run against the best one (by cell F1),
Holm-corrected.

Usage (from ml/cellular/; on Colab after the setup cell):
    python -m segmentation.compare --classical                  # score the classical baseline (once)
    python -m segmentation.compare --rescore                    # re-score all runs from saved masks
    python -m segmentation.compare --h-sensitivity 0.3 0.4 0.5 0.6 0.7   # sensitivity analysis only
    python -m segmentation.compare                              # table + statistics
    python -m segmentation.compare --figure round1_019 round1_002
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare, wilcoxon

from config import load_config
from data_prep.check_annotations import IGNORE, INTERIOR, WALL
from segmentation.classical import ClassicalParams, segment
from segmentation.data import load_samples, round_dir
from segmentation.metrics import print_summary, score_crop, score_run, summarise
from segmentation.postprocess import walls_to_mask

METRICS = ("cell_f1", "boundary_f1", "dice_interior", "iou_interior")


def classical_run(cfg: dict, seg_out: Path) -> None:
    """Phase 1 baseline (h from config) scored exactly like the learned models."""
    params = ClassicalParams.from_config(cfg)
    samples = load_samples(cfg, "raw")
    preds = {}
    for s in samples:
        img = cv2.imread(str(cfg["paths"]["images_dir"] / s.meta["image_file"]), cv2.IMREAD_GRAYSCALE)
        res = segment(img, params)
        y0, x0, n = int(s.meta["y0"]), int(s.meta["x0"]), int(s.meta["size"])
        mask = np.where(res.boundary[y0:y0 + n, x0:x0 + n] > 0, WALL, INTERIOR).astype(np.uint8)
        mask[~res.valid[y0:y0 + n, x0:x0 + n]] = IGNORE
        preds[s.crop_id] = mask
    scores = score_run(samples, preds, seg_out / "classical")
    print_summary("classical", scores)


def rescore(cfg: dict, seg_out: Path) -> None:
    """Re-score every run from its saved masks (after a metric is added); no model is re-run."""
    samples = load_samples(cfg, "raw")
    for mask_dir in sorted(seg_out.glob("*/masks")):
        preds = {f.stem: cv2.imread(str(f), cv2.IMREAD_GRAYSCALE) for f in mask_dir.glob("*.png")}
        scores = score_run(samples, preds, mask_dir.parent)
        print(f"Re-scored {mask_dir.parent.name}: {len(scores)} crops")


def h_sensitivity(cfg: dict, seg_out: Path, hs: list[float]) -> None:
    """
    Sensitivity analysis (NOT model selection): re-score every wall-map run from
    its saved out-of-fold wall probabilities with other watershed thresholds h.
    Official results (fixed h = seg_models.watershed_h) are not changed; output
    goes to <seg_out>/sensitivity/h_sensitivity.csv.
    """
    samples = load_samples(cfg, "raw")
    rows = []
    for oof_dir in sorted(seg_out.glob("*/oof")):
        run = oof_dir.parent.name
        for h in hs:
            per = [{"fold": s.fold, **score_crop(walls_to_mask(np.load(oof_dir / f"{s.crop_id}.npy"), h), s.mask)}
                   for s in samples if (oof_dir / f"{s.crop_id}.npy").exists()]
            df = pd.DataFrame(per)
            per_fold = df.groupby("fold")[["cell_f1", "boundary_f1"]].mean()
            rows.append({"run": run, "h": h, "n_crops": len(df),
                         "cell_f1_mean": per_fold["cell_f1"].mean(), "cell_f1_sd": per_fold["cell_f1"].std(ddof=1),
                         "boundary_f1_mean": per_fold["boundary_f1"].mean(),
                         "area_ratio_tess_median": df["area_ratio_tess"].median()})
            print(f"  {run:16s} h={h:.2f}  cell F1 {rows[-1]['cell_f1_mean']:.3f}", flush=True)

    table = pd.DataFrame(rows)
    (seg_out / "sensitivity").mkdir(exist_ok=True)
    table.to_csv(seg_out / "sensitivity" / "h_sensitivity.csv", index=False)
    official = cfg["seg_models"]["watershed_h"]
    for col, title in (("cell_f1_mean", "Cell F1"), ("area_ratio_tess_median", "Centre-line area ratio (1.0 = correct)")):
        print(f"\n{title} by watershed threshold h (official h = {official}):")
        print(table.pivot(index="run", columns="h", values=col).round(3).to_string())
    best = table.loc[table.groupby("run")["cell_f1_mean"].idxmax(), ["run", "h", "cell_f1_mean"]]
    print("\nBest h per run (for interpretation only):")
    print(best.round(3).to_string(index=False))

    instance = {p.parent.name: pd.read_csv(p) for p in seg_out.glob("*/scores.csv")
                if (p.parent / "inst").exists()}
    if instance:
        print("\nInstance models (no watershed, unaffected by h) for reference:")
        for name, df in sorted(instance.items()):
            print(f"  {name:24s} cell F1 {summarise(df)['cell_f1_mean']:.3f}")


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values."""
    order = sorted(pvals, key=pvals.get)
    m, running, out = len(order), 0.0, {}
    for i, name in enumerate(order):
        running = max(running, min(1.0, (m - i) * pvals[name]))
        out[name] = running
    return out


def comparison(seg_out: Path, n_crops: int) -> None:
    runs = {p.parent.name: pd.read_csv(p) for p in sorted(seg_out.glob("*/scores.csv"))}
    if not runs:
        print(f"No runs found in {seg_out}")
        return

    table = pd.DataFrame({name: summarise(df, METRICS) for name, df in runs.items()}).T
    table["area_ratio_median"] = [runs[n]["area_ratio"].median() for n in table.index]
    table["area_ratio_tess_median"] = [runs[n]["area_ratio_tess"].median() if "area_ratio_tess" in runs[n]
                                       else float("nan") for n in table.index]
    table["cell_f1_challenging"] = [runs[n].loc[runs[n]["difficulty"] == "challenging", "cell_f1"].mean()
                                    for n in table.index]
    table = table.sort_values("cell_f1_mean", ascending=False)
    cols = ["n_crops"] + [f"{m}_{s}" for m in METRICS for s in ("mean", "sd")] + \
           ["cell_f1_challenging", "area_ratio_median", "area_ratio_tess_median"]
    table[cols].to_csv(seg_out / "comparison.csv")
    pd.set_option("display.width", 220)
    print("Mean +- SD over folds (sorted by cell F1):")
    print(table[cols].astype(float).round(3).to_string())

    complete = [n for n, df in runs.items() if len(df) == n_crops]
    partial = sorted(set(runs) - set(complete))
    if partial:
        print(f"\nNot in the statistics yet (incomplete): {', '.join(partial)}")
    if len(complete) < 2:
        return
    paired = pd.DataFrame({n: runs[n].set_index("crop_id")["cell_f1"] for n in complete}).dropna()
    print(f"\nStatistics on cell F1, {len(paired)} crops scored by all {len(complete)} complete runs:")
    if len(complete) >= 3:
        stat, p = friedmanchisquare(*[paired[c] for c in paired])
        print(f"  Friedman chi2 = {stat:.2f}, p = {p:.2g}")
    best = paired.mean().idxmax()
    raw = {}
    for name in paired.columns.drop(best):
        try:
            raw[name] = wilcoxon(paired[best], paired[name]).pvalue
        except ValueError:                        # identical scores
            raw[name] = 1.0
    for name, p in sorted(holm(raw).items(), key=lambda kv: kv[1]):
        diff = (paired[best] - paired[name]).mean()
        print(f"  {best} vs {name:22s} mean diff {diff:+.3f}   Holm p = {p:.2g}")


def figure(cfg: dict, seg_out: Path, crop_ids: list[str]) -> None:
    """Per crop: image | reference | every run (walls red, ignore blue), 2x enlarged."""
    rd = round_dir(cfg)
    runs = sorted(p.parent.name for p in seg_out.glob("*/scores.csv"))
    fig_dir = seg_out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    samples = {s.crop_id: s for s in load_samples(cfg, "raw")}

    def overlay(crop, mask, title):
        view = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        if mask is not None:
            view[mask == WALL] = (0, 0, 255)
            view[mask == IGNORE] = (0.5 * view[mask == IGNORE] + (127, 0, 0)).astype(np.uint8)
        view = cv2.resize(view, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
        cv2.putText(view, title, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        return view

    for cid in crop_ids:
        crop = cv2.imread(str(rd / "crops" / f"{cid}.png"), cv2.IMREAD_GRAYSCALE)
        tiles = [overlay(crop, None, cid), overlay(crop, samples[cid].mask, "reference")]
        for run in runs:
            m = cv2.imread(str(seg_out / run / "masks" / f"{cid}.png"), cv2.IMREAD_GRAYSCALE)
            score = pd.read_csv(seg_out / run / "scores.csv").set_index("crop_id")
            title = f"{run} F1 {score.loc[cid, 'cell_f1']:.2f}" if cid in score.index else f"{run} (n/a)"
            tiles.append(overlay(crop, m, title))
        cols = 4
        while len(tiles) % cols:
            tiles.append(np.zeros_like(tiles[0]))
        sheet = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
        cv2.imwrite(str(fig_dir / f"{cid}.png"), sheet)
        print(f"Figure: {fig_dir / f'{cid}.png'}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Segmentation model comparison.")
    ap.add_argument("--classical", action="store_true", help="score the classical baseline on the folds")
    ap.add_argument("--figure", nargs="+", metavar="CROP_ID", help="overlay figure for these crops")
    ap.add_argument("--rescore", action="store_true", help="re-score all runs from their saved masks")
    ap.add_argument("--h-sensitivity", type=float, nargs="+", metavar="H",
                    help="sensitivity analysis: re-score wall-map runs with these watershed thresholds")
    args = ap.parse_args()

    cfg = load_config()
    seg_out = cfg["paths"]["outputs_dir"] / "seg"
    seg_out.mkdir(parents=True, exist_ok=True)
    if args.classical:
        classical_run(cfg, seg_out)
    elif args.rescore:
        rescore(cfg, seg_out)
    elif args.h_sensitivity:
        h_sensitivity(cfg, seg_out, args.h_sensitivity)
    elif args.figure:
        figure(cfg, seg_out, args.figure)
    else:
        n_crops = len(pd.read_csv(round_dir(cfg) / "index.csv"))
        comparison(seg_out, n_crops)


if __name__ == "__main__":
    main()
