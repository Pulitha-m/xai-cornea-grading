"""
Error analysis (diagnostic, after Phase 6) — where does the disagreement with Konan come from?

Konan measures ~110 cells in an operator-chosen patch of one image; we measure every
complete cell in the ROI. For every image, our measured cells (ROI pipeline, Phase 6) are
cut into all Konan-sized patches (config error_analysis):

  1. patch spread    ECD / HEX / CV of every patch: does Konan's value lie inside the range of
                     the same image's patches? (if yes, patch choice can explain the difference)
  2. oracle          the patch closest to Konan (uses Konan - a LOWER BOUND, not a method)
  3. patch rules     operator-like rules without Konan: centre, most regular (highest HEX),
                     most uniform (lowest CV), median-ECD patch - compared on the CALIBRATION
                     images first (validation only confirms; nothing is selected on validation)
  4. factors         Spearman of the whole-field |ECD error| with image quality, ROI share,
                     cell count, Konan ECD, Konan cell count and within-image density spread

Outputs: <outputs_dir>/error_analysis/<split>.csv, figures/<split>.png
Usage (from ml/cellular/; CPU):
    python -m biomarkers.error_analysis                 # calibration, then validation
    python -m biomarkers.error_analysis --split val
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import load_config
from extraction.run_extract import paths
from segmentation.infer_full import images_of

RULES = ("whole field", "centre patch", "most regular patch (max HEX)", "most uniform patch (min CV)",
         "median-ECD patch")


def patch_stats(cells: pd.DataFrame, um_per_px: float, size: int, stride: int, min_cells: int,
                shape: tuple[int, int] = (972, 1296)) -> pd.DataFrame:
    """ECD, CV, HEX of every size x size window (cells assigned by centroid) with >= min_cells cells."""
    h, w = shape
    cx, cy = cells["cx"].to_numpy(), cells["cy"].to_numpy()
    area = cells["area_px"].to_numpy(float)
    sides = cells["sides"].to_numpy(float)
    rows = []
    for y in range(0, h - size + 1, stride):
        for x in range(0, w - size + 1, stride):
            m = (cx >= x) & (cx < x + size) & (cy >= y) & (cy < y + size)
            n = int(m.sum())
            if n < min_cells:
                continue
            a = area[m]
            s = sides[m]
            s = s[~np.isnan(s)]
            rows.append({"x": x, "y": y, "n_cells": n,
                         "ecd": 1e6 / (a.mean() * um_per_px ** 2),
                         "cv": 100 * a.std() / a.mean(),
                         "hex": 100 * (s == 6).mean() if len(s) else np.nan,
                         "n_sides": len(s)})
    return pd.DataFrame(rows)


def pick(patches: pd.DataFrame, rule: str, shape=(972, 1296), size: int = 252) -> pd.Series | None:
    """One patch per operator-like rule (no Konan values used)."""
    if patches.empty:
        return None
    if rule == "centre patch":
        d = np.hypot(patches["x"] + size / 2 - shape[1] / 2, patches["y"] + size / 2 - shape[0] / 2)
        return patches.loc[d.idxmin()]
    if rule == "most regular patch (max HEX)":
        p = patches[patches["n_sides"] >= 30]
        return p.loc[p["hex"].idxmax()] if len(p) else None
    if rule == "most uniform patch (min CV)":
        return patches.loc[patches["cv"].idxmin()]
    if rule == "median-ECD patch":
        return patches.loc[(patches["ecd"] - patches["ecd"].median()).abs().idxmin()]
    raise ValueError(rule)


def analyse(cfg: dict, split: str) -> pd.DataFrame:
    ea, um = cfg["error_analysis"], cfg["scale"]["um_per_px"]
    _, ext = paths(cfg, cfg["biomarkers"]["run"], split, "lit", True)
    man = images_of(cfg, split).set_index("image_id")
    roi_csv = cfg["paths"]["outputs_dir"] / "roi" / f"roi_{split}.csv"
    roi = pd.read_csv(roi_csv).set_index("image_id") if roi_csv.exists() else None
    rows = []
    for iid, k in man.iterrows():
        f = ext / "cells" / f"{iid}.csv"
        if not f.exists():
            continue
        cells = pd.read_csv(f)
        if len(cells) < 30:
            continue
        p = patch_stats(cells, um, ea["patch_px"], ea["stride_px"], ea["min_patch_cells"])
        a = cells["area_px"].astype(float)
        s = cells["sides"].dropna()
        row = {"image_id": iid, "ecd_band": k["ecd_band"], "konan_ecd": k["ecd"], "konan_hex": k["hex"],
               "konan_cv": k["cv"], "konan_cells": k["num_cells"], "n_cells": len(cells),
               "n_patches": len(p),
               "ecd whole field": 1e6 / (a.mean() * um ** 2), "hex whole field": 100 * (s == 6).mean(),
               "cv whole field": 100 * a.std() / a.mean()}
        if roi is not None and iid in roi.index:
            row.update(quality_score=roi.loc[iid, "quality_score"], roi_share_of_lit=roi.loc[iid, "roi_share_of_lit"])
        if len(p):
            row.update({"patch ecd p10": p["ecd"].quantile(0.1), "patch ecd p90": p["ecd"].quantile(0.9),
                        "patch ecd min": p["ecd"].min(), "patch ecd max": p["ecd"].max(),
                        "patch hex min": p["hex"].min(), "patch hex max": p["hex"].max(),
                        "density spread %": 100 * (p["ecd"].quantile(0.9) / p["ecd"].quantile(0.1) - 1),
                        # spread expected from sampling alone (patches of ~n cells, area CV of the image)
                        "sampling spread %": 100 * ((1 + 1.2816 * se) / (1 - 1.2816 * se) - 1)
                        if (se := a.std() / a.mean() / np.sqrt(p["n_cells"].median())) < 0.7 else np.nan,
                        "ecd oracle": p.loc[(p["ecd"] - k["ecd"]).abs().idxmin(), "ecd"],
                        "hex oracle": p.loc[(p["hex"] - k["hex"]).abs().idxmin(), "hex"]})
            for r in RULES[1:]:
                q = pick(p, r, size=ea["patch_px"])
                if q is not None:
                    row[f"ecd {r}"], row[f"hex {r}"], row[f"cv {r}"] = q["ecd"], q["hex"], q["cv"]
        rows.append(row)
    df = pd.DataFrame(rows)
    d = cfg["paths"]["outputs_dir"] / "error_analysis"
    d.mkdir(parents=True, exist_ok=True)
    df.to_csv(d / f"{split}.csv", index=False)
    return df


def report(cfg: dict, df: pd.DataFrame, split: str) -> None:
    t = cfg["targets"]
    pd.set_option("display.width", 230)
    print(f"\n==================== {split}: {len(df)} images "
          f"(patches {cfg['error_analysis']['patch_px']} px, median {df['n_patches'].median():.0f} per image) ====")

    def agree(col: str, ref: str, target: float, relative: bool = True) -> dict:
        ok = df[col].notna()
        e = 100 * (df.loc[ok, col] - df.loc[ok, ref]) / df.loc[ok, ref]
        return {"n": int(ok.sum()), "bias %": e.mean(), "MAPE %": e.abs().mean(),
                f"within target": (e.abs() <= target).mean(),
                "MAE (points)": (df.loc[ok, col] - df.loc[ok, ref]).abs().mean()}

    rows = {}
    for r in RULES + ("oracle",):
        rows[(r, "ECD")] = agree(f"ecd {r}", "konan_ecd", t["ecd_pct_error"])
        rows[(r, "HEX")] = agree(f"hex {r}", "konan_hex", t["hex_pct_error"])
    tab = pd.DataFrame(rows).T
    print("Agreement with Konan by how the patch is chosen ('oracle' uses Konan = lower bound, not a method):")
    print(tab.round(3).to_string())

    inside_e = ((df["konan_ecd"] >= df["patch ecd min"]) & (df["konan_ecd"] <= df["patch ecd max"])).mean()
    inside_e80 = ((df["konan_ecd"] >= df["patch ecd p10"]) & (df["konan_ecd"] <= df["patch ecd p90"])).mean()
    inside_h = ((df["konan_hex"] >= df["patch hex min"]) & (df["konan_hex"] <= df["patch hex max"])).mean()
    print(f"\nKonan ECD inside the range of the same image's patches: {100 * inside_e:.0f} % of images "
          f"(inside the middle 80 %: {100 * inside_e80:.0f} %); Konan HEX inside the patch range: {100 * inside_h:.0f} %")
    print(f"Within-image density spread (patch ECD p90 / p10 - 1): median {df['density spread %'].median():.1f} %, "
          f"IQR {df['density spread %'].quantile(0.25):.1f}-{df['density spread %'].quantile(0.75):.1f} %; "
          f"expected from sampling alone: median {df['sampling spread %'].median():.1f} % "
          f"(observed > 1.5 x sampling in {100 * (df['density spread %'] > 1.5 * df['sampling spread %']).mean():.0f} % of images "
          "= real density differences inside the image)")

    err = 100 * (df["ecd whole field"] - df["konan_ecd"]) / df["konan_ecd"]
    factors = {"density spread %": "within-image density spread", "quality_score": "ROI quality score",
               "roi_share_of_lit": "ROI share of lit area", "n_cells": "cells measured",
               "konan_cells": "Konan cell count", "konan_ecd": "Konan ECD"}
    rows = []
    for col, lab in factors.items():
        if col in df:
            rows.append({"factor": lab, "rho with |ECD error|": spearmanr(df[col], err.abs()).correlation,
                         "rho with signed ECD error": spearmanr(df[col], err).correlation})
    print("\nWhat goes with the whole-field ECD error (Spearman, exploratory):")
    print(pd.DataFrame(rows).set_index("factor").round(3).to_string())
    print("\nWhole-field ECD error by band (bands defined by KONAN's ECD): " + "; ".join(
        f"{b}: bias {err[g.index].mean():+.1f} %, MAPE {err[g.index].abs().mean():.1f} % (n={len(g)})"
        for b, g in df.groupby("ecd_band")))
    proportional_check(cfg, df)
    figure(cfg, df, split, err)


def proportional_check(cfg: dict, df: pd.DataFrame) -> None:
    """Is the 'proportional bias' real or regression to the mean? A noisy reference (Konan: ~110 cells,
    operator-chosen patch) makes (ours - Konan) correlate negatively with Konan even if ours is unbiased.
    Bland-Altman therefore relates the difference to the MEAN of both methods."""
    from scipy.stats import linregress

    ours, k = df["ecd whole field"], df["konan_ecd"]
    diff, mean = ours - k, (ours + k) / 2
    err = 100 * diff / k
    fit = linregress(mean, diff)
    ci = 1.96 * fit.stderr
    print("\nProportional bias check (Spearman of the signed ECD error with ...):")
    print(f"  Konan ECD {spearmanr(k, err).correlation:+.3f}  |  our ECD {spearmanr(ours, err).correlation:+.3f}  |  "
          f"mean of both {spearmanr(mean, err).correlation:+.3f}")
    print(f"  Bland-Altman regression of (ours - Konan) on the mean: slope {fit.slope:+.3f} "
          f"(95% CI {fit.slope - ci:+.3f} to {fit.slope + ci:+.3f}; 0 = no proportional bias), p = {fit.pvalue:.3g}")
    bands = pd.cut(mean, [0, *cfg["split"]["stratify_ecd_bins"], np.inf],
                   labels=["<2000", "2000-2800", ">2800"])
    print("  Bias by band of the MEAN of both: " + "; ".join(
        f"{b}: {err[bands == b].mean():+.1f} % (n={int((bands == b).sum())})"
        for b in ["<2000", "2000-2800", ">2800"] if (bands == b).any()))


def figure(cfg: dict, df: pd.DataFrame, split: str, err: pd.Series) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    o = df.sort_values("konan_ecd").reset_index(drop=True)
    fig, ax = plt.subplots(1, 2, figsize=(15, 5))
    x = np.arange(len(o))
    ax[0].vlines(x, o["patch ecd min"], o["patch ecd max"], color="0.75", lw=2, label="range of patch ECDs")
    ax[0].scatter(x, o["ecd whole field"], s=10, color="tab:blue", label="ours, whole field")
    ax[0].scatter(x, o["konan_ecd"], s=10, color="tab:red", label="Konan")
    ax[0].set(xlabel="images sorted by Konan ECD", ylabel="ECD (cells/mm²)",
              title=f"{split}: Konan vs our patches of the same image")
    ax[0].legend()
    ax[1].scatter(df["density spread %"], err, s=12)
    ax[1].axhline(0, color="k", lw=1)
    ax[1].set(xlabel="within-image density spread (patch ECD p90/p10 − 1, %)",
              ylabel="whole-field ECD error vs Konan (%)", title="Error vs density spread")
    fig.tight_layout()
    d = cfg["paths"]["outputs_dir"] / "error_analysis" / "figures"
    d.mkdir(parents=True, exist_ok=True)
    fig.savefig(d / f"{split}.png", dpi=100)
    print(f"Figure: {d / f'{split}.png'}")


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Error analysis: where does the disagreement with Konan come from?")
    ap.add_argument("--split", choices=["calibration", "val"], help="default: calibration, then val")
    args = ap.parse_args()
    for split in ([args.split] if args.split else ["calibration", "val"]):
        report(cfg, analyse(cfg, split), split)


if __name__ == "__main__":
    main()
