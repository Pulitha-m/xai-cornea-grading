"""
Export for the web ML service: the ROI network wrapper, ONNX round trip, TensorFlow-free StarDist post-processing,
the web config.

Run (from ml/cellular/):  python -m pytest tests/test_export_web.py -q
(ONNX and stardist parts are skipped where onnxruntime / stardist are not installed; they run in Colab.)
"""

from __future__ import annotations

import json

import numpy as np
import pytest
import torch

from config import load_config
from export_web import build_config, rel, roi_net
from roi import cnn
from segmentation.stardist_onnx import StarDistOnnx, pad_to


def toy_classifier():
    torch.manual_seed(0)
    return torch.nn.Sequential(torch.nn.Conv2d(3, 4, 3, padding=1), torch.nn.ReLU(),
                               torch.nn.AdaptiveAvgPool2d(1), torch.nn.Flatten(), torch.nn.Linear(4, 1)).eval()


def tiles(n=5, s=18, seed=1):
    return np.random.default_rng(seed).integers(0, 256, (n, 3, s, s)).astype(np.uint8)


def test_roi_net_equals_the_training_input_path():
    model, t = toy_classifier(), tiles()
    with torch.no_grad():
        ref = torch.sigmoid(model(cnn.to_input(torch.from_numpy(t), 24))).squeeze(1)
        got = roi_net(model, 24)(torch.from_numpy(t.astype(np.float32)))
    assert torch.allclose(ref, got, atol=1e-6)


def test_roi_net_onnx_round_trip(tmp_path):
    ort = pytest.importorskip("onnxruntime")
    pytest.importorskip("onnx")
    net, t = roi_net(toy_classifier(), 24), tiles().astype(np.float32)
    f = tmp_path / "roi.onnx"
    kwargs = dict(input_names=["tiles"], output_names=["p_analysable"], opset_version=17,
                  dynamic_axes={"tiles": {0: "n"}, "p_analysable": {0: "n"}})
    try:
        torch.onnx.export(net, torch.zeros(2, 3, 18, 18), str(f), dynamo=False, **kwargs)
    except TypeError:
        torch.onnx.export(net, torch.zeros(2, 3, 18, 18), str(f), **kwargs)
    s = ort.InferenceSession(str(f), providers=["CPUExecutionProvider"])
    with torch.no_grad():
        ref = net(torch.from_numpy(t)).numpy()
    assert np.allclose(s.run(["p_analysable"], {"tiles": t})[0], ref, atol=1e-5)    # batch 5 != export batch 2


def test_pad_to_reflects_at_the_end_only():
    x = np.arange(12, dtype=np.float32).reshape(3, 4)
    p, pad = pad_to(x, (4, 4))
    assert p.shape == (4, 4) and pad == ((0, 1), (0, 0))
    assert np.array_equal(p[:3], x) and np.array_equal(p[3], x[1])            # reflect: row 3 = row 1
    assert pad_to(x, (3, 2))[0].shape == (3, 4)                                 # already divisible


class FakeSession:
    """Stands in for onnxruntime: returns fixed outputs and records the input."""

    def __init__(self, prob, dist):
        self.prob, self.dist, self.seen = prob, dist, None

    def get_inputs(self):
        return [type("I", (), {"name": "image"})()]

    def run(self, names, feeds):
        self.seen = (names, feeds["image"].shape)
        return [{"p": self.prob, "d": self.dist}[n] for n in names]


def disc_outputs(shape, centres, radius, n_rays=32, grid=(2, 2)):
    """StarDist-like outputs at grid resolution for round objects: prob high at the centres, dist = radius."""
    h, w = shape[0] // grid[0], shape[1] // grid[1]
    prob = np.zeros((1, h, w, 1), np.float32)
    for cy, cx in centres:
        prob[0, cy // grid[0], cx // grid[1], 0] = 0.95
    dist = np.full((1, h, w, n_rays), radius, np.float32)
    return prob, dist


def test_stardist_onnx_pads_and_reads_named_outputs():
    prob, dist = disc_outputs((64, 64), [(20, 20)], 6)
    s = FakeSession(prob, dist)
    sd = StarDistOnnx(s, (2, 2), (16, 16), 0.5, 0.3, ("p", "d"))
    p, d = sd.predict(np.zeros((60, 50), np.float32))
    assert s.seen == (["p", "d"], (1, 64, 64, 1))                               # padded to 16-multiples
    assert p.shape == (32, 32) and d.shape == (32, 32, 32)


def test_stardist_postprocessing_without_tensorflow():
    pytest.importorskip("stardist")
    import sys
    prob, dist = disc_outputs((64, 64), [(16, 16), (40, 44), (62, 62)], 6)    # the last one is in the padding
    sd = StarDistOnnx(FakeSession(prob, dist), (2, 2), (16, 16), 0.5, 0.3, ("p", "d"))
    labels, det = sd.predict_instances(np.zeros((60, 60), np.float32))
    assert labels.shape == (60, 60) and len(det["points"]) == 2               # padding candidate dropped
    assert labels[16, 16] > 0 and labels[40, 44] > 0 and labels[16, 16] != labels[40, 44]
    assert "tensorflow" not in sys.modules


def test_web_config_has_everything_and_the_hashes(tmp_path):
    from final_test import file_hash
    cfg = load_config()
    files = {"roi": tmp_path / "roi_cnn.onnx", "stardist": tmp_path / "stardist.onnx"}
    for f in files.values():
        f.write_bytes(f.name.encode())
    roi_meta = {"tile_px": 162, "input_px": 224, "arch": "efficientnet_b0", "torch_net": object()}
    sd_meta = {"n_rays": 32, "grid": [2, 2], "div_by": [16, 16], "prob_thresh": 0.49, "nms_thresh": 0.3,
               "outputs": {"prob": "a", "dist": "b"}}
    c = build_config(cfg, roi_meta, sd_meta, "flat", files, {"git_commit": "x"})
    json.dumps(c)                                                               # serialisable (torch_net dropped)
    assert c["models"]["roi"]["sha256"] == file_hash(files["roi"]) and c["models"]["roi"]["file"] == "roi_cnn.onnx"
    assert c["models"]["stardist"]["normalise"] == {"pmin": 1, "pmax": 99.8, "over": "lit area"}
    assert c["scale"]["um_per_px"] == cfg["scale"]["um_per_px"] and c["preprocess"] == "flat"
    for key in ("image", "classical", "roi", "extraction", "pipeline"):
        assert c[key]
    assert c["xai"]["biomarkers"]["block_px"] == cfg["xai"]["biomarkers"]["block_px"]
    assert c["roi"]["stride_px"] == cfg["roi_model"]["stride_px"]


def test_rel():
    assert rel(101.0, 100.0) == pytest.approx(0.01) and rel(None, None) == 0.0 and np.isnan(rel(1.0, None))
