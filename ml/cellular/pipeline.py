"""
End-to-end pipeline for Component 3 (Corneal Cellular Intelligence Platform).

One specular microscopy image in, the cellular analysis out:

    image --3.1--> ROI mask + quality score           (roi/, Phase 6: EfficientNet-B0)
          --3.2--> cell instances                     (segmentation/, Phase 2: StarDist, flat input)
          --3.3--> complete cells + per-cell table    (extraction/, Phase 3)
          --3.4--> biomarker report                   (biomarkers/, Phases 4-5; scale.um_per_px)

The stages call exactly the functions used for the reported results (Phases 2-6),
so a pipeline run reproduces them (``--check``). Nothing is fitted here; quality
flags (config ``pipeline:``) are warnings for the reviewer and never change a number.

Outputs per image (``out_dir``): <image_id>.json (report), <image_id>_cells.csv,
<image_id>_overlay.png (ROI outlined, outside dimmed, measured cells coloured by side count),
and the XAI step 2 explanations (config xai.biomarkers; they never change a number):
<image_id>_reliability.png (cells green / yellow / red), <image_id>_cv_evidence.png (cells coloured
by area vs the median, most extreme cells outlined); report keys "uncertainty" (95 % CIs),
"reliability" (level counts, confidence) and "evidence"; cells CSV columns confidence, level.
For expert oversight (XAI step 4, oversight.py; never changes this result): <image_id>_mask.png (segmentation,
0 interior / 1 wall / 2 unlit), <image_id>_roi.png (1 = lit, 2 = ROI, 3 = both), <image_id>_review_queue.png / .csv
(RED then YELLOW cells first, every cell numbered).

Usage (from ml/cellular/; GPU recommended, the models are on Drive):
    python -m pipeline <image> [<image> ...] [--out DIR]
    python -m pipeline --check 10            # same numbers as the Phase 6 batch run?

    from pipeline import CellularPipeline
    result = CellularPipeline().analyse("image.jpg")
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd

from biomarkers.compute import report
from config import load_config
from data_prep.check_annotations import IGNORE
from extraction.cells import ExtractionParams, extract_cells, instances_from_mask, overlay_sides
from oversight import review_queue, review_queue_image
from roi.tiles import image_planes
from xai.reliability import (area_overlay, bootstrap_ci, cell_confidence, reliability, reliability_overlay,
                             variance_share)


def quality_flags(bm: dict, roi_share_of_lit: float, rules: dict) -> list[dict]:
    """Warnings for the reviewer (level 'error' = biomarkers not reliable, 'warning' = check)."""
    flags = []
    n = bm["n_cells"]
    if n < rules["min_cells"]:
        flags.append({"level": "error", "code": "too_few_cells",
                      "message": f"only {n} complete cells (< {rules['min_cells']}): biomarkers not reliable"})
    if bm["n_cells_with_sides"] < rules["min_cells_with_sides"]:
        flags.append({"level": "warning", "code": "few_side_counts",
                      "message": f"HEX from only {bm['n_cells_with_sides']} cells "
                                 f"(< {rules['min_cells_with_sides']}): less reliable"})
    if roi_share_of_lit < rules["min_roi_share_of_lit"]:
        flags.append({"level": "warning", "code": "small_roi",
                      "message": f"ROI keeps only {100 * roi_share_of_lit:.0f} % of the lit area: "
                                 "image largely of poor quality"})
    if n and bm["n_flagged"] / n > rules["max_flagged_share"]:
        flags.append({"level": "warning", "code": "many_flagged_cells",
                      "message": f"{bm['n_flagged']} implausibly small / large cells "
                                 f"({100 * bm['n_flagged'] / n:.1f} %): check the segmentation"})
    return flags


def overlay(img: np.ndarray, roi: np.ndarray, complete: np.ndarray, cells: pd.DataFrame,
            bm: dict, flags: list[dict]) -> np.ndarray:
    """What was measured: outside the ROI dimmed, ROI outlined (cyan), measured cells coloured by
    side count (<=4 purple, 5 orange, 6 green, 7 blue, >=8 red, unknown grey), summary on top."""
    view = overlay_sides(img, complete, cells).astype(np.float32)
    view[~roi] *= 0.45
    view = view.astype(np.uint8)
    contours, _ = cv2.findContours(roi.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(view, contours, -1, (255, 255, 0), 2)
    fmt = lambda v, d=0: "-" if v is None else f"{v:.{d}f}"
    lines = [f"ECD {fmt(bm['ecd_cells_per_mm2'])} cells/mm2   CV {fmt(bm['cv_pct'])} %   "
             f"HEX {fmt(bm['hex_pct'])} %   {bm['n_cells']} cells",
             "cyan = ROI; sides: <=4 purple, 5 orange, 6 green, 7 blue, >=8 red, unknown grey"]
    lines += [f"{f['level'].upper()}: {f['message']}" for f in flags]
    for k, text in enumerate(lines):
        colour = (0, 0, 255) if text.startswith("ERROR") else (0, 255, 255)
        cv2.putText(view, text, (10, 30 + 30 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2)
    return view


class CellularPipeline:
    """Loads the models once; ``analyse`` runs all stages on one image."""

    def __init__(self, cfg: dict | None = None):
        from roi.run import RoiScorer
        from segmentation.infer_full import make_predictor

        self.cfg = cfg or load_config()
        self.rules = self.cfg["pipeline"]
        self.run = self.rules["run"]
        self.um_per_px = self.cfg["scale"]["um_per_px"]
        self.params = ExtractionParams.from_config(self.cfg)
        # mask: 0 interior / 1 wall / 2 unlit (+ per-pixel StarDist object probability for the XAI)
        self.segment = make_predictor(self.cfg, self.run, "lit", with_prob=self.run.startswith("stardist"))
        self.prob_thresh = getattr(self.segment, "prob_thresh", None)
        self.roi = RoiScorer(self.cfg)

    def analyse(self, image: str | Path | np.ndarray, image_id: str | None = None) -> dict[str, Any]:
        t0 = time.time()
        if isinstance(image, (str, Path)):
            image_id = image_id or Path(image).stem
            img = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise FileNotFoundError(image)
        else:
            img = image
        image_id = image_id or "image"

        planes = image_planes(self.cfg, img)                         # 3.1 ROI
        roi, prob = self.roi(planes)
        lit = planes[2] > 0
        out = self.segment(img)                                      # 3.2 segmentation
        mask, cell_prob = out if isinstance(out, tuple) else (out, None)
        cells, _, complete = extract_cells(instances_from_mask(mask),  # 3.3 complete cells
                                           (mask != IGNORE) & roi, self.params)
        rep = report(image_id, cells, self.um_per_px, self.run)       # 3.4 biomarkers
        roi_share_of_lit = float(roi.sum() / max(lit.sum(), 1))
        flags = quality_flags(rep["biomarkers"], roi_share_of_lit, self.rules)
        rep.update({
            "roi": {"method": self.roi.method, "share_of_image": round(float(roi.mean()), 4),
                    "share_of_lit_area": round(roi_share_of_lit, 4),
                    "quality_score": round(float(prob[lit].mean()), 4) if lit.any() else 0.0},
            "quality_flags": flags,
            "reliable": not any(f["level"] == "error" for f in flags)})
        cells, explain = self.explain(img, cells, complete, cell_prob, rep)
        levels = self.cfg["xai"]["oversight"]["queue_levels"]
        explain["review_queue"] = review_queue_image(img, complete, cells, levels)
        rep["seconds"] = round(time.time() - t0, 2)
        return {"report": rep, "cells": cells,
                "overlay": overlay(img, roi, complete, cells, rep["biomarkers"], flags),
                "explain": explain, "roi": roi, "mask": mask, "lit": lit,
                "queue": review_queue(cells, levels)}

    def explain(self, img: np.ndarray, cells: pd.DataFrame, complete: np.ndarray, prob: np.ndarray | None,
                rep: dict) -> tuple[pd.DataFrame, dict]:
        """XAI step 2 (adds to the report, never changes a number): 95 % CIs, the cells driving CV,
        per-cell reliability. Returns (cells with confidence / level, {name: RGB image})."""
        xb = self.cfg["xai"]["biomarkers"]
        num = lambda x, d=3: round(float(x), d) if x is not None and np.isfinite(x) else None
        ci = bootstrap_ci(cells, self.um_per_px, xb["block_px"], xb["n_boot"], xb["seed"])
        rep["uncertainty"] = {
            "method": f"95 % CI, bootstrap over {xb['block_px']} px blocks of cells ({xb['n_boot']} resamples); "
                      "covers sampling, not segmentation error",
            **{f"{k}_ci95": [ci[k]["lo"], ci[k]["hi"]] for k in ("ecd", "cv", "hex")}}
        top, share = variance_share(cells, xb["top_variance_share"])
        rep["evidence"] = {"most_extreme_cells_pct": 100 * xb["top_variance_share"],
                           "their_share_of_area_variance_pct": num(100 * share, 1)}
        explain = {"cv_evidence": area_overlay(img, complete, cells, top)}
        if prob is None or self.prob_thresh is None or cells.empty:
            rep["reliability"] = None
            return cells, explain
        rel = reliability(cells, cell_confidence(complete, prob, cells["cell_id"]), self.prob_thresh, xb)
        n = rel["level"].value_counts()
        rep["reliability"] = {
            "rule": "red = implausible size / shape; yellow = low StarDist confidence; green = otherwise",
            **{lev: int(n.get(lev, 0)) for lev in ("green", "yellow", "red")},
            "median_confidence": num(rel["confidence"].median())}
        explain["reliability"] = reliability_overlay(img, complete, rel)
        cells = cells.merge(rel[["confidence", "level"]], left_on="cell_id", right_index=True, how="left")
        return cells, explain

    def save(self, result: dict, out_dir: str | Path) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        iid = result["report"]["image_id"]
        (out / f"{iid}.json").write_text(json.dumps(result["report"], indent=2, allow_nan=False))
        result["cells"].to_csv(out / f"{iid}_cells.csv", index=False)
        cv2.imwrite(str(out / f"{iid}_overlay.png"), result["overlay"])
        for name, view in result.get("explain", {}).items():               # RGB -> BGR for OpenCV
            cv2.imwrite(str(out / f"{iid}_{name}.png"), np.ascontiguousarray(view[..., ::-1]))
        if "mask" in result and "roi" in result:                           # for expert oversight (lossless)
            cv2.imwrite(str(out / f"{iid}_mask.png"), result["mask"].astype(np.uint8))
            lit = result.get("lit", np.ones_like(result["roi"], bool))
            cv2.imwrite(str(out / f"{iid}_roi.png"), (lit.astype(np.uint8) + 2 * result["roi"].astype(np.uint8)))
        if "queue" in result:
            result["queue"].to_csv(out / f"{iid}_review_queue.csv", index=False)
        return out / f"{iid}.json"


def run(image_path: str | Path) -> dict[str, Any]:
    """Analyse one specular microscopy image; returns the biomarker report (dict)."""
    return CellularPipeline().analyse(image_path)["report"]


def check(cfg: dict, n: int, out_dir: Path) -> None:
    """Reproducibility: the pipeline vs the Phase 6 batch results (biomarkers inside the ROI)."""
    from segmentation.infer_full import images_of

    ref_csv = cfg["paths"]["outputs_dir"] / "biomarkers" / "val" / f"{cfg['pipeline']['run']}_roi" / "biomarkers.csv"
    if not ref_csv.exists():
        raise SystemExit(f"No Phase 6 results ({ref_csv}) - run notebooks/roi_6.ipynb first.")
    ref = pd.read_csv(ref_csv).set_index("image_id")
    images = images_of(cfg, "val").head(n)
    pipe = CellularPipeline(cfg)
    rows = []
    for r in images.itertuples(index=False):
        res = pipe.analyse(cfg["paths"]["images_dir"] / r.image_file, r.image_id)
        pipe.save(res, out_dir)
        bm = res["report"]["biomarkers"]
        row = {"image_id": r.image_id, "seconds": res["report"]["seconds"],
               "flags": ", ".join(f["code"] for f in res["report"]["quality_flags"]) or "-"}
        for k in ("n_cells", "ecd_cells_per_mm2", "cv_pct", "hex_pct"):
            row[f"{k} pipeline"], row[f"{k} Phase 6"] = bm[k], ref.loc[r.image_id, k]
        rows.append(row)
    t = pd.DataFrame(rows).set_index("image_id")
    pd.set_option("display.width", 250)
    print(t.round(2).to_string())
    same = all(np.isclose(t[f"{k} pipeline"], t[f"{k} Phase 6"], rtol=1e-3, equal_nan=True).all()
               for k in ("n_cells", "ecd_cells_per_mm2", "cv_pct", "hex_pct"))
    print(f"\nSame as the Phase 6 batch run (0.1 % tolerance): {'YES' if same else 'NO - see the table'}")
    print(f"Median time per image: {t['seconds'].median():.1f} s.  Reports and overlays: {out_dir}")


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Component 3: analyse specular microscopy images.")
    ap.add_argument("images", nargs="*", help="image files")
    ap.add_argument("--out", help="output folder (default <outputs_dir>/pipeline)")
    ap.add_argument("--check", type=int, metavar="N", help="reproduce the Phase 6 results on N val images")
    args = ap.parse_args()
    out = Path(args.out) if args.out else cfg["paths"]["outputs_dir"] / "pipeline"
    if args.check:
        check(cfg, args.check, out / "check")
        return
    if not args.images:
        ap.print_help()
        return
    pipe = CellularPipeline(cfg)
    for f in args.images:
        res = pipe.analyse(f)
        path = pipe.save(res, out)
        bm, rep = res["report"]["biomarkers"], res["report"]
        print(f"{rep['image_id']}: ECD {bm['ecd_cells_per_mm2']}, CV {bm['cv_pct']}, HEX {bm['hex_pct']}, "
              f"{bm['n_cells']} cells, ROI {100 * rep['roi']['share_of_lit_area']:.0f} % of lit area, "
              f"{'reliable' if rep['reliable'] else 'NOT reliable'}"
              + "".join(f"\n  {f['level']}: {f['message']}" for f in rep["quality_flags"])
              + "\n  95 % CI: " + ", ".join(f"{k.split('_')[0].upper()} {v}" for k, v in rep["uncertainty"].items()
                                          if k.endswith("ci95"))
              + ("" if not rep["reliability"] else
                 f"\n  cells: {rep['reliability']['green']} green, {rep['reliability']['yellow']} yellow (low "
                 f"confidence), {rep['reliability']['red']} red (implausible)")
              + f"\n  review queue: {len(res['queue'])} cells (red / yellow) -> {rep['image_id']}_review_queue.png"
              + f"\n  -> {path}")


if __name__ == "__main__":
    main()
