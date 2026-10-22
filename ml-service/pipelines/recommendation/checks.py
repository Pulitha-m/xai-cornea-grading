"""Data warnings for the recommendation inputs (matching and 12-month follow-up).

Hard limits (impossible values, duplicate tissue IDs, all weights zero) are enforced by the
request schemas and reject the request. The checks here flag values that are possible but
unusual or outside the data the models learned from: the result is still returned, with a
"check these values" note for the clinician. Thresholds are display defaults, to be confirmed
with NEBSL.
"""
import math

ENDOTHELIAL_SURGERIES = ("PK", "DSEK", "DMEK")
MIN_DONOR_ECD = 2000          # usual eye-bank minimum for a graft that transplants the endothelium
STORAGE_LIMIT_DAYS = 14       # usual storage limit; the case stock uses the same limit
ECD_RISE_TOLERANCE = 0.10     # endothelial cells do not regenerate; a larger rise is likely a typing error
FAILED_ECD = 500              # below this the graft has already failed
# Donor values the follow-up models were trained on (clip limits of the training cohort).
TRAINED_DONOR = {"donor_age": (18, 78, "Donor age", "years"),
                 "baseline_ecd": (2000, 3600, "Donor ECD", "cells/mm²")}


def _present(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def match_warnings(request: dict, candidates: list[dict]) -> list[str]:
    endothelial = (request.get("surgery_type") or "").upper() in ENDOTHELIAL_SURGERIES
    out = []
    for c in candidates:
        rid = c["record_id"]
        days = c.get("days_in_storage")
        if _present(days) and days > STORAGE_LIMIT_DAYS:
            out.append(f"{rid}: stored {days:g} days, longer than the usual {STORAGE_LIMIT_DAYS}-day limit.")
        ecd = c.get("ecd")
        if endothelial and _present(ecd) and ecd < MIN_DONOR_ECD:
            out.append(f"{rid}: ECD {ecd:g} cells/mm² is below the usual minimum of {MIN_DONOR_ECD} "
                       f"for a {request['surgery_type']} graft.")
    return out


def followup_warnings(req: dict) -> list[str]:
    out = []
    for key, (low, high, label, unit) in TRAINED_DONOR.items():
        v = req[key]
        if not low <= v <= high:
            out.append(f"{label} {v:g} {unit} is outside the range the model was trained on ({low}–{high} {unit}); "
                       "the prediction is less reliable.")
    if req["baseline_ecd"] < MIN_DONOR_ECD:
        out.append(f"Donor ECD {req['baseline_ecd']:g} cells/mm² is below the usual eye-bank minimum of {MIN_DONOR_ECD}.")

    points = [("donor", req["baseline_ecd"])]
    for m in (3, 6, 12):
        visit = req.get(f"visit_{m}m")
        if visit:
            points.append((f"{m} months", visit["ecd"]))
    for (a, ea), (b, eb) in zip(points, points[1:]):
        if eb > ea * (1 + ECD_RISE_TOLERANCE):
            out.append(f"ECD rises from {ea:g} ({a}) to {eb:g} ({b}). Endothelial cells do not regenerate: "
                       "check for a typing error.")

    ecd12 = req["visit_12m"]["ecd"]
    if ecd12 < FAILED_ECD:
        out.append(f"12-month ECD {ecd12:g} is below {FAILED_ECD}: the graft has already failed, which is outside "
                   "what the model predicts.")
    return out
