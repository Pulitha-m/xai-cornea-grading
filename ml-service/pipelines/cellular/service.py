"""Cellular analysis of one specular microscopy image (Component 3, Corneal Cellular Intelligence).

The validated pipeline of ml/cellular/pipeline.py, run with the two networks as ONNX:
  3.1 ROI        EfficientNet-B0 on 162 px tiles (half-tile stride) -> analysable region inside the lit area
  3.2 cells      StarDist (flat preprocessing, normalised over the lit area) -> cell instances
  3.3 extraction complete cells only (not touching the image border or the unanalysable area), side counts
  3.4 biomarkers ECD, CV, HEX, ... with the calibrated scale (0.796 um/px)
plus the explanations (95 % CIs, the cells driving CV, per-cell reliability, quality flags) and overlay images.

Validated on 1,296 x 972 images from one specular microscope (eye bank): on the frozen test set (197 images)
mean cell area and CV met their targets vs Konan, ECD (MAPE 5.8 %) and HEX (11.6 %) did not
(docs: ml/cellular/docs/phase/phase_7_final_test.md). The served numbers equal the validated pipeline's within
1 % cells, 0.2 % ECD / CV, 0.5 % HEX (floating-point differences of the ONNX networks; export_web.py).

Served by POST /cellular/analyze (app/routers/cellular.py) on its own page; /analyze does not run it.
Research tool for a specialist, not a clinical measurement device.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from pipelines.cellular import steps
from pipelines.cellular.cells import ExtractionParams, extract_cells, instances_from_mask, report
from pipelines.cellular.config import load_config
from pipelines.cellular.explain import (area_overlay, bootstrap_ci, cell_confidence, overlay, quality_flags,
                                        reliability, reliability_overlay, variance_share)
from pipelines.cellular.model import load_models

METHOD = "roi_efficientnet_b0_stardist_onnx_v1"


def run_cellular_analysis(image) -> dict:
    """Cellular module of the combined /analyze endpoint: not run there (see POST /cellular/analyze)."""
    raise NotImplementedError("Cellular analysis runs on its own page (POST /cellular/analyze).")


def warm_up() -> None:
    """Load the config and both models (raises CellularModelNotReady)."""
    load_config()
    load_models()


@dataclass
class CellularOutcome:
    report: dict                     # as ml/cellular/pipeline.py: biomarkers, roi, quality_flags, reliable,
                                     # uncertainty, evidence, reliability, seconds
    cells: pd.DataFrame              # complete cells with confidence and level
    images: dict = field(default_factory=dict)   # name -> RGB uint8 image
    roi: np.ndarray | None = None
    mask: np.ndarray | None = None


def analyse(gray: np.ndarray, image_id: str = "image") -> CellularOutcome:
    """gray: 8-bit greyscale image (H, W), decoded as in the research pipeline (cv2.IMREAD_GRAYSCALE)."""
    t0 = time.time()
    cfg, models = load_config(), load_models()
    params, xparams = steps.ClassicalParams.from_config(cfg), ExtractionParams.from_config(cfg)
    flat, lit = steps.flatten_illumination(gray, params)

    # 3.1 ROI
    planes = steps.image_planes(gray, flat, lit)
    h, w = lit.shape
    r = cfg["roi"]
    size = h // r["grid_rows"]
    wins = steps.window_grid(h, w, size, r["stride_px"])
    probs = models.roi_probs(np.stack([steps.crop(planes, y, x, size) for y, x in wins]))
    prob = steps.prob_map(probs, wins, (h, w), size)
    roi = steps.roi_from_prob(prob, lit, r["threshold"], int(r["min_island_tiles"] * size * size))

    # 3.2 cells (make_predictor: flat preprocessing, normalised over the lit area)
    norm = cfg["models"]["stardist"]["normalise"]
    x = flat if cfg["preprocess"] == "flat" else gray.astype(np.float32) / 255.0
    labels, details = models.stardist.predict_instances(steps.normalise_lit(x, lit, norm["pmin"], norm["pmax"]))
    mask = steps.instances_to_mask(labels)
    mask[~lit] = steps.IGNORE
    cell_prob = steps.instance_prob_image(labels, details["prob"], details["points"])
    cell_prob[~lit] = 0

    # 3.3 complete cells, 3.4 biomarkers
    cells, _, complete = extract_cells(instances_from_mask(mask), (mask != steps.IGNORE) & roi, xparams)
    rep = report(image_id, cells, cfg["scale"]["um_per_px"], cfg["pipeline"]["run"])
    roi_share_of_lit = float(roi.sum() / max(lit.sum(), 1))
    flags = quality_flags(rep["biomarkers"], roi_share_of_lit, cfg["pipeline"])
    validated = (w, h) == (cfg["image"]["width"], cfg["image"]["height"])
    if not validated:
        flags.append({"level": "warning", "code": "not_validated_size",
                      "message": f"image is {w} x {h} px; the pipeline and its scale were validated on "
                                 f"{cfg['image']['width']} x {cfg['image']['height']} px images from one specular "
                                 "microscope"})
    rep.update({
        "roi": {"method": "cnn", "share_of_image": round(float(roi.mean()), 4),
                "share_of_lit_area": round(roi_share_of_lit, 4),
                "quality_score": round(float(prob[lit].mean()), 4) if lit.any() else 0.0},
        "quality_flags": flags,
        "reliable": not any(f["level"] == "error" for f in flags),
        "validated_image_size": validated})

    # explanations (pipeline.CellularPipeline.explain; never change a number)
    xb = cfg["xai"]["biomarkers"]
    num = lambda v, d=3: round(float(v), d) if v is not None and np.isfinite(v) else None
    ci = bootstrap_ci(cells, cfg["scale"]["um_per_px"], xb["block_px"], xb["n_boot"], xb["seed"])
    rep["uncertainty"] = {
        "method": f"95 % CI, bootstrap over {xb['block_px']} px blocks of cells ({xb['n_boot']} resamples); "
                  "covers sampling, not segmentation error",
        **{f"{k}_ci95": [ci[k]["lo"], ci[k]["hi"]] for k in ("ecd", "cv", "hex")}}
    top, share = variance_share(cells, xb["top_variance_share"])
    rep["evidence"] = {"most_extreme_cells_pct": 100 * xb["top_variance_share"],
                       "their_share_of_area_variance_pct": num(100 * share, 1)}
    # no complete cells: plain image (area_overlay needs cells; the research pipeline never met this case)
    images = {"cv_evidence": area_overlay(gray, complete, cells, top) if len(cells) else np.dstack([gray] * 3)}
    if cells.empty:
        rep["reliability"] = None
    else:
        rel = reliability(cells, cell_confidence(complete, cell_prob, cells["cell_id"]),
                          cfg["models"]["stardist"]["prob_thresh"], xb)
        n = rel["level"].value_counts()
        rep["reliability"] = {
            "rule": "red = implausible size / shape; yellow = low StarDist confidence; green = otherwise",
            **{lev: int(n.get(lev, 0)) for lev in ("green", "yellow", "red")},
            "median_confidence": num(rel["confidence"].median())}
        images["reliability"] = reliability_overlay(gray, complete, rel)
        cells = cells.merge(rel[["confidence", "level"]], left_on="cell_id", right_index=True, how="left")
    images["overlay"] = overlay(gray, roi, complete, cells, rep["biomarkers"], flags)[..., ::-1]  # BGR -> RGB
    rep["seconds"] = round(time.time() - t0, 2)
    return CellularOutcome(report=rep, cells=cells, images=images, roi=roi, mask=mask)
