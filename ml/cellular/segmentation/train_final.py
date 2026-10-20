"""
Phase 2, Step 2.7a — final models of the two finalists, trained on ALL 40 crops.

Same settings as in cross-validation (config.yaml seg_models.cellpose / .stardist);
only the training set changes (all crops instead of 4 folds). StarDist again
holds out ``stardist.n_val_crops`` crops for its checkpoint and thresholds.
These models are used for the full-image check against Konan (step 2.7) and,
for the winner, in the later phases.

Outputs: <models_dir>/seg/final/<run>/   (+ final.json describing the model)

Usage (from ml/cellular/; Colab GPU runtime; one model per call, they use
different frameworks):
    python -m segmentation.train_final --model cellpose
    python -m segmentation.train_final --model stardist
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from config import load_config
from segmentation.data import load_samples


def final_dir(cfg: dict, run: str) -> Path:
    return cfg["paths"]["models_dir"] / "seg" / "final" / run


def main() -> None:
    cfg = load_config()
    sm = cfg["seg_models"]

    ap = argparse.ArgumentParser(description="Train a finalist on all annotated crops.")
    ap.add_argument("--model", required=True, choices=["cellpose", "stardist"])
    ap.add_argument("--preprocess", choices=["raw", "flat"], default=sm["preprocess"])
    ap.add_argument("--force", action="store_true", help="retrain even if a final model exists")
    args = ap.parse_args()

    run = f"{args.model}_finetune_{args.preprocess}"
    out = final_dir(cfg, run)
    if (out / "final.json").exists() and not args.force:
        print(f"{run}: final model exists already ({out}) - use --force to retrain")
        return
    out.mkdir(parents=True, exist_ok=True)
    samples = load_samples(cfg, args.preprocess)
    t0 = time.time()

    if args.model == "cellpose":
        from segmentation.run_cellpose import check_version, finetune
        check_version()
        info = {"model_path": finetune(samples, sm["cellpose"], "final", out)}
        info["train_crops"] = [s.crop_id for s in samples]
    else:
        from segmentation.run_stardist import finetune
        sd = sm["stardist"]
        rng = np.random.default_rng(sd["seed"])
        val_ids = set(rng.choice([s.crop_id for s in samples], size=sd["n_val_crops"], replace=False))
        train = [s for s in samples if s.crop_id not in val_ids]
        val = [s for s in samples if s.crop_id in val_ids]
        model = finetune(train, val, sd, out / "final", sd["seed"])
        info = {"model_dir": str(out / "final"), "train_crops": [s.crop_id for s in train],
                "val_crops": sorted(val_ids),
                "thresholds": {"prob": float(model.thresholds.prob), "nms": float(model.thresholds.nms)}}

    info.update({"run": run, "preprocess": args.preprocess, "minutes": round((time.time() - t0) / 60, 1)})
    (out / "final.json").write_text(json.dumps(info, indent=2))
    print(f"{run}: final model trained on {len(info['train_crops'])} crops in {info['minutes']} min -> {out}")


if __name__ == "__main__":
    main()
