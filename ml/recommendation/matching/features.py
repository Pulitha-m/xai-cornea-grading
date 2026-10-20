"""Feature preparation for the machine-learning ranker.

Turns Ranking_Pairs rows into a numeric feature table (one row per request-candidate
pair). Only information available on the decision date is used: identifiers, dates,
the label and outcome columns are never features.

Feature groups (23 features):
  grade        how the candidate's grade compares with the requested grade
  endothelium  ECD/CV/HEX, counted only where the endothelium is transplanted
  logistics    days in storage, donor age, death-to-preservation time
  safety       serology not confirmed
  pool         how the candidate compares with the other candidates for the same
               request (percentile within the pool: 0 = worst, 1 = best)
  criteria     the five MCDA criterion scores (0-1), so the model can learn its own
               weights for them instead of using the placeholder weights

Missing values stay as NaN; the model pipeline fills them (median) and an explicit
flag records missing endothelial measures.
"""
import pandas as pd

from recommendation.matching import mcda

GRADE_NUM = {"A+": 3, "A": 2, "B": 1}

# Columns that must never be used as features (identifiers, dates, answers, outcomes).
NOT_FEATURES = {
    "Request_ID", "Candidate_Record_ID", "Request_Date", "Decision_Date",
    "Label_Allocated", "Positive_Outside_Window", "Outcome_Grade_Request_Met",
}

FEATURE_GROUPS = {
    "grade": ["Grade_Gap", "Grade_Exact", "Grade_Below", "Grade_Abs_Gap", "Cand_Grade_Num"],
    "endothelium": ["ECD_if_Endo", "Endo_Procedure", "Endo_Missing"],
    "logistics": ["Cand_Days_In_Storage"],
    "safety": ["Serology_Unknown"],
    "pool": ["Grade_Abs_Gap_PoolPct", "Cand_ECD_PoolPct", "Cand_CV_PoolPct", "Cand_HEX_PoolPct",
             "Cand_Days_In_Storage_PoolPct", "Cand_Donor_Age_PoolPct",
             "Cand_Death_to_Preservation_h_PoolPct", "Pool_Size"],
    "criteria": ["s_grade_fit", "s_endothelium", "s_freshness", "s_donor_age", "s_preservation_time"],
}
FEATURES = [f for group in FEATURE_GROUPS.values() for f in group]

# For pool percentiles: +1 means higher is better, -1 means lower is better.
POOL_DIRECTION = {
    "Cand_ECD": 1, "Cand_HEX": 1, "Cand_CV": -1,
    "Cand_Days_In_Storage": -1, "Cand_Donor_Age": -1, "Cand_Death_to_Preservation_h": -1,
}


def build_features(pairs: pd.DataFrame) -> pd.DataFrame:
    """Return the 23-column feature table, same index as ``pairs``."""
    df = pairs
    num = lambda c: pd.to_numeric(df[c], errors="coerce")  # noqa: E731
    X = pd.DataFrame(index=df.index)

    # grade
    gap = num("Grade_Gap")
    X["Grade_Gap"] = gap
    X["Grade_Exact"] = (gap == 0).astype(float)
    X["Grade_Below"] = (gap < 0).astype(float)
    X["Grade_Abs_Gap"] = gap.abs()
    X["Cand_Grade_Num"] = df["Cand_Tissue_Grade"].map(GRADE_NUM)

    # endothelium (only meaningful for PK / DSEK / DMEK)
    endo = df["Surgery_Type"].isin(mcda.ENDOTHELIAL_PROCEDURES)
    X["ECD_if_Endo"] = num("Cand_ECD").where(endo)
    X["Endo_Procedure"] = endo.astype(float)
    X["Endo_Missing"] = df["Cand_ECD"].isna().astype(float)

    # logistics and safety
    X["Cand_Days_In_Storage"] = num("Cand_Days_In_Storage")
    X["Serology_Unknown"] = df["Cand_Serology_Clear"].eq("Unknown").astype(float)

    # position within the request's candidate pool
    g = df["Request_ID"]
    X["Grade_Abs_Gap_PoolPct"] = (-X["Grade_Abs_Gap"]).groupby(g).rank(pct=True)
    for c, sign in POOL_DIRECTION.items():
        X[f"{c}_PoolPct"] = (num(c) * sign).groupby(g).rank(pct=True)
    X["Pool_Size"] = g.map(g.value_counts()).astype(float)

    # MCDA criterion scores (no weights involved)
    X["s_grade_fit"] = mcda.grade_fit(gap)
    X["s_endothelium"] = mcda.endothelium(df)
    X["s_freshness"] = mcda.freshness(num("Cand_Days_In_Storage"))
    X["s_donor_age"] = mcda.donor_age(num("Cand_Donor_Age"))
    X["s_preservation_time"] = mcda.preservation_time(num("Cand_Death_to_Preservation_h"))

    X = X[FEATURES].astype(float)
    assert not (set(X.columns) & NOT_FEATURES), "identifier or label used as a feature"
    return X
