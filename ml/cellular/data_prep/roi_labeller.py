"""
Phase 1, Step 1.7 — Colab widget to label image tiles good / usable / poor.

Shows one image at a time (order from index.csv, written by
data_prep/select_roi_images.py) as a grid of tiles, each with three buttons
G / U / P. The tile border turns green / yellow / red when labelled. Labels are
saved to labels.csv after every image, so labelling can stop and resume at any
time (a new session starts at the first unlabelled image).

Blind repeats: repeat images are shown rotated 180 deg and without their ID;
their labels are stored in the ORIGINAL tile positions, so summary() can compare
them directly with the first labelling (intra-rater agreement).

In a notebook (after the setup cell):
    from data_prep.roi_labeller import RoiLabeller, summary
    RoiLabeller().show()                     # round 1 (config roi.round)
    RoiLabeller(round="round2").show()       # a later round
    summary()  /  summary("round2")

Repeats of a later round may be images labelled in an earlier round; summary()
then compares them with that earlier labelling (drift check between rounds).

Class definitions: docs/roi_labelling_protocol.md
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from config import load_config

LABELS = ("good", "usable", "poor")                 # ordinal: best -> worst
BORDER = {"good": "#2e7d32", "usable": "#f9a825", "poor": "#c62828", None: "#bdbdbd"}
COLUMNS = ["order", "image_id", "split", "is_repeat", "tile_row", "tile_col",
           "y0", "x0", "size", "label", "labelled_at"]


def tile_size(height: int, width: int, rows: int, cols: int) -> int:
    """Side of the square tiles; the grid must cover the image exactly."""
    size = height // rows
    if size * rows != height or size * cols != width:
        raise ValueError(f"{rows}x{cols} grid does not give square tiles on a {width}x{height} image")
    return size


def _round_dir(rnd: str | None = None) -> tuple[dict, Path]:
    cfg = load_config()
    return cfg, cfg["paths"]["annotations_dir"] / "roi" / (rnd or cfg["roi"]["round"])


def _read_labels(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame(columns=COLUMNS)


def _png(img: np.ndarray) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()


class RoiLabeller:
    """Grid labelling widget. display_px = on-screen size of one tile (162 = 1:1)."""

    def __init__(self, display_px: int = 128, round: str | None = None):
        cfg, self.dir = _round_dir(round)
        self.rows, self.cols = cfg["roi"]["grid_rows"], cfg["roi"]["grid_cols"]
        self.images_dir = cfg["paths"]["images_dir"]
        self.index = pd.read_csv(self.dir / "index.csv")
        self.labels_csv = self.dir / "labels.csv"
        self.display_px = display_px
        done = set(_read_labels(self.labels_csv)["order"].astype(int))
        self.pos = next((i for i in range(len(self.index)) if i not in done), len(self.index))
        self._build()

    # -- layout -----------------------------------------------------------------
    def _build(self) -> None:
        import ipywidgets as W

        d = self.display_px
        self.header = W.HTML()
        self.status = W.HTML()
        self.tiles, self.buttons, boxes = [], [], []
        for _ in range(self.rows * self.cols):
            img = W.Image(format="png", layout=W.Layout(width=f"{d}px", height=f"{d}px"))
            btn = W.ToggleButtons(options=[("G", "good"), ("U", "usable"), ("P", "poor")], value=None,
                                  style={"button_width": f"{(d - 12) // 3}px"},
                                  layout=W.Layout(margin="0"))
            box = W.VBox([img, btn], layout=W.Layout(border=f"3px solid {BORDER[None]}",
                                                     padding="1px", margin="1px"))
            btn.observe(lambda ch, b=box: setattr(b.layout, "border", f"3px solid {BORDER[ch['new']]}"),
                        names="value")
            self.tiles.append(img)
            self.buttons.append(btn)
            boxes.append(box)
        self.grid = W.GridBox(boxes, layout=W.Layout(grid_template_columns=f"repeat({self.cols}, {d + 10}px)"))

        fill = W.Button(description="Unlabelled -> good", tooltip="Set every tile still grey to good")
        back = W.Button(description="< Back")
        save = W.Button(description="Save & next >", button_style="success")
        fill.on_click(lambda _: self._fill_good())
        back.on_click(lambda _: self._go(self.pos - 1))
        save.on_click(lambda _: self._save_next())
        self.ui = W.VBox([self.header, W.HBox([back, fill, save]), self.status, self.grid])

    def show(self):
        from IPython.display import display
        self._go(self.pos)
        display(self.ui)

    # -- navigation -------------------------------------------------------------
    def _original_rc(self, r: int, c: int, view: str) -> tuple[int, int]:
        """Tile position in the original image for display position (r, c)."""
        return (self.rows - 1 - r, self.cols - 1 - c) if view == "rot180" else (r, c)

    def _go(self, pos: int) -> None:
        self.pos = max(0, min(pos, len(self.index)))
        n_done = _read_labels(self.labels_csv)["order"].nunique()
        if self.pos >= len(self.index):
            self.header.value = f"<h3>All {len(self.index)} images labelled - run summary()</h3>"
            self.grid.layout.display = "none"
            return
        self.grid.layout.display = None
        row = self.index.iloc[self.pos]
        img = cv2.imread(str(self.images_dir / row["image_file"]), cv2.IMREAD_GRAYSCALE)
        size = tile_size(*img.shape, self.rows, self.cols)
        shown = cv2.rotate(img, cv2.ROTATE_180) if row["view"] == "rot180" else img

        saved = _read_labels(self.labels_csv)
        saved = saved[saved["order"] == self.pos].set_index(["tile_row", "tile_col"])["label"].to_dict()
        for k in range(self.rows * self.cols):
            r, c = divmod(k, self.cols)
            tile = shown[r * size:(r + 1) * size, c * size:(c + 1) * size]
            self.tiles[k].value = _png(cv2.resize(tile, (self.display_px, self.display_px),
                                                  interpolation=cv2.INTER_AREA))
            self.buttons[k].value = saved.get(self._original_rc(r, c, row["view"]))
        # No image ID or split on screen: keeps the repeats blind.
        self.header.value = (f"<h3>Image {self.pos + 1} / {len(self.index)}</h3>"
                             f"{n_done} saved &nbsp;|&nbsp; G = good, U = usable, P = poor")
        self.status.value = ""
        self.size = size

    def _fill_good(self) -> None:
        for b in self.buttons:
            if b.value is None:
                b.value = "good"

    def _save_next(self) -> None:
        missing = sum(b.value is None for b in self.buttons)
        if missing:
            self.status.value = f"<b style='color:#c62828'>{missing} tiles not labelled yet (grey border).</b>"
            return
        row = self.index.iloc[self.pos]
        now = dt.datetime.now().isoformat(timespec="seconds")
        new = []
        for k, b in enumerate(self.buttons):
            r, c = self._original_rc(*divmod(k, self.cols), row["view"])
            new.append({"order": self.pos, "image_id": row["image_id"], "split": row["split"],
                        "is_repeat": bool(row["is_repeat"]), "tile_row": r, "tile_col": c,
                        "y0": r * self.size, "x0": c * self.size, "size": self.size,
                        "label": b.value, "labelled_at": now})
        saved = _read_labels(self.labels_csv)
        saved = pd.concat([saved[saved["order"] != self.pos], pd.DataFrame(new)])
        tmp = self.labels_csv.with_suffix(".tmp")
        saved.sort_values(["order", "tile_row", "tile_col"]).to_csv(tmp, index=False)
        tmp.replace(self.labels_csv)                  # write-then-rename: never a half-written file
        self._go(self.pos + 1)


def summary(round: str | None = None) -> pd.DataFrame:
    """Progress, label counts per split, and intra-rater agreement on the repeats
    (repeats of earlier-round images are compared with that earlier labelling)."""
    from sklearn.metrics import cohen_kappa_score

    _, out_dir = _round_dir(round)
    index = pd.read_csv(out_dir / "index.csv")
    lab = _read_labels(out_dir / "labels.csv")
    print(f"Images labelled: {lab['order'].nunique()} / {len(index)}   tiles: {len(lab)}")
    if lab.empty:
        return lab

    lab["is_repeat"] = lab["is_repeat"].astype(str).str.lower().eq("true")
    first = lab[~lab["is_repeat"]]
    print("\nTile labels (first labelling):")
    print(pd.crosstab(first["split"], first["label"], margins=True).reindex(
        columns=[*LABELS, "All"], fill_value=0).to_string())

    earlier = [_read_labels(f) for f in out_dir.parent.glob("*/labels.csv") if f.parent != out_dir]
    earlier = [e.assign(is_repeat=e["is_repeat"].astype(str).str.lower().eq("true")) for e in earlier if len(e)]
    reference = pd.concat([first, *[e[~e["is_repeat"]] for e in earlier]])
    pairs = lab[lab["is_repeat"]].merge(reference, on=["image_id", "tile_row", "tile_col"],
                                        suffixes=("_repeat", "_first"))
    if len(pairs):
        rank = {name: i for i, name in enumerate(LABELS)}
        a, b = pairs["label_first"].map(rank), pairs["label_repeat"].map(rank)
        print(f"\nIntra-rater repeatability ({pairs['image_id'].nunique()} images, {len(pairs)} tiles):")
        print(f"  exact agreement      {(a == b).mean():.3f}")
        print(f"  Cohen's kappa        {cohen_kappa_score(a, b):.3f}")
        print(f"  weighted kappa (lin) {cohen_kappa_score(a, b, weights='linear'):.3f}  (ordinal good>usable>poor)")
        pa, pb = a.eq(rank["poor"]), b.eq(rank["poor"])
        print(f"  poor vs analysable   agreement {(pa == pb).mean():.3f}, kappa {cohen_kappa_score(pa, pb):.3f}"
              "  (the distinction the ROI model learns)")
    return lab
