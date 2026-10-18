"""
XAI step 3 — Seg-Grad-CAM helpers; the TensorFlow part on a toy network with a known answer (skipped without TF).

Run (from ml/cellular/):  python -m pytest tests/test_seg_gradcam.py -q
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from xai.seg_explain import draw, instance_of
from xai.seg_gradcam import delete, pad_to, rolled_in_window, shares, to_grid, top_in_window, window


def test_pad_and_grid():
    a = np.ones((250, 254), np.float32)
    assert pad_to(a, 32).shape == (256, 256) and pad_to(a, 2).shape == (250, 254)
    r = np.zeros((8, 8), bool)
    r[2:6, 2:6] = True
    assert to_grid(r, (4, 4)).sum() == 4                  # 2 x 2 grid: the 4 blocks fully inside
    r = np.zeros((8, 8), bool)
    r[3, 3] = True
    assert to_grid(r, (4, 4)).sum() == 1                  # tiny region: still one pixel


def test_window_top_and_rolled_masks():
    heat = np.zeros((40, 40), np.float32)
    heat[18:22, 18:22] = 1
    region = np.zeros((40, 40), bool)
    region[17:23, 17:23] = True
    win = window(region, 5, (40, 40))
    assert (win[0].start, win[0].stop, win[1].start, win[1].stop) == (12, 28, 12, 28)
    assert window(region, 30, (40, 40)) == (slice(0, 40), slice(0, 40))   # clipped to the crop
    top = top_in_window(heat, win, 16 / 256)
    assert top.sum() == 16 and top[18:22, 18:22].all()
    for m in rolled_in_window(top, win, np.random.default_rng(0), 5):
        assert m.sum() == 16 and not m[:12].any() and not m[:, 28:].any() and not m[18:22, 18:22].all()
    x = np.arange(1600, dtype=np.float32).reshape(40, 40)
    d = delete(x, top, win)
    assert np.allclose(d[top], x[win].mean()) and np.array_equal(d[~top], x[~top])


def test_shares():
    region = np.zeros((40, 40), bool)
    region[15:25, 15:25] = True
    win = (slice(5, 35), slice(5, 35))
    heat = region.astype(np.float32)
    s = shares(heat, win, region, 2)
    assert s["heat_cell"] == 1 and np.isclose(s["area_cell"], 14 * 14 / 900 - 4 * 3 / 900, atol=0.02)
    assert 0 < s["heat_wall"] < 1 and s["area_wall"] < s["area_cell"]
    assert np.isnan(shares(np.zeros((40, 40)), win, region, 2)["heat_cell"])


def test_instance_and_sample():
    labels = np.zeros((6, 6), np.int32)
    labels[:, :3], labels[:, 3:] = 4, 9
    complete = np.zeros((6, 6), np.int32)
    complete[1:5, 1:4] = 1                                  # mostly on instance 4
    assert instance_of(complete, labels, 1) == 4 and instance_of(complete, labels, 2) == 0
    t = pd.DataFrame({"level": ["green"] * 10 + ["yellow"] * 2 + ["red"], "cell_id": range(13)})
    xs = {"seed": 1, "n_green": 4, "n_flagged": 5}
    p = draw(t, xs)
    assert (p["group"] == "green").sum() == 4 and (p["group"] == "flagged").sum() == 3   # all flagged if fewer
    assert p.equals(draw(t, xs))                            # reproducible


def toy_model():
    """features = ReLU(input) (channel 0) and ReLU(-input) (channel 1); prob = sigmoid(8 * f0 - 4)."""
    tf = pytest.importorskip("tensorflow")
    try:
        import tf_keras as K
    except ImportError:
        K = tf.keras
    inp = K.Input((16, 16, 1))
    f = K.layers.Conv2D(2, 1, activation="relu", name="features")(inp)
    p = K.layers.Conv2D(1, 1, activation="sigmoid", name="prob")(f)
    m = K.Model(inp, p)
    m.get_layer("features").set_weights([np.array([1.0, -1.0], np.float32).reshape(1, 1, 1, 2), np.zeros(2, np.float32)])
    m.get_layer("prob").set_weights([np.array([8.0, 0.0], np.float32).reshape(1, 1, 2, 1), np.array([-4.0], np.float32)])
    return m


def test_seg_cam_finds_the_bright_cell_and_deletion_lowers_its_score():
    from xai.seg_gradcam import scores, seg_cam, two_outputs, upsample
    model2 = two_outputs(toy_model(), "features")
    x = np.zeros((16, 16), np.float32)
    x[4:8, 4:8] = 1                                         # the cell
    region = x > 0
    cam, s0 = seg_cam(model2, x, region)
    assert np.isclose(s0, 16 / (1 + np.exp(-4)), rtol=1e-4)
    assert cam[region].min() > 0 and cam[~region].max() == 0      # heat exactly on the cell
    heat = upsample(cam, x.shape)
    win = window(region, 4, x.shape)
    top = top_in_window(heat, win, 16 / 144)
    assert (top == region).all()
    shifted = rolled_in_window(top, win, np.random.default_rng(0), 3)
    sc = scores(model2, [delete(x, m, win) for m in [top, *shifted]], region)
    assert sc[0] < s0 and sc[0] < sc[1:].min()              # removing the heat hurts most
