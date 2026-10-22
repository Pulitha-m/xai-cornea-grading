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

### B. Explainability of departures from the ECD thresholds (exploratory) — complete

**Status:** complete in `12_threshold_departure_explainability.ipynb`. The protocol was not committed separately before execution (recorded in the notebook's deviations log).

**Results:**

- The hybrid recovers about 29% of grades recorded below the ECD thresholds (131 of 445 tissue–repeat pairs), but makes a similar number of incorrect departures (151).
- The image group dominates both kinds of disagreement (+0.063 toward the recorded grade where the hybrid is right, −0.033 where it is wrong), so it does not establish useful image signal.
- Variability (CV, SD) and, more weakly, stromal findings are the more consistent associations.
- Raw data on downgraded tissues (higher variability, lower HEX, more stromal scar and cell dropout) is descriptive and hypothesis-generating.

**Not done:** a model-free comparison of all tissues graded below the ECD thresholds, regardless of model predictions. Post hoc; optional.

The original specification follows.

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

### C. Consolidated results — complete

One reporting document that brings together existing results; no new models. It should cover:

- **Cohorts:** all labelled (1,036), image cohort (1,009), primary non-2023 cohort (551), and its ECD evaluation set (470). Each result is labelled with its cohort.
- **Validation designs:** the earlier row-level holdout and shared split (superseded), and the 5 × 5 donor-grouped CV used from notebook 06 on.
- **Model performance:** ECD tree, ECD-only Random Forest, tabular, hybrid and image-only models, with macro F1, balanced accuracy, accuracy and per-grade recall. All-year and by-year results are kept separate.
- **Paired comparisons:** differences, corrected 95% CIs, p-values, the multiplicity correction applied, and whether each was pre-specified, a follow-up or exploratory.
- **Explainability summary:** from notebook 12.
- **Limitations:** for each result.

**Status:** complete in `RESULTS.md`.

### D. Nested tuning and application model — complete

**Status:** complete in `13_nested_tuning_model_selection.ipynb`. The protocol, selection rule and inner design (3 donor-grouped folds) were fixed before execution but not committed separately.

**Result:**

- Neither the tuned tabular model (+0.009) nor the tuned hybrid (−0.003) convincingly outperformed the fitted ECD tree (Holm p = 1.00), so the **ECD tree was selected** for the application.
- Tuning raised the tabular model by +0.049; the hybrid's earlier edge over tabular disappeared once both were tuned.

**Application:**

- Exported by `scripts/train_grading_model.py` to `ml-service/models/grading_ecd_tree.json`.
- Served by `ml-service` from an `ecd` request field, with `review_required` when ECD is missing and band grade distributions instead of a confidence value.
- Documented in `ml-service/README.md`.

## Amendment 2: application grade from the hybrid model

**Decision (2026-10-16, project decision after section D):** the application grade comes from the tuned hybrid model (24 features + image) instead of the ECD tree that section D's rule selected. The ECD tree is still computed and shown beside it as a reference. (Earlier the same day the tuned tabular model was served briefly; it was replaced by the hybrid at the project owner's request.)

**What the evidence says about this choice:**

- In section D the tuned hybrid was the lowest of the three models: macro F1 0.793, against 0.796 for the ECD tree (T1: −0.003 [−0.034, +0.029]) and 0.805 for the tuned tabular model (T3: −0.012 [−0.045, +0.022]). No difference was significant (Holm p = 1.00).
- The hybrid has **not** been shown to grade better than the ECD tree or the tabular model, and documents must not say it does.
- The selection rule in section D is not re-run or reinterpreted. This is an override after the rule's result was known, recorded as such.

**Model:**

- `scripts/train_hybrid_grading_model.py` reruns notebook 13's hybrid grid (PCA 8/16/32 × 24 forest settings) with 3-fold donor-grouped CV on all 551 K3 tissues, using the research's cached ResNet-50 embeddings.
- Selected: PCA 32 components, `min_samples_leaf=1, max_depth=15, max_features=0.3`, no class weighting. Inner-CV macro F1 0.774.
- The final pipeline, with notebook 13's preprocessing, is fitted on all K3 tissues and exported to `ml-service/models/grading_hybrid_rf.joblib` with its SHA-256.
- The image backbone (torchvision ResNet-50, IMAGENET1K_V2) is exported to ONNX by `ml-service/scripts/export_grading_backbone.py`. Its output on a fixed probe input is recorded with the model, and every export must reproduce it (byte hashes vary across CPUs). Parity: 551 of 551 training tissues get the same prediction with the served ONNX embeddings as with the research embeddings (largest tree-vote difference 0.060; embeddings differ by at most 0.4% relative).
- Every training image was 1296 × 972. Other image sizes are resized to that size and reported as a warning that requires review.
- The performance estimate is notebook 13's nested result (macro F1 0.793 ± 0.047), not the inner score.
- Model probabilities are the share of trees voting. They have not been calibrated and are shown with that label, never as a confidence.

## E. Model family comparison (follow-up) — complete

**Status:** complete in `14_model_family_comparison.ipynb`. It is a follow-up, raised after section D. The protocol, search spaces and selection rule were fixed before execution but not committed separately. It reuses section D's outer folds, so it is **not independent confirmation**.

**Question:** can another model family, tuned the same way, grade better than the deployed tuned RF hybrid?

**Design:**

- **Candidates:** histogram gradient boosting, logistic regression, RBF SVM and Extra Trees, each as tabular and hybrid.
- **Validation:** the same nested donor-grouped design as section D.
- **Comparisons:** each candidate against the RF hybrid (primary, Holm across 8) and against the ECD tree (secondary, Holm across 8).
- **New metric:** quadratic-weighted kappa.

**Result:**

- **Gradient boosting** could not be distinguished from the RF hybrid: hybrid −0.001, tabular −0.009, Holm p = 1.00.
- **Logistic regression, the SVM and Extra Trees** were worse, by 0.07–0.12 macro F1 (Holm p ≤ 0.027).
- **No candidate beat the ECD tree.**
- Under the pre-set rule, **the deployed RF hybrid is retained**. Amendment 2 is unchanged.

**Deviation:** the first execution stopped at the reproduction check because PCA rounding depends on the BLAS thread count. The reference models were refit with notebook 13's threading and the notebook was executed once more. This is recorded in its deviations log.

## F. Extended hybrid Random Forest tuning (follow-up) — complete

**Status:** complete in `15_extended_hybrid_tuning.ipynb`. It is a follow-up, motivated by inspecting notebook 13's selections: `max_features` 0.3 was chosen in 25/25 folds and PCA 32 in 16/25, both at the edge of the grid. The protocol, grid and selection rule were fixed before execution but not committed separately. It is the third tuning-related analysis on section D's outer folds, so it is **not independent confirmation**.

**Design:**

- **Grid:** 48 settings. PCA {16, 32, 64, 128} × `max_features` {0.3, 0.5, 0.7} × `min_samples_leaf` {2, 1} × `class_weight` {balanced, None}.
- **Preprocessing:** notebook 13's, unchanged, with the PCA fitted inside each training fold.
- **Validation:** the same nested donor-grouped design.
- **Comparison:** against notebook 13's tuned hybrid (primary) and the ECD tree (secondary).

**Result:**

- **Primary comparison:** +0.008 macro F1 [−0.016, +0.033], p = 0.48. **Inconclusive.**
- **Secondary comparison:** against the ECD tree, +0.006, also inconclusive.
- **Selections:** PCA 128 was never chosen. `max_features` 0.7, the new edge, was chosen in 13/25 folds.
- Under the pre-set rule, **the deployed RF hybrid is retained**.

**Note:** the notebook's printed `class_weight` count omitted the `None` selections. It was corrected from the saved CSV in a post-run cell and recorded in the deviations log.

## Remaining work

No planned analyses remain. Possible future work:

- Validation on new, independently graded tissues (notebook 09, Section 9).
- A further hybrid search above `max_features` 0.7 (notebook 15: selected at the edge in 13/25 folds). It should be pre-specified and evaluated on new tissues, since the current folds have been used for three tuning analyses (13–15).
- A model-free comparison of tissues graded below the ECD thresholds (post hoc).
- Microscopy-specific image representations under a new protocol.
