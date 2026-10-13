
from pathlib import Path
from collections import defaultdict
import hashlib

import pandas as pd

# --------------------------------------------------
# Paths
# --------------------------------------------------

PROJECT_ROOT = Path(
    r"C:\Users\pulit\OneDrive\Desktop\University\Y4S1\research\xai-cornea-grading"
)

DATASET_PATH = (
    PROJECT_ROOT
    / "ml/grading/data/processed/cleaned_grading_dataset.xlsx"
)

# IMPORTANT: Audit the newly extracted images, not the old folder.
IMAGE_DIR = PROJECT_ROOT / "ml/grading/data/images_sp_v2"

# Extraction manifest records the original tissue ID for every copied image.
MANIFEST_PATH = IMAGE_DIR / "image_manifest.csv"

OUTPUT_DIR = PROJECT_ROOT / "ml/grading/data/image_audit_v2"


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def normalize_tissue_id(value):
    """Normalize case and whitespace without changing the ID itself."""
    if pd.isna(value):
        return ""

    value = " ".join(str(value).strip().split())

    if value.upper().startswith("NEB-"):
        value = "NEB-" + value[4:].lstrip()

    return value.casefold()


def sha256_file(path):
    """Return a SHA-256 hash for exact file-content comparison."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


# --------------------------------------------------
# Main audit
# --------------------------------------------------

def main():
    for path in (DATASET_PATH, MANIFEST_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Required file not found: {path}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # Load dataset and validate columns
    # --------------------------------------------------

    df = pd.read_excel(DATASET_PATH)

    required_columns = {"Tissue_ID", "Tissue_Grade_Clean"}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Dataset is missing columns: {sorted(missing_columns)}"
        )

    df["Normalized_ID"] = df["Tissue_ID"].map(normalize_tissue_id)

    # Map each normalized ID to all distinct non-missing grades.
    grade_lookup = (
        df[df["Normalized_ID"] != ""]
        .groupby("Normalized_ID")["Tissue_Grade_Clean"]
        .apply(
            lambda values: sorted(
                set(values.dropna().astype(str).str.strip())
            )
        )
        .to_dict()
    )

    dataset_ids = set(
        df.loc[df["Normalized_ID"] != "", "Normalized_ID"]
    )

    # --------------------------------------------------
    # Load extraction manifest
    # --------------------------------------------------

    manifest = pd.read_csv(MANIFEST_PATH)

    required_manifest_columns = {
        "Tissue_ID",
        "Source_Path",
        "Copied_Path",
        "Original_Filename",
    }

    missing_manifest_columns = (
        required_manifest_columns - set(manifest.columns)
    )

    if missing_manifest_columns:
        raise ValueError(
            "Manifest is missing columns: "
            f"{sorted(missing_manifest_columns)}"
        )

    manifest["Normalized_ID"] = manifest["Tissue_ID"].map(
        normalize_tissue_id
    )

    # --------------------------------------------------
    # Audit each copied image
    # --------------------------------------------------

    print("Auditing extracted images and calculating hashes...")

    image_rows = []
    missing_files = []
    hash_to_paths = defaultdict(list)

    for row in manifest.to_dict("records"):
        tissue_id = row["Tissue_ID"]
        normalized_id = row["Normalized_ID"]
        copied_path = Path(row["Copied_Path"])

        grades = grade_lookup.get(normalized_id, [])

        if not copied_path.exists():
            missing_files.append({
                "Tissue_ID": tissue_id,
                "Copied_Path": str(copied_path),
            })
            continue

        digest = sha256_file(copied_path)
        hash_to_paths[digest].append(str(copied_path))

        image_rows.append({
            "Tissue_ID": tissue_id,
            "Normalized_ID": normalized_id,
            "Image_Name": row["Original_Filename"],
            "Source_Path": row["Source_Path"],
            "Copied_Path": str(copied_path),
            "SHA256": digest,
            "Matching_Grades": "; ".join(grades),
            "Has_Grade": bool(grades),
            "Grade_Conflict": len(grades) > 1,
        })

    image_df = pd.DataFrame(image_rows)

    # --------------------------------------------------
    # One row per dataset tissue ID
    # --------------------------------------------------

    image_counts = defaultdict(list)

    for row in image_rows:
        image_counts[row["Normalized_ID"]].append(row)

    tissue_rows = []

    for normalized_id in sorted(dataset_ids):
        rows = image_counts.get(normalized_id, [])
        grades = grade_lookup.get(normalized_id, [])

        tissue_rows.append({
            "Tissue_ID": (
                df.loc[
                    df["Normalized_ID"] == normalized_id,
                    "Tissue_ID"
                ].dropna().iloc[0]
            ),
            "Normalized_ID": normalized_id,
            "Image_Count": len(rows),
            "Distinct_Image_Hashes": len({
                row["SHA256"] for row in rows
            }),
            "Matching_Grades": "; ".join(grades),
            "Has_Grade": bool(grades),
            "Grade_Conflict": len(grades) > 1,
            "Has_SP_Image": len(rows) > 0,
        })

    tissue_df = pd.DataFrame(tissue_rows)

    # --------------------------------------------------
    # Exact duplicate file report
    # --------------------------------------------------

    duplicate_rows = []

    for digest, paths in hash_to_paths.items():
        if len(paths) > 1:
            for path in paths:
                duplicate_rows.append({
                    "SHA256": digest,
                    "Number_Of_Copies": len(paths),
                    "Copied_Path": path,
                })

    duplicate_df = pd.DataFrame(duplicate_rows)

    # --------------------------------------------------
    # Missing and unmatched ID reports
    # --------------------------------------------------

    image_ids = set(image_counts)

    missing_ids = sorted(dataset_ids - image_ids)
    unmatched_ids = sorted(image_ids - dataset_ids)

    missing_id_df = pd.DataFrame({
        "Normalized_ID": missing_ids
    })

    unmatched_id_df = pd.DataFrame({
        "Normalized_ID": unmatched_ids
    })

    # --------------------------------------------------
    # Save audit reports
    # --------------------------------------------------

    image_df.to_csv(
        OUTPUT_DIR / "image_inventory.csv", index=False
    )

    tissue_df.to_csv(
        OUTPUT_DIR / "tissue_image_summary.csv", index=False
    )

    duplicate_df.to_csv(
        OUTPUT_DIR / "exact_duplicate_files.csv", index=False
    )

    missing_id_df.to_csv(
        OUTPUT_DIR / "missing_image_ids.csv", index=False
    )

    unmatched_id_df.to_csv(
        OUTPUT_DIR / "images_without_dataset_record.csv",
        index=False,
    )

    pd.DataFrame(missing_files).to_csv(
        OUTPUT_DIR / "missing_copied_files.csv", index=False
    )

    # --------------------------------------------------
    # Summary
    # --------------------------------------------------

    copied_file_count = len(image_rows)
    matched_tissue_count = len(image_ids & dataset_ids)

    print("\n========== IMAGE AUDIT SUMMARY ==========")
    print(f"Dataset rows: {len(df)}")
    print(f"Unique dataset tissue IDs: {len(dataset_ids)}")
    print(f"Manifest entries: {len(manifest)}")
    print(f"Copied image files successfully checked: {copied_file_count}")
    print(f"Dataset tissue IDs with SP images: {matched_tissue_count}")
    print(f"Dataset tissue IDs with no SP image: {len(missing_ids)}")
    print(f"Image IDs absent from dataset: {len(unmatched_ids)}")
    print(
        "Tissue IDs with multiple images:",
        int((tissue_df["Image_Count"] > 1).sum()),
    )
    print(
        "Tissue IDs with byte-identical duplicate files:",
        int(
            (
                tissue_df["Distinct_Image_Hashes"]
                < tissue_df["Image_Count"]
            ).sum()
        ),
    )
    print(
        "Tissue IDs with no grade:",
        int((~tissue_df["Has_Grade"]).sum()),
    )
    print(
        "Tissue IDs with conflicting grades:",
        int(tissue_df["Grade_Conflict"].sum()),
    )
    print(f"Copied files missing on disk: {len(missing_files)}")
    print(f"Reports saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
