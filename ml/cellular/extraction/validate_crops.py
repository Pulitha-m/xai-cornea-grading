"""
Phase 3, Step 3.6 — how segmentation errors carry through to cell features,
on the 40 annotated crops.

The same extraction (extraction/cells.py) runs on the reference masks and on a
segmentation run's out-of-fold predictions (default: the Phase 2 winner). Both
use the same analysable area (pixels not ignored in the reference). Cells are
matched one-to-one (IoU > 0.5) and compared:
  * per cell:  relative area error, side count (exact / within +-1)
  * per crop:  HEX %, CV of area, mean area, cell count (predicted vs reference)

Outputs: <outputs_dir>/extraction/crops/<run>/cells_matched.csv, crops.csv

Usage (from ml/cellular/; CPU is enough):
    python -m extraction.validate_crops
    python -m extraction.validate_crops --run cellpose_finetune_flat
"""

from __future__ import annotations

import argparse

import cv2
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import load_config
from data_prep.check_annotations import IGNORE
from extraction.cells import ExtractionParams, extract_cells, instances_from_mask, match_cells, summarise_cells
from segmentation.data import load_samples


def predicted_instances(seg_run_dir, crop_id: str) -> np.ndarray | None:
    """Instance labels of a run: saved instances (Cellpose / StarDist) or recovered from its mask."""
    inst = seg_run_dir / "inst" / f"{crop_id}.png"
    if inst.exists():
        return cv2.imread(str(inst), cv2.IMREAD_UNCHANGED).astype(np.int32)
    mask = seg_run_dir / "masks" / f"{crop_id}.png"
    return instances_from_mask(cv2.imread(str(mask), cv2.IMREAD_GRAYSCALE)) if mask.exists() else None


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Cell-feature agreement on the annotated crops.")
    ap.add_argument("--run", default=cfg["extraction"]["run"])
    args = ap.parse_args()

    p = ExtractionParams.from_config(cfg)
    seg_dir = cfg["paths"]["outputs_dir"] / "seg" / args.run
    out = cfg["paths"]["outputs_dir"] / "extraction" / "crops" / args.run
    out.mkdir(parents=True, exist_ok=True)

    cell_rows, crop_rows = [], []
    for s in load_samples(cfg, "raw"):
        pred_inst = predicted_instances(seg_dir, s.crop_id)
        if pred_inst is None:
            continue
        analysable = s.mask != IGNORE
        df_g, _, comp_g = extract_cells(instances_from_mask(s.mask), analysable, p)
        df_p, _, comp_p = extract_cells(pred_inst, analysable, p)

        m = match_cells(comp_p, comp_g)
        g = df_g.set_index("cell_id")
        q = df_p.set_index("cell_id")
        for r in m.itertuples(index=False):
            cell_rows.append({"crop_id": s.crop_id, "difficulty": s.meta["difficulty"], "iou": r.iou,
                              "area_gt": g.loc[r.gt_id, "area_px"], "area_pred": q.loc[r.pred_id, "area_px"],
                              "sides_gt": g.loc[r.gt_id, "sides"], "sides_pred": q.loc[r.pred_id, "sides"],
                              "compactness_gt": g.loc[r.gt_id, "compactness"],
                              "compactness_pred": q.loc[r.pred_id, "compactness"]})
        sg, sp = summarise_cells(df_g), summarise_cells(df_p)
        crop_rows.append({"crop_id": s.crop_id, "fold": s.fold, "ecd_band": s.meta["ecd_band"],
                          "difficulty": s.meta["difficulty"], "matched": len(m),
                          **{f"{k}_gt": v for k, v in sg.items()}, **{f"{k}_pred": v for k, v in sp.items()}})

    cells, crops = pd.DataFrame(cell_rows), pd.DataFrame(crop_rows)
    cells.to_csv(out / "cells_matched.csv", index=False)
    crops.to_csv(out / "crops.csv", index=False)

    cells["area_err_pct"] = 100 * (cells["area_pred"] - cells["area_gt"]) / cells["area_gt"]
    both = cells.dropna(subset=["sides_gt", "sides_pred"])
    diff = both["sides_pred"] - both["sides_gt"]
    print(f"{args.run}: {len(crops)} crops, {len(cells)} matched cells "
          f"({len(both)} with a side count in both)")
    print(f"  cell area error      median {cells['area_err_pct'].median():+.1f} %, "
          f"median |error| {cells['area_err_pct'].abs().median():.1f} %")
    print(f"  side count           exact {100 * (diff == 0).mean():.1f} %, within +-1 {100 * (diff.abs() <= 1).mean():.1f} %")
    print(f"  compactness          median |diff| {(cells['compactness_pred'] - cells['compactness_gt']).abs().median():.3f}")
    print("\nSide counts (rows = reference, columns = predicted):")
    print(pd.crosstab(both["sides_gt"].clip(3, 9).astype(int), both["sides_pred"].clip(3, 9).astype(int)).to_string())

    print("\nPer crop (predicted vs reference):")
    for col, unit in (("hex_pct", "points"), ("cv_area_pct", "points"), ("mean_area_px", "px")):
        a, b = crops[f"{col}_pred"], crops[f"{col}_gt"]
        print(f"  {col:13s} reference mean {b.mean():7.1f}  predicted mean {a.mean():7.1f}  "
              f"MAE {(a - b).abs().mean():6.2f} {unit}  Spearman {spearmanr(a, b).correlation:.2f}")
    print("  HEX % MAE by difficulty: " + ", ".join(
        f"{k} {(g['hex_pct_pred'] - g['hex_pct_gt']).abs().mean():.1f}" for k, g in crops.groupby("difficulty")))
    print(f"\nResults: {out}")


if __name__ == "__main__":
    main()
