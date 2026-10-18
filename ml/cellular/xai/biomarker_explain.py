"""
XAI step 2 — explaining the biomarkers: is a measured cell reliable, which cells drive CV / HEX,
how uncertain is each number? Rules: config.yaml -> xai.biomarkers (fixed before any result).

  --crops      the 40 annotated crops, each predicted by the Phase 2 StarDist fold model that never saw it:
               per-cell confidence + plausibility -> GREEN / YELLOW / RED vs real segmentation errors
               (primary: AUC of low confidence for wrong cells); CI coverage of the manual value
  --intervals  95 % CIs (block and per-cell bootstrap) for every validation image from the Phase 6
               per-cell tables (CPU); width vs Konan's ~110-cell sampling uncertainty
  --figures    validation images (GPU): reliability | area evidence (CV) | side-count evidence (HEX)

Outputs: <outputs_dir>/xai/biomarkers/ (crop_cells.csv, crop_ci.csv, crop_vs_phase2.csv, decision.json, intervals.csv,
         figures/<image_id>.png, figures_summary.csv)
Usage (from ml/cellular/; GPU for --crops / --figures):
    python -m xai.biomarker_explain --crops
    python -m xai.biomarker_explain --intervals
    python -m xai.biomarker_explain --figures
"""

from __future__ import annotations

import argparse
import json

import cv2
import numpy as np
import pandas as pd

from config import load_config
from data_prep.check_annotations import IGNORE
from extraction.cells import ExtractionParams, extract_cells, instances_from_mask, match_cells
from xai.reliability import (area_overlay, bootstrap_ci, cell_confidence, reliability,
                             reliability_overlay, sides_overlay, variance_share)

LEVELS = ("green", "yellow", "red")
BIOMARKERS = ("ecd", "cv", "hex")


def out_root(cfg: dict):
    d = cfg["paths"]["outputs_dir"] / "xai" / "biomarkers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def point_values(cells: pd.DataFrame, um_per_px: float) -> dict:
    """ECD, CV, HEX of a cell table (no resampling)."""
    return {k: v["value"] for k, v in bootstrap_ci(cells, um_per_px, 0, 1, 0).items()}


def label_cells(cells: pd.DataFrame, matches: pd.DataFrame, ref: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """Predicted cells vs reference: matched, area error, WRONG (unmatched or area off), side error."""
    m = matches.set_index("pred_id")
    g = ref.set_index("cell_id")
    rows = []
    for r in cells.itertuples(index=False):
        row = {"cell_id": r.cell_id, "matched": r.cell_id in m.index, "area_err_pct": np.nan,
               "sides_ref": np.nan, "side_error": np.nan}
        if row["matched"]:
            gid = m.loc[r.cell_id, "gt_id"]
            row["area_err_pct"] = 100 * (r.area_px - g.loc[gid, "area_px"]) / g.loc[gid, "area_px"]
            row["sides_ref"] = g.loc[gid, "sides"]
            if pd.notna(r.sides) and pd.notna(row["sides_ref"]):
                row["side_error"] = float(r.sides != row["sides_ref"])
        row["wrong"] = (not row["matched"]) or abs(row["area_err_pct"]) > rules["error_area_pct"]
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- crops ----------
def crops(cfg: dict) -> None:
    from stardist.models import StarDist2D

    from segmentation.data import load_samples
    from segmentation.infer_full import instance_prob_image
    from segmentation.run_stardist import to_input
    from segmentation.train_final import final_dir

    xb, run, um = cfg["xai"]["biomarkers"], cfg["extraction"]["run"], cfg["scale"]["um_per_px"]
    p = ExtractionParams.from_config(cfg)
    info = json.loads((final_dir(cfg, run) / "final.json").read_text())
    samples = load_samples(cfg, info["preprocess"])
    model_root = cfg["paths"]["models_dir"] / "seg" / run
    inst_dir = cfg["paths"]["outputs_dir"] / "seg" / run / "inst"
    cell_parts, ci_rows, same = [], [], []
    for k in sorted({s.fold for s in samples}):
        model = StarDist2D(None, name=f"fold{k}", basedir=str(model_root))
        thr = float(model.thresholds.prob)
        for s in (s for s in samples if s.fold == k):
            labels, det = model.predict_instances(to_input(s.image))
            saved = inst_dir / f"{s.crop_id}.png"
            if saved.exists():                    # vs the Phase 2 out-of-fold prediction (label-agnostic)
                old = cv2.imread(str(saved), cv2.IMREAD_UNCHANGED).astype(np.int32)
                m = match_cells(labels, old, 0.5)
                same.append({"identical": bool(np.array_equal(old, labels)), "n_new": int(len(np.unique(labels)) - 1),
                             "n_old": int(len(np.unique(old)) - 1), "matched": len(m),
                             "mean_iou": float(m["iou"].mean()) if len(m) else np.nan})
            analysable = s.mask != IGNORE
            ref, _, comp_g = extract_cells(instances_from_mask(s.mask), analysable, p)
            cells, _, comp_p = extract_cells(labels, analysable, p)
            if cells.empty or ref.empty:
                continue
            prob = instance_prob_image(labels, det["prob"], det["points"])
            rel = reliability(cells, cell_confidence(comp_p, prob, cells["cell_id"]), thr, xb)
            lab = label_cells(cells, match_cells(comp_p, comp_g, xb["error_iou"]), ref, xb)
            part = cells[["cell_id", "area_px", "sides", "compactness"]].merge(
                rel.reset_index(), on="cell_id").merge(lab, on="cell_id")
            cell_parts.append(part.assign(crop_id=s.crop_id, fold=k, difficulty=s.meta.get("difficulty"),
                                          prob_thresh=thr))
            truth = point_values(ref, um)
            for name, bp in (("block", xb["block_px"]), ("cell", 0)):
                ci = bootstrap_ci(cells, um, bp, xb["n_boot"], xb["seed"])
                for b in BIOMARKERS:
                    lo, hi, t = ci[b]["lo"], ci[b]["hi"], truth[b]
                    ci_rows.append({"crop_id": s.crop_id, "bootstrap": name, "biomarker": b,
                                    "value": ci[b]["value"], "lo": lo, "hi": hi, "reference": t,
                                    "covered": None if None in (lo, hi, t) else lo <= t <= hi})
        print(f"  fold {k}: done (detection threshold {thr:.2f})", flush=True)
    cells, cis = pd.concat(cell_parts, ignore_index=True), pd.DataFrame(ci_rows)
    out = out_root(cfg)
    cells.to_csv(out / "crop_cells.csv", index=False)
    cis.to_csv(out / "crop_ci.csv", index=False)
    if same:
        sm = pd.DataFrame(same)
        sm.to_csv(out / "crop_vs_phase2.csv", index=False)
        print(f"  re-predicted vs Phase 2 out-of-fold instances ({len(sm)} crops): identical label images "
              f"{int(sm['identical'].sum())}; cells {sm['n_new'].sum()} now vs {sm['n_old'].sum()} then; "
              f"matched (IoU > 0.5) {100 * sm['matched'].sum() / sm['n_new'].sum():.1f} % of now, "
              f"{100 * sm['matched'].sum() / sm['n_old'].sum():.1f} % of then; mean IoU of matches "
              f"{sm['mean_iou'].mean():.3f}; worst crop {100 * (sm['matched'] / sm['n_new']).min():.1f} % matched")
    decide(cfg, cells, cis)


def auc(y: np.ndarray, score: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, score)) if 0 < y.sum() < len(y) else float("nan")


def decide(cfg: dict, cells: pd.DataFrame, cis: pd.DataFrame) -> None:
    xb = cfg["xai"]["biomarkers"]
    score = 1 - cells["confidence"].fillna(0)                   # unknown confidence = least confident
    y = cells["wrong"].astype(bool).to_numpy()
    rng = np.random.default_rng(xb["seed"])
    ids = cells["crop_id"].unique()
    groups = {c: np.flatnonzero(cells["crop_id"].to_numpy() == c) for c in ids}
    boot = []
    for _ in range(xb["n_boot"]):
        idx = np.concatenate([groups[c] for c in rng.choice(ids, len(ids))])
        boot.append(auc(y[idx], score.to_numpy()[idx]))
    lo, hi = np.nanpercentile(boot, [2.5, 97.5])
    a = auc(y, score.to_numpy())
    ordinal = cells["level"].map({"green": 0, "yellow": 1, "red": 2}).to_numpy()
    by_level = cells.groupby("level").agg(cells=("wrong", "size"), wrong_pct=("wrong", lambda s: 100 * s.mean()),
                                          side_error_pct=("side_error", lambda s: 100 * s.mean()))
    by_level = by_level.reindex([l for l in LEVELS if l in by_level.index])
    by_level["share_pct"] = 100 * by_level["cells"] / by_level["cells"].sum()
    rates = by_level["wrong_pct"].to_numpy()
    cov = (cis.dropna(subset=["covered"]).groupby(["biomarker", "bootstrap"])["covered"]
           .agg(lambda s: round(100 * s.mean(), 1)).unstack())
    summary = {
        "cells": int(len(cells)), "crops": int(len(ids)), "wrong_pct": round(100 * float(y.mean()), 1),
        "confidence_unknown": int(cells["confidence"].isna().sum()),
        "auc_low_confidence": round(a, 3), "auc_ci95": [round(float(lo), 3), round(float(hi), 3)],
        "primary_pass": bool(lo > 0.5),
        "auc_level_ordinal": round(auc(y, ordinal), 3),
        "by_level": by_level.round(1).reset_index().to_dict("records"),
        "error_rate_rises_green_yellow_red": bool(len(rates) == 3 and rates[0] < rates[1] < rates[2]),
        "ci_coverage_pct": cov.to_dict(),
    }
    (out_root(cfg) / "decision.json").write_text(json.dumps(summary, indent=2, default=str))
    pd.set_option("display.width", 200)
    print(f"\n{len(cells)} predicted complete cells on {len(ids)} crops; wrong (no match IoU > {xb['error_iou']} "
          f"or area off > {xb['error_area_pct']} %): {summary['wrong_pct']} %; confidence unknown: "
          f"{summary['confidence_unknown']}")
    print(f"PRIMARY  AUC of low confidence for wrong cells: {a:.3f} (95 % CI {lo:.3f}-{hi:.3f}, bootstrap over "
          f"crops) -> {'PASS' if summary['primary_pass'] else 'FAIL'}")
    print(f"         AUC of the level (green < yellow < red): {summary['auc_level_ordinal']}")
    print("\nBy level:")
    print(by_level.round(1).to_string())
    print(f"error rate rises green < yellow < red: {summary['error_rate_rises_green_yellow_red']}")
    print("\nCI coverage of the manual value (% of crops; < 95 % expected - segmentation error is not in the CI):")
    print(cov.to_string())
    print(f"\nResults: {out_root(cfg)}")


# ---------------------------------------------------------------- intervals ----------
def intervals(cfg: dict) -> None:
    from extraction.run_extract import paths
    from segmentation.infer_full import images_of

    xb, um = cfg["xai"]["biomarkers"], cfg["scale"]["um_per_px"]
    _, ext = paths(cfg, cfg["biomarkers"]["run"], "val", "lit", True)
    rows = []
    for k in images_of(cfg, "val").itertuples(index=False):
        f = ext / "cells" / f"{k.image_id}.csv"
        if not f.exists():
            continue
        cells = pd.read_csv(f)
        if len(cells) < cfg["biomarkers"]["min_cells"]:
            continue
        row = {"image_id": k.image_id, "n_cells": len(cells), "n_sides": int(cells["sides"].notna().sum()),
               "konan_cells": k.num_cells}
        for name, bp in (("block", xb["block_px"]), ("cell", 0)):
            ci = bootstrap_ci(cells, um, bp, xb["n_boot"], xb["seed"])
            for b in BIOMARKERS:
                v, lo, hi = ci[b]["value"], ci[b]["lo"], ci[b]["hi"]
                half = (hi - lo) / 2 if None not in (lo, hi) else np.nan
                row[f"{b} value"] = v
                row[f"{b} lo {name}"], row[f"{b} hi {name}"] = lo, hi
                row[f"{b} half-width {name}"] = 100 * half / v if b == "ecd" else half
        # Konan's own ~110-cell sampling uncertainty (normal approximation, same 95 % level)
        n = max(k.num_cells, 1)
        row["ecd half-width konan"] = 1.96 * k.cv / np.sqrt(n)                 # % of ECD (= rel. SE of mean area)
        row["cv half-width konan"] = 1.96 * k.cv / np.sqrt(2 * n)              # points
        row["hex half-width konan"] = 1.96 * 100 * np.sqrt((k.hex / 100) * (1 - k.hex / 100) / n)   # points
        rows.append(row)
    t = pd.DataFrame(rows)
    t.to_csv(out_root(cfg) / "intervals.csv", index=False)
    print(f"95 % CI half-width on {len(t)} validation images (median; ECD in % of the value, CV / HEX in points):")
    summ = pd.DataFrame({b: {"ours, block bootstrap": t[f"{b} half-width block"].median(),
                             "ours, per-cell bootstrap": t[f"{b} half-width cell"].median(),
                             "Konan (~110 cells, approx.)": t[f"{b} half-width konan"].median()}
                         for b in BIOMARKERS}).T
    print(summ.round(2).to_string())
    print(f"\nmedian cells: ours {t['n_cells'].median():.0f} (with side count {t['n_sides'].median():.0f}), "
          f"Konan {t['konan_cells'].median():.0f}.  Results: {out_root(cfg) / 'intervals.csv'}")


# ---------------------------------------------------------------- figures ----------
def figures(cfg: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from extraction.run_extract import analysable, paths
    from segmentation.infer_full import images_of, make_predictor

    xb, um, run = cfg["xai"]["biomarkers"], cfg["scale"]["um_per_px"], cfg["biomarkers"]["run"]
    p = ExtractionParams.from_config(cfg)
    predict = make_predictor(cfg, run, "lit", with_prob=True)
    _, ext = paths(cfg, run, "val", "lit", True)
    man = images_of(cfg, "val").sort_values("ecd").reset_index(drop=True)
    pick = man.iloc[np.linspace(0, len(man) - 1, xb["n_images"]).round().astype(int)]   # spread over ECD
    d = out_root(cfg) / "figures"
    d.mkdir(exist_ok=True)
    rows = []
    for k in pick.itertuples(index=False):
        img = cv2.imread(str(cfg["paths"]["images_dir"] / k.image_file), cv2.IMREAD_GRAYSCALE)
        mask, prob = predict(img)
        cells, _, complete = extract_cells(instances_from_mask(mask), analysable(cfg, mask, "val", k.image_id, True), p)
        saved = ext / "cells" / f"{k.image_id}.csv"
        n_saved = len(pd.read_csv(saved)) if saved.exists() else None
        rel = reliability(cells, cell_confidence(complete, prob, cells["cell_id"]), predict.prob_thresh, xb)
        ci = bootstrap_ci(cells, um, xb["block_px"], xb["n_boot"], xb["seed"])
        top, share = variance_share(cells, xb["top_variance_share"])
        lev = rel["level"].value_counts(normalize=True).reindex(LEVELS, fill_value=0) * 100
        fmt = lambda b, dec: f"{ci[b]['value']:.{dec}f} (95 % CI {ci[b]['lo']:.{dec}f}-{ci[b]['hi']:.{dec}f})"
        fig, axes = plt.subplots(1, 3, figsize=(21, 6))
        axes[0].imshow(reliability_overlay(img, complete, rel))
        axes[0].set_title(f"{k.image_id}: reliability of {len(cells)} measured cells\n"
                          f"green {lev['green']:.0f} %, yellow (low confidence) {lev['yellow']:.0f} %, "
                          f"red (implausible size / shape) {lev['red']:.0f} %", fontsize=10)
        axes[1].imshow(area_overlay(img, complete, cells, top))
        axes[1].set_title(f"CV {fmt('cv', 1)} % - area vs median: blue <= 1/2, red >= 2x\n"
                          f"yellow outline: {100 * xb['top_variance_share']:.0f} % most extreme cells = "
                          f"{100 * share:.0f} % of the area variance", fontsize=10)
        axes[2].imshow(sides_overlay(img, complete, cells))
        axes[2].set_title(f"HEX {fmt('hex', 1)} % - sides: <=4 purple, 5 orange, 6 green, 7 blue, >=8 red\n"
                          f"ECD {fmt('ecd', 0)} cells/mm2", fontsize=10)
        for ax in axes:
            ax.axis("off")
        fig.tight_layout()
        fig.savefig(d / f"{k.image_id}.png", dpi=70)
        plt.close(fig)
        rows.append({"image_id": k.image_id, "n_cells": len(cells), "n_cells_phase6": n_saved,
                     **{f"{l} %": round(lev[l], 1) for l in LEVELS},
                     "median confidence": round(float(rel["confidence"].median()), 3),
                     "top 5 % share of variance %": round(100 * share, 1),
                     **{f"{b} [lo, hi]": f"{ci[b]['value']} [{ci[b]['lo']}, {ci[b]['hi']}]" for b in BIOMARKERS}})
        print(f"  {k.image_id}: done", flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(out_root(cfg) / "figures_summary.csv", index=False)
    pd.set_option("display.width", 250)
    print(t.to_string(index=False))
    print(f"(n_cells must equal n_cells_phase6: same cells as the reported results)\nFigures: {d}")


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="XAI step 2: biomarker reliability, evidence and uncertainty.")
    ap.add_argument("--crops", action="store_true")
    ap.add_argument("--intervals", action="store_true")
    ap.add_argument("--figures", action="store_true")
    args = ap.parse_args()
    if args.crops:
        crops(cfg)
    if args.intervals:
        intervals(cfg)
    if args.figures:
        figures(cfg)
    if not (args.crops or args.intervals or args.figures):
        ap.print_help()


if __name__ == "__main__":
    main()
