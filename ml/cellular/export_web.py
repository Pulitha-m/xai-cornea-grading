"""
Export the validated cellular pipeline for the web ML service (ml-service/pipelines/cellular).

The web service runs without PyTorch or TensorFlow: both networks as ONNX (onnxruntime), everything else the same
code as pipeline.py. This script (Colab, where the models are):
  1. ROI CNN (EfficientNet-B0)  -> roi_cnn.onnx    tiles (N, 3, 162, 162) float32 0..255 -> P(analysable) (N,);
                                                    resize + ImageNet normalisation + sigmoid inside the graph
  2. StarDist final network     -> stardist.onnx   image (1, H, W, 1) float32 -> prob, dist (tf2onnx)
  3. cellular_config.json        settings the web pipeline needs (copied from config.yaml) + SHA-256 of both files
  4. parity check on validation images: the web path (ONNX networks + segmentation.stardist_onnx) vs the validated
     CellularPipeline (PyTorch on GPU, TensorFlow): ROI probabilities, StarDist outputs and instances, and the
     biomarkers; references saved for the ML service's own parity test.

Outputs: <outputs_dir>/web_export/
    models/cellular/      roi_cnn.onnx, stardist.onnx, cellular_config.json  -> ml-service/models/cellular/
    reference/            per reference image: the image, the validated pipeline outputs (pipeline.save), the web
                          path's report (<id>_web.json) and arrays (<id>_web.npz)  -> ml-service tests (git-ignored)
    parity.csv, parity.json
Usage (from ml/cellular/; Colab GPU, after pip install tensorflow tf-keras stardist onnx onnxruntime tf2onnx):
    python -m export_web
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from config import load_config

N_PARITY = 10                 # first validation images (as pipeline --check) ...
ROI_BATCH = 64
TOL_REL = 1e-3                # ... plus the 3 demo images; same tolerance as pipeline --check (0.1 %)
HEADLINE = ("n_cells", "ecd_cells_per_mm2", "cv_pct", "hex_pct")


def out_root(cfg: dict) -> Path:
    d = cfg["paths"]["outputs_dir"] / "web_export"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- ROI network ----------
def roi_net(model, input_px: int):
    """The trained classifier with roi.cnn.to_input and the sigmoid inside: tiles 0..255 -> P(analysable)."""
    import torch
    import torch.nn.functional as F
    from roi.cnn import MEAN, STD

    class RoiNet(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.model = model
            self.register_buffer("mean", MEAN.clone())
            self.register_buffer("std", STD.clone())

        def forward(self, tiles):
            x = tiles / 255
            x = F.interpolate(x, size=(input_px, input_px), mode="bilinear", align_corners=False)
            return torch.sigmoid(self.model((x - self.mean) / self.std)).squeeze(1)

    return RoiNet().eval()


def export_roi(cfg: dict, path: Path) -> dict:
    import torch
    from roi import cnn
    ck = torch.load(cfg["paths"]["models_dir"] / "roi" / "cnn.pt", map_location="cpu")
    model = cnn.build({**ck["hp"], "pretrained": False})
    model.load_state_dict(ck["state_dict"])
    net = roi_net(model.eval(), ck["hp"]["input_px"])
    tile = cfg["image"]["height"] // cfg["roi"]["grid_rows"]
    kwargs = dict(input_names=["tiles"], output_names=["p_analysable"], opset_version=17,
                  dynamic_axes={"tiles": {0: "n"}, "p_analysable": {0: "n"}})
    example = torch.zeros(2, 3, tile, tile)
    try:
        torch.onnx.export(net, example, str(path), dynamo=False, **kwargs)
    except TypeError:                                    # older torch without the dynamo argument
        torch.onnx.export(net, example, str(path), **kwargs)
    return {"tile_px": tile, "input_px": int(ck["hp"]["input_px"]), "arch": ck["hp"]["arch"],
            "input": "tiles (N, 3, tile_px, tile_px) float32 0..255: raw / flat / lit planes",
            "output": "p_analysable (N,)", "torch_net": net}


def roi_probs(session, tiles: np.ndarray) -> np.ndarray:
    out = [session.run(["p_analysable"], {"tiles": tiles[i:i + ROI_BATCH].astype(np.float32)})[0]
           for i in range(0, len(tiles), ROI_BATCH)]
    return np.concatenate(out) if out else np.zeros(0, np.float32)


# ---------------------------------------------------------------- StarDist network ----------
def stardist_model(cfg: dict):
    from stardist.models import StarDist2D

    from segmentation.train_final import final_dir
    info = json.loads((final_dir(cfg, cfg["pipeline"]["run"]) / "final.json").read_text())
    d = Path(info["model_dir"])
    return StarDist2D(None, name=d.name, basedir=str(d.parent)), info


def export_stardist(model, path: Path) -> dict:
    import tensorflow as tf
    import tf2onnx
    km = model.keras_model
    spec = (tf.TensorSpec((None, None, None, 1), tf.float32, name="image"),)

    @tf.function(input_signature=spec)
    def net(x):
        prob, dist = km(x, training=False)[:2]
        return {"prob": prob, "dist": dist}

    onnx_model, _ = tf2onnx.convert.from_function(net, input_signature=spec, opset=17, output_path=str(path))
    c = model.config
    # output names / order are not guaranteed by tf2onnx: identify them by the channel size (prob 1, dist n_rays)
    channels = {o.name: o.type.tensor_type.shape.dim[-1].dim_value for o in onnx_model.graph.output}
    prob = [n for n, k in channels.items() if k == 1]
    dist = [n for n, k in channels.items() if k == int(c.n_rays)]
    if len(prob) != 1 or len(dist) != 1:
        raise SystemExit(f"cannot identify the StarDist outputs in the ONNX graph: {channels}")
    return {"n_rays": int(c.n_rays), "grid": [int(g) for g in c.grid],
            "div_by": [int(d) for d in model._axes_div_by("YX")],
            "prob_thresh": float(model.thresholds.prob), "nms_thresh": float(model.thresholds.nms),
            "outputs": {"prob": prob[0], "dist": dist[0]},
            "input": "image (1, H, W, 1) float32: flat preprocessing, percentile-normalised over the lit area"}


# ---------------------------------------------------------------- web path ----------
class WebPath:
    """What the web ML service will run: pipeline.py's steps with the two networks as ONNX."""

    def __init__(self, cfg: dict, roi_session, stardist, preprocess: str):
        from extraction.cells import ExtractionParams
        from segmentation.classical import ClassicalParams
        from segmentation.preprocess import Preprocessor
        self.cfg, self.roi_session, self.stardist = cfg, roi_session, stardist
        self.pre, self.params = Preprocessor(cfg, preprocess), ClassicalParams.from_config(cfg)
        self.xparams = ExtractionParams.from_config(cfg)

    def __call__(self, img: np.ndarray, image_id: str) -> dict:
        from biomarkers.compute import report
        from data_prep.check_annotations import IGNORE
        from extraction.cells import extract_cells, instances_from_mask
        from roi.roimap import prob_map, roi_from_prob, window_grid
        from roi.tiles import crop, image_planes
        from segmentation.classical import flatten_illumination
        from segmentation.infer_full import normalise_lit
        from segmentation.postprocess import instances_to_mask

        cfg, rm = self.cfg, self.cfg["roi_model"]
        planes = image_planes(cfg, img)                                   # 3.1 ROI
        lit = planes[2] > 0
        h, w = lit.shape
        size = h // cfg["roi"]["grid_rows"]
        wins = window_grid(h, w, size, rm["stride_px"])
        probs = roi_probs(self.roi_session, np.stack([crop(planes, y, x, size) for y, x in wins]))
        prob = prob_map(probs, wins, (h, w), size)
        roi = roi_from_prob(prob, lit, rm["threshold"], int(rm["min_island_tiles"] * size * size))
        m = flatten_illumination(img, self.params)[1]                    # 3.2 segmentation (make_predictor)
        x = normalise_lit(self.pre(img), m, 1, 99.8)
        labels, details = self.stardist.predict_instances(x)
        mask = instances_to_mask(labels)
        mask[~m] = IGNORE
        cells, _, complete = extract_cells(instances_from_mask(mask), (mask != IGNORE) & roi, self.xparams)
        rep = report(image_id, cells, cfg["scale"]["um_per_px"], cfg["pipeline"]["run"])
        return {"planes": planes, "tile_probs": probs, "roi_prob": prob, "roi": roi, "x": x, "labels": labels,
                "details": details, "mask": mask, "cells": cells, "report": rep}


# ---------------------------------------------------------------- config ----------
def versions() -> dict:
    out = {"python": sys.version.split()[0]}
    for m in ("numpy", "torch", "tensorflow", "stardist", "tf2onnx", "onnx", "onnxruntime", "scikit-image"):
        try:
            mod = __import__("skimage" if m == "scikit-image" else m)
            out[m] = getattr(mod, "__version__", "?")
        except ImportError:
            out[m] = None
    return out


def build_config(cfg: dict, roi_meta: dict, sd_meta: dict, preprocess: str, files: dict, source: dict) -> dict:
    """Everything the web pipeline needs, copied from config.yaml (no defaults on the web side)."""
    from final_test import file_hash
    roi_meta = {k: v for k, v in roi_meta.items() if k != "torch_net"}
    rm = cfg["roi_model"]
    return {
        "format": 1,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "models": {
            "roi": {"file": files["roi"].name, "sha256": file_hash(files["roi"]), **roi_meta},
            "stardist": {"file": files["stardist"].name, "sha256": file_hash(files["stardist"]),
                         "normalise": {"pmin": 1, "pmax": 99.8, "over": "lit area"}, **sd_meta},
        },
        "preprocess": preprocess,
        "image": cfg["image"],
        "classical": cfg["classical"],
        "roi": {"grid_rows": cfg["roi"]["grid_rows"], "grid_cols": cfg["roi"]["grid_cols"],
                "stride_px": rm["stride_px"], "threshold": rm["threshold"], "min_island_tiles": rm["min_island_tiles"]},
        "extraction": cfg["extraction"],
        "scale": {"um_per_px": cfg["scale"]["um_per_px"]},
        "pipeline": cfg["pipeline"],
        "xai": {"biomarkers": cfg["xai"]["biomarkers"], "oversight": cfg["xai"]["oversight"]},
    }


# ---------------------------------------------------------------- parity ----------
def rel(a, b) -> float:
    if a is None or b is None:
        return float("nan") if (a is None) != (b is None) else 0.0
    return abs(a - b) / max(abs(b), 1e-9)


def parity_row(image_id: str, ref: dict, web: dict, keras_out, web_out, keras_labels, roi_ref) -> dict:
    from extraction.cells import match_cells
    bm_ref, bm_web = ref["report"]["biomarkers"], web["report"]["biomarkers"]
    m = match_cells(web["labels"], keras_labels, 0.5)
    n_web, n_ref = int(len(np.unique(web["labels"])) - 1), int(len(np.unique(keras_labels)) - 1)
    row = {"image_id": image_id,
           "roi_prob_max_abs_diff": float(np.abs(web["roi_prob"] - roi_ref).max()),
           "roi_pixels_differ": int((web["roi"] != ref["roi"]).sum()),
           "net_prob_max_abs_diff": float(np.abs(web_out[0] - keras_out[0]).max()),
           "net_dist_max_abs_diff": float(np.abs(web_out[1] - keras_out[1]).max()),
           "instances_web": n_web, "instances_validated": n_ref,
           "instances_matched_pct": 100 * len(m) / max(n_ref, 1),
           "instances_identical": bool(np.array_equal(web["labels"], keras_labels))}
    for k in HEADLINE:
        row[f"{k} validated"], row[f"{k} web"] = bm_ref[k], bm_web[k]
        row[f"{k} rel diff"] = rel(bm_web[k], bm_ref[k])
    return row


def main() -> None:
    import cv2
    import onnxruntime as ort

    from final_test import dir_hash, git
    from pipeline import CellularPipeline
    from roi.run import RoiScorer
    from segmentation.infer_full import images_of
    from segmentation.stardist_onnx import StarDistOnnx, pad_to

    cfg = load_config()
    root = out_root(cfg)
    mdir, rdir = root / "models" / "cellular", root / "reference"
    mdir.mkdir(parents=True, exist_ok=True)
    rdir.mkdir(parents=True, exist_ok=True)
    files = {"roi": mdir / "roi_cnn.onnx", "stardist": mdir / "stardist.onnx"}

    print("1. ROI CNN -> ONNX", flush=True)
    roi_meta = export_roi(cfg, files["roi"])
    print("2. StarDist -> ONNX", flush=True)
    sd_model, info = stardist_model(cfg)
    sd_meta = export_stardist(sd_model, files["stardist"])
    for k, f in files.items():
        print(f"   {f.name}: {f.stat().st_size / 1e6:.1f} MB")

    opts = ort.SessionOptions()
    roi_session = ort.InferenceSession(str(files["roi"]), opts, providers=["CPUExecutionProvider"])
    sd_session = ort.InferenceSession(str(files["stardist"]), opts, providers=["CPUExecutionProvider"])
    stardist = StarDistOnnx(sd_session, sd_meta["grid"], sd_meta["div_by"], sd_meta["prob_thresh"],
                            sd_meta["nms_thresh"], (sd_meta["outputs"]["prob"], sd_meta["outputs"]["dist"]))
    web = WebPath(cfg, roi_session, stardist, info["preprocess"])

    # quick check of the ROI graph against the same network in PyTorch (fp32, CPU)
    import torch
    rng = np.random.default_rng(0)
    probe = rng.integers(0, 256, (8, 3, roi_meta["tile_px"], roi_meta["tile_px"])).astype(np.float32)
    with torch.no_grad():
        p_torch = roi_meta["torch_net"](torch.from_numpy(probe)).numpy()
    roi_graph_diff = float(np.abs(roi_probs(roi_session, probe) - p_torch).max())
    print(f"   ROI ONNX vs PyTorch fp32 on random tiles: max |dP| {roi_graph_diff:.2e}")

    print("3. Parity: web path vs validated pipeline", flush=True)
    pipe, scorer = CellularPipeline(cfg), RoiScorer(cfg)
    val = images_of(cfg, "val")
    demo = [g.sample(1, random_state=1).iloc[0] for _, g in val.groupby("ecd_band")]   # as pipeline_demo
    picks = pd.concat([val.head(N_PARITY), pd.DataFrame(demo)]).drop_duplicates("image_id")
    demo_ids = {r["image_id"] for r in demo}
    rows = []
    for r in picks.itertuples(index=False):
        path = cfg["paths"]["images_dir"] / r.image_file
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        ref = pipe.analyse(path, r.image_id)                            # validated (GPU, PyTorch, TensorFlow)
        out = web(img, r.image_id)
        _, roi_ref = scorer(out["planes"])                              # validated ROI probabilities
        keras_labels, _ = sd_model.predict_instances(out["x"])           # validated StarDist instances
        xp, _ = pad_to(out["x"], tuple(sd_meta["div_by"]))
        k_prob, k_dist = sd_model.keras_model.predict(xp[None, ..., None], verbose=0)[:2]
        w_prob, w_dist = stardist.predict(out["x"])
        rows.append(parity_row(r.image_id, ref, out, (k_prob[0, ..., 0], k_dist[0]), (w_prob, w_dist),
                               keras_labels, roi_ref))
        if r.image_id in demo_ids:                                       # references for the ML service
            shutil.copy(path, rdir / f"{r.image_id}{path.suffix.lower()}")
            pipe.save(ref, rdir)
            (rdir / f"{r.image_id}_web.json").write_text(json.dumps(out["report"], indent=2, allow_nan=False))
            np.savez_compressed(rdir / f"{r.image_id}_web.npz", roi_prob=out["roi_prob"], roi=out["roi"],
                                labels=out["labels"], mask=out["mask"])
        print(f"   {r.image_id}: done", flush=True)

    t = pd.DataFrame(rows).set_index("image_id")
    t.to_csv(root / "parity.csv")
    worst = {k: float(t[f"{k} rel diff"].max()) for k in HEADLINE}
    summary = {"images": len(t), "reference_images": sorted(demo_ids), "tolerance_rel": TOL_REL,
               "roi_onnx_vs_torch_fp32_max_abs": roi_graph_diff,
               "roi_prob_max_abs_diff": float(t["roi_prob_max_abs_diff"].max()),
               "roi_pixels_differ_max": int(t["roi_pixels_differ"].max()),
               "net_prob_max_abs_diff": float(t["net_prob_max_abs_diff"].max()),
               "net_dist_max_abs_diff": float(t["net_dist_max_abs_diff"].max()),
               "instances_identical": int(t["instances_identical"].sum()),
               "instances_matched_pct_min": float(t["instances_matched_pct"].min()),
               "biomarkers_max_rel_diff": worst,
               "pass": all(v <= TOL_REL for v in worst.values())}
    (root / "parity.json").write_text(json.dumps(summary, indent=2))

    source = {"git_commit": git("rev-parse", "HEAD"), "segmentation_run": cfg["pipeline"]["run"],
              "source_models": {"roi": dir_hash(cfg["paths"]["models_dir"] / "roi"),
                                "segmentation_model": dir_hash(Path(info["model_dir"]))},
              "versions": versions(),
              "parity": {k: summary[k] for k in ("images", "biomarkers_max_rel_diff", "pass")}}
    conf = build_config(cfg, roi_meta, sd_meta, info["preprocess"], files, source)
    (mdir / "cellular_config.json").write_text(json.dumps(conf, indent=2))

    pd.set_option("display.width", 250)
    cols = ["roi_prob_max_abs_diff", "roi_pixels_differ", "net_prob_max_abs_diff", "instances_web",
            "instances_validated", "instances_matched_pct"] + [f"{k} rel diff" for k in HEADLINE]
    print("\n" + t[cols].to_string())
    print(f"\nROI: ONNX (CPU, fp32) vs validated (GPU, mixed precision): max |dP| {summary['roi_prob_max_abs_diff']:.2e}, "
          f"at most {summary['roi_pixels_differ_max']} ROI pixels differ")
    print(f"StarDist network: max |d prob| {summary['net_prob_max_abs_diff']:.2e}, |d dist| "
          f"{summary['net_dist_max_abs_diff']:.2e}; instances identical in {summary['instances_identical']} / {len(t)}, "
          f"matched >= {summary['instances_matched_pct_min']:.1f} %")
    print("Biomarkers, largest relative difference: " + ", ".join(f"{k} {v:.2e}" for k, v in worst.items()))
    print(f"\nWEB PATH {'= validated pipeline (within 0.1 %): PASS' if summary['pass'] else 'DIFFERS from the validated pipeline - send me this output'}")
    print(f"Copy {mdir} -> ml-service/models/cellular/\nReference images and outputs: {rdir}")


if __name__ == "__main__":
    main()
