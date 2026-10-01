import os
import shutil
import pandas as pd

# ============================================================
# PATHS
# ============================================================

# Your final Excel file
excel_file = r"C:\Users\minsa_\Downloads\Disease_Labels_Final_filled.xlsx"

# Your external hard drive folder
# NOTE: The actual folder name is "CellChechD"
source_folder = r"D:\CellChechD"

# Folder where ONLY the required cell images will be copied
output_folder = r"C:\Users\minsa_\OneDrive\Desktop\Disease_Cell_Images"


# ============================================================
# CHECK PATHS
# ============================================================

if not os.path.exists(excel_file):
    print("ERROR: Excel file not found:")
    print(excel_file)
    raise SystemExit

if not os.path.exists(source_folder):
    print("ERROR: Image source folder not found:")
    print(source_folder)
    raise SystemExit


# ============================================================
# READ EXCEL
# ============================================================

df = pd.read_excel(excel_file)

print("Excel columns:")
print(df.columns.tolist())

if "Image_ID" not in df.columns:
    print("\nERROR: 'Image_ID' column was not found in the Excel file.")
    raise SystemExit

image_ids = df["Image_ID"].dropna().astype(str).str.strip()

print("\nImages required from Excel:", len(image_ids))


# ============================================================
# REMOVE OLD OUTPUT FOLDER
# ============================================================

if os.path.exists(output_folder):
    print("\nRemoving old output folder...")
    shutil.rmtree(output_folder)

os.makedirs(output_folder)


# ============================================================
# FIND ALL _SP.JPG CELL IMAGES
# ============================================================

print("\nScanning:", source_folder)

all_images = {}

for root, dirs, files in os.walk(source_folder):

    for file in files:

        # Only cell images ending with _SP.jpg
        if file.lower().endswith("_sp.jpg"):

            filename_without_extension = os.path.splitext(file)[0]

            # Store lowercase filename for case-insensitive matching
            all_images[filename_without_extension.lower()] = os.path.join(
                root, file
            )

print("Total _SP.jpg images found:", len(all_images))


# ============================================================
# MATCH EXCEL IMAGE IDs AND COPY
# ============================================================

found = 0
missing = 0

for image_id in image_ids:

    clean_id = image_id.strip()

    # Remove .jpg if it is included in Excel
    if clean_id.lower().endswith(".jpg"):
        clean_id = clean_id[:-4]

    key = clean_id.lower()

    if key in all_images:

        source_file = all_images[key]

        destination_file = os.path.join(
            output_folder,
            os.path.basename(source_file)
        )

        shutil.copy2(source_file, destination_file)

        found += 1

    else:

        missing += 1
        print("MISSING:", image_id)


# ============================================================
# FINAL RESULT
# ============================================================
