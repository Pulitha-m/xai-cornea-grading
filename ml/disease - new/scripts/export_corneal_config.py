"""Export the self-contained runtime config of the v2 disease + severity models.

Writes ml-service/models/disease_v2/corneal_config.json with everything the
service needs besides the model weights, so the running app never reads the
training CSV. Every value is computed exactly as in
notebooks/10_Inference_Final_Models_v2.ipynb (Steps 5, 11 and 12):

- number scaling: median SimpleImputer + StandardScaler fitted on the training
  rows (rows of cv_folds.csv joined to the features CSV with Split == "train"),
  in the FEATURES order below;
- disease thresholds: summary_final.json ["thresholds"]["Image + numbers"];
- severity heads and thresholds: summary_severity.json, overridden by
  combined_summary.json when present (also fecd_sev_method);
- focus "low quality" limit: 5th percentile of the Laplacian variance of 300
  training images (same random sample as the notebook, random_state=0);
- unusual-image distances: 95th (warn) / 99th (reject) percentile of the test
  distances stored in ood_reference_v2.npz;
- value ranges seen in training (ECD, CV, HEX %, donor age) and the possible ranges.

The model files themselves are recorded by export_onnx_models.py.

Usage (from the repo root, with the ml/ environment):
    ml/.venv/Scripts/python.exe "ml/disease-new/scripts/export_corneal_config.py" \
        --images-dir PATH/TO/Disease_Cell_Images
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset_match import list_images, match_images  # noqa: E402

DISEASE_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = REPO_DIR / "ml-service" / "models" / "disease_v2"

DIS_COLS = ["FECD", "Guttata", "Folds", "PolyPleo", "LowCD"]
FEATURES = ["ECD_CD_cells_per_mm2", "ECD_Deficit", "SD", "CV", "HEX_percent", "Donor_Age"]
HEAD_NAME = {"FECDgroup": "FECD group", "Folds": "Folds", "Guttata": "Guttata"}
# Physically possible values (notebook 10, Step 12).
LIMITS = {"ecd": (300, 4500), "sd": (40, 1000), "cv": (10, 110), "hex_pct": (5, 100), "age": (1, 110)}
TRAIN_RANGE_COLUMNS = {"ecd": "ECD_CD_cells_per_mm2", "cv": "CV", "hex_pct": "HEX_percent", "age": "Donor_Age"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images-dir", required=True, help="Disease_Cell_Images folder (training images)")
    parser.add_argument("--features-csv", default=DISEASE_DIR / "data" / "Final_Features_MultiLabel_updated.csv")
    parser.add_argument("--folds-csv", default=DISEASE_DIR / "data" / "cv_folds.csv")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR,
                        help="Folder with summary_final.json, summary_severity.json, combined_summary.json, "
                             "ood_reference_v2.npz; the config is written here")
    args = parser.parse_args()
    model_dir = args.model_dir

    # Rows and training split, as in the notebooks.
    df = pd.read_csv(args.features_csv)
    df = match_images(df, list_images(args.images_dir))
    print(f"Matched images: {df['Img_Path'].notna().sum()} / {len(df)}")
    df = df[df["Img_Path"].notna()].reset_index(drop=True)
    folds = pd.read_csv(args.folds_csv)
    man = df.merge(folds, on="Tissue_ID", how="inner")
    train_df = man[man["Split"] == "train"]
    print(f"Training rows: {len(train_df)} | test rows: {(man['Split'] == 'test').sum()}")

    # The derived feature must follow the rule the service uses.
    expected_deficit = (2500 - train_df["ECD_CD_cells_per_mm2"]).clip(lower=0)
    known = train_df["ECD_CD_cells_per_mm2"].notna()
    assert np.allclose(train_df.loc[known, "ECD_Deficit"], expected_deficit[known]), \
        "ECD_Deficit in the CSV is not max(0, 2500 - ECD)"

    imputer = SimpleImputer(strategy="median").fit(train_df[FEATURES])
    scaler = StandardScaler().fit(imputer.transform(train_df[FEATURES]))

    # Thresholds.
    summary_final = json.loads((model_dir / "summary_final.json").read_text())
    disease_thresholds = summary_final["thresholds"]["Image + numbers"]
    sev_summary = json.loads((model_dir / "summary_severity.json").read_text())
    severity_heads = sev_summary["severity_heads"]
    combined_path = model_dir / "combined_summary.json"
    combined = json.loads(combined_path.read_text()) if combined_path.exists() else {}
    severity_thresholds = {h: combined.get("severity_thresholds", {}).get(h, sev_summary["severity_thresholds"][h])
                           for h in severity_heads}
    fecd_sev_method = combined.get("fecd_sev_method", "model")

    # Focus limit: same 300-image sample as notebook 10.
    sample = train_df["Img_Path"].sample(min(300, len(train_df)), random_state=0)
    focus = [cv2.Laplacian(cv2.resize(cv2.imread(p, 0), (640, 480), interpolation=cv2.INTER_AREA), cv2.CV_64F).var()
             for p in sample]
    focus_low = float(np.percentile(focus, 5))

    # Unusual-image distances.
    ood_path = model_dir / "ood_reference_v2.npz"
    ood = np.load(ood_path)
    d_test = ood["d_test"]

    config = {
        "config": "corneal_disease_severity_v2",
        "version": 1,
        "source": {
            "notebook": "ml/disease-new/notebooks/10_Inference_Final_Models_v2.ipynb",
            "features_csv": Path(args.features_csv).name,
            "n_train": int(len(train_df)),
        },
        "image": {
            "input_width": 384, "input_height": 288,
            "apply_clahe": False,
            "clahe": {"clip_limit": 2.0, "tile_grid_size": [8, 8], "prep_width": 512, "prep_height": 384},
            "imagenet_mean": [0.485, 0.456, 0.406], "imagenet_std": [0.229, 0.224, 0.225],
            "flip_average": True,
        },
        "diseases": DIS_COLS,
        "features": FEATURES,
        "ecd_deficit_reference": 2500,
        "imputer_median": [float(v) for v in imputer.statistics_],
        "scaler_mean": [float(v) for v in scaler.mean_],
        "scaler_scale": [float(v) for v in scaler.scale_],
        "disease_thresholds": {c: float(disease_thresholds[c]) for c in DIS_COLS},
        "severity_heads": severity_heads,
        "severity_head_names": {h: HEAD_NAME.get(h, h) for h in severity_heads},
        "severity_thresholds": {h: float(v) for h, v in severity_thresholds.items()},
        "fecd_sev_method": fecd_sev_method,
        "fecd_cd_rule_ecd_below": 1600,
        "quality": {
            "resize": [640, 480],
            "unusable_std_below": 5, "unusable_saturated_above": 0.5,
            "low_focus_below": focus_low, "low_dark_above": 0.45,
            "dark_pixel_below": 20, "saturated_pixel_above": 245,
            "focus_sample": "Laplacian variance of 300 training images (pandas sample, random_state=0), 5th percentile",
        },
        "image_checks": {"min_side": 300, "aspect_min": 1.1, "aspect_max": 1.6, "colour_score_max": 3},
        "ood": {
            "file": ood_path.name, "sha256": sha256(ood_path), "k": 5,
            "warn_above": float(np.percentile(d_test, 95)), "reject_above": float(np.percentile(d_test, 99)),
            "n_reference": int(ood["ref"].shape[0]), "n_test": int(d_test.shape[0]),
        },
        "number_checks": {
            "limits": {k: list(v) for k, v in LIMITS.items()},
            "training_range": {k: [float(train_df[c].min()), float(train_df[c].max())]
                               for k, c in TRAIN_RANGE_COLUMNS.items()},
            "sd_consistency_tolerance": 0.05,
            "max_missing": 2,
        },
    }

    out = model_dir / "corneal_config.json"
    previous = json.loads(out.read_text()) if out.exists() else {}
    if "models" in previous:  # written by export_onnx_models.py; keep it
        config["models"] = previous["models"]
    out.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    print(f"  focus low limit {focus_low:.1f} | OOD warn {config['ood']['warn_above']:.4f} "
          f"reject {config['ood']['reject_above']:.4f} | FECD severity method {fecd_sev_method}")


if __name__ == "__main__":
    main()
