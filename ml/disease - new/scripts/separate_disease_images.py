
import os
import shutil
import pandas as pd
import re

# ============================================================
# 1. PATHS
# ============================================================

EXCEL_FILE = r"C:\Users\minsa_\Downloads\Disesase next.xlsx"

# Folder containing the SP images
IMAGE_FOLDER = r"C:\Users\minsa_\OneDrive\Desktop\Disease_Cell_Images"

# Output folder
OUTPUT_FOLDER = r"C:\Users\minsa_\OneDrive\Desktop\Disease_Images_Seperated_next"


# ============================================================
# 2. EXCEL COLUMNS
# ============================================================

# New Excel uses Image_ID instead of SP_Image_File
IMAGE_COLUMN = "Image_ID"

LABEL_COLUMN = "Disease_Label"


# ============================================================
# 3. DISEASE FOLDER NAMES
# ============================================================

FOLDER_NAMES = {
    "FECD": "FECD",

    "Guttata": "Guttata",

    "Folds": "Folds",

    "Normal": "Normal",

    "Polymorphism and pleomorphism":
        "Polymorphism_Pleomorphism",

    "Low cell density":
        "Low_Cell_Density",

    "Poor cornea":
        "Poor_Cornea"
}


# ============================================================
# 4. READ EXCEL
# ============================================================

print("=" * 60)
print("READING DATASET")
print("=" * 60)

df = pd.read_excel(EXCEL_FILE)

print(f"Excel rows: {len(df)}")


# ============================================================
# 5. CHECK COLUMNS
# ============================================================

if IMAGE_COLUMN not in df.columns:

    print(f"\nERROR: '{IMAGE_COLUMN}' column not found.")

    print("\nAvailable columns:")
    print(df.columns.tolist())

    exit()


if LABEL_COLUMN not in df.columns:

    print(f"\nERROR: '{LABEL_COLUMN}' column not found.")

    print("\nAvailable columns:")
    print(df.columns.tolist())

    exit()


# ============================================================
# 6. CHECK IMAGE FOLDER
# ============================================================

if not os.path.isdir(IMAGE_FOLDER):

    print("\nERROR: Image folder does not exist:")
    print(IMAGE_FOLDER)

    exit()


# ============================================================
# 7. CREATE OUTPUT FOLDER
# ============================================================

os.makedirs(
    OUTPUT_FOLDER,
    exist_ok=True
)


# ============================================================
# 8. CREATE DISEASE FOLDERS
# ============================================================

for folder_name in FOLDER_NAMES.values():

    os.makedirs(
        os.path.join(
            OUTPUT_FOLDER,
            folder_name
        ),
        exist_ok=True
    )


# ============================================================
# 9. STATISTICS
# ============================================================

copied_images = 0
missing_images = 0
empty_labels = 0
skipped_non_sp = 0

missing_files = []

disease_counts = {}


# ============================================================
# 10. PROCESS EACH ROW
# ============================================================

print("\nProcessing images...")
print("-" * 60)

for index, row in df.iterrows():

    # --------------------------------------------------------
    # Get Image_ID
    # --------------------------------------------------------

    image_id = row[IMAGE_COLUMN]

    if pd.isna(image_id):
        continue

    image_id = str(image_id).strip()


    # --------------------------------------------------------
    # Add .jpg
    #
    # Excel:
    # NEB-2023-01-14659 R_SP
    #
    # Actual image:
    # NEB-2023-01-14659 R_SP.jpg
    # --------------------------------------------------------

    image_name = image_id

    if not image_name.lower().endswith(".jpg"):
        image_name += ".jpg"


    # --------------------------------------------------------
    # Make sure this is an SP image
    # --------------------------------------------------------

    if "_SP" not in image_name.upper():

        skipped_non_sp += 1

        print(
            f"[SKIPPED - NOT SP] {image_name}"
        )

        continue


    # --------------------------------------------------------
    # Get disease label
    # --------------------------------------------------------

    disease_label = row[LABEL_COLUMN]

    if pd.isna(disease_label):

        empty_labels += 1
        continue

    disease_label = str(
        disease_label
    ).strip()


    if disease_label == "":

        empty_labels += 1
        continue


    # --------------------------------------------------------
    # Skip images without a CellChek disease label
    # --------------------------------------------------------

    if disease_label.lower() == \
            "not labelled (no cellchek report)":

        print(
            f"[SKIPPED - NOT LABELLED] {image_name}"
        )

        continue


    # --------------------------------------------------------
    # Find image
    # --------------------------------------------------------

    source_image = os.path.join(
        IMAGE_FOLDER,
        image_name
    )


    # --------------------------------------------------------
    # Check image exists
    # --------------------------------------------------------

    if not os.path.isfile(source_image):

        missing_images += 1

        missing_files.append(
            image_name
        )

        print(
            f"[MISSING] {image_name}"
        )

        continue


    # --------------------------------------------------------
    # Split multiple diseases
    #
    # Example:
    #
    # FECD; Polymorphism and pleomorphism; Low cell density
    #
    # becomes:
    #
    # FECD
    # Polymorphism and pleomorphism
    # Low cell density
    # --------------------------------------------------------

    labels = disease_label.split(";")


    # Remove spaces, empty values and duplicates
    labels = list(
        dict.fromkeys(
            label.strip()
            for label in labels
            if label.strip()
        )
    )


    # --------------------------------------------------------
    # COPY IMAGE INTO EVERY RELATED FOLDER
    # --------------------------------------------------------

    for label in labels:

        folder_name = None


        # Exact match
        if label in FOLDER_NAMES:

            folder_name = FOLDER_NAMES[label]


        # Case-insensitive match
        else:

            for key, value in FOLDER_NAMES.items():

                if key.lower() == label.lower():

                    folder_name = value
                    break


        # ----------------------------------------------------
        # Unknown label
        # ----------------------------------------------------

        if folder_name is None:

            folder_name = re.sub(
                r'[<>:"/\\|?*]',
                '_',
                label
            )

            os.makedirs(
                os.path.join(
                    OUTPUT_FOLDER,
                    folder_name
                ),
                exist_ok=True
            )

            print(
                f"[NEW LABEL] {label} -> {folder_name}"
            )


        # ----------------------------------------------------
        # Destination
        # ----------------------------------------------------

        destination = os.path.join(
            OUTPUT_FOLDER,
            folder_name,
            image_name
        )


        # ----------------------------------------------------
        # Copy image
        # ----------------------------------------------------

        if not os.path.exists(destination):

            shutil.copy2(
                source_image,
                destination
            )

            copied_images += 1


        # ----------------------------------------------------
        # Count
        # ----------------------------------------------------

        disease_counts[folder_name] = (
            disease_counts.get(
                folder_name,
                0
            ) + 1
        )


# ============================================================
# 11. SAVE MISSING IMAGE LIST
# ============================================================

if missing_files:

    missing_file = os.path.join(
        OUTPUT_FOLDER,
        "missing_images.txt"
    )

    with open(
        missing_file,
        "w",
        encoding="utf-8"
    ) as f:

        for filename in missing_files:

            f.write(
                filename + "\n"
            )


# ============================================================
# 12. FINAL SUMMARY
# ============================================================

print("\n")
print("=" * 60)
print("PROCESS COMPLETED")
print("=" * 60)

print(
    f"\nExcel rows:          {len(df)}"
)

print(
    f"Images copied:       {copied_images}"
)

print(
    f"Missing images:      {missing_images}"
)

print(
    f"Empty labels:        {empty_labels}"
)

print(
    f"Non-SP skipped:      {skipped_non_sp}"
)


# ============================================================
# 13. DISEASE COUNTS
# ============================================================

print("\nImages per disease:")
print("-" * 60)

for disease, count in sorted(
    disease_counts.items()
):

    print(
        f"{disease:<35} {count}"
    )


# ============================================================
# 14. MISSING FILE INFORMATION
# ============================================================

if missing_files:

    print(
        "\nMissing image list saved to:"
    )

    print(
        os.path.join(
            OUTPUT_FOLDER,
            "missing_images.txt"
        )
    )


# ============================================================
# 15. OUTPUT LOCATION
# ============================================================

print("\nOutput folder:")
print(OUTPUT_FOLDER)

print("\nDone!")