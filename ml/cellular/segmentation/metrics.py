"""
Phase 2 — one scoring function for every model in the comparison.

All scores compare a predicted mask (0 interior / 1 wall / 2 ignore) with the
reference mask, excluding ignore regions of either:
  cell_f1, boundary_f1      as in Phase 1 (data_prep/check_annotations.py)
  dice/iou_interior         pixel overlap of cell interiors (scope targets 0.85 / 0.80)
  dice_wall                 pixel overlap of walls (strict: walls are 1-3 px wide)
  n_cells_pred/gt, area_ratio   complete cells and mean-area ratio (biomarker sanity)
  area_ratio_tess           mean-area ratio with cells measured up to the wall centre
                            line, so it no longer depends on how thick each model
                            draws walls (1-px watershed lines vs ~2-px reference walls
                            vs gaps between Cellpose cells)
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage.measure import label
from skimage.segmentation import expand_labels

from data_prep.check_annotations import IGNORE, INTERIOR, WALL, agreement, cells_from_mask

# Cells grow into neighbouring wall pixels by at most this distance (nearest cell
# wins), i.e. up to the wall centre line. Larger empty areas (dark or blurry
# regions a model left out) stay unassigned. Same rule for reference and models.
TESS_GROW_PX = 3


def tessellated_cells(mask: np.ndarray) -> np.ndarray:
    """Complete cells grown up to the wall centre line; cells touching the border or ignore are dropped."""
    grown = expand_labels(label(mask == INTERIOR, connectivity=1), distance=TESS_GROW_PX)
    grown[mask == IGNORE] = 0
    edge = np.zeros(mask.shape, bool)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    edge |= ndi.binary_dilation(mask == IGNORE, iterations=2)
    grown[np.isin(grown, np.unique(grown[edge]))] = 0
    return grown


def _overlap(pred: np.ndarray, gt: np.ndarray, cls: int, keep: np.ndarray) -> tuple[float, float]:
    p, g = (pred == cls) & keep, (gt == cls) & keep
    inter, union = (p & g).sum(), (p | g).sum()
    total = p.sum() + g.sum()
    return (2 * inter / total if total else float("nan")), (inter / union if union else float("nan"))


def score_crop(pred_mask: np.ndarray, gt_mask: np.ndarray) -> dict:
    keep = (pred_mask != IGNORE) & (gt_mask != IGNORE)
    out = agreement(pred_mask, gt_mask)
    out["dice_interior"], out["iou_interior"] = _overlap(pred_mask, gt_mask, INTERIOR, keep)
    out["dice_wall"], _ = _overlap(pred_mask, gt_mask, WALL, keep)

    restrict = lambda m: np.where(keep, m, IGNORE).astype(np.uint8)
    areas = [np.bincount(cells_from_mask(restrict(m)).ravel())[1:] for m in (pred_mask, gt_mask)]
    areas = [a[a > 0] for a in areas]
    out["n_cells_pred"], out["n_cells_gt"] = len(areas[0]), len(areas[1])
    out["area_ratio"] = (areas[0].mean() / areas[1].mean()) if len(areas[0]) and len(areas[1]) else float("nan")

    tess = [np.bincount(tessellated_cells(restrict(m)).ravel())[1:] for m in (pred_mask, gt_mask)]
    tess = [a[a > 0] for a in tess]
    out["area_ratio_tess"] = (tess[0].mean() / tess[1].mean()) if len(tess[0]) and len(tess[1]) else float("nan")
    return out


def score_run(samples: list, pred_masks: dict[str, np.ndarray], out_dir: Path) -> pd.DataFrame:
    """Score predicted masks {crop_id: mask}; write them to out_dir/masks/ and scores.csv."""
    (out_dir / "masks").mkdir(parents=True, exist_ok=True)
    rows = []
    for s in samples:
        if s.crop_id not in pred_masks:
            continue
        pred = pred_masks[s.crop_id]
        cv2.imwrite(str(out_dir / "masks" / f"{s.crop_id}.png"), pred)
        rows.append({"crop_id": s.crop_id, "fold": s.fold, "mask_source": s.mask_source,
                     "ecd": s.meta["ecd"], "ecd_band": s.meta["ecd_band"],
                     "difficulty": s.meta["difficulty"], **score_crop(pred, s.mask)})
    scores = pd.DataFrame(rows)
    scores.to_csv(out_dir / "scores.csv", index=False)
    return scores


def summarise(scores: pd.DataFrame, cols=("cell_f1", "boundary_f1", "dice_interior", "iou_interior")) -> dict:
    """Mean and SD over folds (each fold = mean of its crops)."""
    per_fold = scores.groupby("fold")[list(cols)].mean()
    return {**{f"{c}_mean": per_fold[c].mean() for c in cols},
            **{f"{c}_sd": per_fold[c].std(ddof=1) for c in cols},
            "n_crops": len(scores), "n_folds": len(per_fold)}


def print_summary(name: str, scores: pd.DataFrame) -> None:
    if scores.empty:
        print(f"\n{name}: no predictions yet")
        return
    s = summarise(scores)
    print(f"\n{name}: {s['n_crops']} crops, {s['n_folds']} folds")
    for c in ("cell_f1", "boundary_f1", "dice_interior", "iou_interior"):
        print(f"  {c:14s} {s[c + '_mean']:.3f} +- {s[c + '_sd']:.3f}")
    print("  cell F1 by difficulty: " + ", ".join(
        f"{k} {v:.3f}" for k, v in scores.groupby("difficulty")["cell_f1"].mean().items()))
