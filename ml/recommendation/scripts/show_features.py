"""Show the ranker's 23 features, group by group, with summary statistics.

Prints only summaries (no individual records) and saves the same table to
outputs/features/feature_summary.xlsx (git-ignored) so it can be opened in Excel.

Run from ml/:
    uv run python -m recommendation.scripts.show_features
"""
from pathlib import Path

import pandas as pd

from recommendation.matching.features import FEATURE_GROUPS, build_features

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "processed" / "matching_dataset.xlsx"
OUT = ROOT / "outputs" / "features"
OUT.mkdir(parents=True, exist_ok=True)

DESCRIPTION = {
    "Grade_Gap": "candidate grade minus requested grade (A+=3, A=2, B=1)",
    "Grade_Exact": "1 if the grade exactly matches the request",
    "Grade_Below": "1 if the grade is lower than requested",
    "Grade_Abs_Gap": "size of the grade difference, either direction",
    "Cand_Grade_Num": "candidate grade as a number (A+=3, A=2, B=1)",
    "ECD_if_Endo": "ECD, only for PK/DSEK/DMEK (else missing)",
    "Endo_Procedure": "1 if the surgery transplants the endothelium",
    "Endo_Missing": "1 if the cornea has no ECD/CV/HEX measurement",
    "Cand_Days_In_Storage": "days the cornea had been stored at decision date",
    "Serology_Unknown": "1 if serology is not confirmed",
    "Grade_Abs_Gap_PoolPct": "grade closeness vs the other candidates (1 = closest)",
    "Cand_ECD_PoolPct": "ECD vs the other candidates (1 = highest)",
    "Cand_CV_PoolPct": "CV vs the other candidates (1 = lowest, best)",
    "Cand_HEX_PoolPct": "HEX vs the other candidates (1 = highest)",
    "Cand_Days_In_Storage_PoolPct": "freshness vs the other candidates (1 = freshest)",
    "Cand_Donor_Age_PoolPct": "donor age vs the other candidates (1 = youngest)",
    "Cand_Death_to_Preservation_h_PoolPct": "preservation speed vs others (1 = fastest)",
    "Pool_Size": "number of candidates available for this request",
    "s_grade_fit": "MCDA grade-fit score (0-1)",
    "s_endothelium": "MCDA endothelium score from ECD/CV/HEX (0-1)",
    "s_freshness": "MCDA freshness score (0-1)",
    "s_donor_age": "MCDA donor-age score (0-1)",
    "s_preservation_time": "MCDA preservation-time score (0-1)",
}

pairs = pd.read_excel(DATASET, sheet_name="Ranking_Pairs")
X = build_features(pairs)
chosen = pairs["Label_Allocated"] == 1

print(f"Rows: {len(X)}  Features: {X.shape[1]}\n")
rows = []
for group, cols in FEATURE_GROUPS.items():
    print(f"=== {group.upper()} ({len(cols)}) ===")
    for c in cols:
        s = X[c]
        row = {
            "group": group, "feature": c, "meaning": DESCRIPTION[c],
            "missing_%": round(s.isna().mean() * 100, 1),
            "min": round(s.min(), 2), "mean": round(s.mean(), 2), "max": round(s.max(), 2),
            "mean_if_chosen": round(s[chosen].mean(), 2),
            "mean_if_not_chosen": round(s[~chosen].mean(), 2),
        }
        rows.append(row)
        print(f"  {c:<38} chosen {row['mean_if_chosen']:>7}  not chosen {row['mean_if_not_chosen']:>7}"
              f"   missing {row['missing_%']:>4}%   {DESCRIPTION[c]}")
    print()

pd.DataFrame(rows).to_excel(OUT / "feature_summary.xlsx", index=False)
print(f"Saved: {OUT / 'feature_summary.xlsx'}")
