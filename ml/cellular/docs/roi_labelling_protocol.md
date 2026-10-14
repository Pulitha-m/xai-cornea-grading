# ROI Tile Labelling Protocol — Component 3 (Step 1.7, round 1)

**Purpose.** Label image quality tile by tile, to train the patch-quality CNN for automatic ROI
selection (Sub-component 3.1) and to give reference ROI maps for measuring ROI IoU (target 0.75).

**Material.** 30 images (20 train, 10 val; never test), one per tissue, spread over image-quality
terciles and ECD bands, + 3 repeats. Each image is a grid of **6 × 8 tiles of 162 px** (~5.7 cells
across, ~30 cells per tile) → 48 tiles per image, ~1,600 tiles in total.

**Tool.** `notebooks/roi_labelling_1.ipynb` (Colab). Labels: `cellular_annotations/roi/round1/labels.csv`.

---

## 1. Classes

Judge **whether cells in the tile could be counted and measured reliably** — not how pretty it is.

| Button | Class | Use when |
|---|---|---|
| **G** | **good** | Walls sharp and continuous; practically every cell in the tile could be outlined. |
| **U** | **usable** | Cells visible and mostly countable, but some blur, low contrast, noise, or small artefacts; you would use it if nothing better was available. |
| **P** | **poor** | Cells cannot be counted reliably: too dark, out of focus, stress lines / folds, debris, large guttae, or outside the lit area. |

## 2. Rules

1. **More than half rule:** label by what covers **most of the tile**. A tile half dark, half good →
   the better half decides only if it is clearly more than half.
2. **Dark border:** the unlit image edge is **poor**.
3. **When unsure between two classes, choose the worse one** (an ROI must be trustworthy).
4. Do not look at the Konan values or other images while labelling.
5. **"Unlabelled → good"** sets every grey tile to good — use it only after you have marked all
   usable and poor tiles, never as a first click.
6. Some images appear twice (rotated). Label them fresh; this measures repeatability.

## 3. Working

* Typical time: ~1–2 min per image, ~1 hour in total. Work in 2–3 sessions; labelling resumes at
  the first unlabelled image.
* **< Back** reopens the previous image with its saved labels; saving again replaces them.
* Larger tiles: `RoiLabeller(display_px=162)` (full resolution, wider than the screen).

## 4. Notes for the thesis (Methods)

* Tile-level quality labels (3 ordinal classes) on a fixed 6 × 8 grid; all tiles of each image
  labelled, so val images give complete reference ROI maps.
* Single rater (researcher, guided by the NEBSL expert). Intra-rater repeatability on 3 blind,
  rotated repeat images: exact agreement and Cohen's κ (unweighted and linear-weighted), from
  `summary()`.

### Results (round 1, completed 2026-10-12)

* **Labels:** 30 images, 1,440 tiles — good 303 (21 %), usable 631 (44 %), poor 506 (35 %);
  train 960 tiles (207 / 423 / 330), val 480 tiles (96 / 208 / 176).
* **Intra-rater repeatability** (3 repeats, 144 tiles):

  | Distinction | Agreement | Cohen's κ |
  |---|---|---|
  | 3 classes | 0.715 | 0.556 (linear-weighted 0.635) |
  | **poor vs analysable** (good + usable) | **0.910** | **0.804** |
  | good vs rest | 0.806 | 0.390 |

  Disagreement lies almost entirely between *good* and *usable* (26 of 39 tiles first labelled
  good were usable in the repeat — grading became stricter over time); *poor* was stable
  (45 of 47).
* **Decision for the ROI model (3.1):** trained on the binary target **poor vs analysable**
  (reliable reference, κ = 0.80); the good / usable distinction is used only as a soft score to
  rank analysable regions, and no accuracy is reported for it. The intra-rater κ = 0.80 serves
  as the human-level reference for the model.

> Suggested wording: *Intra-rater repeatability (3 blind rotated repeats, 144 tiles) was
> substantial for the clinically relevant decision analysable vs poor (agreement 0.91, κ = 0.80),
> but only fair for good vs usable (κ = 0.39), which drifted toward stricter grading over time.
> ROI selection was therefore trained on the binary target, with tile-quality probabilities used
> only to rank analysable regions.*
