"""
Walk dataset/reports/ , parse every Konan .txt report, and build a single
ground_truth.csv keyed by cornea_id. This is the backbone for all validation.

Usage:
    python src/build_ground_truth.py --reports dataset/reports --out dataset/ground_truth.csv
"""
import argparse
from pathlib import Path
import pandas as pd
from parse_report import parse_report


def build(reports_dir, out_csv):
    reports_dir = Path(reports_dir)
    txt_files = sorted(reports_dir.glob("*.txt"))
    if not txt_files:
        raise SystemExit(f"No .txt reports found in {reports_dir}")

    rows = [parse_report(f) for f in txt_files]
    df = pd.DataFrame(rows)

    # Flag any report whose stated CD disagrees with NUM/AREA by > 2% (data-entry errors)
    def mismatch(r):
        if r.get("ecd") and r.get("ecd_check"):
            return abs(r["ecd"] - r["ecd_check"]) / r["ecd"] > 0.02
        return False
    df["ecd_self_inconsistent"] = df.apply(mismatch, axis=1)

    # Flag empty / failed captures (no cells analysed) -> excluded from modelling,
    # but kept in the CSV with a reason so the exclusion is logged and auditable.
    def exclusion_reason(r):
        if not r.get("num_cells") or r.get("num_cells") == 0:
            return "empty_capture_no_cells"
        if not r.get("ecd") or r.get("ecd") == 0:
            return "zero_ecd"
        return ""
    df["exclude_reason"] = df.apply(exclusion_reason, axis=1)
    df["include"] = df["exclude_reason"] == ""

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    # write the exclusions log alongside the CSV
    excl = df[~df["include"]][["cornea_id", "source_file", "exclude_reason"]]
    excl.to_csv(Path(out_csv).parent / "exclusions_log.csv", index=False)

    print(f"Parsed {len(df)} reports -> {out_csv}")
    print(f"  Included (valid):   {df['include'].sum()}")
    print(f"  Excluded (logged):  {(~df['include']).sum()}  -> exclusions_log.csv")
    print(f"  Missing ECD:        {df['ecd'].isna().sum()}")
    print(f"  Self-inconsistent:  {df['ecd_self_inconsistent'].sum()}")
    print("\nBiomarker summary (mean / min / max):")
    for col in ["ecd", "cv", "hex", "num_cells", "mean_area"]:
        if col in df and df[col].notna().any():
            s = df[col].dropna()
            print(f"  {col:10s}  {s.mean():8.1f}   {s.min():8.1f}   {s.max():8.1f}")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", default="dataset/reports")
    ap.add_argument("--out", default="dataset/ground_truth.csv")
    args = ap.parse_args()
    build(args.reports, args.out)
