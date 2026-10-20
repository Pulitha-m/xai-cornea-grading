"""
Phase 6 — ROI building blocks on synthetic data with known answers.

Run (from ml/cellular/):  python -m pytest tests/test_roi.py -q
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from roi.roimap import largest_component, prob_map, roi_from_prob, window_grid
from roi.tiles import FEATURES, make_folds, mask_to_tiles, tile_features, tile_iou


def test_tile_iou():
    ref = np.array([[1, 1, 0], [0, 0, 0]], bool)
    assert tile_iou(ref, ref) == 1
    assert tile_iou(ref, np.array([[1, 0, 0], [0, 0, 1]], bool)) == 1 / 3
    assert tile_iou(np.zeros((2, 3), bool), np.zeros((2, 3), bool)) == 1     # nothing analysable, none predicted


def test_mask_to_tiles_more_than_half_rule():
    m = np.zeros((972, 1296), bool)
    m[:162, :162] = True                     # tile (0, 0) full
    m[:162, 162:162 + 81] = True             # tile (0, 1) exactly half -> NOT in
    m[162:324, :82] = True                   # tile (1, 0) just over half -> in
    t = mask_to_tiles(m, 6, 8)
    assert t.shape == (6, 8) and t[0, 0] and not t[0, 1] and t[1, 0] and t.sum() == 2


def test_window_grid_covers_the_image_with_half_tile_stride():
    wins = window_grid(972, 1296, 162, 81)
    ys, xs = sorted({y for y, _ in wins}), sorted({x for _, x in wins})
    assert ys[0] == 0 and ys[-1] == 972 - 162 and xs[-1] == 1296 - 162
    assert len(wins) == len(ys) * len(xs) == 11 * 15


def test_prob_map_averages_overlapping_windows():
    wins = window_grid(20, 20, 10, 5)
    probs = [1.0 if (y, x) == (0, 0) else 0.0 for y, x in wins]
    p = prob_map(probs, wins, (20, 20), 10)
    assert p[0, 0] == 1.0                      # covered only by window (0, 0)
    assert np.isclose(p[7, 7], 1 / 4)          # covered by 4 windows, one of them 1
    assert p[15, 15] == 0


def test_roi_respects_lit_and_removes_small_islands_and_holes():
    prob = np.zeros((100, 100), np.float32)
    prob[10:60, 10:60] = 0.9                   # main region
    prob[30:33, 30:33] = 0.1                   # tiny hole -> filled
    prob[80:83, 80:83] = 0.9                   # tiny island -> removed
    lit = np.ones((100, 100), bool)
    lit[10:60, 55:60] = False                  # unlit strip stays out of the ROI
    roi = roi_from_prob(prob, lit, 0.5, 50)
    assert roi[31, 31] and not roi[81, 81] and not roi[20, 57] and roi[20, 20]
    assert not (roi & ~lit).any()


def test_largest_component():
    m = np.zeros((50, 50), bool)
    m[0:10, 0:10] = True
    m[20:45, 20:45] = True
    assert largest_component(m).sum() == 25 * 25


def test_folds_are_by_image_and_balanced():
    imgs = pd.DataFrame({"image_id": [f"i{k}" for k in range(40)], "poor_share": np.linspace(0, 1, 40)})
    folds = make_folds(imgs, 5, 0)
    assert set(folds) == set(imgs["image_id"]) and sorted(set(folds.values())) == [0, 1, 2, 3, 4]
    per = pd.Series(folds).value_counts()
    assert (per == 8).all()
    mean_poor = imgs.assign(f=imgs["image_id"].map(folds)).groupby("f")["poor_share"].mean()
    assert mean_poor.max() - mean_poor.min() < 0.1


def test_features_separate_cells_from_blur_and_dark():
    """A regular cell pattern has a strong spectral peak at the cell spacing; blur and darkness do not."""
    s, cell = 162, 28.2
    yy, xx = np.mgrid[:s, :s]
    cells = (127 + 100 * np.cos(2 * np.pi * xx / cell) * np.cos(2 * np.pi * yy / cell)).astype(np.uint8)
    flat_noise = np.random.default_rng(0).integers(100, 140, (s, s)).astype(np.uint8)
    lit = np.full((s, s), 255, np.uint8)
    f_cells = dict(zip(FEATURES, tile_features(np.stack([cells, cells, lit]), cell)))
    f_noise = dict(zip(FEATURES, tile_features(np.stack([flat_noise, flat_noise, lit]), cell)))
    f_dark = dict(zip(FEATURES, tile_features(np.stack([cells, cells, 0 * lit]), cell)))
    assert f_cells["cell_peak"] > 5 * f_noise["cell_peak"]
    assert f_dark["lit_share"] == 0 and f_cells["lit_share"] == 1
