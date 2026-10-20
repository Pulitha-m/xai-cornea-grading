"""Donor-tissue ranking for a recipient request (MCDA with clinician weights).

Serving version of ml/recommendation/matching/mcda.py. It works on plain Python
objects so the ML service needs no pandas and holds no patient data: the backend
sends one request and the candidate tissues currently in stock, and gets back a
ranked list with scores and reasons. Keep the scoring rules in step with the
research version in ml/recommendation.
"""
from dataclasses import asdict, dataclass

GRADE_NUM = {"A+": 3, "A": 2, "B": 1, "C": 0}

# Procedures that transplant the donor endothelium, so endothelial quality matters.
ENDOTHELIAL_PROCEDURES = {"PK", "DSEK", "DMEK"}


@dataclass(frozen=True)
class Weights:
    """Clinical priority weights proposed by NEBSL clinicians (clinician-2026-10-18)."""
    grade_fit: float = 0.35
    endothelium: float = 0.30
    serology: float = 0.20
    freshness: float = 0.10
    surgery_compatibility: float = 0.05

    def normalised(self) -> dict[str, float]:
        w = asdict(self)
        total = sum(w.values()) or 1.0
        return {k: v / total for k, v in w.items()}


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def grade_gap(candidate_grade: str | None, requested_grade: str | None) -> int | None:
    c, r = GRADE_NUM.get(candidate_grade or ""), GRADE_NUM.get(requested_grade or "")
    return None if c is None or r is None else c - r


def grade_fit(gap: int | None) -> float:
    """1.0 exact match; slightly less when exceeding (saves better tissue); low when below."""
    if gap is None:
        return 0.5
    if gap == 0:
        return 1.0
    if gap > 0:
        return 1.0 - 0.1 * gap
    return 0.3 if gap == -1 else 0.0


def endothelium(ecd: float | None, cv: float | None, hex_: float | None) -> float:
    parts = []
    if ecd is not None:
        parts.append(_clip01((ecd - 2000) / 1500))   # 2000 -> 0, 3500 -> 1
    if cv is not None:
        parts.append(_clip01((50 - cv) / 25))         # 50 -> 0, 25 -> 1
    if hex_ is not None:
        parts.append(_clip01((hex_ - 40) / 30))       # 40 -> 0, 70 -> 1
    return sum(parts) / len(parts) if parts else 0.5


def freshness(days: float | None) -> float:
    return 0.5 if days is None else _clip01(1 - days / 14)


def donor_age(age: float | None) -> float:
    return 0.5 if age is None else _clip01((80 - age) / 50)


def preservation_time(hours: float | None) -> float:
    return 0.5 if hours is None else _clip01((8 - hours) / 7)


def serology_score(status: str) -> float:
    """Confirmed clear = 1, not confirmed = 0.5 (positive tissue is excluded, never scored)."""
    return 1.0 if status == "Yes" else 0.5


def surgery_compatibility(endo_surgery: bool, ecd: float | None) -> float:
    """Endothelial surgeries (PK/DSEK/DMEK) need a measured endothelium; others always fit."""
    return 0.0 if endo_surgery and ecd is None else 1.0


LABELS = {
    "grade_fit": "grade fit",
    "endothelium": "endothelium",
    "serology": "serology",
    "freshness": "freshness",
    "surgery_compatibility": "surgery compatibility",
}


def rank(request: dict, candidates: list[dict], weights: Weights = Weights(), top_k: int | None = None) -> dict:
    """Rank candidate tissues for one request.

    request:    {"requested_grade": "A+", "surgery_type": "PK", ...}
    candidates: [{"record_id", "grade", "ecd", "cv", "hex", "donor_age",
                  "death_to_preservation_h", "days_in_storage", "serology_clear"}, ...]
    """
    w = weights.normalised()
    endo_relevant = (request.get("surgery_type") or "").upper() in ENDOTHELIAL_PROCEDURES
    w_endo = w["endothelium"] if endo_relevant else 0.0
    w_grade = w["grade_fit"] + (w["endothelium"] - w_endo)
    used = {**w, "grade_fit": w_grade, "endothelium": w_endo}

    ranked, excluded = [], []
    for c in candidates:
        serology = (c.get("serology_clear") or "Unknown").capitalize()
        if serology == "No":
            excluded.append({"record_id": c["record_id"], "reason": "positive serology"})
            continue
        gap = grade_gap(c.get("grade"), request.get("requested_grade"))
        scores = {
            "grade_fit": grade_fit(gap),
            "endothelium": endothelium(c.get("ecd"), c.get("cv"), c.get("hex")),
            "serology": serology_score(serology),
            "freshness": freshness(c.get("days_in_storage")),
            "surgery_compatibility": surgery_compatibility(endo_relevant, c.get("ecd")),
        }
        total = sum(used[k] * scores[k] for k in scores)
        considered = {k: v for k, v in scores.items() if used[k] > 0}
        top = sorted(considered.items(), key=lambda kv: kv[1], reverse=True)[:2]
        flags = ["serology not confirmed"] if serology != "Yes" else []
        ranked.append({
            "record_id": c["record_id"],
            "grade": c.get("grade"),
            "match_score": round(total, 4),
            "grade_gap": gap,
            "criterion_scores": {k: round(v, 4) for k, v in scores.items()},
            "reasons": [f"{LABELS[k]} {v:.2f}" for k, v in top],
            "flags": flags,
        })

    ranked.sort(key=lambda r: r["match_score"], reverse=True)
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    if top_k:
        ranked = ranked[:top_k]
    return {
        "ranked": ranked,
        "excluded": excluded,
        "weights_used": {k: round(v, 4) for k, v in used.items()},
        "endothelium_considered": endo_relevant,
    }
