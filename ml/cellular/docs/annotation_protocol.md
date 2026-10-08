# Cell-Boundary Annotation Protocol — Component 3 (round 1)

**Purpose.** Create ground-truth cell-wall masks to train and evaluate the U-Net (Sub-component 3.2)
and to measure the classical baseline. Annotators **correct a draft** produced by the classical
segmenter rather than drawing from scratch.

**Material.** 40 crops of 256 × 256 px (≈ 95 cells each) from 40 different donor tissues of the
**train split only**, spread over ECD bands and image-quality levels; ~30 % are deliberately
harder regions. 10 crops are corrected independently by both annotators (inter-annotator agreement).

**Location (Google Drive).** `Research_Project/cellular_annotations/seg/round1/`

| Folder | Content | Who |
|---|---|---|
| `crops/` | `round1_XXX.png` — grayscale image crop | annotator 1 (input) |
| `drafts/` | `round1_XXX_walls.png` — draft walls, red on transparent | annotator 1 (input) |
| `corrected/` | `round1_XXX_walls.png` — **your corrected layer** | annotator 1 (output) |
| `expert/crops`, `expert/drafts` | the 10 overlap crops | NEBSL expert (input) |
| `expert/corrected/` | expert's corrected layers | NEBSL expert (output) |
| `index.csv`, `preview.png` | crop list and contact sheet | reference |

Patient-derived images: keep them on Drive / your own computer. Do not upload to other services.

---

## 1. What to mark

| Colour (exact) | Meaning |
|---|---|
| **Red `#FF0000`** | cell wall |
| **Blue `#0000FF`** (filled area) | *ignore* region — cells cannot be judged (blur, stress line, fold, debris, too dark) |
| transparent | cell interior / not a wall |

## 2. Rules

1. **Walls sit on the darkest centre line** between two bright cell interiors, **1–2 px wide**.
2. **Every cell must be closed.** A gap of one pixel merges two cells. Zoom in on junctions.
3. **One wall per boundary.** No double lines; walls meet at junctions (usually 3 walls per junction).
4. **Remove false walls** inside a cell (texture, nucleus-like spots, small dark dots). These are the
   most common draft error — the draft deliberately over-splits.
5. **Add missing walls** where two cells were merged.
6. **Cells cut by the crop edge:** draw their walls up to the edge. They are excluded automatically
   later (incomplete cells are never measured).
7. **When unsure, paint the area blue** instead of guessing. Do not paint a whole crop blue; if more
   than half a crop is unusable, note it in the log.
8. Do not use anti-aliasing, soft brushes or other colours — the masks are read by exact colour.

## 3. GIMP (2.10 or 3.x)

1. **File → Open** `crops/round1_XXX.png`.
2. **File → Open as Layers…** `drafts/round1_XXX_walls.png` (now two layers: crop + walls).
3. Select the **walls** layer in the Layers panel. Zoom to **400 %** (`View → Zoom → 4:1`).
4. **Pencil tool** (`N`): size **2 px**, hardness 100, colour **#FF0000** — add walls.
   **Eraser** (`Shift+E`): tick **Hard edge**, size **3 px** — remove false walls.
   For ignore regions: Pencil with colour **#0000FF**, larger size (10–20 px), fill the area.
5. Check: toggle the crop layer's eye icon off and on — every cell should be a closed loop.
6. **Hide the crop layer** (eye icon off) so only the walls layer is visible.
7. **File → Export As…** → `corrected/round1_XXX_walls.png` → keep **Save background colour** off,
   so transparency is kept. (Optionally **File → Save** the `.xcf` to resume later.)

## 4. Krita (alternative)

1. Open `crops/round1_XXX.png`; **Layer → Import/Export → Import Layer…** the walls PNG.
2. Select the walls layer; brush preset **Pixel Art / "Basic-1"** (no smoothing, no anti-aliasing),
   size 2 px, colour `#FF0000`; eraser mode `E`.
3. Hide the crop layer; **File → Export…** `corrected/round1_XXX_walls.png` (PNG, keep alpha).

## 5. Working tips

* Install **Google Drive for desktop** to edit the files in place, or download `crops/` + `drafts/`
  and upload your `corrected/` files when done.
* Typical time: **10–20 min per crop**. Work in sessions of 5–8 crops; quality drops when tired.
* Keep a short log (`log.csv` in the round folder): `crop_id, minutes, notes`.
* **Expert:** work on `expert/` only and **do not look at** the other annotator's corrections — the
  comparison must be independent.

## 6. After annotation

Run `python -m data_prep.check_annotations` (Step 1.5). It checks colours, size and that cells are
closed, converts each layer to a training mask (wall / interior / ignore), and reports the classical
baseline's agreement with your corrections and the inter-annotator agreement.

## 7. Notes for the thesis (Methods)

* Annotation by correction of an automated draft (classical ridge-based watershed, h = 0.20);
  annotator 1 = researcher, annotator 2 = NEBSL technician (10 overlapping crops).
* Both annotators corrected the **same draft**, so agreement measures consistency of correction;
  this is stated as a limitation (a draft can anchor both annotators).
