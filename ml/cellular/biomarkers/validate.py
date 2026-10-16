"""
Phase 5, Steps 5.1-5.4 — biomarkers on the validation images and agreement with Konan.

  (default)   per image: biomarker report (JSON) from the Phase 3 per-cell table and the
              Phase 4 scale (config scale.um_per_px); all reports in biomarkers.csv
  --compare   ECD, mean area, SD, CV, HEX vs Konan: bias, MAPE, share within the scope
              target, Bland-Altman, Spearman rho; by ECD band; compactness (no Konan value:
              per-image CV of compactness, and agreement with the reference masks on the
              40 crops if the Phase 3 crop results exist); the images with the largest ECD error
  --figure    Bland-Altman per biomarker + side-count overlays of the largest ECD errors

ECD = 1e6 / mean area, so ECD and mean-area agreement are one piece of evidence.
Konan measures ~110 operator-chosen cells, we measure every complete cell in the lit area.

Outputs: <outputs_dir>/biomarkers/<split>/<run>/json/<image_id>.json, biomarkers.csv,
         agreement.csv, by_band.csv, worst.csv, figures/bland_altman.png
Usage (from ml/cellular/; CPU is enough):
    python -m biomarkers.validate
    python -m biomarkers.validate --compare
    python -m biomarkers.validate --figure
    python -m biomarkers.validate --roi [--compare | --figure]   # Phase 6: inside the ROI, with the
                                                                # scale calibrated inside the ROI
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from biomarkers.compute import report
from calibration.scale import agreement
from config import load_config
from extraction.run_extract import paths
from segmentation.infer_full import images_of

# biomarker column in biomarkers.csv -> (Konan column, target key, unit, label)
PAIRS = {"ecd_cells_per_mm2": ("ecd", "ecd_pct_error", "cells/mm2", "ECD"),
         "mean_area_um2": ("mean_area", "mean_area_pct_error", "um2", "mean area"),
         "sd_area_um2": ("sd", None, "um2", "SD of area"),
         "cv_pct": ("cv", "cv_pct_error", "points", "CV"),
         "hex_pct": ("hex", "hex_pct_error", "points", "HEX")}


def out_dir(cfg: dict, b: dict):
    d = cfg["paths"]["outputs_dir"] / "biomarkers" / b["split"] / (b["run"] + ("_roi" if cfg.get("_roi") else ""))
    (d / "json").mkdir(parents=True, exist_ok=True)
    return d


def compute_all(cfg: dict) -> None:
    b = cfg["biomarkers"]
    um = scale_of(cfg)
    _, ext = paths(cfg, b["run"], b["split"], "lit", bool(cfg.get("_roi")))
    d = out_dir(cfg, b)
    rows = []
    for r in images_of(cfg, b["split"]).itertuples(index=False):
        f = ext / "cells" / f"{r.image_id}.csv"
        if not f.exists():
            print(f"  missing cells: {r.image_id} - run extraction.run_extract first")
            continue
        rep = report(r.image_id, pd.read_csv(f), um, b["run"])
        (d / "json" / f"{r.image_id}.json").write_text(json.dumps(rep, indent=2))
        bm = rep["biomarkers"]
        rows.append({"image_id": r.image_id, **{k: v for k, v in bm.items() if not isinstance(v, dict)},
                     **{f"area_{k}_um2": v for k, v in bm["area_percentiles_um2"].items()},
                     **{f"sides_{k}_pct": v for k, v in bm["side_distribution_pct"].items()}})
    pd.DataFrame(rows).to_csv(d / "biomarkers.csv", index=False)
    print(f"{len(rows)} {b['split']} images, scale {um} um/px -> {d}")


def scale_of(cfg: dict) -> float:
    """config scale.um_per_px (whole lit area); with --roi the scale calibrated inside the ROI
    (calibration.scale --roi), because the scale must come from the same pipeline it is applied to."""
    if cfg.get("_roi"):
        f = cfg["paths"]["outputs_dir"] / "calibration" / f"{cfg['calibration']['run']}_roi" / "scale.json"
        if not f.exists():
            raise SystemExit(f"No ROI scale ({f}) - run python -m calibration.scale --roi first.")
        return round(json.loads(f.read_text())["um_per_px"], 4)
    if not cfg["scale"]["um_per_px"]:
        raise SystemExit("scale.um_per_px is not set - run Phase 4 (calibration.scale) first.")
    return cfg["scale"]["um_per_px"]


def load(cfg: dict) -> pd.DataFrame:
    b = cfg["biomarkers"]
    d = out_dir(cfg, b)
    ref = images_of(cfg, b["split"])[["image_id", "ecd", "mean_area", "sd", "cv", "hex", "ecd_band"]]
    s = pd.read_csv(d / "biomarkers.csv").merge(ref, on="image_id")
    dropped = int((s["n_cells"] < b["min_cells"]).sum())
    if dropped:
        print(f"  {dropped} image(s) with < {b['min_cells']} complete cells not used")
    s = s[s["n_cells"] >= b["min_cells"]].copy()
    s["ecd_err_pct"] = 100 * (s["ecd_cells_per_mm2"] - s["ecd"]) / s["ecd"]
    return s


def agreement_row(ours: pd.Series, ref: pd.Series, target: float | None) -> dict:
    ok = ours.notna() & ref.notna()
    a = agreement(ours[ok], ref[ok], target or 0)
    within = a.pop(f"within_{(target or 0):g}%_share")
    return {"n": a["n"], "ours mean": ours[ok].mean(), "Konan mean": ref[ok].mean(),
            "bias %": a["bias_%"], "MAPE %": a["mape_%"], "MAE (units)": (ours[ok] - ref[ok]).abs().mean(),
            "target %": target, "within target": within if target else np.nan,
            "BA mean diff": a["ba_mean_diff"], "BA LoA low": a["ba_loa_low"], "BA LoA high": a["ba_loa_high"],
            "rho": a["rho"]}


def compare(cfg: dict) -> None:
    b, t = cfg["biomarkers"], cfg["targets"]
    d = out_dir(cfg, b)
    s = load(cfg)
    pd.set_option("display.width", 240)

    table = pd.DataFrame({f"{lab} ({unit})": agreement_row(s[ours], s[ref], t[key] if key else None)
                          for ours, (ref, key, unit, lab) in PAIRS.items()}).T
    table.to_csv(d / "agreement.csv")
    print(f"Biomarkers vs Konan - {len(s)} {b['split']} images ({b['run']}{', inside the ROI' if cfg.get('_roi') else ''}, "
          f"scale {scale_of(cfg)} um/px)")
    print("error = 100 x (ours - Konan) / Konan; 'within target' = share of images with |error| <= target %")
    print(table.round(3).to_string())

    rows = []
    for band, g in s.groupby("ecd_band"):
        row = {"ECD band": band, "n": len(g)}
        for ours, (ref, _, _, lab) in PAIRS.items():
            row[f"{lab} bias %"] = (100 * (g[ours] - g[ref]) / g[ref]).mean()
            row[f"{lab} rho"] = spearmanr(g[ours], g[ref]).correlation if len(g) > 2 else np.nan
        rows.append(row)
    bands = pd.DataFrame(rows).set_index("ECD band")
    bands.to_csv(d / "by_band.csv")
    print("\nBy ECD band (exploratory; bands with n < 20 are not interpretable):")
    print(bands.round(2).to_string())

    c = s["cv_compactness_pct"]
    print(f"\nCompactness (Konan reports none): mean {s['mean_compactness'].mean():.3f} "
          f"(regular hexagon 0.907); per-image CV of compactness median {c.median():.1f}%, "
          f"{100 * (c <= t['compactness_cv']).mean():.0f}% of images <= {t['compactness_cv']:g}%")
    crops = cfg["paths"]["outputs_dir"] / "extraction" / "crops" / b["run"] / "crops.csv"
    if crops.exists():
        k = pd.read_csv(crops)
        e = 100 * (k["mean_compactness_pred"] - k["mean_compactness_gt"]) / k["mean_compactness_gt"]
        print(f"  vs reference masks ({len(k)} crops): mean compactness error {e.mean():+.2f}%, "
              f"max |error| {e.abs().max():.2f}%, rho {spearmanr(k['mean_compactness_pred'], k['mean_compactness_gt']).correlation:.2f}")

    worst = s.reindex(s["ecd_err_pct"].abs().sort_values(ascending=False).index).head(b["worst_n"])
    cols = ["image_id", "ecd_band", "ecd", "ecd_cells_per_mm2", "ecd_err_pct", "n_cells", "n_flagged",
            "cv", "cv_pct", "hex", "hex_pct"]
    worst[cols].to_csv(d / "worst.csv", index=False)
    print(f"\nLargest ECD errors (overlays: --figure):")
    print(worst[cols].round(1).to_string(index=False))


def figure(cfg: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from extraction.run_extract import figure as overlay

    b = cfg["biomarkers"]
    d = out_dir(cfg, b)
    s = load(cfg)
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    for ax, (ours, (ref, _, unit, lab)) in zip(axes.ravel(), PAIRS.items()):
        g = s[[ours, ref]].dropna()
        mean, diff = (g[ours] + g[ref]) / 2, g[ours] - g[ref]
        sd = diff.std(ddof=1)
        ax.scatter(mean, diff, s=12)
        for y, ls in ((diff.mean(), "-"), (diff.mean() - 1.96 * sd, "--"), (diff.mean() + 1.96 * sd, "--")):
            ax.axhline(y, color="k", ls=ls, lw=1)
        u = "" if unit == "points" else f" ({unit})"
        ax.set(title=f"{lab}: bias {diff.mean():+.1f}, LoA [{diff.mean() - 1.96 * sd:.1f}, "
                     f"{diff.mean() + 1.96 * sd:.1f}]", xlabel=f"mean of ours and Konan{u}",
               ylabel=f"ours − Konan{u}")
    ax = axes.ravel()[-1]
    ax.hist(s["mean_compactness"], bins=30)
    ax.axvline(0.907, color="k", ls="--", label="regular hexagon")
    ax.set(title="Mean compactness per image (no Konan value)", xlabel="compactness")
    ax.legend()
    fig.suptitle(f"Biomarkers vs Konan, {len(s)} {b['split']} images (Bland–Altman)")
    fig.tight_layout()
    (d / "figures").mkdir(exist_ok=True)
    fig.savefig(d / "figures" / "bland_altman.png", dpi=110)
    print(f"Figure: {d / 'figures' / 'bland_altman.png'}")

    worst = pd.read_csv(d / "worst.csv") if (d / "worst.csv").exists() else None
    if worst is not None:
        overlay(cfg, b["run"], b["split"], "lit", list(worst["image_id"]), bool(cfg.get("_roi")))


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Phase 5: biomarkers vs Konan.")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--figure", action="store_true")
    ap.add_argument("--roi", action="store_true", help="cells measured only inside the Phase 6 ROI")
    args = ap.parse_args()
    cfg["_roi"] = args.roi
    if args.compare:
        compare(cfg)
    elif args.figure:
        figure(cfg)
    else:
        compute_all(cfg)


if __name__ == "__main__":
    main()
