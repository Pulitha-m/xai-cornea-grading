import ast
import math
from pathlib import Path

import pytest

from pipelines.grading.feature_schema import load_schema, validate_features

MODELING_SETUP = Path(__file__).resolve().parents[2] / "ml" / "grading" / "scripts" / "modeling_setup.py"


def training_feature_lists():
    """Read the feature lists from the training code without importing its heavy dependencies."""
    tree = ast.parse(MODELING_SETUP.read_text(encoding="utf-8"))
    lists = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            lists[node.targets[0].id] = [elt.value for elt in node.value.elts]
    numeric = lists["ECD_FEATURES"] + lists["MORPHOLOGY_FEATURES"]
    return numeric, lists["CLINICAL_BINARY_FEATURES"], lists["CLINICAL_CATEGORICAL_FEATURES"]


def complete_payload(**overrides):
    payload = {
        "ECD_CD_cells_per_mm2": 2600.0, "CV": 35.0, "HEX_percent": 55.0, "SD": 130.0,
        "Total_Cell_Count": 104, "Total_Area_um2": 40000.0,
        **{f: 0 for f in training_feature_lists()[1]},
        **{f: None for f in training_feature_lists()[2]},
    }
    payload.update(overrides)
    return payload


@pytest.mark.skipif(not MODELING_SETUP.exists(), reason="training code not available")
def test_schema_matches_training_code_order_and_groups():
    numeric, binary, categorical = training_feature_lists()
    schema = load_schema()
    assert schema["feature_count"] == 24
    assert schema["order"] == numeric + binary + categorical
    types = {f["name"]: f["type"] for f in schema["features"]}
    assert all(types[f] == "number" for f in numeric)
    assert all(types[f] == "binary" for f in binary)
    assert all(types[f] == "category" for f in categorical)


def test_complete_payload_is_valid_and_ordered():
    result = validate_features(complete_payload())
    assert result.ok, result.errors
    assert len(result.values) == 24
    assert result.values[0] == 2600.0


@pytest.mark.parametrize("name", load_schema()["order"])
def test_each_feature_is_required(name):
    payload = complete_payload()
    del payload[name]
    result = validate_features(payload)
    assert [(e.code, e.field) for e in result.errors] == [("MISSING_CLINICAL_FEATURES", name)]


def test_unknown_feature_rejected():
    result = validate_features(complete_payload(Donor_Age=70))
    assert ("FEATURE_SCHEMA_MISMATCH", "Donor_Age") in [(e.code, e.field) for e in result.errors]


def test_null_is_allowed_and_zero_is_not_missing():
    nulls = validate_features({name: None for name in load_schema()["order"]})
    assert nulls.ok
    zero_binary = validate_features(complete_payload(Stroma_Has_Scar=0))
    assert zero_binary.ok and 0 in zero_binary.values


@pytest.mark.parametrize("value", ["2600", True, math.nan, math.inf, -math.inf, [2600]])
def test_malformed_numeric_rejected(value):
    result = validate_features(complete_payload(ECD_CD_cells_per_mm2=value))
    assert [e.code for e in result.errors] == ["INVALID_FEATURE_TYPE"]


@pytest.mark.parametrize("name,value", [
    ("ECD_CD_cells_per_mm2", 0), ("ECD_CD_cells_per_mm2", -100), ("HEX_percent", 101), ("SD", -1),
])
def test_impossible_values_rejected(name, value):
    result = validate_features(complete_payload(**{name: value}))
    assert [(e.code, e.field) for e in result.errors] == [("FEATURE_OUT_OF_RANGE", name)]


def test_fractional_cell_count_rejected():
    result = validate_features(complete_payload(Total_Cell_Count=104.5))
    assert [(e.code, e.field) for e in result.errors] == [("INVALID_FEATURE_TYPE", "Total_Cell_Count")]


@pytest.mark.parametrize("value", [0.5, 2, "1", "yes"])
def test_binary_must_be_zero_or_one(value):
    result = validate_features(complete_payload(Stroma_Has_Scar=value))
    assert [(e.code, e.field) for e in result.errors] == [("INVALID_FEATURE_TYPE", "Stroma_Has_Scar")]


def test_unknown_category_rejected_and_known_accepted():
    assert validate_features(complete_payload(Descemet_Fold_Severity="Mild")).ok
    result = validate_features(complete_payload(Descemet_Fold_Severity="Severe"))
    assert [(e.code, e.field) for e in result.errors] == [("FEATURE_OUT_OF_RANGE", "Descemet_Fold_Severity")]


def test_unusual_but_possible_value_is_a_warning_not_an_error():
    # Above the training maximum (4484) but physically possible; count/area kept consistent.
    result = validate_features(complete_payload(ECD_CD_cells_per_mm2=4600.0, Total_Cell_Count=184, Total_Area_um2=40000.0))
    assert result.ok
    assert [w.code for w in result.warnings] == ["FEATURE_OUTSIDE_TRAINING_RANGE"]


def test_inconsistent_ecd_is_flagged():
    result = validate_features(complete_payload(ECD_CD_cells_per_mm2=3000.0))
    assert result.ok
    assert "FEATURE_INCONSISTENT" in [w.code for w in result.warnings]
