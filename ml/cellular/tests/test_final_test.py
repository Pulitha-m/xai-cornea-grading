"""
Phase 7 — the freeze and the agreement statistics (no models, no test images).

Run (from ml/cellular/):  python -m pytest tests/test_final_test.py -q
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import load_config
from final_test import agreement_table, boot_ci, differences, dir_hash


def test_dir_hash_detects_any_change(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "w.h5").write_bytes(b"weights")
    h = dir_hash(tmp_path)
    assert h == dir_hash(tmp_path)                                  # stable
    (tmp_path / "a" / "w.h5").write_bytes(b"weightz")
    assert dir_hash(tmp_path) != h                                  # content
    (tmp_path / "a" / "w.h5").write_bytes(b"weights")
    assert dir_hash(tmp_path) == h
    (tmp_path / "a" / "w.h5").rename(tmp_path / "a" / "v.h5")
    assert dir_hash(tmp_path) != h                                  # name
    assert dir_hash(tmp_path / "missing") is None


def test_differences_lists_every_changed_field():
    frozen = {"git_commit": "abc", "models": {"roi": "1", "seg": "2"}, "um_per_px": 0.796}
    assert differences(frozen, dict(frozen)) == []
    now = {"git_commit": "abd", "models": {"roi": "1", "seg": "3"}, "um_per_px": 0.796}
    assert differences(frozen, now) == ["git_commit: frozen 'abc', now 'abd'", "models.seg: frozen '2', now '3'"]


def test_boot_ci_contains_the_estimate():
    rng = np.random.default_rng(0)
    ref = rng.uniform(2000, 3000, 200)
    ours = ref * (1 + rng.normal(0, 0.06, 200))
    ci = boot_ci(ours, ref, 5.0, 1000, 1)
    mape = np.mean(np.abs(100 * (ours - ref) / ref))
    within = 100 * np.mean(np.abs(100 * (ours - ref) / ref) <= 5)
    assert ci["mape_ci95"][0] < mape < ci["mape_ci95"][1]
    assert ci["within_ci95"][0] < within < ci["within_ci95"][1]
    assert ci == boot_ci(ours, ref, 5.0, 1000, 1)                   # reproducible


def test_targets_are_judged_by_mape():
    cfg = load_config()
    n = 100
    ref = np.full(n, 2500.0)
    s = pd.DataFrame({"ecd_cells_per_mm2": ref * 1.03, "konan_ecd": ref,              # 3 % error -> met (5 %)
                      "mean_area_um2": 400 * 1.12, "konan_mean_area": 400.0,         # 12 % -> not met (8 %)
                      "sd_area_um2": 100.0, "konan_sd": 100.0,
                      "cv_pct": 30.0, "konan_cv": 30.0, "hex_pct": 50.0, "konan_hex": 50.0})
    s.iloc[0, s.columns.get_loc("cv_pct")] = 31.0                   # avoid a constant column for rho
    tab = agreement_table(s, cfg)
    assert np.isclose(tab.loc["ECD", "MAPE %"], 3.0) and tab.loc["ECD", "target met (MAPE <= target)"]
    assert not tab.loc["mean area", "target met (MAPE <= target)"]
    assert tab.loc["ECD", "within target %"] == 100 and tab.loc["SD of area", "target met (MAPE <= target)"] is None
