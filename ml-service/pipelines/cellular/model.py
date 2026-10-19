"""The two networks of the cellular analysis, served with onnxruntime (no PyTorch / TensorFlow).

  roi       EfficientNet-B0 tile classifier (Phase 6): tiles (N, 3, 162, 162) float32 0..255 -> P(analysable);
            resize to 224 px, ImageNet normalisation and sigmoid are inside the ONNX graph
  stardist  StarDist 2D network (Phase 2): image (1, H, W, 1) -> prob, dist; post-processing in stardist_onnx.py

Both exported by ml/cellular/export_web.py, checked against the PyTorch / TensorFlow models there.
"""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from pipelines.cellular.config import checked_file, load_config
from pipelines.cellular.stardist_onnx import StarDistOnnx

ROI_BATCH = 64


@dataclass
class Models:
    roi: object                # onnxruntime.InferenceSession
    stardist: StarDistOnnx

    def roi_probs(self, tiles: np.ndarray) -> np.ndarray:
        out = [self.roi.run(["p_analysable"], {"tiles": tiles[i:i + ROI_BATCH].astype(np.float32)})[0]
               for i in range(0, len(tiles), ROI_BATCH)]
        return np.concatenate(out) if out else np.zeros(0, np.float32)


@lru_cache
def load_models() -> Models:
    """Both ONNX sessions, after the SHA-256 check; loaded once per process (raises CellularModelNotReady)."""
    config = load_config()
    roi_cfg, sd_cfg = config["models"]["roi"], config["models"]["stardist"]
    roi_path = checked_file(roi_cfg["file"], roi_cfg["sha256"])
    sd_path = checked_file(sd_cfg["file"], sd_cfg["sha256"])

    import onnxruntime as ort

    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = ["CPUExecutionProvider"]
    sd_session = ort.InferenceSession(str(sd_path), options, providers=providers)
    return Models(
        roi=ort.InferenceSession(str(roi_path), options, providers=providers),
        stardist=StarDistOnnx(sd_session, sd_cfg["grid"], sd_cfg["div_by"], sd_cfg["prob_thresh"],
                              sd_cfg["nms_thresh"], (sd_cfg["outputs"]["prob"], sd_cfg["outputs"]["dist"])),
    )
