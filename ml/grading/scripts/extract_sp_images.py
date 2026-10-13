
from pathlib import Path
import shutil
import pandas as pd

# --------------------------------------------------
# Paths
# --------------------------------------------------

# Folder containing the original images
IMAGE_DIR = Path(
    r"C:\Users\pulit\OneDrive\Desktop\University\Y4S1\research\CellChechD"
)

# Cleaned dataset
DATASET_PATH = Path(
    r"C:\Users\pulit\OneDrive\Desktop\University\Y4S1\research\xai-cornea-grading\ml\grading\data\processed\cleaned_grading_dataset.xlsx"
)

# Use a NEW folder to avoid mixing with previous extraction results
OUTPUT_DIR = Path(
    r"C:\Users\pulit\OneDrive\Desktop\University\Y4S1\research\xai-cornea-grading\ml\grading\data\images_sp_v2"
)

TISSUE_ID_COLUMN = "Tissue_ID"
IMAGE_SUFFIX = "_SP.jpg"


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def normalize_tissue_id(value):
    """Normalize spacing and case for reliable tissue ID matching."""
    value = str(value).strip()
    value = " ".join(value.split())

    if value.upper().startswith("NEB-"):
        value = "NEB-" + value[4:].lstrip()

    return value.casefold()


def main():
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    if not IMAGE_DIR.exists():
        raise FileNotFoundError(f"Image folder not found: {IMAGE_DIR}")

    # --------------------------------------------------
    # Read and normalize dataset tissue IDs
    # --------------------------------------------------

    df = pd.read_excel(DATASET_PATH)

    if TISSUE_ID_COLUMN not in df.columns:
        raise ValueError(
            f"Column '{TISSUE_ID_COLUMN}' not found in dataset."
        )

    tissue_ids = (
        df[TISSUE_ID_COLUMN]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )

    # Normalized ID -> original dataset ID
    dataset_ids = {}

    for tissue_id in tissue_ids:
        key = normalize_tissue_id(tissue_id)
        dataset_ids.setdefault(key, []).append(tissue_id)

    # --------------------------------------------------
    # Index source images ending exactly in _SP.jpg
    # --------------------------------------------------

    print("Scanning original image directory...")

    image_index = {}

    for image_path in IMAGE_DIR.rglob("*"):
        if not image_path.is_file():
            continue

        if not image_path.name.lower().endswith(IMAGE_SUFFIX.lower()):
            continue

        # Remove only the final _SP.jpg suffix
        filename_id = image_path.name[:-len(IMAGE_SUFFIX)]
        key = normalize_tissue_id(filename_id)

        image_index.setdefault(key, []).append(image_path)

    # --------------------------------------------------
    # Copy matching images and record results
    # --------------------------------------------------

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    copied = 0
    missing = []
    multiple_matches = []
    unmatched_source_images = []
    manifest_rows = []

    for key, original_ids in dataset_ids.items():
        matches = image_index.get(key, [])

        # Use the original ID from Excel for reporting
        tissue_id = original_ids[0]

        if not matches:
            missing.append({
                "Tissue_ID": tissue_id,
                "Normalized_ID": key,
            })
            continue

        if len(matches) > 1:
            multiple_matches.append({
                "Tissue_ID": tissue_id,
                "Match_Count": len(matches),
                "Source_Paths": " | ".join(str(p) for p in matches),
            })

        for source in matches:
            # Keep original filename when possible.
            # If the same filename appears in different source folders,
            # create a distinct destination name.
            destination = OUTPUT_DIR / source.name

            if destination.exists():
                destination = OUTPUT_DIR / (
                    f"{source.parent.name}_{source.name}"
                )

            shutil.copy2(source, destination)
            copied += 1

            manifest_rows.append({
                "Tissue_ID": tissue_id,
                "Normalized_ID": key,
                "Source_Path": str(source),
                "Copied_Path": str(destination),
                "Original_Filename": source.name,
            })

    # Find source SP images that do not match any dataset ID
    for key, paths in image_index.items():
        if key not in dataset_ids:
            for path in paths:
                unmatched_source_images.append({
                    "Filename_ID": path.name[:-len(IMAGE_SUFFIX)],
                    "Normalized_ID": key,
                    "Source_Path": str(path),
                })

    # --------------------------------------------------
    # Save reports
    # --------------------------------------------------

    pd.DataFrame(manifest_rows).to_csv(
        OUTPUT_DIR / "image_manifest.csv",
        index=False
    )

    pd.DataFrame(missing).to_csv(
        OUTPUT_DIR / "missing_images.csv",
        index=False
    )

    pd.DataFrame(multiple_matches).to_csv(
        OUTPUT_DIR / "multiple_matches.csv",
        index=False
    )

    pd.DataFrame(unmatched_source_images).to_csv(
        OUTPUT_DIR / "unmatched_source_images.csv",
        index=False
    )

    # --------------------------------------------------
    # Summary
    # --------------------------------------------------

    print("\n========== EXTRACTION SUMMARY ==========")
    print(f"Unique dataset tissue IDs: {len(dataset_ids)}")
    print(f"Source tissue IDs with SP images: {len(image_index)}")
    print(f"Images copied: {copied}")
    print(f"Tissue IDs with no matching image: {len(missing)}")
    print(f"Tissue IDs with multiple source matches: {len(multiple_matches)}")
    print(f"Unmatched source image files: {len(unmatched_source_images)}")
    print(f"Output folder: {OUTPUT_DIR}")
    print("\nReports saved:")
    print("  image_manifest.csv")
    print("  missing_images.csv")
    print("  multiple_matches.csv")
    print("  unmatched_source_images.csv")


if __name__ == "__main__":
    main()
