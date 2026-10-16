"""Constrained counterfactual explanations for the donor-tissue ranker.

SHAP says why a cornea got its rank. A counterfactual says what would have to be
different for it to rank #1: "R0252 would be ranked #1 if it had been stored 2 fewer
days."

Only realistic changes are searched, one or two at a time, smallest first:

  actionable (the eye bank can act on these)
    serology confirmed   'Unknown' serology results completed and clear
    fresher              fewer days in storage at decision time (never below 0)
  descriptive (properties of the tissue; shown to explain, not to act on)
    higher ECD           +100 to +1000 cells/mm2, endothelial surgeries only
    closer grade         one grade step closer to the requested grade

Everything else (donor age, recipient, other candidates) is held fixed, and the
whole pool is re-scored after each change because some features compare a cornea
with the rest of its pool. Positive-serology tissue is never made eligible.
"""
from dataclasses import dataclass

import pandas as pd

from recommendation.matching.ranker import Ranker

GRADE_STEP = {"B": "A", "A": "A+"}
GRADE_DOWN = {"A+": "A", "A": "B"}
MAX_STORAGE_DAYS = 14
ECD_STEPS = range(100, 1001, 100)
ENDO = {"PK", "DSEK", "DMEK"}


@dataclass
class Change:
    label: str           # e.g. "stored 2 fewer days"
    actionable: bool
    cost: float          # used only to order options: smaller = simpler change


def _rank_of(ranker: Ranker, pool: pd.DataFrame, record_id: str) -> float:
    ranked = ranker.rank(pool)
    return float(ranked.loc[ranked["Candidate_Record_ID"] == record_id, "ML_Rank"].iloc[0])


def _single_changes(row: pd.Series) -> list[tuple[Change, dict]]:
    """Every allowed single change for one candidate, as (description, new values)."""
    out = []
    if row["Cand_Serology_Clear"] == "Unknown":
        out.append((Change("serology confirmed clear", True, 1.0), {"Cand_Serology_Clear": "Yes"}))

    days = int(row["Cand_Days_In_Storage"])
    for d in range(1, days + 1):
        out.append((Change(f"stored {d} fewer day{'s' if d > 1 else ''}", True, 0.5 * d),
                    {"Cand_Days_In_Storage": days - d}))

    if row["Surgery_Type"] in ENDO and pd.notna(row["Cand_ECD"]):
        for e in ECD_STEPS:
            out.append((Change(f"ECD {e} cells/mm2 higher", False, 1.5 + e / 200),
                        {"Cand_ECD": row["Cand_ECD"] + e}))

    gap, grade = row["Grade_Gap"], row["Cand_Tissue_Grade"]
    if pd.notna(gap) and gap < 0 and grade in GRADE_STEP:
        out.append((Change(f"grade {GRADE_STEP[grade]} instead of {grade}", False, 3.0),
                    {"Cand_Tissue_Grade": GRADE_STEP[grade], "Grade_Gap": gap + 1}))
    elif pd.notna(gap) and gap > 0 and grade in GRADE_DOWN:
        out.append((Change(f"grade {GRADE_DOWN[grade]} instead of {grade}", False, 3.0),
                    {"Cand_Tissue_Grade": GRADE_DOWN[grade], "Grade_Gap": gap - 1}))
    return out


def counterfactuals(ranker: Ranker, pool: pd.DataFrame, record_id: str,
                    target_rank: int = 1, max_options: int = 3,
                    actionable_only: bool = False) -> dict:
    """Smallest changes (one or two) that move ``record_id`` to ``target_rank`` or better.

    Returns the current rank and up to ``max_options`` options, simplest first. For each
    kind of change only its smallest sufficient amount is kept (e.g. the fewest days).
    """
    pool = pool.copy()
    idx = pool.index[pool["Candidate_Record_ID"] == record_id][0]
    row = pool.loc[idx]
    current = _rank_of(ranker, pool, record_id)
    result = {"record_id": record_id, "current_rank": current, "options": []}
    if row["Cand_Serology_Clear"] == "No" or current <= target_rank:
        return result

    singles = [s for s in _single_changes(row) if s[0].actionable or not actionable_only]
    by_kind: dict[str, list] = {}
    for change, values in sorted(singles, key=lambda s: s[0].cost):
        by_kind.setdefault(change.label.split(" ")[0], []).append((change, values))

    def first_that_works(trials: list) -> tuple | None:
        """Re-score all trials in one batch (each trial = a modified copy of the pool,
        tagged with its own Request_ID) and return the cheapest one reaching the target."""
        if not trials:
            return None
        copies = []
        for i, (_, values) in enumerate(trials):
            t = pool.copy()
            for col, v in values.items():
                t.loc[idx, col] = v
            t["Request_ID"] = f"__trial{i}"
            copies.append(t)
        ranked = ranker.rank(pd.concat(copies, ignore_index=True))
        mine = ranked[ranked["Candidate_Record_ID"] == record_id].set_index("Request_ID")["ML_Rank"]
        for i, (changes, _) in enumerate(trials):  # trials are ordered cheapest first
            r = mine.get(f"__trial{i}")
            if r is not None and r <= target_rank:
                return changes, float(r)
        return None

    def option(changes: list, rank_: float) -> dict:
        return {"changes": [c.label for c in changes], "new_rank": rank_,
                "actionable": all(c.actionable for c in changes), "cost": sum(c.cost for c in changes)}

    options = []
    # 1. one kind of change: keep its smallest sufficient amount
    solved = set()
    for kind, items in by_kind.items():
        hit = first_that_works([([c], v) for c, v in items])
        if hit:
            options.append(option(*hit))
            solved.add(kind)
    # 2. two kinds together, only where neither works alone
    kinds = [k for k in by_kind if k not in solved]
    for i, k1 in enumerate(kinds):
        for k2 in kinds[i + 1:]:
            combos = sorted((([c1, c2], {**v1, **v2}) for c1, v1 in by_kind[k1] for c2, v2 in by_kind[k2]),
                            key=lambda t: sum(c.cost for c in t[0]))
            hit = first_that_works(combos)
            if hit:
                options.append(option(*hit))

    options.sort(key=lambda o: o["cost"])
    result["options"] = options[:max_options]
    return result


def describe(cf: dict) -> str:
    """One readable line, e.g. 'R0252 (#3) would be #1 if: stored 2 fewer days'."""
    head = f"{cf['record_id']} (#{cf['current_rank']:.0f})"
    if cf["current_rank"] <= 1:
        return f"{head} is already ranked #1"
    if not cf["options"]:
        return f"{head}: no realistic change found that makes it #1"
    alts = [" and ".join(o["changes"]) + ("" if o["actionable"] else " [descriptive]")
            for o in cf["options"]]
    return f"{head} would be #1 if: " + "; or ".join(alts)


def summarise_misses(ranker: Ranker, pairs: pd.DataFrame) -> dict:
    """For every request where the actually allocated cornea is not ranked #1: what
    smallest realistic change would have put it first?"""
    ranked = ranker.rank(pairs)
    alloc = ranked[ranked["Label_Allocated"] == 1]
    counts = {"already #1": 0, "actionable change": 0, "descriptive change only": 0,
              "no realistic change": 0}
    kinds = {"fresher only": 0, "serology confirmed only": 0, "fresher + serology": 0}
    days_needed = []
    for _, r in alloc.iterrows():
        if r["ML_Rank"] <= 1:
            counts["already #1"] += 1
            continue
        cf = counterfactuals(ranker, pairs[pairs["Request_ID"] == r["Request_ID"]],
                             r["Candidate_Record_ID"], max_options=10)
        act = [o for o in cf["options"] if o["actionable"]]
        if act:
            counts["actionable change"] += 1
            labels = act[0]["changes"]
            fresher = any(c.startswith("stored") for c in labels)
            sero = any(c.startswith("serology") for c in labels)
            kinds["fresher + serology" if fresher and sero else
                  "fresher only" if fresher else "serology confirmed only"] += 1
            days_needed += [int(c.split()[1]) for c in labels if c.startswith("stored")]
        elif cf["options"]:
            counts["descriptive change only"] += 1
        else:
            counts["no realistic change"] += 1
    return {"requests": int(len(alloc)), "outcome": counts, "actionable_kinds": kinds,
            "median_days_fewer": float(pd.Series(days_needed).median()) if days_needed else None}
