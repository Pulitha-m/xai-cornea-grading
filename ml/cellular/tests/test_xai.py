"""
XAI step 1 — Grad-CAM / Grad-CAM++ and the deletion test on a toy CNN with a known answer:
its "poor" score is the mean brightness of a feature that only fires on a bright blob, so the
heatmap must sit on the blob, and deleting the blob must lower P(poor) more than deleting elsewhere.

Run (from ml/cellular/):  python -m pytest tests/test_xai.py -q
"""

from __future__ import annotations

import numpy as np
import torch

from xai.gradcam import delete, get_layer, image_map, rolled, tile_cams, top_mask

HP = {"input_px": 64}
DEV = torch.device("cpu")


class Toy(torch.nn.Module):
    def __init__(self):
        super().__init__()
        conv = torch.nn.Conv2d(3, 2, 3, padding=1)
        with torch.no_grad():
            conv.weight.zero_()
            conv.bias.zero_()
            conv.weight[0, 0, 1, 1] = 1.0           # channel 0 = raw plane (normalised): > 0 only where bright
        self.features = torch.nn.Sequential(conv, torch.nn.ReLU())
        self.pool = torch.nn.AdaptiveAvgPool2d(1)
        self.classifier = torch.nn.Linear(2, 1)
        with torch.no_grad():
            self.classifier.weight[:] = torch.tensor([[-8.0, 0.0]])   # bright -> lower logit -> poor
            self.classifier.bias[:] = 2.0

    def forward(self, x):
        return self.classifier(self.pool(self.features(x)).flatten(1))


def blob_tiles(n=3, s=48, centre=(12, 30), r=6):
    t = np.zeros((n, 3, s, s), np.uint8)
    t[:, 1] = 100
    t[:, 2] = 255
    yy, xx = np.indices((s, s))
    blob = (yy - centre[0]) ** 2 + (xx - centre[1]) ** 2 <= r * r
    t[:, 0][:, blob] = 255
    return t, blob


def test_heatmap_sits_on_the_blob_for_both_methods():
    model = Toy()
    tiles, blob = blob_tiles()
    for method in ("gradcam", "gradcam++"):
        p, cams = tile_cams(model, tiles, HP, DEV, "features", method)
        assert cams.shape == (3, 48, 48) and np.isclose(cams.max(axis=(1, 2)), 1).all()
        assert (0 < p).all() and (p < 1).all()
        for m in cams:
            assert blob.flat[int(np.argmax(m))]                     # pointing game hit
            assert m[blob].sum() / m.sum() > 0.6                    # most evidence on the blob (area ~5 %)


def test_no_evidence_for_the_other_class():
    p, cams = tile_cams(Toy(), blob_tiles()[0], HP, DEV, "features", "gradcam++", target="analysable")
    assert np.allclose(cams, 0)


def test_get_layer_efficientnet():
    from roi.cnn import build
    model = build({"arch": "efficientnet_b0", "pretrained": False})
    store = {}
    get_layer(model, "features.8").register_forward_hook(lambda m, i, o: store.__setitem__("a", o))
    model.eval()(torch.zeros(1, 3, 224, 224))
    assert store["a"].shape == (1, 1280, 7, 7)


def test_image_map_ignores_windows_called_analysable():
    cams = np.ones((2, 4, 4), np.float32)
    m = image_map(np.array([1.0, 0.0]), cams, [(0, 0), (0, 4)], (4, 8))
    assert np.allclose(m[:, :4], 0) and np.allclose(m[:, 4:], 1)


def test_masks_and_delete():
    rng = np.random.default_rng(0)
    cams = rng.random((4, 20, 20))
    m = top_mask(cams, 0.2)
    assert (m.sum(axis=(1, 2)) == 80).all()
    assert (cams[m].min() >= np.quantile(cams, 0.5))
    r = rolled(m, rng)
    assert (r.sum(axis=(1, 2)) == 80).all() and not (r == m).all()
    tiles = rng.integers(0, 256, (4, 3, 20, 20)).astype(np.uint8)
    tiles[:, 2] = 0
    tiles[:, 2, :10] = 255
    d = delete(tiles, m)
    assert (d[~np.repeat(m[:, None], 3, 1)] == tiles[~np.repeat(m[:, None], 3, 1)]).all()   # rest untouched
    assert (d[:, 2][m] == 255).all()
    for t, dt, mm in zip(tiles, d, m):
        assert (dt[0][mm] == round(float(t[0][t[2] > 0].mean()))).all()


def test_deleting_the_heatmap_lowers_p_poor_more_than_deleting_elsewhere():
    from roi.cnn import predict
    model = Toy()
    tiles, _ = blob_tiles()
    p0, cams = tile_cams(model, tiles, HP, DEV, "features", "gradcam++")
    masks = top_mask(cams, 0.2)
    p_cam = predict(model, delete(tiles, masks), HP, DEV)
    p_shift = predict(model, delete(tiles, rolled(masks, np.random.default_rng(1))), HP, DEV)
    assert np.allclose(p_cam, 1 / (1 + np.exp(-2.0)), atol=1e-4)    # blob gone: logit back to the bias
    assert (p_cam >= p_shift).all() and (p_cam - p0).mean() > (p_shift - p0).mean() + 0.05


def test_raw_heatmaps_keep_scale_between_windows():
    model = Toy()
    tiles, blob = blob_tiles(n=2)
    tiles[1, 0][blob] = 180                                          # dimmer blob -> weaker evidence
    _, raw = tile_cams(model, tiles, HP, DEV, "features", "gradcam", normalise=False)
    _, norm = tile_cams(model, tiles, HP, DEV, "features", "gradcam")
    assert raw[0].max() > raw[1].max() > 0                           # comparable, not stretched to 1
    assert np.allclose(norm.max(axis=(1, 2)), 1)
    assert np.allclose(raw[0] / raw[0].max(), norm[0], atol=1e-5)


def test_two_part_map_marks_unlit_purple_and_no_heat_there():
    from xai.roi_explain import two_part
    img = np.full((40, 40), 100, np.uint8)
    lit = np.zeros((40, 40), bool)
    lit[:, 20:] = True
    heat = np.ones((40, 40), np.float32)                             # evidence everywhere
    v = two_part(img, lit, np.zeros_like(lit), heat).astype(int)
    tint = (0.55 * 100 + 0.45 * np.array([150, 0, 190])).astype(int)
    assert (np.abs(v[:, :20] - tint) <= 1).all()                     # unlit: grey + purple tint only, no heat
    assert (v[:, 20:, 0] > v[:, 20:, 1] + 40).all() and (v[:, 20:, 0] > v[:, 20:, 2] + 40).all()   # red heat on lit
