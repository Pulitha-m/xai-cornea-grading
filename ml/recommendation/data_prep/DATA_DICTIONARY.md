# Matching dataset: schema

Produced by `build_matching_dataset.py` from the NEBSL research workbook
(sheet `Research Dataset`). The data itself is not in this repository; data goes in `ml/recommendation/data/` (git-ignored). Code: `data_prep/build_matching_dataset.py`.

## Design

A ranking model learns from **request × candidate** pairs, not from single tissue rows.

For every real recipient request that has a request date and a requested grade, the script
lists every donor cornea that was in storage on that date. A tissue counts as "in storage"
from its preservation date (or Konan exam date if missing) for `STORAGE_DAYS = 14` days,
matching Eusol-C storage. The tissue actually allocated to that request gets
`Label_Allocated = 1`; every other in-stock tissue gets `0`.

Every row is derived from a real record. No synthetic rows are generated.

**Split rule:** always split train/test by `Request_ID`, so all candidates for one request
stay in the same partition.

## Sheets

| Sheet | One row per | Notes |
|---|---|---|
| `Tissues` | donor cornea | All records, cleaned |
| `Requests` | recipient request with a recorded allocation | Subset of `Tissues` |
| `Ranking_Pairs` | request × in-stock candidate tissue | Training table |
| `Data_Dictionary` | field | Short definitions |
| `Build_Notes` | build statistic | Counts and settings for the report |

## Ranking_Pairs columns

### Request (recipient) side

| Column | Type | Source column | Cleaning |
|---|---|---|---|
| `Request_ID` | str | generated | `Q0001`… |
| `Request_Date` | date | `Request_Date` | parsed |
| `Recipient_Age` | float | `Recipient_Age` | numeric part |
| `Recipient_Sex` | Male/Female | `Recipient_Sex` | conflicting entries set to missing |
| `Recipient_Disease_Group` | category | `Recipient_Indication` | keyword grouping: Keratoconus, Failed/Re-graft, Fuchs/Endothelial, Infective keratitis, Perforation/Thinning, Scar/Opacity, Dystrophy (other), Trauma/Chemical, Other; illegible entries set to missing |
| `Previous_Grafts` | int | `Previous_Grafts` | leading number; "Not ticked" → missing |
| `Surgery_Type` | category | `Primary_Procedure`, else `Planned_Procedure` | PK, DALK, DSEK (incl. DSAEK), DMEK, Lamellar, Patch/Tectonic, Other |
| `Indication_Type` | Optical/Therapeutic/Tectonic | `Request_Indication_Type` | struck/verify entries → missing |
| `Request_Urgency` | Routine/Emergency | `Request_Urgency` | |
| `Requested_Grade` | A+/A/B | `Requested_Grade` | "A+ / A (both ticked)" → A (lower bound accepted) |
| `Recipient_Bed_Size_mm` | float | `Recipient_Bed_Size_mm` | |

### Candidate (donor tissue) side

| Column | Type | Source column | Cleaning |
|---|---|---|---|
| `Candidate_Record_ID` | str | generated | `R0001`… |
| `Candidate_Tissue_ID` | str | `Tissue_ID` | unchanged, for traceability |
| `Cand_Tissue_Grade` | A+/A/B | `Tissue_Grade` | leading grade token |
| `Cand_ECD` / `Cand_CV` / `Cand_HEX` | float | Konan values | readings of 0 (empty analysis) → missing |
| `Cand_Donor_Age` | float | `Donor_Age` | |
| `Cand_Donor_Disease` | category | `Disease_Label` | Normal, Folds, Guttata, FECD, Other. Recorded eye-bank finding, not a model output |
| `Cand_Death_to_Preservation_h` | float | `Death_to_Preservation_Time` | "2 h 10 min" → 2.17 |
| `Cand_Serology_Clear` | Yes/No/Unknown | four serology columns | Yes = all Negative; No = any Positive |
| `Cand_Days_In_Storage` | int | derived | request date − available-from date |

### Derived match features and label

| Column | Meaning |
|---|---|
| `Grade_Gap` | candidate grade − requested grade (A+=3, A=2, B=1); positive = exceeds request |
| `Meets_Requested_Grade` | Yes if `Grade_Gap ≥ 0` |
| `Label_Allocated` | 1 = tissue actually allocated to this request, 0 = other in-stock tissue |
| `Outcome_Grade_Request_Met` | recorded outcome for the allocated tissue only (Yes / Exceeded / Below request) |

## Known limitations

- `Previous_Grafts` is about 25% complete and `Recipient_Bed_Size_mm` about 61%.
- Serology is `Unknown` for tissues without a completed serology section; treat as "needs check", not cleared.
- The 14-day window approximates inventory; tissues exported or discarded early may appear as candidates.
- `Label_Allocated` reflects historical practice, which is not necessarily the clinically optimal choice.
- Disease grouping uses keyword rules; review `Recipient_Disease` against `Recipient_Disease_Group` with a clinician.
