"""Tests for P7 follow-up recommendation rules. Scenario rows are made up."""
import pandas as pd

from recommendation.followup import recommend as R


def _p(**over):
    """A healthy graft at its 12-month visit; override fields per scenario."""
    base = {"ecd_24m": 1600.0, "ecd_24m_low": 1450.0, "ecd_24m_high": 1750.0,
            "ecd_36m": 1450.0, "ecd_36m_low": 1200.0, "ecd_36m_high": 1650.0,
            "ecd_60m": 1250.0, "ecd_60m_low": 900.0, "ecd_60m_high": 1500.0,
            "failure_risk_12m": 0.0, "failure_risk_24m": 0.01, "low_ecd_risk_12m": 0.01, "low_ecd_risk_24m": 0.05,
            "ecd_12m": 1900.0, "loss_12m": 0.25, "rejection_by_12m": False, "already_low_ecd": False}
    base.update(over)
    return pd.DataFrame([base])


def _level(**over):
    return R.apply_rules(_p(**over)).iloc[0]


def test_healthy_graft_is_green_with_routine_yearly_visit():
    r = _level()
    assert r["alert"] == "green" and r["next_visit_months"] == 12
    assert r["actions"] == ["Routine follow-up"] and r["rules_fired"] == []


def test_rejection_is_always_red_and_prompts_rejection_review():
    r = _level(rejection_by_12m=True)
    assert r["alert"] == "red" and r["next_visit_months"] == 3
    assert "Review for graft rejection" in r["actions"]


def test_high_short_term_failure_risk_is_red():
    assert _level(failure_risk_12m=0.35, failure_risk_24m=0.5)["alert"] == "red"


def test_low_12_month_ecd_is_red():
    assert _level(ecd_12m=700.0)["alert"] == "red"


def test_moderate_risk_is_amber_with_repeat_microscopy():
    r = _level(failure_risk_24m=0.08)
    assert r["alert"] == "amber" and r["next_visit_months"] == 6
    assert any("specular microscopy" in a for a in r["actions"])


def test_projected_failure_prompts_regraft_assessment():
    r = _level(ecd_36m=450.0, ecd_60m_low=300.0, failure_risk_24m=0.3)
    assert any("regraft" in a for a in r["actions"])


def test_red_overrides_amber_and_lists_every_reason():
    r = _level(rejection_by_12m=True, loss_12m=0.5, failure_risk_24m=0.1)
    assert r["alert"] == "red"
    assert len(r["rules_fired"]) >= 3


def test_thresholds_come_from_the_rules_given():
    strict = {**R.DEFAULT_RULES, "amber": {**R.DEFAULT_RULES["amber"], "loss_12m_at_least": 0.20}}
    assert R.apply_rules(_p(), strict).iloc[0]["alert"] == "amber"
    assert R.apply_rules(_p(), R.DEFAULT_RULES).iloc[0]["alert"] == "green"


def test_outcomes_safety_and_visit_burden():
    rec = pd.DataFrame({"alert": ["green", "green", "amber", "red"], "next_visit_months": [12, 12, 6, 3]})
    table = pd.DataFrame({"failure_event": [False, True, True, True],
                          "failure_months_after_landmark": [40, 30, 10, 5],
                          "low_ecd_event": [False, True, True, True],
                          "low_ecd_months_after_landmark": [40, 20, 8, 2],
                          "low_ecd_before_landmark": [False] * 4})
    out = R.outcomes_by_alert(rec, table)
    assert out.set_index("alert").loc["red", "failed_within_12m"] == 1
    assert R.safety(out) == {"green_failed_within_12m": 0, "green_grafts": 2}
    vb = R.visit_burden(rec)
    assert vb["recommended_visits_per_graft_year"] == (1 + 1 + 2 + 4) / 4
