"""MCDA baseline for ranking candidate donor tissues against a recipient request.

Each candidate gets a score in [0, 1] per criterion; the final score is a weighted sum.
Weights come from config.yaml (matching.weights); they are placeholders until clinicians set them (e.g. through AHP pairwise
comparison) and must be recorded with every run.

Hard rule: tissue with any positive serology is excluded before scoring.
"""
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

GRADE_NUM = {"A+": 3, "A": 2, "B": 1, "C": 0}

# Procedures where the donor endothelium is transplanted, so endothelial quality matters.
ENDOTHELIAL_PROCEDURES = {"PK", "DSEK", "DMEK"}


@dataclass(frozen=True)
class Weights:
    grade_fit: float = 0.35
    endothelium: float = 0.30
    freshness: float = 0.15
    donor_age: float = 0.10
    preservation_time: float = 0.10

    def normalised(self) -> dict[str, float]:
        w = asdict(self)
        total = sum(w.values())
        return {k: v / total for k, v in w.items()}


def _clip01(x):
    return np.clip(x, 0.0, 1.0)


def grade_fit(gap: pd.Series) -> pd.Series:
    """1.0 for an exact grade match, slightly less when exceeding the request
    (keeps higher-grade tissue for recipients who need it), low when below."""
    score = pd.Series(np.nan, index=gap.index)
    score[gap == 0] = 1.0
    score[gap > 0] = 1.0 - 0.1 * gap[gap > 0]
    score[gap == -1] = 0.3
    score[gap <= -2] = 0.0
    return score.fillna(0.5)


def endothelium(df: pd.DataFrame) -> pd.Series:
    """Combine ECD, CV and HEX into one 0-1 quality score."""
    ecd = _clip01((df["Cand_ECD"] - 2000) / 1500)   # 2000 → 0, 3500 → 1
    cv = _clip01((50 - df["Cand_CV"]) / 25)          # 50 → 0, 25 → 1
    hex_ = _clip01((df["Cand_HEX"] - 40) / 30)       # 40 → 0, 70 → 1
    return pd.concat([ecd, cv, hex_], axis=1).mean(axis=1).fillna(0.5)


def freshness(days: pd.Series) -> pd.Series:
    return _clip01(1 - days / 14).fillna(0.5)


def donor_age(age: pd.Series) -> pd.Series:
    return _clip01((80 - age) / 50).fillna(0.5)     # 30 → 1, 80 → 0


def preservation_time(hours: pd.Series) -> pd.Series:
    return _clip01((8 - hours) / 7).fillna(0.5)     # ≤1 h → 1, 8 h → 0


def score(pairs: pd.DataFrame, weights: Weights = Weights()) -> pd.DataFrame:
    """Return ``pairs`` with per-criterion scores, ``MCDA_Score`` and ``MCDA_Rank``.

    Rows failing the serology hard filter get ``Excluded = True`` and no rank.
    """
    df = pairs.copy()
    df["Excluded"] = df["Cand_Serology_Clear"].eq("No")

    df["s_grade_fit"] = grade_fit(df["Grade_Gap"])
    df["s_endothelium"] = endothelium(df)
    df["s_freshness"] = freshness(df["Cand_Days_In_Storage"])
    df["s_donor_age"] = donor_age(df["Cand_Donor_Age"])
    df["s_preservation_time"] = preservation_time(df["Cand_Death_to_Preservation_h"])

    w = weights.normalised()
    # Endothelium does not matter for anterior lamellar / tectonic grafts:
    # move its weight to grade fit for those procedures.
    endo_relevant = df["Surgery_Type"].isin(ENDOTHELIAL_PROCEDURES)
    w_endo = np.where(endo_relevant, w["endothelium"], 0.0)
    w_grade = w["grade_fit"] + (w["endothelium"] - w_endo)

    df["MCDA_Score"] = (
        w_grade * df["s_grade_fit"]
        + w_endo * df["s_endothelium"]
        + w["freshness"] * df["s_freshness"]
        + w["donor_age"] * df["s_donor_age"]
        + w["preservation_time"] * df["s_preservation_time"]
    )
    df.loc[df["Excluded"], "MCDA_Score"] = np.nan
    df["MCDA_Rank"] = df.groupby("Request_ID")["MCDA_Score"].rank(ascending=False, method="first")
    return df


def explain(row: pd.Series, weights: Weights = Weights()) -> str:
    """One-line reason for a candidate's score, for the 'Why #1?' panel."""
    parts = {
        "grade fit": row["s_grade_fit"],
        "endothelium": row["s_endothelium"],
        "freshness": row["s_freshness"],
        "donor age": row["s_donor_age"],
        "preservation time": row["s_preservation_time"],
    }
    top = sorted(parts.items(), key=lambda kv: kv[1], reverse=True)[:2]
    flags = []
    if row.get("Cand_Serology_Clear") == "Unknown":
        flags.append("serology not confirmed")
    reason = ", ".join(f"{k} {v:.2f}" for k, v in top)
    return reason + (f" ({'; '.join(flags)})" if flags else "")
