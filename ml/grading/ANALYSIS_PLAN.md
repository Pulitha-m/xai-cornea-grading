# Analysis Plan

## Research aim

Investigate whether explainable multimodal analysis can improve donor cornea grading beyond ECD alone, using slit-lamp clinical findings, endothelial morphology (Konan) measurements and specular microscopy images.

## Amendment 1: non-2023 primary cohort

**Date:** 2026-10-16

### Change

| | Before | After |
|---|---|---|
| Primary modelling cohort | All labelled, image-matched tissues (1,009) | Image-matched tissues from years other than 2023 (551 tissues, 312 inferred donors) |
| Role of 2023 tissues | Included | Excluded from primary model development and evaluation; all-year results retained as contextual evidence |
| Year definition | Konan exam year, with `Tissue_ID` year as fallback (notebook 08) | Four-digit year in `Tissue_ID` |

### Rationale

Slit-lamp clinical findings are unavailable for every 2023 tissue in the collected dataset and cannot be recovered. A multimodal analysis of clinical findings, morphology and images therefore cannot be carried out on those tissues. The exclusion is based on data availability, not on model performance.

### Timing disclosure

This amendment was made **after** the results of notebooks 08 and 09 were known, including that:

- recorded 2023 grades were almost perfectly predictable from the Konan measurements (macro F1 0.99);
- on non-2023 tissues the hybrid model's macro F1 difference was +0.038 (corrected 95% CI −0.013 to +0.088).

Consequently:

- Notebook 09 remains a **pre-specified sensitivity analysis** with an **inconclusive** result. It is not relabelled as a primary or confirmatory analysis.
- Analyses on the new primary cohort are pre-specified from this point on, but the cohort choice itself was informed by earlier results.

### Limitations introduced

- Findings may not generalise to 2023 tissues or to any period with a similar grading or documentation pattern.
- The primary cohort is about half the data. Per-fold class counts are smaller (12–20 grade B tissues per test fold), so estimates are less precise.
- 81 of the 551 tissues have no Konan measurements, including ECD. Every analysis must state how they are handled.

## Planned analyses on the primary cohort

Each analysis gets its own protocol, written and committed before any code is run, as for notebook 09. Existing donor-grouped folds (`donor_grouped_folds.csv`) are reused throughout.

### A. Beyond-ECD comparison — complete

Question: Do the tabular and hybrid models improve on ECD alone for unseen donors?

| Analysis | Notebook | Status | Result |
|---|---|---|---|
| A: models vs ECD-only Random Forest | `10_beyond_ecd_comparison.ipynb` | Pre-specified | Both improved (+0.048, +0.081 macro F1; Holm p 0.030, 0.006), but the comparator was weak |
| A2: models vs fitted ECD-only depth-2 tree | `11_fitted_ecd_threshold_comparison.ipynb` | Follow-up, motivated by A | Inconclusive for both (Tabular −0.040, Hybrid −0.007) |

**Conclusion:** improvement beyond ECD alone was not established.

- The fitted tree recovered cut points near 2230 and 2500 in every training fold. This supports the consistency of these thresholds in the recorded labels; it does not show that every year followed an identical official protocol.
- The hybrid recovers more grade A tissues that depart from the thresholds (A recall 0.65 vs 0.53) at the cost of A+ recall (0.89 vs 0.99).

### B. Explainability of departures from the ECD thresholds (exploratory)

Refocused after analysis A. Ranking features by overall predictive importance is less informative when the models do not outperform ECD alone. The clinically meaningful question is narrower.

**Question:** For held-out tissues whose recorded grade departs from the ECD-based prediction, which information sources are associated with the hybrid model predicting the recorded grade correctly?

- **Cases of interest:** held-out tissues (evaluation set, out-of-fold, per repeat) where the hybrid predicts the recorded grade correctly and the fitted ECD tree does not. Comparison groups: tissues where both are correct, and where the hybrid is wrong and the tree is correct.
- **Grouped SHAP**, computed with the fold model that did not train on each tissue. Features are grouped as:
  - ECD-derived Konan features (ECD, cell count, area);
  - variability (CV, SD);
  - HEX;
  - slit-lamp findings, by tissue layer;
  - image (the 16 PCA components as one source).
- Report by direction of departure (e.g. recorded A where ECD suggests A+), by grade, and with stability across folds and repeats.
- **Exploratory:** no hypothesis tests or claims of improvement. SHAP values describe associations in the model, not clinical explanations or causal evidence. Any pattern is a hypothesis for clinical review.

A protocol will be written and committed before analysis code, as for notebooks 09–11.

### C. Consolidated results

One table for the primary cohort (ECD tree, ECD-only Random Forest, tabular, hybrid), with corrected confidence intervals and per-grade recall, plus the all-year results as context, with each row's cohort stated.

### Recommended order

B, then C.
