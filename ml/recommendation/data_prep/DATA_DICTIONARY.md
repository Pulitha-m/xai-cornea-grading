# Matching dataset: schema

Produced by `build_matching_dataset.py` from the NEBSL research workbook
(sheet `Research Dataset`). The data itself is not in this repository; data goes in `ml/recommendation/data/` (git-ignored). Code: `data_prep/build_matching_dataset.py`.

## Design

A ranking model learns from **request × candidate** pairs, not from single tissue rows.

For every real recipient request that has a request date and a requested grade, the script
lists every donor cornea that was genuinely available on the request's **decision date**.

- **Decision date** = the later of the request date and the date the allocated tissue was
  ready (preserved and Konan-examined), capped at the surgery date. Recipients wait on a list,
  so this is when the choice was actually made.
- A candidate must be **ready by the decision date** (preserved and examined, so no
  information from the future is used), **within `STORAGE_DAYS = 14` days** of preservation
  (Eusol-C storage), and **not already allocated** to an earlier request.

The tissue actually allocated gets `Label_Allocated = 1`; every other available tissue gets `0`.

Every row is derived from a real record. No synthetic rows are generated.

**Split rule:** always split train/test by `Request_ID`, so all candidates for one request
stay in the same partition.

## Identifiers

The working dataset contains no NEBSL identifier. Each tissue gets a study code `Record_ID`
(`R0001`…) and each request a `Request_ID` (`Q0001`…). The script writes the
`Record_ID` → NEBSL `Tissue_ID` key to a separate file, `*_id_key.xlsx`, which must be kept
offline or with the data custodian and never shared with the working dataset.

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
| `Decision_Date` | date | derived | later of request date and allocated tissue ready date, capped at surgery date |
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
| `Cand_Tissue_Grade` | A+/A/B | `Tissue_Grade` | leading grade token |
| `Cand_ECD` / `Cand_CV` / `Cand_HEX` | float | Konan values | readings of 0 (empty analysis) → missing |
| `Cand_Donor_Age` | float | `Donor_Age` | |
| `Cand_Donor_Disease` | category | `Disease_Label` | Normal, Folds, Guttata, FECD, Other. Recorded eye-bank finding, not a model output |
| `Cand_Death_to_Preservation_h` | float | `Death_to_Preservation_Time` | "2 h 10 min" → 2.17 |
| `Cand_Serology_Clear` | Yes/No/Unknown | four serology columns | Yes = all Negative; No = any Positive |
| `Cand_Days_In_Storage` | int | derived | decision date − available-from date |

### Derived match features and label

| Column | Meaning |
|---|---|
| `Grade_Gap` | candidate grade − requested grade (A+=3, A=2, B=1); positive = exceeds request |
| `Meets_Requested_Grade` | Yes if `Grade_Gap ≥ 0` |
| `Label_Allocated` | 1 = tissue actually allocated to this request, 0 = other available tissue |
| `Positive_Outside_Window` | 1 if the allocated tissue broke the availability rules but was kept (0 cases in the current data) |
| `Outcome_Grade_Request_Met` | recorded outcome for the allocated tissue only (Yes / Exceeded / Below request) |

## Known limitations

- `Previous_Grafts` is about 25% complete and `Recipient_Bed_Size_mm` about 61%.
- Serology is `Unknown` for tissues without a completed serology section; treat as "needs check", not cleared.
- The 14-day window approximates inventory. Tissues allocated to earlier requests are removed, but tissues exported or discarded without a recorded date may still appear as candidates.
- Almost all requests fall in 2024 (99) and 2025 (85); a time-based check (train 2024, test 2025) is recommended.
- `Label_Allocated` reflects historical practice, which is not necessarily the clinically optimal choice.
- Disease grouping uses keyword rules; review `Recipient_Disease` against `Recipient_Disease_Group` with a clinician.
