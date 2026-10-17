"""CSV row <-> image file matching, identical to the v2 notebooks (Step 3 of 06/08/10).

Pass 1: exact match after lower-casing and removing everything but letters and digits.
Pass 2: tissue number + eye (e.g. "15063L"), only for images not already taken and
only when unambiguous.
"""
import glob
import os
import re

import pandas as pd

IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def short_key(s) -> str | None:
    m = re.search(r"(\d{4,6})[\s_\-]*([LR])(?![A-Z])", str(s).upper())
    return f"{m.group(1)}{m.group(2)}" if m else None


def list_images(image_dir: str) -> list[str]:
    paths = [p for p in glob.glob(os.path.join(image_dir, "**", "*"), recursive=True)
             if p.lower().endswith(IMG_EXT) and "__MACOSX" not in p]
    return sorted(paths)


def match_images(df: pd.DataFrame, image_paths: list[str]) -> pd.DataFrame:
    """Returns df with an Img_Path column (None where no image matched)."""
    df = df.copy()
    full_map, short_map = {}, {}
    for p in image_paths:
        stem = os.path.splitext(os.path.basename(p))[0]
        full_map.setdefault(norm(stem), p)
        sk = short_key(stem)
        if sk:
            short_map.setdefault(sk, []).append(p)

    df["Img_Path"] = df["Tissue_ID"].map(lambda t: full_map.get(norm(t)))
    taken = set(df["Img_Path"].dropna())
    sk_rows = df[df["Img_Path"].isna()]["Tissue_ID"].map(short_key)
    for i, k in sk_rows.items():
        cands = [p for p in short_map.get(k or "", []) if p not in taken]
        if len(cands) == 1 and (sk_rows == k).sum() == 1:
            df.at[i, "Img_Path"] = cands[0]
            taken.add(cands[0])
    return df
