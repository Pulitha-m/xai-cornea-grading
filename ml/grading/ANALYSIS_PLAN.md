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

### A. Beyond-ECD comparison (addresses the research aim directly)

Question: Do the tabular and hybrid models improve on ECD alone for unseen donors?

- **Comparator:** an ECD-only model trained within each donor-grouped training fold, compared with the tabular and hybrid models on the same held-out tissues.
- **Evaluation tissues:** the 470 primary-cohort tissues with an ECD value. Handling of the 81 without ECD is to be fixed in the protocol.
- **Descriptive extra:** a fixed two-threshold ECD rule. The protocol must state the threshold source: documented eye-bank criteria if available; otherwise, thresholds inferred from 2023 records, in which case the rule is reported as descriptive only.
- Open protocol choices: the ECD-only model type, the primary pairwise comparisons, and multiplicity correction.

### B. Donor-grouped explainability (XAI)

Question: Which information sources drive the models' grade predictions in the primary cohort, and how stable are the explanations?

- SHAP values computed out-of-fold on the donor-grouped folds, so each explanation comes from a model that did not train on that tissue.
- Derived Konan features grouped before interpretation (ECD with cell count and area; CV with SD), and image PCA components grouped as a single image source.
- Report global importance by source, per grade (especially B), and stability across folds and repeats.
- Interpretation in light of analysis A: if neither model improves on ECD alone, the explanations describe model behaviour, not evidence that the other sources add information.

### C. Consolidated results

One table for the primary cohort (tabular, hybrid, ECD comparator), with corrected confidence intervals and per-grade recall, plus the all-year results as context, with each row's cohort stated.

### Recommended order

A, then B, then C. Analysis A determines how the explanations in B can be interpreted.
