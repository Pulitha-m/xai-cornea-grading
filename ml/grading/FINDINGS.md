# Grading Model: Findings to Date

Checkpoint of the evidence from notebooks `images/06`–`images/08`. The notebooks contain the full analysis and outputs; this file records what they establish and what they do not.

## Research question

Can image-derived information improve donor cornea tissue grading beyond existing clinical and endothelial morphology measurements, particularly when some measurements are unavailable?

**Primary task:** AI-assisted expert grading during tissue evaluation. All 24 tabular features (6 Konan morphology measurements, 18 slit-lamp findings) are legitimate inputs. Pre-examination prediction (no slit-lamp findings) is a separate, secondary scenario.

## Data and evaluation

| Item | Value |
|---|---|
| Labelled tissues | 1,036 (1,009 with an image) |
| Grades (image cohort) | A+ 530, A 314, B 165 |
| Donors | ~778 inferred; 258 fellow-eye pairs |
| Evaluation | 5 repeats × 5 donor-grouped stratified folds (`data/processed/donor_grouped_folds.csv`) |
| Classifier | Random Forest, hyperparameters from notebook 05, identical in every comparison |
| Image features | ImageNet ResNet-50, frozen, full-resolution input, PCA (16 components) fitted per fold |
| Uncertainty | Corrected repeated-CV t-test on paired fold differences; Holm correction across pre-specified comparisons |

## Findings

### 1. No direct leakage in the tabular features (notebook 06)

- No feature source column mentions a grade; `Additional_Findings`, which does, is excluded.
- No single feature predicts the grade almost perfectly (best: ECD, macro F1 0.77).
- Missingness indicators alone do not predict the grade (macro F1 0.27).

### 2. Fellow eyes were split across earlier evaluation sets (notebook 06)

- Fellow eyes share a grade 77.9% of the time (39.9% expected by chance).
- 78 of 258 pairs were split across the 80/20 holdout and 108 of 239 across the shared image/tabular split.
- Donor grouping lowers the tabular RF from 0.858 to 0.844 macro F1. All new results use donor-grouped folds.

### 3. Image embeddings do not significantly improve the full-feature model (notebook 07)

| Arm | Macro F1 | Balanced accuracy |
|---|---:|---:|
| Tabular | 0.849 | 0.841 |
| Hybrid | 0.859 | 0.841 |
| Image only | 0.442 | 0.442 |

- Difference +0.010, 95% CI [−0.012, +0.031], p = 0.36. Not robust to the number of PCA components (8: −0.004; 32: +0.003).
- Grade B recall falls from 0.851 to 0.819 with images.

### 4. The recorded data contain two distinct patterns (notebook 08)

- Slit-lamp findings are missing for all 455 tissues from 2023 and almost no others. They cannot be recovered.
- In 2023, recorded grades agree with fixed ECD thresholds (B < 2250, A 2250–2499, A+ ≥ 2500) for 95% of tissues, compared with 72–84% in other years.
- Tabular macro F1 is 0.992 on 2023 tissues and 0.729 on other years. Pooled results (~0.85) combine the two.

**What this does not show:** why the pattern arose. It is consistent with a change in protocol or documentation, but it is not evidence that specialists graded 2023 tissues from ECD alone, or that two official grading protocols existed.

### 5. Images do not reliably compensate for missing information (notebook 08)

| Comparison (Hybrid − Tabular, macro F1) | Difference [95% CI] | p (Holm) |
|---|---|---|
| C1 Natural: slit-lamp missing | −0.022 [−0.045, +0.001] | 0.17 |
| C2 Natural: Konan missing (85 tissues) | −0.068 [−0.235, +0.100] | 0.82 |
| C3 Slit-lamp masked at test | +0.062 [+0.024, +0.099] | 0.013 |
| C4 Konan masked at test | +0.061 [+0.011, +0.111] | 0.073 |
| C5 Pre-examination (no slit-lamp) | +0.005 [−0.023, +0.034] | 0.82 |

- **C1** is the 2023 subset, where tabular is at ceiling; it does not test image value.
- **C3** is significant but not evidence of benefit: masking shifts the tabular model toward the 2023 pattern (agreement with ECD thresholds 0.85 → 0.95), balanced accuracy is unchanged, and grade B recall falls from 0.82 to 0.68.
- **C5**, the cleanest test, shows no gain.

## Exploratory, hypothesis-generating only

On non-2023 tissues the hybrid gains +0.036 macro F1 [−0.004, +0.075], p = 0.078 (unadjusted), larger than in 2023 (interaction p = 0.03). This was found after seeing the data and is not a confirmed benefit. It motivates a separately pre-specified experiment on non-2023 tissues.

## Limitations

- Donor pairs are inferred from consecutive serial numbers and donor details, not confirmed against a register.
- RF hyperparameters were tuned in notebook 05 for tabular features with non-grouped CV, which may slightly favour the tabular arm.
- Image features are generic (ImageNet, frozen); a representation adapted to specular microscopy has not been tested.
- 2023 slit-lamp findings are permanently missing; their absence is tied to a subset with a distinct grade pattern.

## Planned next steps

1. Pre-specified tabular vs hybrid comparison restricted to non-2023 tissues (same folds, metrics and RF settings), with settings fixed before results are examined.
2. If worthwhile, a separately pre-specified experiment with a specular-microscopy-appropriate image representation.
3. Report all results overall and by year.
