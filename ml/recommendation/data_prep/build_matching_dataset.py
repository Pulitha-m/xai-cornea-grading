"""Build the finalised donor-recipient matching dataset from the NEBSL research workbook.

Outputs one workbook with:
  - Tissues        : 591 cleaned real tissue records (one row per donor cornea)
  - Requests       : real recipient requests with a recorded allocated tissue
  - Ranking_Pairs  : request x candidate-tissue pairs built from real inventory windows
                     (label = 1 for the tissue actually allocated, 0 for other available tissues)
  - Data_Dictionary
  - Build_Notes
"""
import argparse
import re

import numpy as np
import pandas as pd

STORAGE_DAYS = 14  # Eusol-C storage window used to define "available in inventory"

# ---------- normalisers ----------
def grade(v):
    if pd.isna(v):
        return np.nan
    s = str(v).upper()
    m = re.match(r"\s*(A\+|A|B|C)", s)
    return m.group(1) if m else np.nan

GRADE_NUM = {"A+": 3, "A": 2, "B": 1, "C": 0}

def requested_grade(v):
    if pd.isna(v):
        return np.nan
    s = str(v).upper()
    if "A+" in s and "/" in s:  # e.g. "A+ / A (both ticked)" -> accept the lower bound
        return "A"
    if "A / B" in s:
        return "B"
    return grade(s)

def sero(v):
    if pd.isna(v):
        return np.nan
    s = str(v).lower()
    if "positive" in s or "+ve" in s:
        return "Positive"
    if "negative" in s:
        return "Negative"
    return np.nan

def sex(v):
    if pd.isna(v):
        return np.nan
    s = str(v).lower()
    if "both" in s or "conflict" in s or "verify" in s:
        return np.nan
    if s.startswith("female"):
        return "Female"
    if s.startswith("male"):
        return "Male"
    return np.nan

def eye(v):
    if pd.isna(v):
        return np.nan
    s = str(v).lower()
    if "conflict" in s:
        return np.nan
    return "Left" if "left" in s else ("Right" if "right" in s else np.nan)

def urgency(v):
    if pd.isna(v):
        return np.nan
    s = str(v).lower()
    return "Emergency" if "emergency" in s else ("Routine" if "routine" in s else np.nan)

def ind_type(v):
    if pd.isna(v):
        return np.nan
    s = str(v).lower()
    if "verify" in s or "struck" in s:
        return np.nan
    for k in ("optical", "therapeutic", "tectonic"):
        if k in s:
            return k.capitalize()
    return np.nan

def procedure(v):
    """Surgery type, normalised to PK / DALK / DSEK / DMEK / Lamellar / Other."""
    if pd.isna(v):
        return np.nan
    s = str(v).upper()
    for k in ("DMEK", "DSAEK", "DSEK", "DALK"):
        if k in s:
            return "DSEK" if k == "DSAEK" else k
    if "PENETRATING" in s or re.search(r"\bPK\b|\bPKP\b", s):
        return "PK"
    if "LAMELLAR" in s:
        return "Lamellar"
    if "PATCH" in s or "TECTONIC" in s:
        return "Patch/Tectonic"
    return "Other"

def indication_group(v):
    """Recipient disease grouped into clinical categories."""
    if pd.isna(v):
        return np.nan
    s = str(v).lower()
    rules = [
        ("Keratoconus", ["keratoconus", "ectasia"]),
        ("Failed/Re-graft", ["failed graft", "graft failure", "regraft", "re-graft", "reject"]),
        ("Fuchs/Endothelial", ["fuchs", "fecd", "endothelial", "bullous", "decompensat", "pbk", "abk"]),
        ("Infective keratitis", ["keratitis", "ulcer", "fungal", "bacterial", "infect", "abscess"]),
        ("Perforation/Thinning", ["perforat", "descemetocele", "melt", "puk", "thinning"]),
        ("Scar/Opacity", ["scar", "opacit", "leucoma", "leukoma", "nebula", "hazy", "haze"]),
        ("Dystrophy (other)", ["dystroph"]),
        ("Trauma/Chemical", ["trauma", "injur", "chemical", "burn", "rupture"]),
    ]
    if any(k in s for k in ("not written", "not legible", "unclear handwriting", "blank")):
        return np.nan
    for name, keys in rules:
        if any(k in s for k in keys):
            return name
    return "Other"

def prev_grafts(v):
    if pd.isna(v):
        return np.nan
    m = re.match(r"\s*(\d+)", str(v))
    return int(m.group(1)) if m else np.nan

def complication(v):
    if pd.isna(v):
        return np.nan
    s = str(v).lower()
    if "no intra" in s and "unclear" not in s:
        return "No"
    if "yes" in s or any(k in s for k in ("rupture", "loss", "haemorrh", "hemorrh", "tear")):
        return "Yes"
    return np.nan

def hours(v):
    if pd.isna(v):
        return np.nan
    s = str(v).lower()
    h = re.search(r"(\d+(?:\.\d+)?)\s*h", s)
    m = re.search(r"(\d+)\s*min", s)
    if not h and not m:
        return np.nan
    return round((float(h.group(1)) if h else 0) + (int(m.group(1)) / 60 if m else 0), 2)

def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        m = re.search(r"\d+(?:\.\d+)?", str(v)) if not pd.isna(v) else None
        return float(m.group(0)) if m else np.nan

def disease_main(v):
    if pd.isna(v):
        return np.nan
    s = str(v)
    if "FECD" in s:
        return "FECD"
    if "Guttata" in s:
        return "Guttata"
    if "Folds" in s:
        return "Folds"
    if s.strip() == "Normal":
        return "Normal"
    return "Other"

def build(src: str, out: str, storage_days: int = STORAGE_DAYS) -> dict:
    """Read the NEBSL workbook at ``src`` and write the matching dataset to ``out``."""
    raw = pd.read_excel(src, sheet_name="Research Dataset")

    # ---------- cleaned tissue table ----------
    t = pd.DataFrame({
        "Record_ID": [f"R{i:04d}" for i in range(1, len(raw) + 1)],
        "Tissue_ID": raw["Tissue_ID"],
        "Donor_Eye": raw["Eye"],
        "Donor_Age": raw["Donor_Age"].map(num),
        "Donor_Sex": raw["Donor_Sex"].map(sex),
        "Death_to_Preservation_h": raw["Death_to_Preservation_Time"].map(hours),
        "Lens_Status": raw["Lens_Status"].map(lambda v: np.nan if pd.isna(v) else ("Pseudophakic" if "pseudo" in str(v).lower() else ("Aphakic" if "aphak" in str(v).lower() else "Phakic"))),
        "ECD": raw["ECD_CD_cells_per_mm2"].map(num),
        "CV": raw["CV"].map(num),
        "HEX": raw["HEX_percent"].map(num),
        "Donor_Disease": raw["Disease_Label"].map(disease_main),
        "Donor_Disease_Severity": raw["Disease_Severity"],
        "Tissue_Grade": raw["Tissue_Grade"].map(grade),
        "Serology_HBsAg": raw["Serology_HBsAg"].map(sero),
        "Serology_HCV": raw["Serology_HCV"].map(sero),
        "Serology_HIV": raw["Serology_HIV"].map(sero),
        "Serology_VDRL": raw["Serology_VDRL"].map(sero),
        "Donor_Graft_Size_mm": raw["Donor_Graft_Size_mm"].map(num),
        "Preservation_Date": pd.to_datetime(raw["Preservation_Date_Time"], errors="coerce"),
        "Konan_Exam_Date": pd.to_datetime(raw["Konan_Exam_Date"], errors="coerce"),
        # recipient / request side (present only when the tissue was requested)
        "Request_Date": pd.to_datetime(raw["Request_Date"], errors="coerce"),
        "Requested_Grade": raw["Requested_Grade"].map(requested_grade),
        "Request_Urgency": raw["Request_Urgency"].map(urgency),
        "Indication_Type": raw["Request_Indication_Type"].map(ind_type),
        "Recipient_Age": raw["Recipient_Age"].map(num),
        "Recipient_Sex": raw["Recipient_Sex"].map(sex),
        "Recipient_Eye": raw["Recipient_Eye"].map(eye),
        "Recipient_Disease": raw["Recipient_Indication"],
        "Recipient_Disease_Group": raw["Recipient_Indication"].map(indication_group),
        "Previous_Grafts": raw["Previous_Grafts"].map(prev_grafts),
        "Surgery_Type_Planned": raw["Planned_Procedure"].map(procedure),
        "Surgery_Type_Performed": raw["Primary_Procedure"].map(procedure),
        "Recipient_Bed_Size_mm": raw["Recipient_Bed_Size_mm"].map(num),
        "Intraop_Complication": raw["Intraop_Complications"].map(complication),
        "Surgery_Date": pd.to_datetime(raw["Surgery_Date"], errors="coerce"),
        "Request_to_Surgery_Days": raw["Request_to_Surgery_Days"].map(num),
        "Grade_Request_Met": raw["Grade_Request_Met"],
        "Linkage_Status": raw["Linkage_Status"],
    })
    # a single surgery-type column: performed if recorded, else planned
    t["Surgery_Type"] = t["Surgery_Type_Performed"].fillna(t["Surgery_Type_Planned"])
    # drop Konan reads of 0 (empty analysis) rather than treating them as real ECD values
    for c in ("ECD", "CV", "HEX"):
        t.loc[t[c] <= 0, c] = np.nan
    t["Grade_Num"] = t["Tissue_Grade"].map(GRADE_NUM)
    t["Serology_Clear"] = np.where(
        t[["Serology_HBsAg", "Serology_HCV", "Serology_HIV", "Serology_VDRL"]].eq("Positive").any(axis=1), "No",
        np.where(t[["Serology_HBsAg", "Serology_HCV", "Serology_HIV", "Serology_VDRL"]].eq("Negative").all(axis=1), "Yes", "Unknown"))
    t["Available_From"] = t["Preservation_Date"].dt.normalize().fillna(t["Konan_Exam_Date"])
    t["Available_Until"] = t["Available_From"] + pd.Timedelta(days=storage_days)

    # ---------- requests (real allocations) ----------
    req = t[t["Requested_Grade"].notna() & t["Request_Date"].notna()].copy()
    req["Request_ID"] = [f"Q{i:04d}" for i in range(1, len(req) + 1)]

    # ---------- ranking pairs: each request vs every tissue in inventory on that date ----------
    pairs = []
    tis = t[t["Available_From"].notna()]
    for _, r in req.iterrows():
        d = r["Request_Date"]
        pool = tis[(tis["Available_From"] <= d) & (tis["Available_Until"] >= d)]
        if r["Record_ID"] not in set(pool["Record_ID"]):
            pool = pd.concat([pool, t[t["Record_ID"] == r["Record_ID"]]])  # keep the real allocation
        for _, c in pool.iterrows():
            rg = GRADE_NUM.get(r["Requested_Grade"], np.nan)
            pairs.append({
                "Request_ID": r["Request_ID"],
                "Request_Date": d.date(),
                "Recipient_Age": r["Recipient_Age"],
                "Recipient_Sex": r["Recipient_Sex"],
                "Recipient_Disease_Group": r["Recipient_Disease_Group"],
                "Previous_Grafts": r["Previous_Grafts"],
                "Surgery_Type": r["Surgery_Type"],
                "Indication_Type": r["Indication_Type"],
                "Request_Urgency": r["Request_Urgency"],
                "Requested_Grade": r["Requested_Grade"],
                "Recipient_Bed_Size_mm": r["Recipient_Bed_Size_mm"],
                "Candidate_Record_ID": c["Record_ID"],
                "Candidate_Tissue_ID": c["Tissue_ID"],
                "Cand_Tissue_Grade": c["Tissue_Grade"],
                "Cand_ECD": c["ECD"], "Cand_CV": c["CV"], "Cand_HEX": c["HEX"],
                "Cand_Donor_Age": c["Donor_Age"],
                "Cand_Donor_Disease": c["Donor_Disease"],
                "Cand_Death_to_Preservation_h": c["Death_to_Preservation_h"],
                "Cand_Serology_Clear": c["Serology_Clear"],
                "Cand_Days_In_Storage": (d - c["Available_From"]).days if pd.notna(c["Available_From"]) else np.nan,
                "Grade_Gap": (c["Grade_Num"] - rg) if pd.notna(c["Grade_Num"]) and pd.notna(rg) else np.nan,
                "Meets_Requested_Grade": ("Yes" if c["Grade_Num"] >= rg else "No") if pd.notna(c["Grade_Num"]) and pd.notna(rg) else np.nan,
                "Label_Allocated": int(c["Record_ID"] == r["Record_ID"]),
                "Outcome_Grade_Request_Met": r["Grade_Request_Met"] if c["Record_ID"] == r["Record_ID"] else np.nan,
            })
    pairs = pd.DataFrame(pairs)

    # ---------- write ----------
    dict_rows = [
        ("Tissues", "One row per real donor cornea record (591). Free-text fields normalised; original Tissue_ID kept for traceability."),
        ("Requests", "Subset of Tissues that have a recipient request with a date and requested grade; each is one real allocation."),
        ("Ranking_Pairs", f"For each request, every tissue whose availability window ({storage_days} days from preservation) covers the request date. Label_Allocated = 1 for the tissue actually allocated, 0 for other tissues that were in stock. Use with grouped split by Request_ID."),
        ("Surgery_Type", "PK / DALK / DSEK / DMEK / Lamellar / Patch-Tectonic / Other. Performed procedure if recorded, else planned procedure."),
        ("Recipient_Disease_Group", "Recipient indication grouped into clinical categories (Keratoconus, Failed/Re-graft, Fuchs/Endothelial, Infective keratitis, Perforation, Scar/Opacity, Dystrophy, Trauma/Chemical, Other). Raw text kept in Recipient_Disease."),
        ("Donor_Disease", "Recorded donor endothelial finding from the eye-bank form (Normal / Folds / Guttata / FECD / Other). This is the historical record, not a model output."),
        ("Grade_Gap", "Candidate grade minus requested grade (A+=3, A=2, B=1). Positive = exceeds request."),
        ("Serology_Clear", "Yes if all four tests Negative, No if any Positive, Unknown otherwise. Use as a hard filter."),
    ]
    notes = [
        ("Source", "dataset_final_labeled.xlsx, sheet 'Research Dataset' (591 rows, 79 columns)."),
        ("Real tissue records", len(t)),
        ("Real requests with date + requested grade", len(req)),
        ("Ranking pairs (request x in-stock candidate)", len(pairs)),
        ("Positive pairs (actual allocations)", int(pairs["Label_Allocated"].sum())),
        ("Mean candidates per request", round(len(pairs) / max(len(req), 1), 1)),
        ("Inventory window", f"{storage_days} days from preservation date (Konan exam date if preservation date missing)"),
        ("Synthetic rows", "None. Every row is derived from a real NEBSL record."),
        ("Split rule", "Split by Request_ID (grouped) so a request's candidates never appear in both train and test."),
    ]
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        t.drop(columns=["Grade_Num"]).to_excel(xw, sheet_name="Tissues", index=False)
        req.drop(columns=["Grade_Num"]).to_excel(xw, sheet_name="Requests", index=False)
        pairs.to_excel(xw, sheet_name="Ranking_Pairs", index=False)
        pd.DataFrame(dict_rows, columns=["Field / Sheet", "Meaning"]).to_excel(xw, sheet_name="Data_Dictionary", index=False)
        pd.DataFrame(notes, columns=["Item", "Value"]).to_excel(xw, sheet_name="Build_Notes", index=False)

    for k, v in notes:
        print(f"{k}: {v}")
    return dict(notes)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src", help="NEBSL research workbook (.xlsx)")
    ap.add_argument("out", help="output workbook path (.xlsx)")
    ap.add_argument("--storage-days", type=int, default=STORAGE_DAYS)
    a = ap.parse_args()
    build(a.src, a.out, a.storage_days)


if __name__ == "__main__":
    main()
