"""Step 2 of EDA: distributions, text-in-number columns and outliers (raw workbook).

Prints only counts and summaries and saves charts to outputs/eda_raw/.
It never prints individual records and never changes the workbook.

Run from ml/:
    uv run python recommendation/scripts/eda_step2.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "raw" / "dataset_final_labeled.xlsx"
OUT = ROOT / "outputs" / "eda_raw"
OUT.mkdir(parents=True, exist_ok=True)

BLUE, SURFACE, INK, MUTED, GRID = "#2a78d6", "#fcfcfb", "#0b0b0b", "#898781", "#e1e0d9"

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

df = pd.read_excel(DATA_PATH, sheet_name="Research Dataset")

# Some grades carry notes, e.g. "A+ (as read)". Keep the first grade written.
df["Grade_Clean"] = df["Tissue_Grade"].astype(str).str.extract(r"^\s*(A\+|A|B)")[0]


def style(ax, title, xlabel="", ylabel=""):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold")
    ax.set_xlabel(xlabel, color=MUTED)
    ax.set_ylabel(ylabel, color=MUTED)
    ax.tick_params(colors=MUTED, length=0)
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)


# ---------------------------------------------------------------- 2.1 Grades
print("=== 2.1 TISSUE GRADE ===")
plain = df["Tissue_Grade"].isin(["A+", "A", "B"]).sum()
print(f"Plain grade: {plain}, grade with a note: {df['Tissue_Grade'].notna().sum() - plain}, "
      f"missing: {df['Tissue_Grade'].isna().sum()}")
print("\nCleaned grade counts (first grade written):")
print(df["Grade_Clean"].value_counts(dropna=False))

print("\n=== REQUESTED GRADE COUNTS (rows with a request) ===")
print(df["Requested_Grade"].value_counts())

print("\n=== WAS THE REQUESTED GRADE MET? ===")
print(df["Grade_Request_Met"].value_counts())

fig, ax = plt.subplots(figsize=(6, 3.5), facecolor=SURFACE)
g = df["Grade_Clean"].value_counts().reindex(["A+", "A", "B"])
bars = ax.bar(g.index.astype(str), g.values, color=BLUE, width=0.6)
ax.bar_label(bars, color=MUTED, fontsize=8)
style(ax, "Donor corneas by tissue grade", "Grade", "Corneas")
fig.tight_layout()
fig.savefig(OUT / "raw_01_tissue_grade.png", dpi=150, facecolor=SURFACE)
plt.close(fig)

# ------------------------------------------- 2.2 ECD / CV / HEX distributions
fig, axes = plt.subplots(1, 3, figsize=(10, 3.2), facecolor=SURFACE)
for ax, (col, label) in zip(axes, [("ECD_CD_cells_per_mm2", "ECD (cells/mm²)"),
                                   ("CV", "CV (%)"), ("HEX_percent", "HEX (%)")]):
    ax.hist(df[col].dropna(), bins=25, color=BLUE, edgecolor=SURFACE)
    style(ax, label, "", "Corneas" if col.startswith("ECD") else "")
fig.tight_layout()
fig.savefig(OUT / "raw_02_endothelial.png", dpi=150, facecolor=SURFACE)
plt.close(fig)

print("\n=== 2.2 ECD / CV / HEX BY GRADE (median) ===")
print(df.groupby("Grade_Clean")[["ECD_CD_cells_per_mm2", "CV", "HEX_percent"]]
      .median().round(0))

# ----------------------------------------------------------- 2.3 Years
print("\n=== 2.3 RECORDS PER YEAR (by Konan exam date) ===")
print(df["Konan_Exam_Date"].dt.year.value_counts().sort_index())
print("\n=== REQUESTS PER YEAR ===")
print(df["Request_Date"].dt.year.value_counts().sort_index())

# --------------------------------- 2.4 Number columns that contain text
# These showed as 'object' in step 1: numbers mixed with text.
print("\n=== 2.4 TEXT FOUND IN NUMBER COLUMNS ===")
for col in ["Recipient_Age", "Previous_Grafts", "Donor_Graft_Size_mm",
            "Recipient_Bed_Size_mm", "Form_ECD_cells_per_mm2", "Death_to_Preservation_Time"]:
    s = df[col].dropna()
    as_num = pd.to_numeric(s, errors="coerce")
    text = s[as_num.isna()].astype(str)
    print(f"\n{col}: {len(s)} filled, {as_num.notna().sum()} numeric, {len(text)} text")
    print("  most common text values:", text.value_counts().head(5).to_dict())

# --------------------------------------------------------- 2.5 Outliers
print("\n=== 2.5 VALUES OUTSIDE PLAUSIBLE RANGES (counts only) ===")
checks = {
    "ECD below 1000 or above 4000": (df["ECD_CD_cells_per_mm2"] < 1000) | (df["ECD_CD_cells_per_mm2"] > 4000),
    "CV above 60": df["CV"] > 60,
    "HEX below 30": df["HEX_percent"] < 30,
    "Total_Cell_Count below 50": df["Total_Cell_Count"] < 50,
    "Death_to_Surgery_Days above 14": df["Death_to_Surgery_Days"] > 14,
    "Request_to_Surgery_Days negative": df["Request_to_Surgery_Days"] < 0,
    "Request_to_Surgery_Days above 60": df["Request_to_Surgery_Days"] > 60,
    "Konan exam before death": df["Konan_Exam_Date"] < df["Death_Date_Time"].dt.normalize(),
    "Surgery before death": df["Surgery_Date"] < df["Death_Date_Time"].dt.normalize(),
}
for name, mask in checks.items():
    print(f"{name}: {int(mask.sum())}")

print(f"\nCharts saved to {OUT}")
print("Step 2 complete.")
