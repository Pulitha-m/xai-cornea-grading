"""
Phase 6 (Sub-component 3.1) — ROI selection: compare, train, evaluate, apply.

  --cv       Steps 6.1-6.3: the three methods (config roi_model) on the SAME folds of the
             train tiles (grouped by image): lit-area rule, quality features + logistic
             regression, EfficientNet-B0. Out-of-fold P(analysable) per tile, per-image tile
             IoU of the analysable area, tile metrics, and the pre-registered decision.
  --final    train the selected method on all train tiles
  --iou      Step 6.5: ROI IoU on the 10 validation reference maps (scope target roi_iou):
             selected method vs the lit mask, largest-region variant, human ceiling
             (intra-rater IoU on the blind repeats), figure
  --apply    Step 6.4: ROI masks for every image of a split (val / calibration) for the
             re-run of Phases 3-5 inside the ROI (extraction.run_extract --roi)

Outputs: <outputs_dir>/roi/ (oof.csv, cv_iou.csv, decision.json, final.json, val_iou.csv,
         figures/, masks/<split>/<image_id>.png, roi_<split>.csv); model in <models_dir>/roi/
Usage (from ml/cellular/; GPU for --cv / --final with the CNN):
    python -m roi.run --cv
    python -m roi.run --final
    python -m roi.run --iou
    python -m roi.run --apply --split val
"""

from __future__ import annotations

import argparse
import json
import time

import cv2
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config import load_config
from roi.roimap import largest_component, prob_map, roi_from_prob, window_grid
from roi.tiles import (crop, image_planes, load_labels, make_folds, mask_to_tiles, repeat_pairs,
                       tile_features, tile_iou)
from segmentation.classical import ClassicalParams
from segmentation.infer_full import images_of

METHODS = ("lit", "logreg", "cnn")                       # in order of complexity


def out_root(cfg: dict):
    d = cfg["paths"]["outputs_dir"] / "roi"
    d.mkdir(parents=True, exist_ok=True)
    return d


def device():
    import torch
    d = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if d.type != "cuda":
        print("  (no GPU - the CNN runs slowly; Runtime > Change runtime type > GPU)")
    return d


def load_planes(cfg: dict, files: pd.DataFrame) -> dict:
    return {r.image_id: image_planes(cfg, cv2.imread(str(cfg["paths"]["images_dir"] / r.image_file),
                                                     cv2.IMREAD_GRAYSCALE))
            for r in files.drop_duplicates("image_id").itertuples(index=False)}


def stack_tiles(planes: dict, df: pd.DataFrame) -> np.ndarray:
    return np.stack([crop(planes[r.image_id], r.y0, r.x0, r.size) for r in df.itertuples(index=False)])


def features(cfg: dict, tiles: np.ndarray) -> np.ndarray:
    cell_px = ClassicalParams.from_config(cfg).cell_px
    return np.stack([tile_features(t, cell_px) for t in tiles])


def lit_rule(cfg: dict, X: np.ndarray) -> np.ndarray:
    return (X[:, 0] > cfg["roi_model"]["lit_min_share"]).astype(np.float32)


def fit_logreg(cfg: dict, X: np.ndarray, y: np.ndarray):
    return make_pipeline(StandardScaler(), LogisticRegression(C=cfg["roi_model"]["logreg_C"],
                                                              max_iter=5000)).fit(X, y)


def per_image_iou(df: pd.DataFrame, col: str, thr: float) -> pd.Series:
    return df.groupby("image_id").apply(lambda g: tile_iou(g["y"] == 1, g[col] >= thr))


# ---------------------------------------------------------------- Steps 6.1-6.3 -----
def cv(cfg: dict, use_cnn: bool, epochs: int | None) -> None:
    rm = cfg["roi_model"]
    lab = load_labels(cfg)
    tr = lab[lab["split"] == "train"].reset_index(drop=True)
    print(f"Train tiles: {len(tr)} from {tr['image_id'].nunique()} images "
          f"({100 * (1 - tr['y'].mean()):.0f} % poor); rounds {rm['rounds']}")
    t0 = time.time()
    planes = load_planes(cfg, tr)
    tiles = stack_tiles(planes, tr)
    X = features(cfg, tiles)
    y = tr["y"].to_numpy()
    print(f"  tiles and features ready ({time.time() - t0:.0f} s)")

    imgs = tr.groupby("image_id")["y"].mean().rsub(1).rename("poor_share").reset_index()
    folds = make_folds(imgs, rm["n_folds"], rm["fold_seed"])
    tr["fold"] = tr["image_id"].map(folds)
    p = {m: np.full(len(tr), np.nan, np.float32) for m in METHODS}
    dev = device() if use_cnn else None
    for k in range(rm["n_folds"]):
        te = (tr["fold"] == k).to_numpy()
        p["lit"][te] = lit_rule(cfg, X[te])
        p["logreg"][te] = fit_logreg(cfg, X[~te], y[~te]).predict_proba(X[te])[:, 1]
        if use_cnn:
            from roi import cnn
            print(f"  fold {k + 1}/{rm['n_folds']}: CNN on {int((~te).sum())} tiles", flush=True)
            model = cnn.train(tiles[~te], y[~te], rm["cnn"], dev, rm["cnn"]["seed"] + k, epochs)
            p["cnn"][te] = cnn.predict(model, tiles[te], rm["cnn"], dev)
    oof = tr[["image_id", "round", "tile_row", "tile_col", "label", "y", "fold"]].assign(
        **{f"p_{m}": p[m] for m in METHODS if use_cnn or m != "cnn"})
    oof.to_csv(out_root(cfg) / "oof.csv", index=False)
    compare(cfg)


def compare(cfg: dict) -> None:
    rm = cfg["roi_model"]
    thr = rm["threshold"]
    oof = pd.read_csv(out_root(cfg) / "oof.csv")
    methods = [m for m in METHODS if f"p_{m}" in oof]
    ious = pd.DataFrame({m: per_image_iou(oof, f"p_{m}", thr) for m in methods})
    ious.to_csv(out_root(cfg) / "cv_iou.csv")
    rows = []
    for m in methods:
        pred = oof[f"p_{m}"] >= thr
        poor = oof["y"] == 0
        rows.append({"method": m, "mean image IoU": ious[m].mean(), "SD": ious[m].std(),
                     "min": ious[m].min(),
                     "pooled IoU": tile_iou(oof["y"] == 1, pred),
                     "AUC": roc_auc_score(oof["y"], oof[f"p_{m}"]),
                     "balanced acc": balanced_accuracy_score(oof["y"], pred),
                     "poor tiles excluded": (~pred[poor]).mean(),
                     "analysable tiles kept": pred[~poor].mean()})
    table = pd.DataFrame(rows).set_index("method")
    pd.set_option("display.width", 200)
    print(f"\nCross-validation ({rm['n_folds']} folds by image, {ious.shape[0]} images, "
          f"{len(oof)} tiles, threshold {thr}):")
    print(table.round(3).to_string())

    winner, tests = "lit", {}
    for m in methods[1:]:
        d = ious[m] - ious[winner]
        pval = wilcoxon(ious[m], ious[winner]).pvalue if (d != 0).any() else 1.0
        tests[f"{m} vs {winner}"] = {"mean diff": float(d.mean()), "p": float(pval)}
        print(f"  {m} vs {winner}: mean IoU diff {d.mean():+.3f}, Wilcoxon p = {pval:.4g}")
        if d.mean() > 0 and pval < rm["alpha"]:
            winner = m
    print(f"DECISION (pre-registered): {winner}")
    (out_root(cfg) / "decision.json").write_text(json.dumps(
        {"winner": winner, "tests": tests, "cv": table.reset_index().to_dict("records")}, indent=2))


# ---------------------------------------------------------------- final model -------
def final(cfg: dict, epochs: int | None) -> None:
    rm = cfg["roi_model"]
    winner = json.loads((out_root(cfg) / "decision.json").read_text())["winner"]
    mdir = cfg["paths"]["models_dir"] / "roi"
    mdir.mkdir(parents=True, exist_ok=True)
    lab = load_labels(cfg)
    tr = lab[lab["split"] == "train"].reset_index(drop=True)
    if winner == "logreg":
        import joblib
        planes = load_planes(cfg, tr)
        joblib.dump(fit_logreg(cfg, features(cfg, stack_tiles(planes, tr)), tr["y"].to_numpy()),
                    mdir / "logreg.joblib")
    elif winner == "cnn":
        import torch
        from roi import cnn
        planes = load_planes(cfg, tr)
        model = cnn.train(stack_tiles(planes, tr), tr["y"].to_numpy(), rm["cnn"], device(),
                          rm["cnn"]["seed"], epochs)
        torch.save({"state_dict": model.state_dict(), "hp": rm["cnn"]}, mdir / "cnn.pt")
    info = {"method": winner, "train_images": int(tr["image_id"].nunique()), "train_tiles": len(tr)}
    (out_root(cfg) / "final.json").write_text(json.dumps(info, indent=2))
    print(f"Final ROI method: {winner} ({info['train_images']} images, {info['train_tiles']} tiles)"
          + (f" -> {mdir}" if winner != "lit" else " (no model to train)"))


class RoiScorer:
    """The final ROI method applied to a whole image: (ROI mask, probability map)."""

    def __init__(self, cfg: dict):
        self.cfg, rm = cfg, cfg["roi_model"]
        self.method = json.loads((out_root(cfg) / "final.json").read_text())["method"]
        mdir = cfg["paths"]["models_dir"] / "roi"
        if self.method == "logreg":
            import joblib
            self.model = joblib.load(mdir / "logreg.joblib")
        elif self.method == "cnn":
            import torch
            from roi import cnn
            self.dev = device()
            ck = torch.load(mdir / "cnn.pt", map_location=self.dev)
            self.model = cnn.build({**ck["hp"], "pretrained": False}).to(self.dev)
            self.model.load_state_dict(ck["state_dict"])
            self.hp = ck["hp"]

    def __call__(self, planes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        rm = self.cfg["roi_model"]
        lit = planes[2] > 0
        h, w = lit.shape
        size = h // self.cfg["roi"]["grid_rows"]
        if self.method == "lit":
            return lit, lit.astype(np.float32)
        wins = window_grid(h, w, size, rm["stride_px"])
        tiles = np.stack([crop(planes, y, x, size) for y, x in wins])
        if self.method == "logreg":
            probs = self.model.predict_proba(features(self.cfg, tiles))[:, 1]
        else:
            from roi import cnn
            probs = cnn.predict(self.model, tiles, self.hp, self.dev)
        prob = prob_map(probs, wins, (h, w), size)
        roi = roi_from_prob(prob, lit, rm["threshold"], int(rm["min_island_tiles"] * size * size))
        return roi, prob


# ---------------------------------------------------------------- Step 6.5 ----------
def iou(cfg: dict) -> None:
    rows_n, cols_n = cfg["roi"]["grid_rows"], cfg["roi"]["grid_cols"]
    lab = load_labels(cfg)
    va = lab[lab["split"] == "val"]
    scorer = RoiScorer(cfg)
    planes = load_planes(cfg, va)
    rows, views = [], {}
    for iid, g in va.groupby("image_id"):
        ref = np.zeros((rows_n, cols_n), bool)
        ref[g["tile_row"], g["tile_col"]] = g["y"] == 1
        roi, prob = scorer(planes[iid])
        lit = planes[iid][2] > 0
        rows.append({"image_id": iid, "reference analysable tiles": int(ref.sum()),
                     f"ROI ({scorer.method})": tile_iou(ref, mask_to_tiles(roi, rows_n, cols_n)),
                     "lit mask": tile_iou(ref, mask_to_tiles(lit, rows_n, cols_n)),
                     f"ROI ({scorer.method}), largest region": tile_iou(
                         ref, mask_to_tiles(largest_component(roi), rows_n, cols_n))})
        views[iid] = (planes[iid][0], ref, roi)
    t = pd.DataFrame(rows).set_index("image_id")
    t.to_csv(out_root(cfg) / "val_iou.csv")

    rep = repeat_pairs(cfg)
    human = rep.groupby("image_id").apply(lambda g: tile_iou(g["label_first"] != "poor",
                                                             g["label_repeat"] != "poor"))
    target = cfg["targets"]["roi_iou"]
    pd.set_option("display.width", 200)
    print(f"ROI IoU on {len(t)} validation reference maps (tile level, 'more than half' rule; "
          f"target {target}):")
    print(t.round(3).to_string())
    summ = t.drop(columns="reference analysable tiles").agg(["mean", "min"]).T
    summ["meets target (mean)"] = summ["mean"] >= target
    print("\n" + summ.round(3).to_string())
    print(f"\nHuman ceiling (intra-rater, {len(human)} blind repeat images): mean IoU {human.mean():.3f} "
          f"(min {human.min():.3f})")
    figure(cfg, views, t[f"ROI ({scorer.method})"])


def figure(cfg: dict, views: dict, ious: pd.Series) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows_n, cols_n = cfg["roi"]["grid_rows"], cfg["roi"]["grid_cols"]
    n = len(views)
    fig, axes = plt.subplots((n + 1) // 2, 2, figsize=(14, 3.6 * ((n + 1) // 2)))
    for ax, (iid, (img, ref, roi)) in zip(axes.ravel(), views.items()):
        rgb = np.dstack([img] * 3).astype(np.float32)
        rgb[roi] = 0.6 * rgb[roi] + 0.4 * np.array([0, 200, 0])
        ax.imshow(rgb.astype(np.uint8))
        size = img.shape[0] // rows_n
        for r in range(rows_n):
            for c in range(cols_n):
                if not ref[r, c]:
                    ax.add_patch(plt.Rectangle((c * size + 2, r * size + 2), size - 4, size - 4,
                                               fill=False, ec="red", lw=1.2))
        ax.set_title(f"{iid}  IoU {ious[iid]:.2f}", fontsize=9)
        ax.axis("off")
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    fig.suptitle("Green = predicted ROI; red boxes = tiles you labelled poor")
    fig.tight_layout()
    d = out_root(cfg) / "figures"
    d.mkdir(exist_ok=True)
    fig.savefig(d / "val_roi.png", dpi=80)
    print(f"Figure: {d / 'val_roi.png'}")


# ---------------------------------------------------------------- Step 6.4 ----------
def apply(cfg: dict, split: str) -> None:
    scorer = RoiScorer(cfg)
    d = out_root(cfg) / "masks" / split
    d.mkdir(parents=True, exist_ok=True)
    rows, t0 = [], time.time()
    images = images_of(cfg, split)
    for i, r in enumerate(images.itertuples(index=False), 1):
        img = cv2.imread(str(cfg["paths"]["images_dir"] / r.image_file), cv2.IMREAD_GRAYSCALE)
        planes = image_planes(cfg, img)
        roi, prob = scorer(planes)
        lit = planes[2] > 0
        cv2.imwrite(str(d / f"{r.image_id}.png"), roi.astype(np.uint8) * 255)
        rows.append({"image_id": r.image_id, "lit_share": lit.mean(), "roi_share": roi.mean(),
                     "roi_share_of_lit": roi.sum() / max(lit.sum(), 1),
                     "quality_score": float(prob[lit].mean()) if lit.any() else 0.0})
        if i % 25 == 0 or i == len(images):
            print(f"  {i}/{len(images)} images, {(time.time() - t0) / i:.2f} s/image", flush=True)
    s = pd.DataFrame(rows)
    s.to_csv(out_root(cfg) / f"roi_{split}.csv", index=False)
    print(f"ROI ({scorer.method}) for {len(s)} {split} images -> {d}")
    print(f"  median share of the lit area kept: {s['roi_share_of_lit'].median():.2f} "
          f"(min {s['roi_share_of_lit'].min():.2f}); images with an empty ROI: {(s['roi_share'] == 0).sum()}")


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Phase 6: ROI selection.")
    ap.add_argument("--cv", action="store_true")
    ap.add_argument("--no-cnn", action="store_true", help="skip the CNN (e.g. without a GPU)")
    ap.add_argument("--compare", action="store_true", help="re-print the CV comparison from oof.csv")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--iou", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--split", default="val", choices=["val", "calibration"],
                    help="test stays frozen until Phase 7")
    ap.add_argument("--epochs", type=int, help="override CNN epochs (smoke tests only, not for results)")
    args = ap.parse_args()
    if args.cv:
        cv(cfg, not args.no_cnn, args.epochs)
    elif args.compare:
        compare(cfg)
    elif args.final:
        final(cfg, args.epochs)
    elif args.iou:
        iou(cfg)
    elif args.apply:
        apply(cfg, args.split)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
