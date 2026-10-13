
from pathlib import Path
import hashlib
import shutil

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

IMAGE_DIR = PROJECT_ROOT / "ml/grading/data/images_sp_v2"

EXTRACTION_MANIFEST = IMAGE_DIR / "image_manifest.csv"

OUTPUT_DIR = PROJECT_ROOT / "ml/grading/image/data/processed"
CLEAN_IMAGE_DIR = OUTPUT_DIR / "images"

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def normalize_tissue_id(value):
    if pd.isna(value):
        return ""

    value = " ".join(str(value).strip().split())

    if value.upper().startswith("NEB-"):
        value = "NEB-" + value[4:].lstrip()

    return value.casefold()


def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def main():
    for path in (DATASET_PATH, EXTRACTION_MANIFEST):
        if not path.exists():
            raise FileNotFoundError(f"Required file not found: {path}")

    # --------------------------------------------------
    # Load dataset and labels
    # --------------------------------------------------

    df = pd.read_excel(DATASET_PATH)

    required = {"Tissue_ID", "Tissue_Grade_Clean"}
    missing_columns = required - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Dataset missing columns: {sorted(missing_columns)}"
        )

    df["Normalized_ID"] = df["Tissue_ID"].map(normalize_tissue_id)

    # Keep only non-missing specialist-reviewed grades.
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

    # --------------------------------------------------
    # Load extraction manifest
    # --------------------------------------------------

    manifest = pd.read_csv(EXTRACTION_MANIFEST)

    required_manifest = {
        "Tissue_ID",
        "Copied_Path",
        "Source_Path",
        "Original_Filename",
    }

    missing_columns = required_manifest - set(manifest.columns)

    if missing_columns:
        raise ValueError(
            f"Manifest missing columns: {sorted(missing_columns)}"
        )

    manifest["Normalized_ID"] = manifest["Tissue_ID"].map(
        normalize_tissue_id
    )

    # Create a new output location; never delete the source images.
    CLEAN_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    selected_rows = []
    duplicate_rows = []
    missing_files = []
    conflicting_grades = []

    # Group all copied files by normalized tissue ID.
    for tissue_id, group in manifest.groupby("Normalized_ID", sort=True):
        if not tissue_id:
            continue

        grades = grade_lookup.get(tissue_id, [])

        if len(grades) > 1:
            conflicting_grades.append({
                "Normalized_ID": tissue_id,
                "Grades": "; ".join(grades),
            })
            continue

        candidates = []

        for row in group.to_dict("records"):
            image_path = Path(row["Copied_Path"])

            if not image_path.exists():
                missing_files.append({
                    "Tissue_ID": row["Tissue_ID"],
                    "Copied_Path": str(image_path),
                })
                continue

            candidates.append({
                **row,
                "Path": image_path,
                "SHA256": sha256_file(image_path),
            })

        if not candidates:
            continue

        # Group by exact file content, not just filename.
        by_hash = {}

        for candidate in candidates:
            by_hash.setdefault(candidate["SHA256"], []).append(candidate)

        # Keep one image only if all candidates are byte-identical.
        if len(by_hash) > 1:
            duplicate_rows.append({
                "Tissue_ID": group["Tissue_ID"].iloc[0],
                "Normalized_ID": tissue_id,
                "File_Count": len(candidates),
                "Distinct_Hashes": len(by_hash),
                "Status": "Different image contents; manual review required",
            })
            continue

        # Deterministic choice: use the alphabetically first copied path.
        identical_candidates = next(iter(by_hash.values()))
        chosen = sorted(
            identical_candidates,
            key=lambda item: str(item["Path"]).casefold(),
        )[0]

        # Use a stable, tissue-ID-derived filename.
        safe_id = "".join(
            char if char.isalnum() or char in "-_" else "_"
            for char in str(chosen["Tissue_ID"]).strip()
        )

        destination = CLEAN_IMAGE_DIR / f"{safe_id}_SP.jpg"

        shutil.copy2(chosen["Path"], destination)

        selected_rows.append({
            "Tissue_ID": chosen["Tissue_ID"],
            "Normalized_ID": tissue_id,
            "Tissue_Grade_Clean": grades[0] if grades else None,
            "Selected_Image": str(destination),
            "Original_Filename": chosen["Original_Filename"],
            "SHA256": chosen["SHA256"],
            "Source_File_Count": len(candidates),
            "Byte_Identical_Copy_Count": len(candidates) - 1,
            "Has_Grade": bool(grades),
        })

        # Record all extra copies for traceability.
        for candidate in identical_candidates:
            if candidate["Path"] == chosen["Path"]:
                continue

            duplicate_rows.append({
                "Tissue_ID": chosen["Tissue_ID"],
                "Normalized_ID": tissue_id,
                "File_Count": len(candidates),
                "Distinct_Hashes": 1,
                "Status": (
                    f"Byte-identical copy: {candidate['Path']}"
                ),
            })

    # --------------------------------------------------
    # Save outputs
    # --------------------------------------------------

    pd.DataFrame(selected_rows).to_csv(
        OUTPUT_DIR / "clean_image_manifest.csv",
        index=False,
    )

    pd.DataFrame(duplicate_rows).to_csv(
        OUTPUT_DIR / "duplicate_review.csv",
        index=False,
    )

    pd.DataFrame(missing_files).to_csv(
        OUTPUT_DIR / "missing_copied_files.csv",
        index=False,
    )

    pd.DataFrame(conflicting_grades).to_csv(
        OUTPUT_DIR / "conflicting_grades.csv",
        index=False,
    )

    # --------------------------------------------------
    # Summary
    # --------------------------------------------------

    result = pd.DataFrame(selected_rows)

    print("\n========== CLEAN IMAGE DATASET ==========")
    print(f"Input manifest entries: {len(manifest)}")
    print(f"Unique tissue IDs retained: {result['Normalized_ID'].nunique() if not result.empty else 0}")
    print(f"Images copied to clean folder: {len(result)}")
    print(f"Images with specialist-reviewed grade: {int(result['Has_Grade'].sum()) if not result.empty else 0}")
    print(f"Images without grade: {int((~result['Has_Grade']).sum()) if not result.empty else 0}")
    print(f"Tissue IDs needing duplicate review: {sum('manual review required' in row['Status'] for row in duplicate_rows)}")
    print(f"Missing copied files: {len(missing_files)}")
    print(f"Conflicting grade IDs: {len(conflicting_grades)}")
    print(f"Clean images: {CLEAN_IMAGE_DIR}")
    print(f"Reports: {OUTPUT_DIR}")



if __name__ == "__main__":
    main()
