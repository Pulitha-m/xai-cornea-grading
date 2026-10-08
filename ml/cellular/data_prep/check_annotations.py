"""
Phase 1, Step 1.5 — check corrected annotations, build training masks, and
measure the classical baseline and inter-annotator agreement.

Reads the corrected GIMP/Krita layers of a round:

    <round>/corrected/<crop_id>_walls.png          annotator 1
    <round>/expert/corrected/<crop_id>_walls.png   NEBSL expert (overlap crops)

For every file it
  1. validates the export: size, transparency kept, colours (red = wall,
     blue = ignore), and flags a visible crop layer or anti-aliased brushes;
  2. writes a training mask  masks/<crop_id>.png  (0 = interior, 1 = wall,
     2 = ignore) — expert masks go to expert/masks/;
  3. checks cells: closed cells, suspiciously LARGE regions (probably a gap
     in a wall -> two cells merged) and tiny fragments (probably a stray wall);
  4. scores agreement with
       * the draft it started from     (how much was corrected),
       * the classical baseline (h from config.yaml) — the Phase 1 baseline,
       * the other annotator           (overlap crops only),
     using boundary F1 (walls matched within 2 px) and cell F1
     (cells matched at IoU > 0.5). Ignore regions are excluded.

Outputs: <round>/check_report.csv and a printed summary.

Usage (from ml/cellular/; on Colab after the setup cell):
    python -m data_prep.check_annotations                 # all corrected crops
    python -m data_prep.check_annotations --crop round1_000
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage.measure import label
from skimage.morphology import skeletonize

from config import load_config
from segmentation.classical import ClassicalParams, segment

INTERIOR, WALL, IGNORE = 0, 1, 2
BOUNDARY_TOLERANCE_PX = 2
CELL_IOU_MATCH = 0.5
MAX_OTHER_COLOUR_SHARE = 0.20      # more than this -> crop layer was visible at export


# -----------------------------------------------------------------------------
# Reading an exported layer
# -----------------------------------------------------------------------------
def read_layer(path: Path, size: int) -> tuple[np.ndarray | None, list[str], list[str]]:
    """Return (mask 0/1/2, errors, warnings) for one exported walls layer."""
    errors, warnings = [], []
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None, [f"cannot read {path.name}"], warnings
    if img.shape[:2] != (size, size):
        return None, [f"size {img.shape[1]}x{img.shape[0]}, expected {size}x{size}"], warnings

    if img.ndim == 2 or img.shape[2] == 3:
        warnings.append("no transparency (alpha) in export - reading colours only")
        bgr = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        alpha = np.full(img.shape[:2], 255, np.uint8)
    else:
        bgr, alpha = img[..., :3], img[..., 3]
    b, g, r = (bgr[..., i].astype(int) for i in range(3))
    opaque = alpha > 127

    red = opaque & (r >= 150) & (g <= 100) & (b <= 100)
    blue = opaque & (b >= 150) & (r <= 100) & (g <= 100)
    other = opaque & ~red & ~blue

    if other.mean() > MAX_OTHER_COLOUR_SHARE:
        errors.append(f"{other.mean():.0%} of pixels are neither red nor blue - the crop layer was "
                      "probably visible when exporting (hide it, then export again)")
        return None, errors, warnings
    if other.any():
        warnings.append(f"{int(other.sum())} off-colour pixels (soft/anti-aliased brush?) - "
                        "assigned to the nearest of red / blue")

    mask = np.full((size, size), INTERIOR, np.uint8)
    mask[red | (other & (r >= b))] = WALL
    mask[blue | (other & (b > r))] = IGNORE
    return mask, errors, warnings


# -----------------------------------------------------------------------------
# Cells and agreement
# -----------------------------------------------------------------------------
def cells_from_mask(mask: np.ndarray) -> np.ndarray:
    """Label complete cells: interior regions not touching the crop border or ignore areas."""
    interior = mask == INTERIOR
    labels = label(interior, connectivity=1)                 # 4-connectivity: 1-px walls separate
    edge = np.zeros_like(interior)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    edge |= ndi.binary_dilation(mask == IGNORE, iterations=2)
    touching = np.unique(labels[edge])
    labels[np.isin(labels, touching)] = 0
    return labels


def cell_issues(labels: np.ndarray, expected_area: float) -> dict:
    areas = np.bincount(labels.ravel())[1:]
    areas = areas[areas > 0]
    return {
        "n_cells": int(len(areas)),
        "n_large_regions": int((areas > 2.5 * expected_area).sum()),   # likely a wall gap
        "n_tiny_fragments": int((areas < 0.25 * expected_area).sum()),  # likely a stray wall
        "mean_cell_area_px": float(areas.mean()) if len(areas) else float("nan"),
    }


def boundary_f1(pred_walls: np.ndarray, gt_walls: np.ndarray, keep: np.ndarray) -> float:
    """F1 of 1-px wall skeletons matched within BOUNDARY_TOLERANCE_PX, inside `keep`."""
    p = skeletonize(pred_walls) & keep
    g = skeletonize(gt_walls) & keep
    if not p.any() or not g.any():
        return float("nan")
    precision = (ndi.distance_transform_edt(~g)[p] <= BOUNDARY_TOLERANCE_PX).mean()
    recall = (ndi.distance_transform_edt(~p)[g] <= BOUNDARY_TOLERANCE_PX).mean()
    return float(2 * precision * recall / (precision + recall + 1e-9))


def cell_f1(pred_labels: np.ndarray, gt_labels: np.ndarray) -> float:
    """Cell-level F1: a match is a pair of cells with IoU > 0.5 (one-to-one by construction)."""
    n_pred, n_gt = int(pred_labels.max()), int(gt_labels.max())
    if n_pred == 0 or n_gt == 0:
        return float("nan")
    both = (pred_labels > 0) & (gt_labels > 0)
    pairs = np.bincount(pred_labels[both].astype(np.int64) * (n_gt + 1) + gt_labels[both],
                        minlength=(n_pred + 1) * (n_gt + 1)).reshape(n_pred + 1, n_gt + 1)
    area_p = np.bincount(pred_labels.ravel(), minlength=n_pred + 1)
    area_g = np.bincount(gt_labels.ravel(), minlength=n_gt + 1)
    iou = pairs / (area_p[:, None] + area_g[None, :] - pairs + 1e-9)
    tp = int((iou[1:, 1:] > CELL_IOU_MATCH).sum())
    pred_count = len(np.unique(pred_labels)) - 1
    gt_count = len(np.unique(gt_labels)) - 1
    return float(2 * tp / (pred_count + gt_count))


def agreement(pred_mask: np.ndarray, gt_mask: np.ndarray) -> dict:
    keep = (pred_mask != IGNORE) & (gt_mask != IGNORE)
    merged_ignore = np.where(keep, 0, IGNORE).astype(np.uint8)
    pred = np.maximum(pred_mask * (pred_mask == WALL), merged_ignore)
    gt = np.maximum(gt_mask * (gt_mask == WALL), merged_ignore)
    return {"boundary_f1": boundary_f1(pred == WALL, gt == WALL, keep),
            "cell_f1": cell_f1(cells_from_mask(pred), cells_from_mask(gt))}


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Check corrected annotation layers.")
    ap.add_argument("--crop", help="check only this crop_id (e.g. round1_000)")
    args = ap.parse_args()

    cfg = load_config()
    paths, ann = cfg["paths"], cfg["annotation"]
    size = ann["crop_size"]
    rd = paths["annotations_dir"] / "seg" / ann["round"]
    index = pd.read_csv(rd / "index.csv").set_index("crop_id")
    baseline_params = ClassicalParams.from_config(cfg)
    um_per_px = cfg["scale"]["um_per_px_prelim"]       # sanity checks only

    def expected_area_px(crop_id: str) -> float:
        """Expected cell area for this tissue (Konan ECD -> um^2 -> px), so low-ECD
        crops with genuinely large cells are not flagged as wall gaps."""
        return 1e6 / float(index.loc[crop_id, "ecd"]) / um_per_px ** 2

    sources = {"annotator": rd / "corrected", "expert": rd / "expert" / "corrected"}
    masks: dict[tuple[str, str], np.ndarray] = {}
    rows = []

    for who, folder in sources.items():
        mask_dir = (rd if who == "annotator" else rd / "expert") / "masks"
        mask_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(folder.glob("*_walls.png")):
            crop_id = path.name.replace("_walls.png", "")
            if args.crop and crop_id != args.crop:
                continue
            if crop_id not in index.index:
                rows.append({"crop_id": crop_id, "who": who, "status": "ERROR",
                             "errors": "not in index.csv (wrong file name?)"})
                continue

            mask, errors, warnings = read_layer(path, size)
            row = {"crop_id": crop_id, "who": who, "status": "ERROR" if errors else "OK",
                   "errors": "; ".join(errors), "warnings": "; ".join(warnings)}
            if mask is not None:
                cv2.imwrite(str(mask_dir / f"{crop_id}.png"), mask)
                masks[(who, crop_id)] = mask
                row.update(cell_issues(cells_from_mask(mask), expected_area_px(crop_id)))
                row["ignore_share"] = round(float((mask == IGNORE).mean()), 3)

                draft, _, _ = read_layer(rd / "drafts" / f"{crop_id}_walls.png", size)
                if draft is not None:
                    row.update({f"draft_{k}": v for k, v in agreement(draft, mask).items()})

                meta = index.loc[crop_id]
                img = cv2.imread(str(paths["images_dir"] / meta["image_file"]), cv2.IMREAD_GRAYSCALE)
                y0, x0 = int(meta["y0"]), int(meta["x0"])
                base = segment(img, baseline_params)
                base_mask = np.where(base.boundary[y0:y0 + size, x0:x0 + size] > 0, WALL, INTERIOR)
                base_mask[~base.valid[y0:y0 + size, x0:x0 + size]] = IGNORE
                row.update({f"baseline_{k}": v for k, v in agreement(base_mask.astype(np.uint8), mask).items()})
                if row.get("n_large_regions", 0) or row.get("n_tiny_fragments", 0):
                    row["status"] = "CHECK" if row["status"] == "OK" else row["status"]
            rows.append(row)

    # inter-annotator agreement on overlap crops done by both
    for (who, crop_id), m in list(masks.items()):
        if who == "expert" and ("annotator", crop_id) in masks:
            ia = agreement(masks[("annotator", crop_id)], m)
            rows.append({"crop_id": crop_id, "who": "inter-annotator", "status": "OK",
                         **{f"inter_{k}": v for k, v in ia.items()}})

    report = pd.DataFrame(rows)
    if report.empty:
        print(f"No corrected files found in {sources['annotator']} or {sources['expert']}.")
        return
    report.to_csv(rd / "check_report.csv", index=False)

    pd.set_option("display.width", 200)
    show = [c for c in ["crop_id", "who", "status", "n_cells", "n_large_regions", "n_tiny_fragments",
                        "ignore_share", "draft_boundary_f1", "baseline_boundary_f1", "baseline_cell_f1",
                        "inter_boundary_f1", "inter_cell_f1"] if c in report]
    print(report[show].round(3).to_string(index=False))
    for _, r in report.iterrows():
        for kind in ("errors", "warnings"):
            if isinstance(r.get(kind), str) and r[kind]:
                print(f"  {r['crop_id']} [{r['who']}] {kind}: {r[kind]}")
    flagged = report[report["status"] == "CHECK"]
    if not flagged.empty:
        print("\nCHECK = possible wall gap (large region) or stray wall (tiny fragment); "
              "re-open in GIMP and fix: " + ", ".join(flagged["crop_id"]))

    done = report[(report["who"] == "annotator") & (report["status"] != "ERROR")]
    if len(done):
        print(f"\nAnnotator crops OK: {len(done)} / {len(index)}  |  baseline vs annotation: "
              f"boundary F1 {done['baseline_boundary_f1'].mean():.3f}, "
              f"cell F1 {done['baseline_cell_f1'].mean():.3f}")
    print(f"Masks: {rd / 'masks'}  |  report: {rd / 'check_report.csv'}")


if __name__ == "__main__":
    main()
