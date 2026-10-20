"""The Part B report builds from whatever results exist and names the commands for missing ones."""
import json

from recommendation.reporting.followup_report import build_followup_report


def test_report_lists_missing_stages_with_their_commands(tmp_path):
    cfg = {"paths": {"outputs": str(tmp_path / "out"), "models": str(tmp_path / "models"),
                     "followup_dataset": str(tmp_path / "none.xlsx"), "followup_cohort": str(tmp_path / "none.xlsx")}}
    path, log = build_followup_report(cfg)
    page = path.read_text(encoding="utf-8")
    assert path.name == "followup_report.html" and log == []
    for command in ("followup-eda", "followup-data", "trajectory", "risk", "followup-robustness"):
        assert f"recommendation.main {command}" in page


def test_report_shows_a_stage_and_its_data_source(tmp_path):
    out = tmp_path / "out" / "robustness"
    out.mkdir(parents=True)
    scen = {"grafts": 400, "failures": 20, "trajectory_mae_baseline": 170.0, "trajectory_mae_gbm": 150.0,
            "gbm_gain_pct": 11.8, "graft_failure_cox_c_index": 0.9, "graft_failure_deepsurv_c_index": 0.88,
            "low_ecd_cox_c_index": 0.85, "low_ecd_deepsurv_c_index": 0.84, "literature_patterns_met": "5/5"}
    (out / "robustness_results.json").write_text(json.dumps({
        "scenarios": {"reference": scen}, "gbm_beats_baseline_in": "1/1", "cox_as_good_as_deepsurv_in": "1/1"}))
    cfg = {"paths": {"outputs": str(tmp_path / "out"), "models": str(tmp_path / "m"),
                     "followup_dataset": str(tmp_path / "x.xlsx"), "followup_cohort": str(tmp_path / "x.xlsx")}}
    path, log = build_followup_report(cfg)
    page = path.read_text(encoding="utf-8")
    assert "Stage 8. Robustness" in page and "1/1" in page
    assert any("robustness" in line for line in log)
