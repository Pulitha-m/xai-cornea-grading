"""Step 1 of EDA: look at the structure of the raw NEBSL workbook.

Prints only summaries (counts, types, missing %, min/mean/max).
It never prints individual records and never changes the workbook.

Run from ml/:
    uv run python recommendation/scripts/eda_check.py
"""
from pathlib import Path

import pandas as pd

# The workbook lives in the git-ignored data folder.
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "dataset_final_labeled.xlsx"
SHEET = "Research Dataset"  # the workbook has 6 sheets; this one holds the records

# Show every row/column of the summary tables instead of "..."
pd.set_option("display.max_rows", 200)
pd.set_option("display.width", 200)

if not DATA_PATH.exists():
    raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

# 1. Which sheets are in the workbook?
print("=== SHEETS IN WORKBOOK ===")
print(pd.ExcelFile(DATA_PATH).sheet_names)

df = pd.read_excel(DATA_PATH, sheet_name=SHEET)

# 2. Size
print("\n=== DATASET STRUCTURE ===")
print("Rows:", len(df))
print("Columns:", len(df.columns))

# 3. Column names and the type pandas gave each one
print("\n=== COLUMN NAMES AND TYPES ===")
for col, dtype in df.dtypes.items():
    print(f"{col}: {dtype}")

# 4. Missing values, worst first
print("\n=== MISSING VALUES ===")
missing = pd.DataFrame({
    "Missing Count": df.isna().sum(),
    "Missing %": (df.isna().mean() * 100).round(1),
})
print(missing.sort_values("Missing %", ascending=False))

# 5. Numeric columns: count, mean, min, quartiles, max
print("\n=== NUMERICAL SUMMARY ===")
print(df.describe().T.round(1).to_string())

# 6. Find the columns we will look at in later steps
print("\n=== GRADE COLUMNS ===")
print([c for c in df.columns if "grade" in c.lower()])
print("\n=== DATE COLUMNS ===")
print([c for c in df.columns if "date" in c.lower()])
print("\n=== BIOMARKER COLUMNS (ECD, CV, HEX) ===")
print([c for c in df.columns if any(t in c.lower() for t in ["ecd", "cv", "hex"])])

print("\nStep 1 complete.")
