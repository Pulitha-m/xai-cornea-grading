"""
Phase 7 — final test: the frozen pipeline on the untouched test set vs Konan, judged against the scope targets.
Rules: config.yaml -> final_test (fixed before any test image is processed).

  --freeze    record the fingerprint of everything that produces a number (git commit, config.yaml, ROI and
              StarDist model files, scale, test image list); refuses with uncommitted changes in ml/cellular
  --run       verify the fingerprint, then run pipeline.CellularPipeline once on every test image
              (resumes after a disconnect; refuses once the run is complete)
  --compare   agreement with Konan (same definitions as Phases 5-6), targets, test vs validation, secondary
              results, figures

Outputs: <outputs_dir>/final_test/ (freeze.json, run_log.json, reports/, per_image.csv, agreement.csv,
         decision.json, figures/)
Usage (from ml/cellular/; GPU for --run):
    python -m final_test --freeze
    python -m final_test --run
    python -m final_test --compare
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import load_config

HERE = Path(__file__).resolve().parent
# biomarker -> (Konan column, target key, label)  - same pairs as biomarkers.validate
PAIRS = {"ecd_cells_per_mm2": ("ecd", "ecd_pct_error", "ECD"),
         "mean_area_um2": ("mean_area", "mean_area_pct_error", "mean area"),
         "sd_area_um2": ("sd", None, "SD of area"),
         "cv_pct": ("cv", "cv_pct_error", "CV"),
         "hex_pct": ("hex", "hex_pct_error", "HEX")}
CI_KEYS = {"ecd_cells_per_mm2": ("ecd_ci95", "ecd"), "cv_pct": ("cv_ci95", "cv"), "hex_pct": ("hex_ci95", "hex")}


def out_root(cfg: dict) -> Path:
    d = cfg["paths"]["outputs_dir"] / "final_test"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- freeze ----------
def file_hash(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_hash(d: Path) -> str | None:
    """Hash of every file (relative path + content) under d; None if d does not exist."""
    d = Path(d)
    if not d.exists():
        return None
    h = hashlib.sha256()
    for p in sorted(x for x in d.rglob("*") if x.is_file() and "__pycache__" not in x.parts):
        h.update(p.relative_to(d).as_posix().encode())
        h.update(file_hash(p).encode())
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout.strip()


def test_images(cfg: dict) -> pd.DataFrame:
    from segmentation.infer_full import images_of
    return images_of(cfg, cfg["final_test"]["split"])


def fingerprint(cfg: dict) -> dict:
    """Everything that produces a number. Two runs with the same fingerprint give the same results."""
    from segmentation.train_final import final_dir
    run = cfg["pipeline"]["run"]
    fdir = final_dir(cfg, run)
    info = json.loads((fdir / "final.json").read_text())
    ids = test_images(cfg)["image_id"].tolist()
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "uncommitted_changes": bool(git("status", "--porcelain", "--", ".", ":(exclude)notebooks")),   # notebooks: no numbers
        "config_sha256": file_hash(HERE / "config.yaml"),
        "models": {"roi": dir_hash(cfg["paths"]["models_dir"] / "roi"),
                   "segmentation_final": dir_hash(fdir),
                   "segmentation_model": dir_hash(Path(info.get("model_dir", fdir)))},
        "segmentation_run": run, "um_per_px": cfg["scale"]["um_per_px"],
        "test_images": len(ids), "test_ids_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
    }


def differences(frozen: dict, now: dict, prefix: str = "") -> list[str]:
    out = []
    for k in sorted(set(frozen) | set(now)):
        a, b = frozen.get(k), now.get(k)
        if isinstance(a, dict) and isinstance(b, dict):
            out += differences(a, b, f"{prefix}{k}.")
        elif a != b:
            out.append(f"{prefix}{k}: frozen {a!r}, now {b!r}")
    return out


def freeze(cfg: dict) -> None:
    f = out_root(cfg) / "freeze.json"
    now = fingerprint(cfg)
    if now["uncommitted_changes"]:
        raise SystemExit("uncommitted changes in ml/cellular - commit and pull first; the frozen state must be a commit")
    if any(v is None for v in now["models"].values()):
        raise SystemExit(f"model folder missing: {now['models']}")
    if f.exists():
        old = json.loads(f.read_text())
        diff = differences(old["fingerprint"], now)
        raise SystemExit("already frozen " + old["time"] + (" - identical, nothing to do" if not diff else
                         " - and things changed since:\n  " + "\n  ".join(diff)))
    f.write_text(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "fingerprint": now}, indent=2))
    print(json.dumps(now, indent=2))
    print(f"\nFROZEN -> {f}\nNothing that produces a number may change until the run is complete.")


# ---------------------------------------------------------------- run ----------
def run(cfg: dict) -> None:
    from pipeline import CellularPipeline

    root = out_root(cfg)
    ff = root / "freeze.json"
    if not ff.exists():
        raise SystemExit("not frozen - run python -m final_test --freeze first")
    frozen = json.loads(ff.read_text())
    diff = differences(frozen["fingerprint"], fingerprint(cfg))
    if diff:
        raise SystemExit("REFUSED - the pipeline differs from the frozen state:\n  " + "\n  ".join(diff))
    log_f = root / "run_log.json"
    log = json.loads(log_f.read_text()) if log_f.exists() else {"started": time.strftime("%Y-%m-%d %H:%M:%S"),
                                                                "sessions": 0, "failures": {}}
    if log.get("completed"):
        raise SystemExit(f"the run is complete ({log['completed']}) - it is not repeated. Use --compare.")
    log["sessions"] += 1
    reports = root / "reports"
    images = test_images(cfg)
    todo = images[~images["image_id"].map(lambda i: (reports / f"{i}.json").exists())]
    print(f"{len(images)} test images, {len(images) - len(todo)} done, {len(todo)} to go "
          f"(session {log['sessions']})", flush=True)
    pipe = CellularPipeline(cfg)
    t0 = time.time()
    for i, r in enumerate(todo.itertuples(index=False), 1):
        try:
            res = pipe.analyse(cfg["paths"]["images_dir"] / r.image_file, r.image_id)
            pipe.save(res, reports)
            log["failures"].pop(r.image_id, None)
        except Exception as e:                                   # recorded, never silently dropped
            log["failures"][r.image_id] = f"{type(e).__name__}: {e}"
        if i % 20 == 0 or i == len(todo):
            log_f.write_text(json.dumps(log, indent=2))
            print(f"  {i}/{len(todo)}  {(time.time() - t0) / i:.1f} s/image", flush=True)
    done = sum((reports / f"{i}.json").exists() for i in images["image_id"])
    if done + len(log["failures"]) >= len(images):
        log["completed"] = time.strftime("%Y-%m-%d %H:%M:%S")
    log_f.write_text(json.dumps(log, indent=2))
    print(f"{done} reports, {len(log['failures'])} failures"
          + (" - RUN COMPLETE" if log.get("completed") else " - re-run --run to resume"))


# ---------------------------------------------------------------- compare ----------
def collect(cfg: dict) -> pd.DataFrame:
    """One row per test image: our biomarkers, flags, reliability, CIs, Konan values."""
    reports = out_root(cfg) / "reports"
    rows = []
    for r in test_images(cfg).itertuples(index=False):
        f = reports / f"{r.image_id}.json"
        row = {"image_id": r.image_id, "ecd_band": r.ecd_band, "report": f.exists()}
        for k in ("ecd", "mean_area", "sd", "cv", "hex", "num_cells"):
            row[f"konan_{k}"] = getattr(r, k)
        if f.exists():
            rep = json.loads(f.read_text())
            bm = rep["biomarkers"]
            row.update({k: v for k, v in bm.items() if not isinstance(v, dict)})
            row["reliable"] = rep["reliable"]
            row["flags"] = ",".join(x["code"] for x in rep["quality_flags"])
            row["roi_share_of_lit"] = rep["roi"]["share_of_lit_area"]
            for lev in ("green", "yellow", "red"):
                row[lev] = (rep.get("reliability") or {}).get(lev)
            for k, (ck, _) in CI_KEYS.items():
                lo, hi = (rep.get("uncertainty") or {}).get(ck, [None, None])
                row[f"{k}_lo"], row[f"{k}_hi"] = lo, hi
        rows.append(row)
    return pd.DataFrame(rows)


def boot_ci(ours: np.ndarray, ref: np.ndarray, target: float | None, n_boot: int, seed: int) -> dict:
    """95 % CI of MAPE and of the within-target share, bootstrap over images."""
    err = np.abs(100 * (ours - ref) / ref)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(err), size=(n_boot, len(err)))
    mape = err[idx].mean(1)
    out = {"mape_ci95": [float(np.percentile(mape, 2.5)), float(np.percentile(mape, 97.5))]}
    if target:
        w = (err[idx] <= target).mean(1) * 100
        out["within_ci95"] = [float(np.percentile(w, 2.5)), float(np.percentile(w, 97.5))]
    return out


def agreement_table(s: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    from calibration.scale import agreement
    ft, t = cfg["final_test"], cfg["targets"]
    rows = {}
    for ours, (ref, key, lab) in PAIRS.items():
        ok = s[ours].notna() & s[f"konan_{ref}"].notna()
        o, r = s.loc[ok, ours].to_numpy(float), s.loc[ok, f"konan_{ref}"].to_numpy(float)
        target = t[key] if key else None
        a = agreement(o, r, target or 0)
        ci = boot_ci(o, r, target, ft["n_boot"], ft["seed"])
        within = 100 * a.pop(f"within_{(target or 0):g}%_share")
        rows[lab] = {"n": a["n"], "bias %": a["bias_%"], "MAPE %": a["mape_%"],
                     "MAPE 95% CI": ci["mape_ci95"], "target %": target,
                     "target met (MAPE <= target)": (a["mape_%"] <= target) if target else None,
                     "within target %": within if target else None, "within 95% CI": ci.get("within_ci95"),
                     "ceiling %": ft["ceiling_within_target_pct"].get(ours),
                     "BA mean diff": a["ba_mean_diff"], "BA LoA": [a["ba_loa_low"], a["ba_loa_high"]],
                     "rho": a["rho"]}
    return pd.DataFrame(rows).T


def validation_table(cfg: dict) -> pd.DataFrame | None:
    """Phase 6 validation agreement (inside the ROI), if available."""
    f = cfg["paths"]["outputs_dir"] / "biomarkers" / "val" / f"{cfg['pipeline']['run']}_roi" / "agreement.csv"
    if not f.exists():
        return None
    v = pd.read_csv(f, index_col=0)
    v.index = [i.split(" (")[0] for i in v.index]
    return v


def compare(cfg: dict) -> None:
    root, ft, t = out_root(cfg), cfg["final_test"], cfg["targets"]
    log_f = root / "run_log.json"
    log = json.loads(log_f.read_text()) if log_f.exists() else {}
    if not log.get("completed"):
        print("WARNING: the run is not complete - results below are partial.\n")
    d = collect(cfg)
    d.to_csv(root / "per_image.csv", index=False)
    have = d[d["report"]]
    s = have[have["n_cells"] >= ft["min_cells"]].copy()
    failed = d[~d["image_id"].isin(s["image_id"])]
    pd.set_option("display.width", 250)
    print(f"Phase 7 - {len(d)} test images; analysed {len(s)}; failures {len(failed)} "
          f"(no report {int((~d['report']).sum())}, < {ft['min_cells']} cells "
          f"{int((have['n_cells'] < ft['min_cells']).sum())})" + (f": {', '.join(failed['image_id'])}" if len(failed) else ""))

    tab = agreement_table(s, cfg)
    tab.to_csv(root / "agreement.csv")
    fmt = lambda x: "-" if x is None or (isinstance(x, float) and np.isnan(x)) else (
        f"[{x[0]:.1f}, {x[1]:.1f}]" if isinstance(x, list) else f"{x:.2f}" if isinstance(x, float) else str(x))
    print("\nAgreement with Konan on the TEST set (error = 100 x (ours - Konan) / Konan):")
    print(tab.map(fmt).to_string())

    print("\nScope targets:")
    for lab, row in tab.iterrows():
        if row["target %"] is None:
            continue
        print(f"  {lab:10s} MAPE {row['MAPE %']:.2f} % (95 % CI {fmt(row['MAPE 95% CI'])}) vs target {row['target %']:g} % "
              f"-> {'MET' if row['target met (MAPE <= target)'] else 'NOT MET'}; within target {row['within target %']:.1f} % "
              f"of images (95 % CI {fmt(row['within 95% CI'])})"
              + (f", realistic ceiling ~{row['ceiling %']:g} %" if row["ceiling %"] else ""))
    comp = s["cv_compactness_pct"]
    print(f"  compactness CV <= {t['compactness_cv']:g} % (our definition): {100 * (comp <= t['compactness_cv']).mean():.1f} % of images")
    print("  not judgeable on test (no reference on test images):")
    for k, v in ft["validation_only"].items():
        print(f"    {k}: {v['value']} on {v['where']} (target {t[k]})")

    val = validation_table(cfg)
    gap = None
    if val is not None:
        rows = []
        for lab in tab.index:
            if lab in val.index:
                rows.append({"biomarker": lab, "MAPE val": float(val.loc[lab, "MAPE %"]), "MAPE test": tab.loc[lab, "MAPE %"],
                             "within val %": 100 * float(val.loc[lab, "within target"]) if pd.notna(val.loc[lab, "within target"]) else np.nan,
                             "within test %": tab.loc[lab, "within target %"],
                             "rho val": float(val.loc[lab, "rho"]), "rho test": tab.loc[lab, "rho"]})
        gap = pd.DataFrame(rows).set_index("biomarker")
        gap["MAPE gap (test - val)"] = gap["MAPE test"] - gap["MAPE val"]
        print("\nTest vs validation (Phase 6, inside ROI):")
        print(gap.astype(float).round(2).to_string())

    print("\nSecondary (descriptive):")
    flags = s["flags"].fillna("").str.split(",").explode()
    flags = flags[flags != ""].value_counts()
    print(f"  reliable {int(s['reliable'].sum())} / {len(s)}; flags: " + (", ".join(f"{k} {v}" for k, v in flags.items()) or "-"))
    tot = s[["green", "yellow", "red"]].sum()
    if tot.sum() > 0:
        print("  cells: " + ", ".join(f"{k} {100 * v / tot.sum():.1f} %" for k, v in tot.items()))
    cover = {}
    for k, (_, ref) in CI_KEYS.items():
        ok = s[f"{k}_lo"].notna()
        inside = (s.loc[ok, f"{k}_lo"] <= s.loc[ok, f"konan_{ref}"]) & (s.loc[ok, f"konan_{ref}"] <= s.loc[ok, f"{k}_hi"])
        cover[ref] = round(100 * float(inside.mean()), 1) if ok.any() else None
    print(f"  Konan inside our 95 % CI (sampling only; Konan measures another patch): {cover}")
    s["ecd_err_pct"] = 100 * (s["ecd_cells_per_mm2"] - s["konan_ecd"]) / s["konan_ecd"]
    band = s.groupby("ecd_band").agg(n=("ecd_err_pct", "size"), ecd_bias=("ecd_err_pct", "mean"),
                                     ecd_mape=("ecd_err_pct", lambda x: x.abs().mean()))
    print("  by ECD band:\n" + band.round(2).to_string())
    worst = s.reindex(s["ecd_err_pct"].abs().sort_values(ascending=False).index).head(6)
    print("  largest ECD errors:\n" + worst[["image_id", "ecd_band", "konan_ecd", "ecd_cells_per_mm2", "ecd_err_pct",
                                             "n_cells", "flags"]].round(1).to_string(index=False))

    decision = {"run": log, "frozen": json.loads((root / "freeze.json").read_text()) if (root / "freeze.json").exists() else None,
                "images": len(d), "analysed": len(s), "failures": failed["image_id"].tolist(),
                "targets": {lab: {"mape": row["MAPE %"], "mape_ci95": row["MAPE 95% CI"], "target": row["target %"],
                                  "met": row["target met (MAPE <= target)"], "within_pct": row["within target %"],
                                  "within_ci95": row["within 95% CI"], "rho": row["rho"], "bias_pct": row["bias %"]}
                            for lab, row in tab.iterrows() if row["target %"] is not None},
                "compactness_cv_within_pct": round(100 * float((comp <= t["compactness_cv"]).mean()), 1),
                "validation_only": ft["validation_only"], "ci_coverage_of_konan_pct": cover,
                "test_vs_val": None if gap is None else gap.round(3).to_dict("index")}
    (root / "decision.json").write_text(json.dumps(decision, indent=2, default=lambda x: x.item() if hasattr(x, "item") else str(x)))
    figures(cfg, s)
    print(f"\nResults: {root}")


def figures(cfg: dict, s: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(16, 9.5))
    for j, (ours, ref, lab, unit) in enumerate((("ecd_cells_per_mm2", "konan_ecd", "ECD", "cells/mm²"),
                                                ("cv_pct", "konan_cv", "CV", "%"), ("hex_pct", "konan_hex", "HEX", "%"))):
        o, r = s[ours].astype(float), s[ref].astype(float)
        ok = o.notna() & r.notna()
        o, r = o[ok], r[ok]
        ax = axes[0, j]
        ax.scatter(r, o, s=10, alpha=0.6)
        lim = [min(o.min(), r.min()), max(o.max(), r.max())]
        ax.plot(lim, lim, "k--", lw=0.8)
        ax.set_xlabel(f"Konan {lab} ({unit})")
        ax.set_ylabel(f"ours {lab} ({unit})")
        ax.set_title(f"{lab}: rho {spearmanr(o, r).correlation:.3f}, n {len(o)}")
        ax = axes[1, j]
        m, dlt = (o + r) / 2, o - r
        sd = dlt.std(ddof=1)
        ax.scatter(m, dlt, s=10, alpha=0.6)
        for y, ls in ((dlt.mean(), "-"), (dlt.mean() - 1.96 * sd, "--"), (dlt.mean() + 1.96 * sd, "--")):
            ax.axhline(y, color="r", ls=ls, lw=0.8)
        ax.set_xlabel(f"mean of ours and Konan ({unit})")
        ax.set_ylabel(f"ours - Konan ({unit})")
        ax.set_title(f"Bland-Altman {lab}: {dlt.mean():.1f} [{dlt.mean() - 1.96 * sd:.1f}, {dlt.mean() + 1.96 * sd:.1f}]")
    fig.suptitle("Phase 7 - frozen pipeline on the test set vs Konan")
    fig.tight_layout()
    d = out_root(cfg) / "figures"
    d.mkdir(exist_ok=True)
    fig.savefig(d / "agreement.png", dpi=80)
    plt.close(fig)


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Phase 7: frozen pipeline on the test set.")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--compare", action="store_true")
    args = ap.parse_args()
    if args.freeze:
        freeze(cfg)
    elif args.run:
        run(cfg)
    elif args.compare:
        compare(cfg)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
