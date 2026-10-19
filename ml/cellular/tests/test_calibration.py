"""
Phase 4 — scale calibration on synthetic numbers with a known answer.

Run (from ml/cellular/):  python -m pytest tests/test_calibration.py -q
"""

from __future__ import annotations

import numpy as np

from calibration.scale import agreement, ecd_from_area, estimate_scale, per_image_scale


def test_known_scale_is_recovered_exactly():
    area_px = np.array([500.0, 620.0, 710.0, 880.0])
    s = per_image_scale(area_px * 0.8 ** 2, area_px)
    assert np.allclose(s, 0.8)
    assert np.isclose(estimate_scale(s, 200, 0)["um_per_px"], 0.8)


def test_missing_or_zero_area_gives_nan_and_is_ignored():
    s = per_image_scale([400.0, 400.0, 400.0], [625.0, 0.0, np.nan])
    assert np.isclose(s[0], 0.8) and np.isnan(s[1]) and np.isnan(s[2])
    assert estimate_scale(s, 100, 0)["n_images"] == 1


def test_median_is_robust_to_region_mismatch_outliers():
    rng = np.random.default_rng(0)
    s = np.r_[rng.normal(0.8, 0.01, 40), [1.3, 1.5, 0.4]]     # a few images where Konan's region differs
    est = estimate_scale(s, 2000, 1)
    assert abs(est["um_per_px"] - 0.8) < 0.01
    assert est["ci_low"] <= est["um_per_px"] <= est["ci_high"]
    assert est["ci_high"] - est["ci_low"] < 0.02


def test_bootstrap_is_reproducible():
    s = np.random.default_rng(3).normal(0.8, 0.05, 60)
    assert estimate_scale(s, 500, 7) == estimate_scale(s, 500, 7)


def test_ecd_from_area():
    # 625 px^2 at 0.8 um/px = 400 um^2 per cell -> 2500 cells/mm^2
    assert np.isclose(ecd_from_area(625.0, 0.8), 2500.0)


def test_agreement():
    ref = np.array([2000.0, 2500.0, 3000.0])
    a = agreement(ref, ref, 5)
    assert a["bias_%"] == 0 and a["mape_%"] == 0 and a["within_5%_share"] == 1 and a["ba_mean_diff"] == 0
    b = agreement(ref * 1.1, ref, 5)
    assert np.isclose(b["bias_%"], 10) and b["within_5%_share"] == 0 and np.isclose(b["rho"], 1)
