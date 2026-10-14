"""
Build the VALIDATION ground-truth dataset for Component 3.

For the validation phase, every image the pipeline analyses is compared against
the certified Konan biomarkers for the same tissue. This script turns the parsed
reports into one clean, analysis-ready table keyed by cornea_id.

Outputs (dataset/):
  validation_ground_truth.csv   one row per valid capture (the file you use)
  validation_excluded.csv       empty / unusable captures, with reasons
  validation_data_dictionary.csv  column definitions
"""
import pandas as pd
from pathlib import Path

SRC = "dataset/ground_truth_full.csv"
OUT = "dataset/validation_ground_truth.csv"

KONAN = ["ecd", "cv", "hex", "sd", "mean_area", "num_cells", "area_um2"]
KEEP = (["cornea_id", "source_file", "eye", "year", "grade", "donor_age", "tech"]
        + KONAN + ["ecd_check"])


def main():
    df = pd.read_csv(SRC)

    # 1) Validity: a usable validation target must have cells and a density.
    valid = df[(df["num_cells"].fillna(0) > 0) & (df["ecd"].fillna(0) > 0)].copy()
    excluded = df[~df.index.isin(valid.index)].copy()
    excluded["exclude_reason"] = excluded.get("exclude_reason", "").fillna("empty_capture_no_cells")

    # 2) Normalise the join key: "NEB-2023-06-15181 R" (collapse internal spaces).
    valid["cornea_id"] = valid["cornea_id"].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)

    # 3) Duplicate captures of the same tissue+eye: keep the one with more cells
    #    (larger analysed sample = more reliable), flag that a duplicate existed.
    valid["is_duplicate_capture"] = valid.duplicated("cornea_id", keep=False)
    valid = (valid.sort_values("num_cells", ascending=False)
                  .drop_duplicates("cornea_id", keep="first")
                  .sort_values("cornea_id")
                  .reset_index(drop=True))

    # 4) Sanity flags reviewers will ask about (kept, not dropped).
    valid["year_out_of_range"] = (valid["year"] < 2018) | (valid["year"] > 2026)

    out = valid[KEEP + ["is_duplicate_capture", "year_out_of_range"]]
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    excluded[["source_file", "cornea_id", "num_cells", "ecd", "exclude_reason"]] \
        .to_csv("dataset/validation_excluded.csv", index=False)

    # 5) Data dictionary
    ddict = [
        ("cornea_id", "Tissue + eye key, e.g. 'NEB-2023-06-15181 R'. Join key to the image file."),
        ("source_file", "Original Konan .txt report filename."),
        ("eye", "OD (right) / OS (left) as recorded by the device."),
        ("year", "Acquisition year from the measurement Date (NOT the ID prefix)."),
        ("grade", "Konan reliability grade: green / yellow / red."),
        ("donor_age", "Donor age in years."),
        ("tech", "Technician name."),
        ("ecd", "GROUND TRUTH endothelial cell density, cells/mm^2 (Konan CD)."),
        ("cv", "GROUND TRUTH coefficient of variation of cell area, %."),
        ("hex", "GROUND TRUTH hexagonality (% six-sided cells)."),
        ("sd", "Std dev of cell area, um^2."),
        ("mean_area", "Mean cell area, um^2 (Konan AVE)."),
        ("num_cells", "Number of cells Konan analysed (NUM)."),
        ("area_um2", "Total analysed area, um^2 (AREA = sum of cell areas)."),
        ("ecd_check", "num_cells / (area_um2/1e6); must match ecd (parser cross-check)."),
        ("is_duplicate_capture", "True if this tissue had >1 capture; kept the higher-NUM one."),
        ("year_out_of_range", "True if acquisition year looks anomalous; kept for review."),
    ]
    pd.DataFrame(ddict, columns=["column", "meaning"]).to_csv(
        "dataset/validation_data_dictionary.csv", index=False)

    # Report
    print(f"Valid validation targets : {len(out)}")
    print(f"Excluded (empty/unusable): {len(excluded)}")
    print(f"Duplicate captures merged: {int(valid['is_duplicate_capture'].sum())} "
          f"tissues had >1 capture")
    print(f"Year-out-of-range flagged: {int(valid['year_out_of_range'].sum())}")
    print(f"\nGrade mix: {out['grade'].value_counts().to_dict()}")
    print(f"Eye mix  : {out['eye'].value_counts().to_dict()}")
    print(f"\nGround-truth biomarker ranges:")
    for c in ["ecd", "cv", "hex", "num_cells", "mean_area"]:
        s = out[c]
        print(f"  {c:11s} mean {s.mean():7.1f}   min {s.min():7.1f}   max {s.max():7.1f}")
    print(f"\nWrote -> {OUT}")


if __name__ == "__main__":
    main()
