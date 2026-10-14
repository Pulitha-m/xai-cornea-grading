import os, zipfile
from PIL import Image

SRC = r"C:\Users\minsa_\OneDrive\Desktop\Disease_Cell_Images"
OUT_ZIP = r"C:\Users\minsa_\OneDrive\Desktop\xai-cornea-grading\SP_images_640_resized.zip"

files = [f for f in os.listdir(SRC) if f.lower().endswith("_sp.jpg")]
print("SP images found:", len(files))

with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for i, f in enumerate(files, 1):
        im = Image.open(os.path.join(SRC, f)).convert("L")
        im.thumbnail((640, 640))
        tmp = os.path.join(os.environ["TEMP"], "tmp_sp.jpg")
        im.save(tmp, "JPEG", quality=92)
        z.write(tmp, arcname=f)
        if i % 100 == 0:
            print(i, "done")

print("Saved:", OUT_ZIP, round(os.path.getsize(OUT_ZIP) / 1e6, 1), "MB")