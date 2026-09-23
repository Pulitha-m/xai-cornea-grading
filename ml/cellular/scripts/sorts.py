"""
Separate a mixed folder of Konan exports into three categories:

    specular images   (*_SP.jpg / .png / .tif)  -> dataset/images/
    report images      (*_C.jpg  / .png)          -> dataset/report_images/
    text reports       (*T.txt / *.txt)           -> dataset/reports/

It COPIES (not moves) by default, so your originals are never touched.
It also extracts the cornea id from each filename and prints how many
specular images pair with a text report (the pairing you need for Day 1).

Usage:
    python src/sort_files.py --src "/path/to/mixed/folder" --dest dataset
    # add --move to move instead of copy, --dry-run to preview only
"""
import argparse
import re
import shutil
from pathlib import Path
from collections import defaultdict

IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


def classify(name):
    """Return one of: 'specular', 'report_image', 'text', or 'other'."""
    low = name.lower()
    ext = Path(name).suffix.lower()

    if ext == ".txt":
        return "text"
    if ext in IMG_EXT:
        stem = Path(low).stem
        # specular: ends with _sp (optionally _sp_01 etc.)
        if re.search(r"_sp(\b|_|\d|$)", stem):
            return "specular"
        # report/colour iris image: ends with _c
        if re.search(r"_c(\b|_|\d|$)", stem):
            return "report_image"
        # fallback: unlabelled image -> treat as specular (most common)
        return "specular"
    return "other"


def cornea_id(name):
    """
    Extract the cornea id from a filename.
    Examples:
      4499_SP.jpg            -> 4499
      4499T.txt              -> 4499
      4499_C.jpg             -> 4499
      1787732510104_01_SP.jpg-> 1787732510104_01
      E.D.S-698-01_SP.png    -> E.D.S-698-01
    """
    stem = Path(name).stem
    # drop the trailing type marker
    stem = re.sub(r"[_-]?SP(_\d+)?$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[_-]?C(_\d+)?$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"T$", "", stem)  # 4499T -> 4499
    return stem.strip(" _-")


def run(src, dest, move=False, dry=False):
    src, dest = Path(src), Path(dest)
    cats = {
        "specular":     dest / "images",
        "report_image": dest / "report_images",
        "text":         dest / "reports",
        "other":        dest / "other",
    }
    if not dry:
        for d in cats.values():
            d.mkdir(parents=True, exist_ok=True)

    counts = defaultdict(int)
    ids = defaultdict(set)   # category -> set of cornea ids
    op = shutil.move if move else shutil.copy2

    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        cat = classify(f.name)
        counts[cat] += 1
        if cat in ("specular", "report_image", "text"):
            ids[cat].add(cornea_id(f.name))
        if not dry:
            target = cats[cat] / f.name
            if target.exists():                      # avoid clobbering duplicates
                target = cats[cat] / f"{f.stem}__dup{f.suffix}"
            op(str(f), str(target))

    # ---- report ----
    print(f"{'DRY RUN - nothing written' if dry else 'Done'}  (src={src})\n")
    for c in ("specular", "report_image", "text", "other"):
        print(f"  {c:14s} {counts[c]:5d} files"
              + (f"  | {len(ids[c])} unique cornea ids" if c != 'other' else ""))

    # pairing check — the thing Day 1 depends on
    sp, tx = ids["specular"], ids["text"]
    paired = sp & tx
    print(f"\nPairing (specular <-> text report):")
    print(f"  paired ids            : {len(paired)}")
    print(f"  specular without report: {len(sp - tx)}")
    print(f"  report without specular: {len(tx - sp)}")
    if sp - tx:
        print("  e.g. specular missing report:", list(sorted(sp - tx))[:5])
    if tx - sp:
        print("  e.g. report missing specular:", list(sorted(tx - sp))[:5])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="folder containing the mixed files")
    ap.add_argument("--dest", default="dataset", help="output root (default: dataset)")
    ap.add_argument("--move", action="store_true", help="move instead of copy")
    ap.add_argument("--dry-run", action="store_true", help="preview only, write nothing")
    a = ap.parse_args()
    run(a.src, a.dest, move=a.move, dry=a.dry_run)
