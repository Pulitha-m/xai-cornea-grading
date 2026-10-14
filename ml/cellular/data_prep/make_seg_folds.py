"""
Phase 2, Step 2.1 — fixed cross-validation folds shared by ALL segmentation models.

The 40 annotated crops (one per tissue, so tissue grouping holds automatically)
are dealt into ``seg_models.n_folds`` folds, spread evenly over ECD band x
difficulty strata. Every model in the comparison — classical, U-Net, U-Net++,
SegFormer, nnU-Net, Cellpose, StarDist — is trained and tested on exactly these
folds, so results can be compared crop by crop.

Writes splits/seg_folds_<round>.csv (tracked in git; refuses to overwrite).

Usage (run from ml/cellular/; on Colab after the setup cell):
    python -m data_prep.make_seg_folds
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from config import load_config


def assign_folds(index: pd.DataFrame, k: int, seed: int) -> pd.DataFrame:
    """Shuffle inside each ECD band x difficulty stratum, then deal crops round robin."""
    rng = np.random.default_rng(seed)
    order = []
    for _, g in sorted(index.groupby(["ecd_band", "difficulty"])):
        order.extend(rng.permutation(g.index.to_numpy()))
    folds = index.copy()
    folds.loc[order, "fold"] = [i % k for i in range(len(order))]   # equal fold sizes, strata spread
    folds["fold"] = folds["fold"].astype(int)
    if folds.groupby("group_id")["fold"].nunique().max() > 1:
        raise RuntimeError("a tissue appears in two folds")
    return folds


def main() -> None:
    ap = argparse.ArgumentParser(description="Create the shared segmentation CV folds.")
    ap.add_argument("--force", action="store_true", help="overwrite existing folds (invalidates all results)")
    args = ap.parse_args()

    cfg = load_config()
    sm = cfg["seg_models"]
    out = cfg["paths"]["splits_dir"] / f"seg_folds_{sm['round']}.csv"
    if out.exists() and not args.force:
        raise SystemExit(f"{out} already exists - all models must use the same folds.")

    index = pd.read_csv(cfg["paths"]["annotations_dir"] / "seg" / sm["round"] / "index.csv")
    folds = assign_folds(index, sm["n_folds"], sm["fold_seed"])
    cols = ["crop_id", "group_id", "ecd", "ecd_band", "difficulty", "expert_overlap", "fold"]
    folds[cols].sort_values(["fold", "crop_id"]).to_csv(out, index=False)

    print(f"Wrote {out}")
    print(pd.crosstab(folds["fold"], [folds["ecd_band"], folds["difficulty"]], margins=True).to_string())


if __name__ == "__main__":
    main()
