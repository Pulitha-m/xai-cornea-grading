"""Serving version of the trained donor-tissue ranker (ML model, no pandas/sklearn).

Mirrors ml/recommendation/matching/features.py and the logistic-regression ranker,
using the parameters exported by `python -m recommendation.main export` into
ml-service/models/recommendation_ranker.json. For each candidate it returns:

  ml_score        the model's score (higher = more like the corneas NEBSL chose)
  why             contribution of each reason compared with the other candidates
                  (exact SHAP for a linear model, relative to the pool)
  counterfactual  smallest realistic change that would make it #1

Keep this file in step with the research code: the parity test in
ml/recommendation/tests/test_export.py compares both on the real dataset.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

from pipelines.recommendation.engine import (
    ENDOTHELIAL_PROCEDURES, donor_age, endothelium, freshness, grade_fit, preservation_time,
)

# Team convention: trained model files live in ml-service/models/ (next to grading_hybrid_rf.json)
MODEL_FILE = Path(__file__).resolve().parents[2] / "models" / "recommendation_ranker.json"
GRADE_NUM = {"A+": 3, "A": 2, "B": 1}
REASONS = ["grade match", "endothelium", "freshness", "donor age", "preservation time", "serology"]
NAN = float("nan")


@lru_cache(maxsize=1)
def load_model(path: str = str(MODEL_FILE)) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def _num(v) -> float:
    return NAN if v is None else float(v)


def _pool_pct(values: list[float]) -> list[float]:
    """pandas rank(pct=True): average rank among non-missing values / their count."""
    present = sorted((v, i) for i, v in enumerate(values) if not math.isnan(v))
    n = len(present)
    out = [NAN] * len(values)
    j = 0
    while j < n:
        k = j
        while k + 1 < n and present[k + 1][0] == present[j][0]:
            k += 1
        avg_rank = (j + k) / 2 + 1
        for t in range(j, k + 1):
            out[present[t][1]] = avg_rank / n
        j = k + 1
    return out


def features(request: dict, candidates: list[dict]) -> list[dict]:
    """The 23 model features for every candidate of one request (same order as given)."""
    req_grade = GRADE_NUM.get(request.get("requested_grade") or "")
    endo = (request.get("surgery_type") or "").upper() in ENDOTHELIAL_PROCEDURES
    rows = []
    for c in candidates:
        cg = GRADE_NUM.get(c.get("grade") or "")
        gap = NAN if cg is None or req_grade is None else float(cg - req_grade)
        ecd = _num(c.get("ecd"))
        days = _num(c.get("days_in_storage"))
        serology = (c.get("serology_clear") or "Unknown").capitalize()
        rows.append({
            "Grade_Gap": gap,
            "Grade_Exact": 1.0 if gap == 0 else 0.0,
            "Grade_Below": 1.0 if gap < 0 else 0.0,
            "Grade_Abs_Gap": abs(gap),
            "Cand_Grade_Num": NAN if cg is None else float(cg),
            "ECD_if_Endo": ecd if endo else NAN,
            "Endo_Procedure": 1.0 if endo else 0.0,
            "Endo_Missing": 1.0 if math.isnan(ecd) else 0.0,
            "Cand_Days_In_Storage": days,
            "Serology_Unknown": 1.0 if serology == "Unknown" else 0.0,
            "s_grade_fit": grade_fit(None if math.isnan(gap) else int(gap)),
            "s_endothelium": endothelium(c.get("ecd"), c.get("cv"), c.get("hex")),
            "s_freshness": freshness(c.get("days_in_storage")),
            "s_donor_age": donor_age(c.get("donor_age")),
            "s_preservation_time": preservation_time(c.get("death_to_preservation_h")),
        })
    pools = {
        "Grade_Abs_Gap_PoolPct": [-r["Grade_Abs_Gap"] for r in rows],
        "Cand_ECD_PoolPct": [_num(c.get("ecd")) for c in candidates],
        "Cand_HEX_PoolPct": [_num(c.get("hex")) for c in candidates],
        "Cand_CV_PoolPct": [-_num(c.get("cv")) for c in candidates],
        "Cand_Days_In_Storage_PoolPct": [-_num(c.get("days_in_storage")) for c in candidates],
        "Cand_Donor_Age_PoolPct": [-_num(c.get("donor_age")) for c in candidates],
        "Cand_Death_to_Preservation_h_PoolPct": [-_num(c.get("death_to_preservation_h")) for c in candidates],
    }
    for name, values in pools.items():
        for r, p in zip(rows, _pool_pct(values)):
            r[name] = p
    for r in rows:
        r["Pool_Size"] = float(len(candidates))
    return rows


def _standardise(model: dict, rows: list[dict]) -> list[list[float]]:
    z = []
    for r in rows:
        vals = []
        for f, med, mu, sd in zip(model["features"], model["impute_median"], model["mean"], model["scale"]):
            x = r[f]
            x = med if math.isnan(x) else x
            vals.append((x - mu) / sd)
        z.append(vals)
    return z


def scores(model: dict, request: dict, candidates: list[dict]) -> tuple[list[float], list[list[float]]]:
    z = _standardise(model, features(request, candidates))
    return [model["intercept"] + sum(c * v for c, v in zip(model["coef"], row)) for row in z], z


def _eligible(c: dict) -> bool:
    return (c.get("serology_clear") or "Unknown").capitalize() != "No"


def ranks(model: dict, request: dict, candidates: list[dict]) -> list[int | None]:
    """1 = best; None for positive-serology tissue. Ties keep the input order."""
    s, _ = scores(model, request, candidates)
    order = sorted((i for i, c in enumerate(candidates) if _eligible(c)), key=lambda i: -s[i])
    out: list[int | None] = [None] * len(candidates)
    for r, i in enumerate(order, start=1):
        out[i] = r
    return out


def why(model: dict, z: list[list[float]], i: int, top: int = 3, min_effect: float = 0.05):
    """Contribution of each reason for candidate i, compared with the pool average."""
    n = len(z)
    means = [sum(row[j] for row in z) / n for j in range(len(model["features"]))]
    by_reason = {r: 0.0 for r in REASONS}
    for j, f in enumerate(model["features"]):
        reason = model["reason_of"].get(f)
        if reason in by_reason:
            by_reason[reason] += model["coef"][j] * (z[i][j] - means[j])
    items = sorted(by_reason.items(), key=lambda kv: -abs(kv[1]))
    strongest = [(k, v) for k, v in items if abs(v) >= min_effect][:top]
    text = ("; ".join(f"{k} ({v:+.2f})" for k, v in strongest)
            or "no single factor stands out from the other candidates")
    return [{"reason": k, "effect": round(v, 3)} for k, v in items], text


# ---------------------------------------------------------------- counterfactuals
GRADE_UP = {"B": "A", "A": "A+"}
GRADE_DOWN = {"A+": "A", "A": "B"}


def _single_changes(request: dict, c: dict) -> dict[str, list]:
    """Allowed changes per kind, cheapest first: (label, actionable, cost, new values)."""
    kinds: dict[str, list] = {}
    if (c.get("serology_clear") or "Unknown").capitalize() == "Unknown":
        kinds["serology"] = [("serology confirmed clear", True, 1.0, {"serology_clear": "Yes"})]
    days = c.get("days_in_storage")
    if days is not None and days >= 1:
        kinds["stored"] = [(f"stored {d} fewer day{'s' if d > 1 else ''}", True, 0.5 * d,
                            {"days_in_storage": days - d}) for d in range(1, int(days) + 1)]
    if (request.get("surgery_type") or "").upper() in ENDOTHELIAL_PROCEDURES and c.get("ecd") is not None:
        kinds["ECD"] = [(f"ECD {e} cells/mm2 higher", False, 1.5 + e / 200, {"ecd": c["ecd"] + e})
                        for e in range(100, 1001, 100)]
    cg, rg = GRADE_NUM.get(c.get("grade") or ""), GRADE_NUM.get(request.get("requested_grade") or "")
    if cg is not None and rg is not None and cg != rg:
        new = GRADE_UP.get(c["grade"]) if cg < rg else GRADE_DOWN.get(c["grade"])
        if new:
            kinds["grade"] = [(f"grade {new} instead of {c['grade']}", False, 3.0, {"grade": new})]
    return kinds


def counterfactual(model: dict, request: dict, candidates: list[dict], i: int) -> str | None:
    """Smallest realistic change (one or two kinds) that makes candidate i rank #1."""
    current = ranks(model, request, candidates)[i]
    if current is None or current == 1:
        return None

    def first_that_works(trials):
        """trials: (labels, actionable, cost, values), cheapest first."""
        for labels, actionable, cost, values in trials:
            trial = [dict(c) for c in candidates]
            trial[i].update(values)
            if ranks(model, request, trial)[i] == 1:
                return cost, labels, actionable
        return None

    kinds = _single_changes(request, candidates[i])
    found, solved = [], set()
    for kind, items in kinds.items():
        hit = first_that_works(([lab], act, cost, vals) for lab, act, cost, vals in items)
        if hit:
            found.append(hit)
            solved.add(kind)
    rest = [k for k in kinds if k not in solved]
    for a in range(len(rest)):
        for b in range(a + 1, len(rest)):
            combos = sorted((([x[0], y[0]], x[1] and y[1], x[2] + y[2], {**x[3], **y[3]})
                             for x in kinds[rest[a]] for y in kinds[rest[b]]), key=lambda t: t[2])
            hit = first_that_works(combos)
            if hit:
                found.append(hit)
    if not found:
        return "no realistic change found that makes it #1"
    found.sort(key=lambda t: t[0])
    alts = [" and ".join(labels) + ("" if actionable else " [descriptive]")
            for _, labels, actionable in found[:2]]
    return "would be #1 if: " + "; or ".join(alts)


def rank_ml(request: dict, candidates: list[dict], top_k: int | None = None,
            with_counterfactuals: bool = True) -> dict | None:
    """Rank with the trained model. Returns None if no exported model is installed."""
    model = load_model()
    if model is None:
        return None
    s, z = scores(model, request, candidates)
    r = ranks(model, request, candidates)
    ranked, excluded = [], []
    for i, c in enumerate(candidates):
        if r[i] is None:
            excluded.append({"record_id": c["record_id"], "reason": "positive serology"})
            continue
        reasons, text = why(model, z, i)
        flags = [] if (c.get("serology_clear") or "Unknown").capitalize() == "Yes" else ["serology not confirmed"]
        ranked.append({"rank": r[i], "index": i, "record_id": c["record_id"], "grade": c.get("grade"),
                       "ml_score": round(s[i], 4), "why": reasons, "why_text": text, "flags": flags})
    ranked.sort(key=lambda x: x["rank"])
    if top_k:
        ranked = ranked[:top_k]
    if with_counterfactuals:
        for x in ranked:
            x["counterfactual"] = counterfactual(model, request, candidates, x["index"])
    for x in ranked:
        x.pop("index")
    return {"ranked": ranked, "excluded": excluded,
            "model": f"{model['name']} {model['version']}", "model_summary": model.get("summary", {})}
