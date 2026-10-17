"""
XAI step 1 — explaining the ROI model (Grad-CAM on the Phase 6 EfficientNet-B0).

Question answered for the reviewer: "why was this region left out of the ROI?"
Settings and the pre-registered rules: config.yaml -> xai.roi.

  --evaluate   validation reference images (fully tile-labelled, never used for training), for
               the configured method and the comparison (config xai.roi: Grad-CAM, Grad-CAM++):
                 faithfulness  deletion test in the windows the model calls poor: top heatmap
                               pixels -> neutral lit tissue vs the same mask shifted elsewhere
                 plausibility  windows partly labelled poor: heatmap share inside the poor part
                               vs its area share; pointing game (heatmap maximum in the poor part)
               unit = image (overlapping windows are not independent); one-sided Wilcoxon
  --figures    per image: ROI and labelled-poor tiles | why left out (purple = too dark from the lit
               mask; heatmap = judged poor by the CNN, on lit tissue, one scale for all images);
               example windows (lit, P(poor) not saturated): heatmap, top pixels replaced, shifted mask

Outputs: <outputs_dir>/xai/roi/ (deletion.csv, plausibility.csv, per_image.csv, decision.json, figures/)
Usage (from ml/cellular/; GPU recommended):
    python -m xai.roi_explain --evaluate
    python -m xai.roi_explain --figures
"""

from __future__ import annotations

import argparse
import json

import cv2
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from config import load_config
from roi import cnn
from roi.run import RoiScorer, load_planes
from roi.roimap import prob_map
from roi.tiles import load_labels
from xai.gradcam import delete, image_map, rolled, tile_cams, top_mask, windows


def out_root(cfg: dict):
    d = cfg["paths"]["outputs_dir"] / "xai" / "roi"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup(cfg: dict):
    """Scorer (must be the CNN), validation reference labels and image planes."""
    scorer = RoiScorer(cfg)
    if scorer.method != "cnn":
        raise SystemExit(f"The selected ROI method is {scorer.method!r}; Grad-CAM explains the CNN only.")
    lab = load_labels(cfg)
    va = lab[lab["split"] == "val"]
    return scorer, va, load_planes(cfg, va)


def poor_pixels(g: pd.DataFrame, shape: tuple[int, int], rows: int, cols: int) -> np.ndarray:
    """Pixel mask of the tiles labelled poor in one reference image."""
    h, w = shape
    th, tw = h // rows, w // cols
    m = np.zeros(shape, bool)
    for r in g[g["y"] == 0].itertuples(index=False):
        m[r.tile_row * th:(r.tile_row + 1) * th, r.tile_col * tw:(r.tile_col + 1) * tw] = True
    return m


def one_sided(x: pd.Series) -> float:
    x = x.dropna()
    return float(wilcoxon(x, alternative="greater").pvalue) if len(x) and (x != 0).any() else 1.0


# ---------------------------------------------------------------- evaluate ----------
def evaluate(cfg: dict) -> None:
    xc = cfg["xai"]["roi"]
    rows_n, cols_n = cfg["roi"]["grid_rows"], cfg["roi"]["grid_cols"]
    methods = [xc["method"], *xc["compare"]]
    scorer, va, planes = setup(cfg)
    rng = np.random.default_rng(xc["seed"])
    p_of = lambda t: cnn.predict(scorer.model, t, scorer.hp, scorer.dev)
    del_rows, pl_rows = [], []
    for iid, g in va.groupby("image_id"):
        p = planes[iid]
        size = p.shape[1] // rows_n
        wins, tiles = windows(p, size, cfg["roi_model"]["stride_px"])
        poor = poor_pixels(g, p.shape[1:], rows_n, cols_n)
        lit_share = tiles[:, 2].mean(axis=(1, 2)) / 255
        p0 = p_of(tiles)
        for method in methods:
            _, cams = tile_cams(scorer.model, tiles, scorer.hp, scorer.dev, xc["layer"], method)
            # faithfulness: windows called poor
            idx = np.flatnonzero((1 - p0 >= xc["min_p_poor"]) & (lit_share >= xc["min_lit_share"]))
            if len(idx):
                masks = top_mask(cams[idx], xc["top_share"])
                # drop = how much P(poor) falls when the pixels are replaced (P(analysable) rises)
                drop_cam = p_of(delete(tiles[idx], masks)) - p0[idx]
                drop_rand = np.mean([p_of(delete(tiles[idx], rolled(masks, rng))) - p0[idx]
                                     for _ in range(xc["n_random"])], axis=0)
                for k, i in enumerate(idx):
                    del_rows.append({"image_id": iid, "window": int(i), "method": method,
                                     "p_poor": float(1 - p0[i]), "drop heatmap": float(drop_cam[k]),
                                     "drop shifted": float(drop_rand[k])})
            # plausibility: windows partly labelled poor
            for i, (y, x) in enumerate(wins):
                wp = poor[y:y + size, x:x + size]
                share = float(wp.mean())
                if not xc["min_mixed_share"] <= share <= 1 - xc["min_mixed_share"] or cams[i].sum() == 0:
                    continue
                pl_rows.append({"image_id": iid, "window": i, "method": method, "p_poor": float(1 - p0[i]),
                                "poor area share": share,
                                "heatmap share in poor part": float(cams[i][wp].sum() / cams[i].sum()),
                                "maximum in poor part": bool(wp.flat[int(np.argmax(cams[i]))])})
        print(f"  {iid}: {len(wins)} windows, {int((1 - p0 >= xc['min_p_poor']).sum())} called poor", flush=True)
    dele, pl = pd.DataFrame(del_rows), pd.DataFrame(pl_rows)
    out = out_root(cfg)
    dele.to_csv(out / "deletion.csv", index=False)
    pl.to_csv(out / "plausibility.csv", index=False)
    decide(cfg, dele, pl, methods)


def decide(cfg: dict, dele: pd.DataFrame, pl: pd.DataFrame, methods: list[str]) -> None:
    xc = cfg["xai"]["roi"]
    dele = dele.assign(gain=dele["drop heatmap"] - dele["drop shifted"])
    pl = pl.assign(excess=pl["heatmap share in poor part"] - pl["poor area share"],
                   hit=pl["maximum in poor part"].astype(float))
    per_img = (dele.groupby(["method", "image_id"])[["drop heatmap", "drop shifted", "gain"]].mean()
               .join(pl.groupby(["method", "image_id"])[["excess", "hit", "poor area share"]].mean(), how="outer"))
    per_img.to_csv(out_root(cfg) / "per_image.csv")
    summary = {}
    for m in methods:
        pi = per_img.loc[m]
        d, q = dele[dele["method"] == m], pl[pl["method"] == m]
        summary[m] = {
            "faithfulness": {"images": int(pi["gain"].notna().sum()), "windows": len(d),
                             "median drop of P(poor), heatmap": round(float(d["drop heatmap"].median()), 4),
                             "median drop of P(poor), shifted mask": round(float(d["drop shifted"].median()), 4),
                             "images where heatmap > shifted": int((pi["gain"] > 0).sum()),
                             "p (images, one-sided Wilcoxon)": round(one_sided(pi["gain"]), 5),
                             "p (windows, for reference)": round(one_sided(d["gain"]), 5)},
            "plausibility": {"images": int(pi["excess"].notna().sum()), "windows": len(q),
                             "median heatmap share in poor part": round(float(q["heatmap share in poor part"].median()), 3),
                             "median poor area share": round(float(q["poor area share"].median()), 3),
                             "pointing game hit rate": round(float(q["hit"].mean()), 3),
                             "pointing game expected by chance": round(float(q["poor area share"].mean()), 3),
                             "p (images, one-sided Wilcoxon)": round(one_sided(pi["excess"]), 5)}}
        f, pz = summary[m]["faithfulness"], summary[m]["plausibility"]
        f["faithful"] = f["p (images, one-sided Wilcoxon)"] < xc["alpha"]
        pz["plausible"] = pz["p (images, one-sided Wilcoxon)"] < xc["alpha"]
    (out_root(cfg) / "decision.json").write_text(json.dumps(summary, indent=2))
    pd.set_option("display.width", 220)
    print("\nPer image (mean over windows; drop = fall of P(poor) after replacing the top "
          f"{100 * xc['top_share']:.0f} % of the heatmap):")
    print(per_img.round(3).to_string())
    for m in methods:
        tag = "PRIMARY" if m == xc["method"] else "comparison"
        print(f"\n{m} ({tag}):")
        for part, vals in summary[m].items():
            print(f"  {part}: " + "; ".join(f"{k} {v}" for k, v in vals.items()))
    print(f"\nResults: {out_root(cfg)}")


# ---------------------------------------------------------------- figures ----------
def heat_rgb(img: np.ndarray, heat: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    col = cv2.applyColorMap((np.clip(heat, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_JET)[..., ::-1]
    base = np.dstack([img] * 3).astype(np.float32)
    a = alpha * np.clip(heat, 0, 1)[..., None] ** 0.5          # transparent where there is no evidence
    return (base * (1 - a) + col * a).astype(np.uint8)


def two_part(img: np.ndarray, lit: np.ndarray, roi: np.ndarray, heat: np.ndarray) -> np.ndarray:
    """Why left out: unlit area tinted purple ('too dark', from the lit mask - a rule), heatmap of the
    CNN's 'poor' evidence on lit tissue only, ROI outlined in cyan."""
    view = heat_rgb(img, np.where(lit, heat, 0)).astype(np.float32)
    view[~lit] = 0.55 * view[~lit] + 0.45 * np.array([150, 0, 190])
    view = view.astype(np.uint8)
    cs, _ = cv2.findContours(roi.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(view, cs, -1, (0, 255, 255), 2)
    return view


def figures(cfg: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    xc = cfg["xai"]["roi"]
    rows_n = cfg["roi"]["grid_rows"]
    lo, hi = xc["example_p_poor"]
    scorer, va, planes = setup(cfg)
    d = out_root(cfg) / "figures"
    (d / "maps").mkdir(parents=True, exist_ok=True)
    maps, examples = {}, []
    for iid, g in va.groupby("image_id"):
        p = planes[iid]
        size = p.shape[1] // rows_n
        wins, tiles = windows(p, size, cfg["roi_model"]["stride_px"])
        _, raw = tile_cams(scorer.model, tiles, scorer.hp, scorer.dev, xc["layer"], xc["method"], normalise=False)
        # window probabilities exactly as the ROI scorer computes them (mixed precision on GPU;
        # the heatmap pass runs in float32 for the gradients)
        probs = cnn.predict(scorer.model, tiles, scorer.hp, scorer.dev)
        roi, prob = scorer(p)
        assert np.allclose(prob_map(probs, wins, p.shape[1:], size), prob, atol=1e-5)   # same windows as the ROI
        lit = p[2] > 0
        maps[iid] = (p[0], lit, roi, image_map(probs, raw, wins, p.shape[1:]), g, size)
        # examples: lit windows called poor but not saturated, so the deletion effect is visible
        pp, lit_share = 1 - probs, tiles[:, 2].mean(axis=(1, 2)) / 255
        cand = np.flatnonzero((pp >= lo) & (pp <= hi) & (lit_share >= xc["example_min_lit_share"]))
        for i in cand[np.argsort(-pp[cand])][:2]:
            mx = float(raw[i].max())
            examples.append((float(pp[i]), iid, tiles[i], raw[i] / mx if mx > 0 else raw[i]))
    # one scale for all images: 99th percentile of the positive evidence on lit tissue
    pos = np.concatenate([e[lit & (e > 0)] for _, lit, _, e, _, _ in maps.values()])
    scale = float(np.percentile(pos, 99)) if len(pos) else 1.0
    for iid, (img, lit, roi, ev, g, size) in maps.items():
        fig, axes = plt.subplots(1, 2, figsize=(15, 6.3))
        view = np.dstack([img] * 3)
        cs, _ = cv2.findContours(roi.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(view, cs, -1, (0, 255, 255), 3)
        axes[0].imshow(view)
        for r in g[g["y"] == 0].itertuples(index=False):
            axes[0].add_patch(plt.Rectangle((r.tile_col * size + 3, r.tile_row * size + 3), size - 6, size - 6,
                                            fill=False, ec="red", lw=1.3))
        axes[0].set_title(f"{iid}: cyan = ROI, red boxes = tiles you labelled poor", fontsize=10)
        axes[1].imshow(two_part(img, lit, roi, ev / scale))
        axes[1].set_title(f"why left out: purple = too dark (lit mask); heat = judged poor by the CNN ({xc['method']})",
                          fontsize=10)
        for ax in axes:
            ax.axis("off")
        fig.tight_layout()
        fig.savefig(d / "maps" / f"{iid}.png", dpi=70)
        plt.close(fig)
    # example windows: tile | heatmap | top share replaced | same mask shifted (the test's baseline)
    examples = sorted(examples, key=lambda e: -e[0])[:xc["n_examples"]]
    if not examples:
        print("No lit windows with P(poor) in the example range.")
    else:
        rng = np.random.default_rng(xc["seed"])
        fig, axes = plt.subplots(len(examples), 4, figsize=(12, 3 * len(examples)))
        for row, (pp, iid, tile, m) in zip(np.atleast_2d(axes), examples):
            mask = top_mask(m[None], xc["top_share"])
            shifted = rolled(mask, rng)
            p_del, p_shift = (1 - cnn.predict(scorer.model, delete(tile[None], mk), scorer.hp, scorer.dev)[0]
                              for mk in (mask, shifted))
            row[0].imshow(tile[0], cmap="gray", vmin=0, vmax=255)
            row[0].set_title(f"{iid}\nP(poor) {pp:.2f}", fontsize=8)
            row[1].imshow(heat_rgb(tile[0], m))
            row[1].set_title(xc["method"], fontsize=8)
            row[2].imshow(delete(tile[None], mask)[0][0], cmap="gray", vmin=0, vmax=255)
            row[2].set_title(f"top {100 * xc['top_share']:.0f} % of heatmap replaced\nP(poor) {p_del:.2f}", fontsize=8)
            row[3].imshow(delete(tile[None], shifted)[0][0], cmap="gray", vmin=0, vmax=255)
            row[3].set_title(f"same mask, shifted\nP(poor) {p_shift:.2f}", fontsize=8)
            for ax in row:
                ax.axis("off")
        fig.tight_layout()
        fig.savefig(d / "examples.png", dpi=80)
        plt.close(fig)
    print(f"Figures: {d / 'maps'} (one per image), {d / 'examples.png'}")


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--figures", action="store_true")
    args = ap.parse_args()
    if args.evaluate:
        evaluate(cfg)
    if args.figures:
        figures(cfg)
    if not (args.evaluate or args.figures):
        ap.print_help()


if __name__ == "__main__":
    main()
