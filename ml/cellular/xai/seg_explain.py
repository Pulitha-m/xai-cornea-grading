"""
XAI step 3 — Seg-Grad-CAM on StarDist: which pixels make the model see a cell, and is the heatmap faithful?
Rules: config.yaml -> xai.segmentation (fixed before any result).

  --evaluate   the 40 annotated crops, each predicted by the Phase 2 StarDist fold model that never saw it
               (the same cells, levels and errors as step 2); a random sample of GREEN and of YELLOW / RED cells:
               deletion test (primary: Grad-CAM), heat on the cell and its walls, wrong vs correct cells;
               the same for the comparison methods (HiResCAM, exploratory); example figures

Outputs: <outputs_dir>/xai/segmentation/ (cells.csv, decision.json, figures/examples.png, examples_<method>.png)
Usage (from ml/cellular/; GPU):
    python -m xai.seg_explain --evaluate
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, wilcoxon

from config import load_config
from data_prep.check_annotations import IGNORE
from extraction.cells import ExtractionParams, extract_cells, instances_from_mask, match_cells
from xai.biomarker_explain import label_cells
from xai.reliability import cell_confidence, reliability
from xai.seg_gradcam import (delete, pad_to, rolled_in_window, scores, seg_cam, shares, to_grid, top_in_window,
                             two_outputs, upsample, window)


NAMES = {"gradcam": "Seg-Grad-CAM", "hirescam": "HiResCAM"}


def out_root(cfg: dict):
    d = cfg["paths"]["outputs_dir"] / "xai" / "segmentation"
    d.mkdir(parents=True, exist_ok=True)
    return d


def instance_of(complete: np.ndarray, labels: np.ndarray, cell_id: int) -> int:
    """StarDist instance a measured cell comes from (most frequent instance label under the cell)."""
    v = labels[(complete == cell_id) & (labels > 0)]
    return int(np.bincount(v).argmax()) if v.size else 0


def candidates(cfg: dict, models: dict, samples: list) -> tuple[pd.DataFrame, dict]:
    """Every predicted complete cell of the crops with its step 2 level and error label."""
    from segmentation.infer_full import instance_prob_image
    from segmentation.run_stardist import to_input

    xb = cfg["xai"]["biomarkers"]
    p = ExtractionParams.from_config(cfg)
    rows, labels_of = [], {}
    for s in samples:
        model = models[s.fold]
        labels, det = model.predict_instances(to_input(s.image))
        labels_of[s.crop_id] = labels
        analysable = s.mask != IGNORE
        ref, _, comp_g = extract_cells(instances_from_mask(s.mask), analysable, p)
        cells, _, comp_p = extract_cells(labels, analysable, p)
        if cells.empty or ref.empty:
            continue
        prob = instance_prob_image(labels, det["prob"], det["points"])
        rel = reliability(cells, cell_confidence(comp_p, prob, cells["cell_id"]), float(model.thresholds.prob), xb)
        lab = label_cells(cells, match_cells(comp_p, comp_g, xb["error_iou"]), ref, xb).set_index("cell_id")
        for cid in cells["cell_id"]:
            rows.append({"crop_id": s.crop_id, "fold": s.fold, "cell_id": int(cid),
                         "instance": instance_of(comp_p, labels, cid), "level": rel.loc[cid, "level"],
                         "confidence": rel.loc[cid, "confidence"], "wrong": bool(lab.loc[cid, "wrong"])})
    t = pd.DataFrame(rows)
    return t[t["instance"] > 0].reset_index(drop=True), labels_of


def draw(t: pd.DataFrame, xs: dict) -> pd.DataFrame:
    """Pre-registered sample: n_green GREEN and n_flagged YELLOW / RED cells at random (all if fewer)."""
    rng = np.random.default_rng(xs["seed"])
    parts = []
    for group, n in (("green", xs["n_green"]), ("flagged", xs["n_flagged"])):
        pool = t[(t["level"] == "green") == (group == "green")]
        if pool.empty:
            continue
        parts.append(pool.iloc[np.sort(rng.choice(len(pool), min(n, len(pool)), replace=False))].assign(group=group))
    return pd.concat(parts, ignore_index=True)


def explain_cell(model2, x: np.ndarray, hw: tuple[int, int], grid: tuple[int, int], region: np.ndarray,
                 xs: dict, rng: np.random.Generator, method: str = "gradcam") -> tuple[dict, dict]:
    """One cell: heatmap, deletion test, heat shares. x and region are padded; hw = the crop's real size."""
    g_shape = (x.shape[0] // grid[0], x.shape[1] // grid[1])
    region_g = to_grid(region, g_shape)
    cam, s0 = seg_cam(model2, x, region_g, method)
    heat = upsample(cam, x.shape)
    heat[hw[0]:], heat[:, hw[1]:] = 0, 0                               # padding is not part of the crop
    win = window(region, xs["context_px"], hw)
    top = top_in_window(heat, win, xs["top_share"])
    shifted = rolled_in_window(top, win, rng, xs["n_random"])
    sc = scores(model2, [delete(x, m, win) for m in [top, *shifted]], region_g)
    row = {"score": s0, "mean_prob": s0 / region_g.sum(), "score_cam": float(sc[0]),
           "score_shift": float(sc[1:].mean()), "drop_cam": (s0 - sc[0]) / s0,
           "drop_shift": float(np.mean((s0 - sc[1:]) / s0)), **shares(heat, win, region, xs["ring_px"])}
    view = {"img": x[win], "heat": heat[win], "region": region[win], "top": top[win], "shift": shifted[0][win],
            "x_top": delete(x, top, win)[win], "x_shift": delete(x, shifted[0], win)[win],
            "score": s0, "score_cam": float(sc[0]), "score_shift0": float(sc[1])}
    return row, view


def evaluate(cfg: dict) -> None:
    from stardist.models import StarDist2D

    from segmentation.data import load_samples
    from segmentation.run_stardist import to_input
    from segmentation.train_final import final_dir

    xs, run = cfg["xai"]["segmentation"], cfg["extraction"]["run"]
    info = json.loads((final_dir(cfg, run) / "final.json").read_text())
    samples = load_samples(cfg, info["preprocess"])
    by_id = {s.crop_id: s for s in samples}
    model_root = cfg["paths"]["models_dir"] / "seg" / run
    models = {k: StarDist2D(None, name=f"fold{k}", basedir=str(model_root)) for k in sorted({s.fold for s in samples})}
    pool, labels_of = candidates(cfg, models, samples)
    pick = draw(pool, xs)
    print(f"{len(pool)} predicted complete cells on {pool['crop_id'].nunique()} crops; sample: "
          f"{(pick['group'] == 'green').sum()} green, {(pick['group'] == 'flagged').sum()} yellow / red", flush=True)

    methods = [xs["method"], *xs.get("compare", [])]
    rngs = {m: np.random.default_rng(xs["seed"]) for m in methods}     # own stream: primary run reproducible
    rows, views = [], {m: [] for m in methods}
    want = {m: {"green": xs["n_examples"] // 2, "flagged": xs["n_examples"] - xs["n_examples"] // 2}
            for m in methods}
    for k, model in models.items():
        model2 = two_outputs(model.keras_model, xs["layer"])
        grid = tuple(int(g) for g in model.config.grid)
        div = int(2 ** model.config.unet_n_depth * max(grid))
        for r in pick[pick["fold"] == k].itertuples(index=False):
            s = by_id[r.crop_id]
            x = pad_to(to_input(s.image), div)
            region = pad_to(labels_of[r.crop_id] == r.instance, div, mode="constant")
            for m in methods:
                row, view = explain_cell(model2, x, s.image.shape, grid, region, xs, rngs[m], m)
                rows.append({**r._asdict(), "method": m, **row})
                if want[m][r.group] > 0:
                    want[m][r.group] -= 1
                    views[m].append({**r._asdict(), **view})
        print(f"  fold {k}: done", flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(out_root(cfg) / "cells.csv", index=False)
    summaries = {m: decide(cfg, t[t["method"] == m].reset_index(drop=True), m, m == xs["method"]) for m in methods}
    (out_root(cfg) / "decision.json").write_text(json.dumps(summaries, indent=2))
    print(f"\nResults: {out_root(cfg)}")
    for m in methods:
        figure(cfg, views[m], m, m == xs["method"])


def _p(a, b=None, alternative="greater") -> float:
    d = (np.asarray(a) - (0 if b is None else np.asarray(b)))
    d = d[np.isfinite(d)]
    return float(wilcoxon(d, alternative=alternative).pvalue) if np.any(d != 0) else float("nan")


def decide(cfg: dict, t: pd.DataFrame, method: str = "gradcam", primary: bool = True) -> dict:
    xs = cfg["xai"]["segmentation"]
    p_del = _p(t["drop_cam"], t["drop_shift"])
    p_cell = _p(t["heat_cell"], t["area_cell"])
    p_wall = _p(t["heat_wall"], t["area_wall"])
    med = lambda c, m=None: round(float(t.loc[m, c].median() if m is not None else t[c].median()), 3)
    groups = {}
    for name, m in (("green", t["group"] == "green"), ("flagged", t["group"] == "flagged"),
                    ("wrong", t["wrong"]), ("correct", ~t["wrong"])):
        groups[name] = {"cells": int(m.sum()), "drop_cam": med("drop_cam", m), "drop_shift": med("drop_shift", m),
                        "heat_cell": med("heat_cell", m), "area_cell": med("area_cell", m),
                        "heat_wall": med("heat_wall", m), "mean_prob": med("mean_prob", m)}
    mw = lambda c, a, b: (float(mannwhitneyu(t.loc[a, c].dropna(), t.loc[b, c].dropna()).pvalue)
                          if a.sum() and b.sum() else float("nan"))
    summary = {
        "role": "primary (pre-registered)" if primary else "exploratory (added after the primary result)",
        "cells": int(len(t)), "crops": int(t["crop_id"].nunique()), "wrong": int(t["wrong"].sum()),
        "faithfulness": {"median_drop_cam": med("drop_cam"), "median_drop_shift": med("drop_shift"),
                         "cam_beats_shift": int((t["drop_cam"] > t["drop_shift"]).sum()),
                         "p_wilcoxon": p_del, "pass": bool(p_del < xs["alpha"])},
        "plausibility": {"median_heat_cell_ring": med("heat_cell"), "median_area_cell_ring": med("area_cell"),
                         "p_cell": p_cell, "median_heat_wall": med("heat_wall"),
                         "median_area_wall": med("area_wall"), "p_wall": p_wall},
        "groups": groups,
        "p_heat_cell_wrong_vs_correct": mw("heat_cell", t["wrong"], ~t["wrong"]),
        "p_heat_cell_green_vs_flagged": mw("heat_cell", t["group"] == "green", t["group"] == "flagged"),
    }
    f = summary["faithfulness"]
    print(f"\n=== {NAMES.get(method, method)}: {summary['role']} ===")
    print(f"{len(t)} cells on {summary['crops']} crops ({summary['wrong']} wrong vs the manual masks)")
    print(f"{'PRIMARY' if primary else 'EXPLORATORY'}  deletion of the top {100 * xs['top_share']:.0f} % heat pixels: median score drop "
          f"{f['median_drop_cam']:.3f} vs {f['median_drop_shift']:.3f} for the shifted mask; heatmap better in "
          f"{f['cam_beats_shift']} / {len(t)} cells; Wilcoxon p = {p_del:.2g} -> {'PASS' if f['pass'] else 'FAIL'}")
    pl = summary["plausibility"]
    print(f"heat on the cell + {xs['ring_px']} px ring: {pl['median_heat_cell_ring']:.2f} vs area "
          f"{pl['median_area_cell_ring']:.2f} (p = {p_cell:.2g}); on the wall band: {pl['median_heat_wall']:.2f} vs "
          f"area {pl['median_area_wall']:.2f} (p = {p_wall:.2g})")
    print("\nBy group (medians):")
    print(pd.DataFrame(groups).T.to_string())
    print(f"heat on the cell, wrong vs correct: p = {summary['p_heat_cell_wrong_vs_correct']:.2g}; "
          f"green vs flagged: p = {summary['p_heat_cell_green_vs_flagged']:.2g} (Mann-Whitney, descriptive)")
    return summary


def figure(cfg: dict, views: list[dict], method: str = "gradcam", primary: bool = True) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from skimage.segmentation import find_boundaries

    if not views:
        return
    fig, axes = plt.subplots(len(views), 4, figsize=(13, 3.3 * len(views)))
    axes = np.atleast_2d(axes)
    vmax = max(float(np.percentile(v["heat"], 99)) for v in views) or 1.0      # one scale for all cells
    for ax, v in zip(axes, views):
        edge = find_boundaries(v["region"], mode="outer")
        rgb = np.dstack([v["img"]] * 3).clip(0, 1)
        rgb[edge] = (1, 0.9, 0)
        conf = "unknown" if pd.isna(v["confidence"]) else f"{v['confidence']:.2f}"
        ax[0].imshow(rgb)
        ax[0].set_title(f"{v['crop_id']} cell {v['cell_id']}\n{v['level']}, confidence {conf}, "
                        f"{'WRONG' if v['wrong'] else 'correct'} vs manual", fontsize=8)
        ax[1].imshow(v["img"], cmap="gray", vmin=0, vmax=1)
        ax[1].imshow(v["heat"], cmap="jet", alpha=0.45, vmin=0, vmax=vmax)
        ax[1].contour(v["region"], levels=[0.5], colors="w", linewidths=0.6)
        ax[1].set_title(f"{NAMES.get(method, method)} (one scale for all rows)", fontsize=8)
        change = lambda s: 100 * (s - v["score"]) / v["score"]
        ax[2].imshow(v["x_top"], cmap="gray", vmin=0, vmax=1)
        ax[2].set_title(f"top {100 * cfg['xai']['segmentation']['top_share']:.0f} % heat removed\n"
                        f"score {change(v['score_cam']):+.0f} %", fontsize=8)
        ax[3].imshow(v["x_shift"], cmap="gray", vmin=0, vmax=1)
        ax[3].set_title(f"same mask shifted\nscore {change(v['score_shift0']):+.0f} %", fontsize=8)
        for a in ax:
            a.axis("off")
    fig.tight_layout()
    d = out_root(cfg) / "figures"
    d.mkdir(exist_ok=True)
    name = "examples.png" if primary else f"examples_{method}.png"
    fig.savefig(d / name, dpi=90)
    plt.close(fig)
    print(f"Figure: {d / name}")


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="XAI step 3: Seg-Grad-CAM on StarDist.")
    ap.add_argument("--evaluate", action="store_true")
    args = ap.parse_args()
    if args.evaluate:
        evaluate(cfg)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
