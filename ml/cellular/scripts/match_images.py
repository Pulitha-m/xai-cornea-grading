"""
Match the user's 1000 image filenames to the Konan reports and emit the
validation ground truth for exactly those images.

Image filenames are extremely noisy (NE3B-, NBE-, NEB=, 'NEB--09-', double
spaces, etc.), so we DON'T match on the raw string. We match on a robust key:

    (tissue_serial, eye)

where tissue_serial = the 4-5 digit tissue number (the stable unique id, e.g.
11886, 15181, 4499) and eye = L/R. These survive the typos because the serial
digits and the trailing L/R are almost always intact.
"""
import re
import pandas as pd
from pathlib import Path

IMG_LIST = None  # set by main
GT = "dataset/validation_ground_truth.csv"


def norm_id(name):
    """Aggressive normalisation for exact full-ID matching: strip ext/suffix,
    uppercase, remove every non-alphanumeric char. 'HS-2022-442' -> 'HS2022442'."""
    s = re.sub(r"\.(jpg|jpeg|png|txt)$", "", name, flags=re.I)
    s = re.sub(r"_(SP|C)\s*$", "", s, flags=re.I)
    s = re.sub(r"T$", "", s)
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


def extract_key(name):
    """Return (serial, eye) from a filename or cornea_id string."""
    s = name
    # drop extension and the _SP / _C suffix
    s = re.sub(r"\.(jpg|jpeg|png|txt)$", "", s, flags=re.I)
    s = re.sub(r"_(SP|C)\s*$", "", s, flags=re.I)
    s = re.sub(r"T$", "", s)            # report files end in 'T'

    # --- eye: trailing L / R / RL (ignore the _SP already stripped) ---
    eye = None
    m = re.search(r"([LR])\s*$", s.strip())
    if m:
        eye = m.group(1).upper()
    # also handle 'RL' -> treat as R (rare)
    if re.search(r"RL\s*$", s.strip()):
        eye = "R"

    # --- serial: all digit groups, choose the tissue serial ---
    nums = re.findall(r"\d+", s)
    serial = None
    # prefer a 4-5 digit group that is NOT a year (1990-2035) and not a month
    cands = [n for n in nums if 4 <= len(n) <= 5 and not (1990 <= int(n) <= 2035)]
    if cands:
        serial = cands[-1]            # the last such group is the tissue serial
    else:
        # fallback: longest digit group
        if nums:
            serial = max(nums, key=len)
    return (serial, eye)


def main(img_list_path):
    gt = pd.read_csv(GT)
    # build lookup keyed by (serial, eye) and a serial-only fallback
    gt["serial"], gt["eye_key"] = zip(*gt["cornea_id"].map(extract_key))
    gt["nid"] = gt["cornea_id"].map(norm_id)
    by_nid = {}
    by_serial_eye = {}
    by_serial = {}
    for _, r in gt.iterrows():
        by_nid.setdefault(r["nid"], r)  # exact normalised-ID lookup (first wins)
        if r["serial"]:
            by_serial.setdefault(r["serial"], []).append(r)
            if r["eye_key"]:
                by_serial_eye[(r["serial"], r["eye_key"])] = r

    images = [ln.strip() for ln in Path(img_list_path).read_text().splitlines() if ln.strip()]

    matched, unmatched, ambiguous = [], [], []
    for img in images:
        serial, eye = extract_key(img)
        row = None
        how = ""
        # A serial is only trustworthy if it is a real 4-5 digit tissue number
        # that is NOT a year (e.g. "2021"). Year-like serials cause spurious
        # collisions, so they must never drive serial / serial+eye matching.
        valid_serial = bool(serial) and 4 <= len(serial) <= 5 and not (1990 <= int(serial) <= 2035)

        # Pass 0: exact normalised-ID match (reliable for HS-series and clean IDs)
        if norm_id(img) in by_nid:
            row, how = by_nid[norm_id(img)], "exact_id"
        elif valid_serial and eye and (serial, eye) in by_serial_eye:
            row, how = by_serial_eye[(serial, eye)], "serial+eye"
        elif valid_serial and serial in by_serial:
            cands = by_serial[serial]
            if len(cands) == 1:
                row, how = cands[0], "serial_only"
            else:
                # multiple eyes for this serial, eye unknown -> ambiguous
                ambiguous.append((img, serial, eye))
                continue
        if row is not None:
            # Trustworthy if the matched id carries a real tissue serial somewhere:
            #   - a 5-digit run >= 10000 (NEB serials), or
            #   - an HS/HSEB-series id, or
            #   - a short purely-numeric id (e.g. 4499, 5177).
            cid = str(row["cornea_id"])
            has_serial = (
                any(int(d) >= 10000 for d in re.findall(r"(?=(\d{5}))", cid))
                or bool(re.match(r"^\s*(HS|HSEB)", cid, re.I))
                or bool(re.fullmatch(r"\s*\d{3,5}\s*[LR]?\s*", cid))
            )
            rec = {"image_filename": img, "match_method": how,
                   "matched_cornea_id": row["cornea_id"],
                   "needs_review": (how == "serial_only") or (not has_serial)}
            for c in ["eye", "year", "grade", "donor_age", "ecd", "cv", "hex",
                      "sd", "mean_area", "num_cells", "area_um2", "ecd_check", "source_file"]:
                rec[c] = row[c]
            matched.append(rec)
        else:
            unmatched.append((img, serial, eye))

    mdf = pd.DataFrame(matched)
    Path("dataset").mkdir(exist_ok=True)
    mdf.to_csv("dataset/validation_ground_truth_1000.csv", index=False)
    pd.DataFrame(unmatched, columns=["image_filename", "parsed_serial", "parsed_eye"]) \
        .to_csv("dataset/unmatched_images.csv", index=False)
    pd.DataFrame(ambiguous, columns=["image_filename", "parsed_serial", "parsed_eye"]) \
        .to_csv("dataset/ambiguous_images.csv", index=False)

    print(f"Images in list     : {len(images)}")
    print(f"Matched            : {len(matched)}  "
          f"(serial+eye {sum(m['match_method']=='serial+eye' for m in matched)}, "
          f"serial-only {sum(m['match_method']=='serial_only' for m in matched)})")
    print(f"Unmatched          : {len(unmatched)}  -> unmatched_images.csv")
    print(f"Ambiguous          : {len(ambiguous)}  -> ambiguous_images.csv")
    if matched:
        dup = mdf["matched_cornea_id"].duplicated().sum()
        print(f"Reports matched >1 image: {dup}")
    return mdf, unmatched, ambiguous


if __name__ == "__main__":
    import sys
    main(sys.argv[1])
