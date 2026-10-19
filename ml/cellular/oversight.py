"""
XAI step 4 — expert oversight: the expert corrects a pipeline result without re-running any model; every review
is logged and the original result is never changed. Rules: config.yaml -> xai.oversight.

  python -m oversight <out>/<id>.json --edits <edits.json> [--image <image>]   apply edits, recompute, log
  python -m oversight --simulate                                               evaluation on the 40 crops (CPU)

The pipeline saves what a review needs next to each report: <id>_mask.png (segmentation: 0 interior / 1 wall /
2 unlit), <id>_roi.png (1 = lit, 2 = ROI, 3 = both), <id>_review_queue.png / .csv (RED cells first, then YELLOW,
least confident first; every cell numbered).

Edits file (always the complete set of changes relative to the pipeline result; a new file replaces the reviewed
result, the log keeps every version):
  {"reviewer": "name",
   "edits": [{"action": "exclude_cells", "cell_ids": [605, 761], "reason": "on a bubble"},
             {"action": "include_cells", "cell_ids": [761]},
             {"action": "remove_area", "polygon": [[x, y], ...], "reason": "blurred"},
             {"action": "add_area", "polygon": [[x, y], ...]}]}
Area edits change the ROI; the cells are re-extracted from the saved mask with the pipeline's rules (cells cut by
the new ROI border are no longer complete; added area counts only where the image is lit), then the excluded cells
are removed. Cell ids are the instance labels of the saved mask, so they do not change between reviews.
Outputs: <id>_reviewed.json (report + "oversight": reviewer, edits, numbers before -> after),
<id>_reviewed_cells.csv, <id>_reviewed_overlay.png (with --image), <id>_edits.jsonl (append-only log).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from biomarkers.compute import report
from config import load_config
from data_prep.check_annotations import IGNORE
from extraction.cells import ExtractionParams, extract_cells, instances_from_mask
from xai.reliability import LEVEL_RGB, bootstrap_ci

ACTIONS = {"exclude_cells": "cell_ids", "include_cells": "cell_ids", "remove_area": "polygon",
           "add_area": "polygon"}
BIOMARKERS = (("n_cells", "n_cells"), ("ecd", "ecd_cells_per_mm2"), ("cv", "cv_pct"), ("hex", "hex_pct"))


# ---------------------------------------------------------------- review queue ----------
def review_queue(cells: pd.DataFrame, levels=("red", "yellow")) -> pd.DataFrame:
    """Cells to check first: RED, then YELLOW; least confident first within a level."""
    if "level" not in cells:
        return cells.iloc[:0]
    q = cells[cells["level"].isin(levels)].copy()
    q["_rank"] = q["level"].map({lev: i for i, lev in enumerate(levels)})
    conf = q["confidence"] if "confidence" in q else pd.Series(np.nan, index=q.index)
    q["_conf"] = conf.fillna(-1)
    q = q.sort_values(["_rank", "_conf", "cell_id"]).drop(columns=["_rank", "_conf"])
    cols = [c for c in ("cell_id", "level", "confidence", "area_px", "sides", "compactness", "cx", "cy",
                        "flag_small", "flag_large") if c in q]
    return q[cols].reset_index(drop=True)


def review_queue_image(img: np.ndarray, complete: np.ndarray, cells: pd.DataFrame,
                       levels=("red", "yellow")) -> np.ndarray:
    """RGB: every measured cell outlined and numbered (small grey); queue cells tinted by level, numbered large."""
    from scipy import ndimage as ndi
    view = np.dstack([img] * 3).astype(np.float32)
    queue = set(review_queue(cells, levels)["cell_id"]) if "level" in cells else set()
    lev = cells.set_index("cell_id")["level"] if "level" in cells else pd.Series(dtype=object)
    for cid in queue:
        m = complete == cid
        view[m] = 0.55 * view[m] + 0.45 * np.array(LEVEL_RGB[lev[cid]], np.float32)
    view[complete != ndi.grey_erosion(complete, size=3)] = 0
    view = view.clip(0, 255).astype(np.uint8)
    for r in cells.itertuples(index=False):
        big = r.cell_id in queue
        text, scale = str(int(r.cell_id)), (0.42 if big else 0.28)
        (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
        org = (int(r.cx - w / 2), int(r.cy + h / 2))
        if big:
            cv2.putText(view, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 3)
        cv2.putText(view, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0) if big else (70, 70, 70), 1)
    return view


# ---------------------------------------------------------------- edits ----------
def validate(edits: list[dict]) -> None:
    for i, e in enumerate(edits):
        key = ACTIONS.get(e.get("action"))
        if key is None:
            raise ValueError(f"edit {i}: unknown action {e.get('action')!r} (allowed: {sorted(ACTIONS)})")
        if key not in e:
            raise ValueError(f"edit {i} ({e['action']}): missing {key!r}")
        if key == "polygon" and len(e["polygon"]) < 3:
            raise ValueError(f"edit {i} ({e['action']}): a polygon needs at least 3 points")


def polygon_mask(poly, shape: tuple[int, int]) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(np.asarray(poly, float)).astype(np.int32)], 1)
    return m.astype(bool)


def edited_roi(roi: np.ndarray, edits: list[dict]) -> np.ndarray:
    """Area edits in order (a later edit wins where they overlap)."""
    r = roi.copy()
    for e in edits:
        if e["action"] == "remove_area":
            r &= ~polygon_mask(e["polygon"], r.shape)
        elif e["action"] == "add_area":
            r |= polygon_mask(e["polygon"], r.shape)
    return r


def excluded(edits: list[dict]) -> set[int]:
    out: set[int] = set()
    for e in edits:
        if e["action"] == "exclude_cells":
            out |= {int(c) for c in e["cell_ids"]}
        elif e["action"] == "include_cells":
            out -= {int(c) for c in e["cell_ids"]}
    return out


def apply_edits(mask: np.ndarray, roi: np.ndarray, edits: list[dict], params: ExtractionParams,
                previous: pd.DataFrame | None = None) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """-> (cells, complete-cell labels, edited ROI). previous = the pipeline's cell table: confidence / level are
    carried over by cell id (cells that become complete only after an edit have none)."""
    validate(edits)
    roi_new = edited_roi(roi, edits)
    cells, _, complete = extract_cells(instances_from_mask(mask), (mask != IGNORE) & roi_new, params)
    drop = excluded(edits)
    if drop:
        cells = cells[~cells["cell_id"].isin(drop)].reset_index(drop=True)
        complete = np.where(np.isin(complete, list(drop)), 0, complete)
    if previous is not None:
        extra = [c for c in ("confidence", "level") if c in previous]
        if extra:
            cells = cells.merge(previous[["cell_id", *extra]], on="cell_id", how="left")
    return cells, complete, roi_new


def headline(rep: dict) -> dict:
    bm = rep["biomarkers"]
    return {k: bm[key] for k, key in BIOMARKERS}


def reviewed_report(original: dict, cells: pd.DataFrame, roi_old: np.ndarray, roi: np.ndarray, lit: np.ndarray,
                    edits: list[dict], reviewer: str, cfg: dict) -> dict:
    """The pipeline report recomputed on the reviewed cells, with the 'oversight' block (before -> after)."""
    from pipeline import quality_flags
    xb = cfg["xai"]["biomarkers"]
    um = original["um_per_px"]
    rep = report(original["image_id"], cells, um, original["segmentation_run"])
    share = float(roi.sum() / max(lit.sum(), 1))
    flags = quality_flags(rep["biomarkers"], share, cfg["pipeline"])
    rep["roi"] = {**original["roi"], "share_of_image": round(float(roi.mean()), 4),
                  "share_of_lit_area": round(share, 4),
                  "edited_by_expert": any(e["action"].endswith("_area") for e in edits)}
    rep["quality_flags"] = flags
    rep["reliable"] = not any(f["level"] == "error" for f in flags)
    ci = bootstrap_ci(cells, um, xb["block_px"], xb["n_boot"], xb["seed"])
    rep["uncertainty"] = {**(original.get("uncertainty") or {}),
                          **{f"{k}_ci95": [ci[k]["lo"], ci[k]["hi"]] for k in ("ecd", "cv", "hex")}}
    if "level" in cells:
        n = cells["level"].value_counts()
        rep["reliability"] = {**(original.get("reliability") or {}),
                              **{lev: int(n.get(lev, 0)) for lev in ("green", "yellow", "red")},
                              "not_scored": int(cells["level"].isna().sum())}
    before, after = headline(original), headline(rep)
    rep["oversight"] = {
        "reviewer": reviewer, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "n_edits": len(edits), "edits": edits,
        "excluded_cells": sorted(excluded(edits)),
        "area_removed_px": int((roi_old & ~roi).sum()), "area_added_px": int((roi & ~roi_old).sum()),
        "before": before, "after": after,
        "note": "original pipeline result unchanged in <id>.json; numbers recomputed from the saved segmentation"}
    return rep


def append_log(path: Path, rep: dict) -> None:
    o = rep["oversight"]
    line = {"time": o["time"], "image_id": rep["image_id"], "reviewer": o["reviewer"], "edits": o["edits"],
            "before": o["before"], "after": o["after"]}
    with open(path, "a", encoding="utf-8") as f:                    # append-only
        f.write(json.dumps(line) + "\n")


def load_saved(report_path: Path) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    original = json.loads(report_path.read_text())
    d, iid = report_path.parent, original["image_id"]
    missing = [p for p in (d / f"{iid}_mask.png", d / f"{iid}_roi.png") if not p.exists()]
    if missing:
        raise SystemExit(f"missing {', '.join(map(str, missing))} - re-run the pipeline on this image")
    mask = cv2.imread(str(d / f"{iid}_mask.png"), cv2.IMREAD_UNCHANGED)
    code = cv2.imread(str(d / f"{iid}_roi.png"), cv2.IMREAD_UNCHANGED)
    return original, mask, (code & 2) > 0, (code & 1) > 0, pd.read_csv(d / f"{iid}_cells.csv")


def review(report_path: str | Path, edits_path: str | Path, image: str | Path | None = None,
           cfg: dict | None = None) -> dict:
    from pipeline import overlay
    cfg = cfg or load_config()
    report_path = Path(report_path)
    original, mask, roi, lit, previous = load_saved(report_path)
    spec = json.loads(Path(edits_path).read_text())
    edits, reviewer = spec.get("edits", []), spec.get("reviewer", "unknown")
    cells, complete, roi_new = apply_edits(mask, roi, edits, ExtractionParams.from_config(cfg), previous)
    rep = reviewed_report(original, cells, roi, roi_new, lit, edits, reviewer, cfg)
    d, iid = report_path.parent, original["image_id"]
    (d / f"{iid}_reviewed.json").write_text(json.dumps(rep, indent=2, allow_nan=False))
    cells.to_csv(d / f"{iid}_reviewed_cells.csv", index=False)
    if image is not None:
        img = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
        view = overlay(img, roi_new, complete, cells, rep["biomarkers"], rep["quality_flags"])
        cv2.putText(view, f"REVIEWED by {reviewer}: {len(edits)} edits, {len(excluded(edits))} cells excluded",
                    (10, view.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imwrite(str(d / f"{iid}_reviewed_overlay.png"), view)
    append_log(d / f"{iid}_edits.jsonl", rep)
    return rep


# ---------------------------------------------------------------- evaluation ----------
def policy_errors(cells: pd.DataFrame, refs: pd.DataFrame, policies: dict, um_per_px: float) -> pd.DataFrame:
    """Per crop and policy: biomarkers of the kept cells and their error vs the manual value
    (ECD in %, CV / HEX in points). policies: name -> function(cells of one crop) -> bool mask of cells to drop."""
    from xai.biomarker_explain import point_values
    ref = refs.pivot(index="crop_id", columns="biomarker", values="reference")
    rows = []
    for crop, c in cells.groupby("crop_id"):
        for name, drop in policies.items():
            d = drop(c)
            v = point_values(c[~d], um_per_px)
            row = {"crop_id": crop, "policy": name, "cells": int((~d).sum()), "excluded": int(d.sum())}
            for b in ("ecd", "cv", "hex"):
                t = ref.loc[crop, b] if crop in ref.index else np.nan
                if v[b] is None or pd.isna(t):
                    err = np.nan
                else:
                    err = 100 * (v[b] - t) / t if b == "ecd" else v[b] - t
                row[b], row[f"{b}_err"] = v[b], err
            rows.append(row)
    return pd.DataFrame(rows)


def holm(p: dict) -> dict:
    keys = sorted((k for k in p if np.isfinite(p[k])), key=lambda k: p[k])
    out, prev = {k: float("nan") for k in p}, 0.0
    for i, k in enumerate(keys):
        prev = max(prev, min(1.0, (len(keys) - i) * p[k]))
        out[k] = prev
    return out


def simulate(cfg: dict) -> None:
    from scipy.stats import wilcoxon

    xo, um = cfg["xai"]["oversight"], cfg["scale"]["um_per_px"]
    src = cfg["paths"]["outputs_dir"] / "xai" / "biomarkers"
    if not (src / "crop_cells.csv").exists():
        raise SystemExit(f"{src / 'crop_cells.csv'} missing - run python -m xai.biomarker_explain --crops first")
    cells = pd.read_csv(src / "crop_cells.csv")
    refs = pd.read_csv(src / "crop_ci.csv").query("bootstrap == 'block'")[["crop_id", "biomarker", "reference"]]
    queue = set(xo["queue_levels"])
    policies = {"none": lambda c: np.zeros(len(c), bool),
                "red": lambda c: (c["level"] == "red").to_numpy(),
                "flagged": lambda c: c["level"].isin(queue).to_numpy(),
                "oracle": lambda c: c["wrong"].astype(bool).to_numpy()}
    t = policy_errors(cells, refs, policies, um)
    out = cfg["paths"]["outputs_dir"] / "xai" / "oversight"
    out.mkdir(parents=True, exist_ok=True)
    t.to_csv(out / "simulation.csv", index=False)

    base = t[t["policy"] == "none"].set_index("crop_id")
    summary, pvals = {"crops": int(base.shape[0]), "policies": {}}, {}
    for name in policies:
        cur = t[t["policy"] == name].set_index("crop_id").loc[base.index]
        s = {"excluded_cells_median": float(cur["excluded"].median()),
             "excluded_share_pct": round(100 * cur["excluded"].sum() / base["cells"].sum(), 1)}
        for b in ("ecd", "cv", "hex"):
            a0, a1 = base[f"{b}_err"].abs(), cur[f"{b}_err"].abs()
            ok = a0.notna() & a1.notna()
            diff = (a1 - a0)[ok]
            p = float(wilcoxon(diff).pvalue) if (diff != 0).any() else float("nan")
            s[b] = {"median_abs_err": round(float(a1[ok].median()), 2),
                    "median_signed_err": round(float(cur[f"{b}_err"][ok].median()), 2),
                    "better_crops": int((diff < 0).sum()), "worse_crops": int((diff > 0).sum()),
                    "p_vs_none": p}
            if name == xo["primary_policy"]:
                pvals[b] = p
        summary["policies"][name] = s
    adj = holm(pvals)
    verdict = {}
    for b in ("ecd", "cv", "hex"):
        s = summary["policies"][xo["primary_policy"]][b]
        better = s["median_abs_err"] < summary["policies"]["none"][b]["median_abs_err"]
        verdict[b] = ("no difference" if not adj[b] < xo["alpha"] else "helps" if better else "hurts")
        s["p_holm"] = adj[b]
    summary["primary"] = {"policy": xo["primary_policy"], "verdict": verdict}
    (out / "decision.json").write_text(json.dumps(summary, indent=2))

    unit = {"ecd": "% of manual", "cv": "points", "hex": "points"}
    print(f"Simulated reviewer on {summary['crops']} crops (out-of-fold; errors vs the manual masks)\n")
    rows = []
    for name, s in summary["policies"].items():
        rows.append({"policy": name, "cells excluded (median / crop)": s["excluded_cells_median"],
                     "share excluded %": s["excluded_share_pct"],
                     **{f"|{b.upper()} err| ({unit[b]})": s[b]["median_abs_err"] for b in ("ecd", "cv", "hex")},
                     **{f"{b.upper()} err signed": s[b]["median_signed_err"] for b in ("ecd", "cv", "hex")}})
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).set_index("policy").to_string())
    print(f"\nPRIMARY ({xo['primary_policy']} vs none, paired Wilcoxon of |error|, Holm over 3):")
    for b in ("ecd", "cv", "hex"):
        s = summary["policies"][xo["primary_policy"]][b]
        print(f"  {b.upper()}: better in {s['better_crops']}, worse in {s['worse_crops']} crops; "
              f"p = {s['p_vs_none']:.2g}, Holm p = {s['p_holm']:.2g} -> {verdict[b]}")
    print(f"\nResults: {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="XAI step 4: expert oversight (edit, recompute, log).")
    ap.add_argument("report", nargs="?", help="pipeline report <id>.json")
    ap.add_argument("--edits", help="edits JSON")
    ap.add_argument("--image", help="the original image (for the reviewed overlay)")
    ap.add_argument("--simulate", action="store_true", help="simulated reviewer on the 40 crops")
    args = ap.parse_args()
    cfg = load_config()
    if args.simulate:
        simulate(cfg)
        return
    if not (args.report and args.edits):
        ap.print_help()
        return
    rep = review(args.report, args.edits, args.image, cfg)
    o = rep["oversight"]
    print(f"{rep['image_id']} reviewed by {o['reviewer']}: {o['n_edits']} edits, {len(o['excluded_cells'])} cells "
          f"excluded, area -{o['area_removed_px']} / +{o['area_added_px']} px")
    for k, _ in BIOMARKERS:
        print(f"  {k}: {o['before'][k]} -> {o['after'][k]}")
    print("  flags: " + (", ".join(f["code"] for f in rep["quality_flags"]) or "-"))


if __name__ == "__main__":
    main()
