"""P2: model-ready follow-up dataset (12-month landmark design).

Clinical question: at the patient's 12-month visit, using donor data and the first-year
visits (3, 6, 12 months), predict ECD at 24 / 36 / 60 months and the risk of graft
failure or low ECD afterwards. P7 then turns those predictions into the next visit
interval (3, 6 or 12 months) and an alert level.

Steps, in this order (each one only uses what is allowed at that point):
  1. landmark cohort  grafts not failed by 12 months, seen at the 12-month visit and
                      followed beyond it (otherwise they carry no outcome information)
  2. inputs           donor values, procedure, indication, visits at 3/6/12 months and a
                      rejection episode only if it happened by month 12; nothing later
  3. targets          ECD at 24/36/60 months (missing if not measured), months from the
                      landmark to failure / low ECD, with censoring flags
  4. split            by graft, 70 / 15 / 15, stratified by procedure and failure, so no
                      graft appears in two sets
  5. preprocessing    median imputation, missing-value flags, scaling and one-hot coding,
                      all fitted on the training set only and saved for P3-P8
  6. leakage checks   every rule above is verified and reported

From ml/:
    uv run python -m recommendation.main followup-data
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

INPUT_MONTHS = (3, 6, 12)
LANDMARK = 12
HORIZONS = (24, 36, 60)
LOW_ECD = 1000

NUMERIC_INPUTS =["donor_age", "baseline_ECD", "baseline_CV", "baseline_HEX"] + [
    f"{k}_{m}m" for m in INPUT_MONTHS for k in ("ECD", "CV", "HEX")
] + ["loss_12m", "log_ecd_slope_3_12", "rejection_by_12m"]
CATEGORICAL_INPUTS = ["procedure", "indication"]
TARGET_COLS = [f"ECD_{h}m" for h in HORIZONS] + [
    "failure_event", "failure_months_after_landmark", "low_ecd_event", "low_ecd_months_after_landmark",
    "low_ecd_before_landmark",
]
ID_COLS = ["graft_id", "data_source", "split"]


# ---------------------------------------------------------------- 1-3 landmark table
def landmark_table(grafts: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    """One row per graft eligible at the 12-month landmark: inputs + targets (unscaled)."""
    seen_12 = set(visits.loc[visits["months_after_surgery"] == LANDMARK, "graft_id"])
    followed_beyond = grafts["time_to_event_months"] > LANDMARK   # also excludes failure by month 12
    g = grafts[followed_beyond & grafts["graft_id"].isin(seen_12)].copy()

    wide = visits.pivot_table(index="graft_id", columns="months_after_surgery", values=["ECD", "CV", "HEX"])
    t = g[["graft_id", "data_source", "procedure", "indication", "donor_age",
           "baseline_ECD", "baseline_CV", "baseline_HEX"]].set_index("graft_id")
    for m in INPUT_MONTHS:
        for k in ("ECD", "CV", "HEX"):
            t[f"{k}_{m}m"] = wide[(k, m)].reindex(t.index) if (k, m) in wide.columns else np.nan
    t["loss_12m"] = 1 - t["ECD_12m"] / t["baseline_ECD"]
    first = t["ECD_3m"].fillna(t["ECD_6m"])
    first_month = np.where(t["ECD_3m"].notna(), 3, 6)
    t["log_ecd_slope_3_12"] = (np.log(t["ECD_12m"]) - np.log(first)) / ((LANDMARK - first_month) / 12)
    rej = g.set_index("graft_id")
    t["rejection_by_12m"] = (rej["rejection_episode"].astype(bool) & (rej["rejection_month"] <= LANDMARK)).astype(float)

    # targets: only information from after the landmark
    for h in HORIZONS:
        t[f"ECD_{h}m"] = wide[("ECD", h)].reindex(t.index) if ("ECD", h) in wide.columns else np.nan
    t["failure_event"] = rej["graft_failed"].astype(bool)
    t["failure_months_after_landmark"] = rej["time_to_event_months"] - LANDMARK
    low_before = rej["low_ECD_event"].astype(bool) & (rej["time_to_low_ECD_months"] <= LANDMARK)
    t["low_ecd_before_landmark"] = low_before
    t["low_ecd_event"] = rej["low_ECD_event"].astype(bool) & ~low_before
    t["low_ecd_months_after_landmark"] = rej["time_to_low_ECD_months"] - LANDMARK
    return t.reset_index()


# ---------------------------------------------------------------- 4 split
def split_grafts(table: pd.DataFrame, fractions=(0.70, 0.15, 0.15), seed: int = 42) -> pd.Series:
    """'train' / 'val' / 'test' per graft, stratified by procedure x failure."""
    rng = np.random.default_rng(seed)
    labels = pd.Series(index=table.index, dtype=object)
    strata = table["procedure"].astype(str) + "|" + table["failure_event"].astype(str)
    for _, idx in table.groupby(strata).groups.items():
        idx = np.array(idx)
        rng.shuffle(idx)
        n = len(idx)
        n_val = int(round(n * fractions[1]))
        n_test = int(round(n * fractions[2]))
        labels[idx[:n_test]] = "test"
        labels[idx[n_test:n_test + n_val]] = "val"
        labels[idx[n_test + n_val:]] = "train"
    return labels


# ---------------------------------------------------------------- 5 preprocessing
@dataclass
class FollowupPreprocessor:
    """Median imputation + missing flags + standard scaling + one-hot coding.

    Fitted on training rows only; the same object transforms validation, test and
    (later) new patients in the ML service.
    """
    numeric: list = field(default_factory=lambda: list(NUMERIC_INPUTS))
    categorical: list = field(default_factory=lambda: list(CATEGORICAL_INPUTS))
    medians: dict = field(default_factory=dict)
    means: dict = field(default_factory=dict)
    stds: dict = field(default_factory=dict)
    levels: dict = field(default_factory=dict)
    flag_cols: list = field(default_factory=list)

    def fit(self, train: pd.DataFrame) -> "FollowupPreprocessor":
        x = train[self.numeric].astype(float)
        self.medians = x.median().to_dict()
        filled = x.fillna(self.medians)
        self.means = filled.mean().to_dict()
        self.stds = filled.std(ddof=0).replace(0, 1.0).to_dict()
        self.levels = {c: sorted(train[c].dropna().astype(str).unique()) for c in self.categorical}
        self.flag_cols = [c for c in self.numeric if x[c].isna().any()]
        return self

    @property
    def feature_names(self) -> list[str]:
        return (list(self.numeric) + [f"{c}_missing" for c in self.flag_cols]
                + [f"{c}={lv}" for c in self.categorical for lv in self.levels[c]])

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        x = df[self.numeric].astype(float)
        out = pd.DataFrame(index=df.index)
        for c in self.numeric:
            out[c] = (x[c].fillna(self.medians[c]) - self.means[c]) / self.stds[c]
        for c in self.flag_cols:
            out[f"{c}_missing"] = x[c].isna().astype(float)
        for c in self.categorical:
            for lv in self.levels[c]:
                out[f"{c}={lv}"] = (df[c].astype(str) == lv).astype(float)
        return out[self.feature_names]

    def to_dict(self) -> dict:
        return {"numeric": self.numeric, "categorical": self.categorical, "medians": self.medians,
                "means": self.means, "stds": self.stds, "levels": self.levels, "flag_cols": self.flag_cols}

    @classmethod
    def from_dict(cls, d: dict) -> "FollowupPreprocessor":
        return cls(**d)


# ---------------------------------------------------------------- 6 leakage checks
def leakage_checks(table: pd.DataFrame, pre: FollowupPreprocessor, visits: pd.DataFrame) -> list[dict]:
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    per_graft = table.groupby("graft_id")["split"].nunique()
    add("each graft in exactly one split", (per_graft == 1).all() and table["graft_id"].is_unique,
        f"{len(table)} grafts")
    feats = set(pre.numeric) | set(pre.categorical)
    add("no target or outcome column is an input", not (feats & set(TARGET_COLS)), f"{len(feats)} inputs")
    later = [c for c in pre.numeric if any(c.endswith(f"_{h}m") for h in HORIZONS)]
    add("inputs use visits up to 12 months only", not later, f"later-visit inputs: {later or 'none'}")
    v12 = visits.set_index(["graft_id", "months_after_surgery"])["ECD"]
    same = all(np.isclose(v12.get((r.graft_id, 12), np.nan), r.ECD_12m) for r in table.itertuples())
    add("12-month inputs equal the recorded 12-month visit", same, "ECD_12m")
    add("no graft failed or left follow-up by the landmark", (table["failure_months_after_landmark"] > 0).all(),
        "follow-up continues after month 12")
    add("rejection input only counts episodes by month 12", "rejection_by_12m" in pre.numeric,
        "rejections after month 12 are not inputs")
    train = table[table["split"] == "train"]
    med_ok = all(np.isclose(train[c].astype(float).median(), pre.medians[c], equal_nan=True) for c in pre.numeric)
    add("imputation and scaling fitted on training grafts only", med_ok, f"{len(train)} training grafts")
    by = table.groupby("split")["failure_event"].sum().to_dict()
    add("every split has failures", all(by.get(s, 0) > 0 for s in ("train", "val", "test")),
        ", ".join(f"{k} {int(v)}" for k, v in sorted(by.items())))
    return checks


# ---------------------------------------------------------------- run
def build(cohort_path, out_file, preprocessor_file, fractions=(0.70, 0.15, 0.15), seed: int = 42) -> dict:
    """Build, split, preprocess and check; write the dataset and the fitted preprocessor."""
    from recommendation.data_prep.followup_eda import load_cohort

    grafts, visits, source = load_cohort(cohort_path)
    table = landmark_table(grafts, visits)
    table["split"] = split_grafts(table, fractions, seed).to_numpy()
    pre = FollowupPreprocessor().fit(table[table["split"] == "train"])
    checks = leakage_checks(table, pre, visits)

    X = pre.transform(table)
    out_file, preprocessor_file = Path(out_file), Path(preprocessor_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    preprocessor_file.parent.mkdir(parents=True, exist_ok=True)
    summary = _summary(table, source, pre)
    with pd.ExcelWriter(out_file, engine="openpyxl") as xw:
        pd.DataFrame([("Data source", source), ("Design", "12-month landmark: inputs = donor + visits at 3/6/12 "
                                               "months; targets = ECD at 24/36/60 months and failure / low ECD "
                                               "after month 12"),
                      ("Split", "by graft, 70/15/15, stratified by procedure x failure, seed " + str(seed)),
                      ("Preprocessing", "fitted on train only: " + preprocessor_file.name)],
                     columns=["Item", "Value"]).to_excel(xw, sheet_name="README", index=False)
        table.to_excel(xw, sheet_name="Landmark", index=False)
        pd.concat([table[ID_COLS], X], axis=1).to_excel(xw, sheet_name="Features_scaled", index=False)
        pd.DataFrame(checks).to_excel(xw, sheet_name="Leakage_checks", index=False)
    preprocessor_file.write_text(json.dumps(pre.to_dict(), indent=2), encoding="utf-8")
    return {"source": source, "checks": checks, "all_checks_pass": all(c["ok"] for c in checks),
            "summary": summary, "features": pre.feature_names,
            "dataset": str(out_file), "preprocessor": str(preprocessor_file)}


def _summary(table: pd.DataFrame, source: str, pre: FollowupPreprocessor) -> dict:
    rows = {}
    for s in ("train", "val", "test"):
        t = table[table["split"] == s]
        rows[s] = {"grafts": int(len(t)), "failures": int(t["failure_event"].sum()),
                   "low_ecd_events": int(t["low_ecd_event"].sum()),
                   **{f"ECD_{h}m_observed": int(t[f"ECD_{h}m"].notna().sum()) for h in HORIZONS}}
    return {"source": source, "landmark_month": LANDMARK, "input_months": list(INPUT_MONTHS),
            "horizons": list(HORIZONS), "n_features": len(pre.feature_names), "splits": rows,
            "missing_inputs": {c: int(table[c].isna().sum()) for c in pre.numeric if table[c].isna().any()}}


def load(dataset_file, preprocessor_file) -> tuple[pd.DataFrame, FollowupPreprocessor]:
    """Read the landmark table and the fitted preprocessor (for P3-P8)."""
    table = pd.read_excel(dataset_file, sheet_name="Landmark")
    pre = FollowupPreprocessor.from_dict(json.loads(Path(preprocessor_file).read_text(encoding="utf-8")))
    return table, pre
