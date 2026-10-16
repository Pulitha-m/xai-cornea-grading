"""
Phase 4 — physical scale (um per pixel) from the calibration subset.

The Konan magnification is fixed, so um/px is ONE constant for the dataset.
It is not stated in the Konan output, so it is recovered from images that are
used for nothing else (the 69-image calibration subset, Phase 0):

  per image   s_i = sqrt(Konan mean cell area [um^2] / our mean cell area [px^2])
              our area = Phase 3 extraction, all complete cells, centre-line area
  scale       median of s_i  (robust: Konan measures ~110 operator-chosen cells,
              we measure the whole lit area), 95 % CI by bootstrap over images

Rules are fixed in config.yaml (calibration:) before any result was seen.
Sensitivity rows (without flagged cells, geometric mean, per ECD band, the
preliminary audit scale) are printed for interpretation only.
--check applies the scale to the validation images (never used to fit it):
ECD vs Konan — bias, MAPE, share within the scope target, Bland-Altman.
ECD = 1e6 / mean area, so ECD and mean-area errors are the same evidence.

Outputs: <outputs_dir>/calibration/<run>/scale.json, per_image.csv,
         val_ecd.csv, figures/calibration.png
The scale is copied into config.yaml (scale.um_per_px) by hand after review.

Usage (from ml/cellular/; CPU is enough once the masks are extracted):
    python -m calibration.scale
    python -m calibration.scale --check
    python -m calibration.scale --figure
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import load_config
from extraction.run_extract import paths
from segmentation.infer_full import images_of


def per_image_scale(konan_area_um2, area_px) -> np.ndarray:
    """um/px of each image: sqrt(Konan area / our area); NaN where our area is missing or 0."""
    a = np.asarray(area_px, float)
    k = np.asarray(konan_area_um2, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(a > 0, np.sqrt(k / a), np.nan)


def estimate_scale(s, n_bootstrap: int = 2000, seed: int = 0) -> dict:
    """Median of the per-image scales with a percentile-bootstrap 95 % CI over images."""
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    rng = np.random.default_rng(seed)
    boot = np.median(rng.choice(s, size=(n_bootstrap, len(s)), replace=True), axis=1)
    q25, q75 = np.percentile(s, [25, 75])
    med = float(np.median(s))
    return {"um_per_px": med, "ci_low": float(np.percentile(boot, 2.5)),
            "ci_high": float(np.percentile(boot, 97.5)), "n_images": int(len(s)),
            "iqr_pct": float(100 * (q75 - q25) / med)}


def ecd_from_area(area_px, um_per_px: float):
    """Endothelial cell density (cells/mm^2) from the mean cell area in px^2."""
    return 1e6 / (np.asarray(area_px, float) * um_per_px ** 2)


def agreement(ours, ref, target_pct: float) -> dict:
    """ECD (or any measure) vs the reference: % bias, MAPE, share within the target, Bland-Altman."""
    ours, ref = np.asarray(ours, float), np.asarray(ref, float)
    pct = 100 * (ours - ref) / ref
    diff = ours - ref
    sd = diff.std(ddof=1) if len(diff) > 1 else np.nan
    return {"n": len(ref), "bias_%": float(np.mean(pct)), "median_bias_%": float(np.median(pct)),
            "mape_%": float(np.mean(np.abs(pct))),
            f"within_{target_pct:g}%_share": float(np.mean(np.abs(pct) <= target_pct)),
            "ba_mean_diff": float(diff.mean()), "ba_loa_low": float(diff.mean() - 1.96 * sd),
            "ba_loa_high": float(diff.mean() + 1.96 * sd),
            "rho": float(spearmanr(ours, ref).correlation)}


def out_dir(cfg: dict):
    d = cfg["paths"]["outputs_dir"] / "calibration" / cfg["calibration"]["run"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(cfg: dict, split: str) -> pd.DataFrame:
    """Phase 3 extraction summary of a split joined with Konan; images with too few cells dropped."""
    c = cfg["calibration"]
    _, ext = paths(cfg, c["run"], split, "lit")
    if not (ext / "summary.csv").exists():
        raise SystemExit(f"No extraction for '{split}' ({ext}). Run segmentation.infer_full and "
                         f"extraction.run_extract with --split {split} first.")
    ref = images_of(cfg, split)[["image_id", "mean_area", "ecd", "ecd_band"]]
    s = pd.read_csv(ext / "summary.csv").merge(ref, on="image_id")
    s = s.dropna(subset=["mean_area", "ecd", "mean_area_px"])
    dropped = int((s["n_cells"] < c["min_cells"]).sum())
    if dropped:
        print(f"  {dropped} {split} image(s) with < {c['min_cells']} complete cells not used")
    return s[s["n_cells"] >= c["min_cells"]].reset_index(drop=True)


def calibrate(cfg: dict) -> None:
    c = cfg["calibration"]
    s = load(cfg, c["split"])
    s["um_per_px"] = per_image_scale(s["mean_area"], s["mean_area_px"])
    s["um_per_px_unflagged"] = per_image_scale(s["mean_area"], s["mean_area_px_unflagged"])
    est = estimate_scale(s["um_per_px"], c["n_bootstrap"], c["seed"])
    prelim = cfg["scale"]["um_per_px_prelim"]

    rows = [{"estimate": "OFFICIAL: median, all complete cells", "um_per_px": est["um_per_px"],
             "n": est["n_images"]},
            {"estimate": "median, without flagged cells", "um_per_px": s["um_per_px_unflagged"].median(),
             "n": len(s)},
            {"estimate": "geometric mean, all complete cells",
             "um_per_px": float(np.exp(np.log(s["um_per_px"]).mean())), "n": len(s)}]
    rows += [{"estimate": f"median, ECD band {b}{' (too few)' if len(g) < 20 else ''}",
              "um_per_px": g["um_per_px"].median(), "n": len(g)}
             for b, g in s.groupby("ecd_band")]
    rows.append({"estimate": "preliminary (Phase 0 audit)", "um_per_px": prelim, "n": np.nan})
    table = pd.DataFrame(rows).set_index("estimate")
    table["vs official %"] = 100 * (table["um_per_px"] / est["um_per_px"] - 1)

    d = out_dir(cfg)
    s.to_csv(d / "per_image.csv", index=False)
    (d / "scale.json").write_text(json.dumps({**est, "split": c["split"], "run": c["run"],
                                              "estimator": "median of per-image scales"}, indent=2))
    pd.set_option("display.width", 200)
    print(f"Scale from {est['n_images']} {c['split']} images ({c['run']}):")
    print(f"  um_per_px = {est['um_per_px']:.4f}  (95% CI {est['ci_low']:.4f} - {est['ci_high']:.4f}); "
          f"per-image spread IQR {est['iqr_pct']:.1f}% of the median")
    print(f"  area scale = {est['um_per_px'] ** 2:.4f} um^2/px^2; preliminary {prelim} -> "
          f"{100 * (est['um_per_px'] / prelim - 1):+.1f}%")
    print("\nSensitivity (interpretation only; the official estimate is fixed in config):")
    print(table.round(4).to_string())
    print(f"\nSaved: {d / 'scale.json'}")


def check(cfg: dict) -> None:
    """Apply the calibrated scale to the validation images (not used for fitting)."""
    c = cfg["calibration"]
    d = out_dir(cfg)
    if not (d / "scale.json").exists():
        raise SystemExit("Run python -m calibration.scale first.")
    um = json.loads((d / "scale.json").read_text())["um_per_px"]
    target = cfg["targets"]["ecd_pct_error"]
    v = load(cfg, c["check_split"])
    v["ecd_ours"] = ecd_from_area(v["mean_area_px"], um)
    v["ecd_prelim"] = ecd_from_area(v["mean_area_px"], cfg["scale"]["um_per_px_prelim"])
    v.to_csv(d / "val_ecd.csv", index=False)

    rows = {"calibrated scale": agreement(v["ecd_ours"], v["ecd"], target),
            "preliminary scale": agreement(v["ecd_prelim"], v["ecd"], target)}
    rows.update({f"calibrated, ECD band {b} (n={len(g)}{', too few' if len(g) < 20 else ''})":
                 agreement(g["ecd_ours"], g["ecd"], target) for b, g in v.groupby("ecd_band")})
    pd.set_option("display.width", 220)
    print(f"ECD vs Konan on {len(v)} {c['check_split']} images (scale {um:.4f} um/px; "
          f"scope target: error <= {target:g}%):")
    print(pd.DataFrame(rows).T.round(3).to_string())
    print("\nBland-Altman in cells/mm^2 (ours - Konan). ECD = 1e6 / mean area, so the mean-area error is "
          "the same evidence, not independent.")


def figure(cfg: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = out_dir(cfg)
    est = json.loads((d / "scale.json").read_text())
    s = pd.read_csv(d / "per_image.csv")
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    ax[0].scatter(s["ecd"], s["um_per_px"], s=14)
    ax[0].axhline(est["um_per_px"], color="k", label=f"median {est['um_per_px']:.4f}")
    ax[0].axhspan(est["ci_low"], est["ci_high"], color="k", alpha=0.15, label="95% CI")
    ax[0].axhline(cfg["scale"]["um_per_px_prelim"], color="tab:orange", ls="--", label="preliminary")
    ax[0].set(xlabel="Konan ECD (cells/mm²)", ylabel="per-image µm/px",
              title=f"Calibration images (n={len(s)})")
    ax[0].legend()
    if (d / "val_ecd.csv").exists():
        v = pd.read_csv(d / "val_ecd.csv")
        mean, diff = (v["ecd_ours"] + v["ecd"]) / 2, v["ecd_ours"] - v["ecd"]
        sd = diff.std(ddof=1)
        ax[1].scatter(mean, diff, s=14)
        for y, ls in ((diff.mean(), "-"), (diff.mean() - 1.96 * sd, "--"), (diff.mean() + 1.96 * sd, "--")):
            ax[1].axhline(y, color="k", ls=ls)
        ax[1].set(xlabel="mean of ours and Konan ECD (cells/mm²)", ylabel="ours − Konan (cells/mm²)",
                  title=f"Validation images, Bland–Altman (n={len(v)})")
    else:
        ax[1].set_axis_off()
    fig.tight_layout()
    (d / "figures").mkdir(exist_ok=True)
    fig.savefig(d / "figures" / "calibration.png", dpi=120)
    print(f"Figure: {d / 'figures' / 'calibration.png'}")


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Phase 4: um/px from the calibration subset.")
    ap.add_argument("--check", action="store_true", help="apply the scale to the validation images")
    ap.add_argument("--figure", action="store_true")
    args = ap.parse_args()
    if args.check:
        check(cfg)
    elif args.figure:
        figure(cfg)
    else:
        calibrate(cfg)


if __name__ == "__main__":
    main()
