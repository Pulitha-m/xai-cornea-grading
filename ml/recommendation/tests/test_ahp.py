"""Tests for AHP weights. Made-up judgements only."""
import numpy as np
import pytest

from recommendation.matching.ahp import CRITERIA, PAIRS, apply_to_config, combine, matrix, weights_and_cr


def _consistent(true_w):
    """Perfectly consistent answers derived from known weights."""
    ans = {}
    for a, b in PAIRS:
        r = true_w[a] / true_w[b]
        ans[(a, b)] = ("A", r) if r >= 1 else ("B", 1 / r)
    return ans


def test_consistent_answers_recover_weights_with_cr_zero():
    true_w = {"grade_fit": 0.35, "endothelium": 0.30, "serology": 0.20, "freshness": 0.10,
              "surgery_compatibility": 0.05}
    w, cr = weights_and_cr(matrix(_consistent(true_w)))
    assert cr == pytest.approx(0, abs=1e-3)
    for k in CRITERIA:
        assert w[k] == pytest.approx(true_w[k], abs=1e-3)


def test_equal_answers_give_equal_weights():
    w, cr = weights_and_cr(matrix({p: ("Equal", 1) for p in PAIRS}))
    assert all(v == pytest.approx(0.2) for v in w.values())


def test_contradictory_answers_are_flagged():
    ans = {p: ("Equal", 1) for p in PAIRS}
    ans[("grade_fit", "endothelium")] = ("A", 9)
    ans[("endothelium", "freshness")] = ("A", 9)
    ans[("grade_fit", "freshness")] = ("B", 9)       # grade > endo > fresh, but fresh > grade
    _, cr = weights_and_cr(matrix(ans))
    assert cr >= 0.10


def test_strength_must_be_1_to_9():
    with pytest.raises(ValueError):
        matrix({("grade_fit", "endothelium"): ("A", 12)})


def test_combine_is_geometric_mean():
    a, b = matrix({("grade_fit", "endothelium"): ("A", 4)}), matrix({("grade_fit", "endothelium"): ("A", 1)})
    assert combine([a, b])[0, 1] == pytest.approx(2.0)
    assert np.allclose(combine([a, b]) * combine([a, b]).T, 1)


def test_apply_to_config_keeps_comments(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("matching:\n  weights_version: placeholder\n  weights:\n"
                   "    grade_fit: 0.35   # comment\n    endothelium: 0.30\n    serology: 0.20\n"
                   "    freshness: 0.10\n    surgery_compatibility: 0.05\n")
    apply_to_config(cfg, {"grade_fit": 0.5, "endothelium": 0.2, "serology": 0.1, "freshness": 0.1,
                          "surgery_compatibility": 0.1}, "ahp-test")
    text = cfg.read_text()
    assert "weights_version: ahp-test" in text and "grade_fit: 0.5   # comment" in text
