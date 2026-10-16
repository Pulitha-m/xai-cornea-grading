"""
Inference normalisation fix: model input is normalised over the lit tissue only,
so a large dark area cannot change how the tissue itself is scaled.

Run (from ml/cellular/):  python -m pytest tests/test_normalise.py -q
"""

from __future__ import annotations

import numpy as np
import pytest

from segmentation.infer_full import normalise_lit


def tissue(rng, shape=(100, 100)):
    return rng.uniform(0.3, 0.7, size=shape).astype(np.float32)


def test_lit_tissue_spans_0_to_1_and_dark_is_0():
    rng = np.random.default_rng(0)
    x = np.zeros((200, 200), np.float32)
    lit = np.zeros(x.shape, bool)
    lit[50:150, 50:150] = True
    x[lit] = tissue(rng).ravel()
    out = normalise_lit(x, lit, 1, 99.8)
    assert out[~lit].max() == 0
    assert out[lit].min() == 0 and out[lit].max() == 1
    assert np.percentile(out[lit], 1) < 0.02 and np.percentile(out[lit], 99) > 0.98


def test_dark_area_size_does_not_change_the_tissue():
    """The same tissue gets the same input values with a small or a large dark area."""
    rng = np.random.default_rng(1)
    t = tissue(rng)
    small, large = np.zeros((120, 120), np.float32), np.zeros((400, 400), np.float32)
    small[10:110, 10:110] = t
    large[10:110, 10:110] = t
    a = normalise_lit(small, small > 0, 1, 99.8)[10:110, 10:110]
    b = normalise_lit(large, large > 0, 1, 99.8)[10:110, 10:110]
    assert np.allclose(a, b)


def test_matches_crop_normalisation_used_in_training():
    """On a fully lit crop, lit normalisation equals plain percentile normalisation (training)."""
    normalize = pytest.importorskip("csbdeep.utils").normalize      # installed in Colab with StarDist
    rng = np.random.default_rng(2)
    t = tissue(rng)
    ours = normalise_lit(t, np.ones(t.shape, bool), 1, 99.8)
    training = np.clip(normalize(t, 1, 99.8), 0, 1)
    assert np.allclose(ours, training, atol=1e-4)
