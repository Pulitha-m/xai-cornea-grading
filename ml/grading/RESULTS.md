# Consolidated Results (Analysis C)

All results for the cornea grading models, drawn from saved outputs of notebooks `05` and `images/02`–`images/13`. No models were rerun for this document. Interpretation and claim status are in `CLAIMS_AUDIT.md`; the analysis history is in `ANALYSIS_PLAN.md`.

## How to read this document

- **Each results table covers one cohort and one validation design.** Compare rows within a table, never across tables. Tables differ in tissues, years, training data and folds, so similar-looking numbers in different tables are not comparable.
- **Fold-level values** are the mean (± SD) over 25 folds (5 repeats × 5 donor-grouped folds).
- **Paired comparisons** use the corrected repeated-CV t-test (Nadeau & Bengio, 2003; Bouckaert & Frank, 2004) with 24 degrees of freedom. Confidence intervals are 95%, corrected for fold overlap, and not adjusted for multiplicity.
- **Source** is given for every table: a saved CSV in `data/processed/` (git-ignored), or a notebook's saved output where no CSV exists. Values from CSVs were recomputed and agree with the notebook outputs.

## 1. Cohorts

| ID | Cohort | Tissues | Donors | Grades (A+ / A / B) | Definition |
|---|---|---:|---:|---|---|
| K1 | All labelled | 1,036 | ~778 | 545 / 319 / 172 | `Tissue_Grade_Clean` in {A+, A, B} |
| K2 | Image cohort | 1,009 | ~770 | 530 / 314 / 165 | K1 with a usable image (two review tissues excluded) |
| K3 | **Primary cohort** | 551 | 312 | 277 / 196 / 78 | K2 with `Tissue_ID` year ≠ 2023 |
| K4 | **ECD evaluation set** | 470 | 280 | 244 / 159 / 67 | K3 with a non-missing ECD |
| K5 | No-ECD set | 81 | 58 | 33 / 37 / 11 | K3 without ECD (all Konan features missing) |

**Year definitions differ between analyses:**

- Notebook 08 used the Konan exam year, falling back to the `Tissue_ID` year. It splits K2 into 455 (2023) and 554 (other years).
- Notebooks 09–12 use the `Tissue_ID` year. That gives 458 (2023) and 551 (other years). The 3 tissues that move have a 2023 ID and a 2024 exam date.

Donor counts are inferred from consecutive tissue serials and donor details (`modeling_setup.get_donor_groups`), not from a donor register.

## 2. Validation designs

| ID | Design | Donor-grouped | Used by | Status |
|---|---|---|---|---|
| V0 | 80/20 stratified row-level holdout (828 / 208), tuning by 5-fold CV on the 828 | No | 05 | Superseded: 78 donor pairs split; holdout informed earlier decisions |
| V1 | 70/15/15 stratified split (706 / 151 / 152) | No | images/02–05 | Superseded: 108 donor pairs split; single test set, no uncertainty |
| V2 | 5 repeats × 5 stratified donor-grouped folds (`donor_grouped_folds.csv`) | Yes | 06–12 | Current design |

Notebooks 09–12 restrict V2 to the primary cohort (K3): training and test tissues are both non-2023. The fold assignment of each tissue is unchanged.

## 3. Analysis types

| Type | Meaning |
|---|---|
| Pre-specified | Protocol documented before the analysis was run, with git history supporting that sequence: the protocol cell was committed before analysis code (notebook 10) |
| Planned | Settings written into the notebook before its comparisons, but the timing cannot be independently verified from git history (notebooks 07–08 and 13) |
| Sensitivity | Pre-specified (protocol committed before analysis code) re-analysis on data that already generated the hypothesis (notebook 09); not independent confirmation |
| Follow-up | Pre-specified (protocol committed before analysis code), but motivated by an earlier result (notebook 11); not independent confirmation |
| Exploratory | Descriptive, no hypothesis tests (notebook 12) |
| Diagnostic | Added after seeing results, to explain them (notebook 06 grouping check; notebook 08 Section 10) |

## 4. Results by cohort and design

### R1. Effect of donor grouping (K1, all years; notebook 06; diagnostic)

Tabular Random Forest (24 features, hyperparameters from notebook 05), macro F1 over 25 folds.

| Folds | Macro F1 |
|---|---:|
| Stratified, ignoring donors | 0.858 ± 0.015 |
| Donor-grouped (V2) | 0.844 ± 0.020 |

Source: notebook 06 output (no CSV). No paired test was run.

### R2. Image embeddings, all years (K2, V2; notebook 07; planned)

| Model | Macro F1 | Balanced accuracy | Accuracy |
|---|---:|---:|---:|
| Tabular | 0.849 ± 0.021 | 0.841 ± 0.023 | 0.850 ± 0.020 |
| Hybrid (PCA 16) | 0.859 ± 0.025 | 0.841 ± 0.028 | 0.861 ± 0.024 |
| Image only (PCA 16; reference arm) | 0.442 ± 0.033 | 0.442 ± 0.033 | 0.505 ± 0.033 |

| Hybrid − Tabular | Difference [95% CI] | p | Folds improved |
|---|---|---:|---:|
| Macro F1 (primary) | +0.010 [−0.012, +0.031] | 0.359 | 16/25 |
| Balanced accuracy | −0.000 [−0.022, +0.021] | 0.971 | 11/25 |
| Accuracy | +0.012 [−0.013, +0.036] | 0.345 | 15/25 |

**PCA sensitivity (macro F1, hybrid − tabular):** 8 components −0.004 [−0.026, +0.017], p = 0.678; 32 components +0.003 [−0.021, +0.027], p = 0.784.

**Grade B recall, pooled over repeats:** tabular 0.851, hybrid 0.819 (notebook 07 output only).

Source: `hybrid_fold_scores.csv`; paired tests from notebook 07 output.

**Caveat:** this pools 2023 (tabular macro F1 0.992) with other years (0.729); see R3.

### R3. Missing information, all years (K2, V2; notebook 08)

Models are trained on all years. Comparisons C1–C5 are planned, with Holm correction across the five macro F1 p-values.

| ID | Comparison | Tissues evaluated | Tabular | Hybrid | Difference [95% CI] | p | p (Holm) |
|---|---|---:|---:|---:|---|---:|---:|
| C1 | Natural: slit-lamp missing | 458 | 0.992 | 0.970 | −0.022 [−0.045, +0.001] | 0.056 | 0.169 |
| C2 | Natural: Konan missing | 85 | 0.470 | 0.403 | −0.068 [−0.235, +0.100] | 0.412 | 0.824 |
| C3 | Slit-lamp masked at test | 551 | 0.678 | 0.740 | +0.062 [+0.024, +0.099] | 0.003 | 0.013 |
| C4 | Konan masked at test | 924 | 0.306 | 0.367 | +0.061 [+0.011, +0.111] | 0.018 | 0.073 |
| C5 | Pre-examination (no slit-lamp in training) | 1,009 | 0.845 | 0.850 | +0.005 [−0.023, +0.034] | 0.706 | 0.824 |

All values are macro F1.

**Grade B recall, hybrid − tabular:** C3 −0.140 [−0.239, −0.040]; C4 −0.630 [−0.716, −0.543]; C1, C2 and C5 not significant.

**Interpretation constraints (from notebook 08):**

- C1 coincides with the 2023 subset, where tabular is at ceiling.
- C3 is confounded by masking: the tabular model's agreement with the ECD thresholds rose from 0.85 to 0.95.
- C5 is the cleanest test.

**By year (diagnostic, Section 10 of notebook 08; year from exam date):**

| Subset | Tissues | Tabular | Hybrid | Difference [95% CI] | p |
|---|---:|---:|---:|---|---:|
| 2023 | 455 | 0.992 | 0.971 | −0.022 [−0.044, +0.001] | 0.056 |
| Other years | 554 | 0.729 | 0.765 | +0.036 [−0.004, +0.075] | 0.078 |

Source: `missing_information_results.csv` (C1–C5 values); Holm p-values and by-year table from notebook 08 output.

### R4. Non-2023 sensitivity analysis (K3, V2 restricted; notebook 09; sensitivity)

Models are trained and evaluated on non-2023 tissues only. It shares tissues, folds and features with the exploratory "other years" result in R3, so it is not independent of it.

| Model | Macro F1 | Balanced accuracy | Accuracy | Grade B recall |
|---|---:|---:|---:|---:|
| Tabular | 0.711 ± 0.044 | 0.705 ± 0.045 | 0.716 ± 0.037 | 0.722 ± 0.120 |
| Hybrid | 0.748 ± 0.041 | 0.734 ± 0.046 | 0.760 ± 0.036 | 0.714 ± 0.124 |

| Hybrid − Tabular | Difference [95% CI] | p | Folds improved |
|---|---|---:|---:|
| **Macro F1 (primary)** | +0.038 [−0.013, +0.088] | 0.135 | 19/25 |
| Balanced accuracy | +0.029 [−0.018, +0.077] | 0.215 | 17/25 |
| Accuracy | +0.044 [−0.003, +0.092] | 0.066 | 20/25 |
| Grade B recall | −0.008 [−0.105, +0.089] | 0.869 | 7/25 |

**Verdict under the protocol:** inconclusive. No qualifier was triggered.

Source: `non_2023_fold_scores.csv`; paired tests from notebook 09 output.

### R5. Comparison with ECD alone (K4, V2 restricted; notebooks 10–11)

All five predictors are evaluated on the **same 470 tissues and held-out folds**, so the rows of this table are directly comparable.

| Predictor | Inputs | Fitted where | Macro F1 | Balanced accuracy | Accuracy | Grade B recall |
|---|---|---|---:|---:|---:|---:|
| ECD-only Random Forest | ECD | Training folds (K4 tissues) | 0.707 ± 0.051 | 0.711 ± 0.052 | 0.709 ± 0.049 | 0.793 ± 0.110 |
| ECD tree (depth 2) | ECD | Training folds (K4 tissues) | 0.796 ± 0.038 | 0.768 ± 0.043 | 0.804 ± 0.031 | 0.790 ± 0.117 |
| ECD rule (2250 / 2500)* | ECD | Not fitted | 0.797 ± 0.037 | 0.769 ± 0.042 | 0.806 ± 0.029 | 0.790 ± 0.117 |
| Tabular | 24 features | Training folds (K3 tissues) | 0.756 ± 0.042 | 0.753 ± 0.043 | 0.758 ± 0.040 | 0.814 ± 0.102 |
| Hybrid | 24 features + image | Training folds (K3 tissues) | 0.789 ± 0.041 | 0.782 ± 0.045 | 0.797 ± 0.033 | 0.809 ± 0.127 |

\* Descriptive only. Thresholds inferred from 2023 records after inspection; not documented eye-bank criteria.

**Notebook 10 (pre-specified):** comparison with the ECD-only Random Forest; Holm across the two primary comparisons.

| Comparison (macro F1) | Difference [95% CI] | p | p (Holm) | Folds improved | Verdict |
|---|---|---:|---:|---:|---|
| Tabular − ECD-only RF | +0.048 [+0.005, +0.092] | 0.030 | 0.030 | 22/25 | Improved |
| Hybrid − ECD-only RF | +0.081 [+0.031, +0.132] | 0.003 | 0.006 | 25/25 | Improved |

The ECD-only Random Forest is a weak comparator: ECD supports at least 0.796 with a fitted tree.

**Notebook 11 (follow-up, motivated by notebook 10):** comparison with the fitted ECD tree; Holm across the two primary comparisons.

| Comparison (macro F1) | Difference [95% CI] | p | p (Holm) | Folds improved | Verdict |
|---|---|---:|---:|---:|---|
| Tabular − ECD tree | −0.040 [−0.084, +0.004] | 0.071 | 0.141 | 2/25 | Inconclusive |
| Hybrid − ECD tree | −0.007 [−0.046, +0.031] | 0.702 | 0.702 | 11/25 | Inconclusive |

**Secondary metrics against the ECD tree (unadjusted):**

- Tabular accuracy is lower: −0.046 [−0.091, −0.001], p = 0.044.
- Hybrid balanced accuracy is higher but not significantly: +0.014 [−0.025, +0.053], p = 0.464.

**Conclusion:** improvement beyond ECD alone was not established.

**Learned cut points (descriptive):** in all 25 training folds the tree learned 2232 and 2494–2503 (19 folds: 2497; 5 folds: 2503; 1 fold: 2494).

**No-ECD set (K5, descriptive):** neither ECD-only predictor can grade these tissues. Tabular macro F1 0.406 and hybrid 0.468, with grade B recall 0.164 for both.

Sources: `beyond_ecd_fold_scores.csv`, `beyond_ecd_results.csv`, `fitted_ecd_fold_scores.csv`, `fitted_ecd_results.csv`, `fitted_ecd_cut_points.csv`. No-ECD values from notebook 10 output.

### R6. Explainability of threshold departures (K4, V2 restricted; notebook 12; exploratory)

No hypothesis tests. SHAP values describe associations within the hybrid model, not clinical explanations or causal evidence. Hybrid and ECD tree reproduced notebook 11 exactly.

| Case group (2,350 tissue–repeat pairs) | Pairs | Unique tissues |
|---|---:|---:|
| Hybrid-only correct | 133 | 37 |
| Both correct | 1,739 | 366 |
| Tree-only correct | 151 | 58 |
| Both wrong | 327 | 78 |

| Mean grouped SHAP toward the recorded grade | Hybrid-only correct | Both correct | Tree-only correct |
|---|---:|---:|---:|
| ECD-derived | +0.029 | +0.164 | +0.075 |
| Variability (CV, SD) | +0.027 | +0.056 | −0.000 |
| HEX | +0.008 | +0.004 | −0.004 |
| Slit-lamp: stroma | +0.019 | +0.017 | +0.009 |
| Slit-lamp: epithelium / endothelium / Descemet | +0.002 / −0.001 / +0.000 | +0.002 / +0.003 / +0.006 | −0.000 / +0.000 / +0.000 |
| Image | +0.063 | +0.050 | −0.033 |

- The hybrid recovers 131 of 445 downgrade pairs (29%), with 151 incorrect departures.
- Image dominates both kinds of disagreement, which indicates model reliance, not demonstrated signal.
- Variability is positive in hybrid-only-correct cases in all 5 repeats and ≈ 0 in tree-only-correct cases.
- Raw-data differences in downgraded tissues are listed in `FINDINGS.md`, section 11. They are hypothesis-generating and affected by selection on the model's predictions.

Source: `threshold_departure_shap.csv` (group means recomputed); raw-data prevalences from notebook 12 output.

### R6b. Nested tuning and application model selection (K4, V2 restricted + inner CV; notebook 13; planned)

The protocol was written before execution but not committed separately, so this is labelled "planned".

- **Outer folds:** as R5.
- **Inner tuning:** 3-fold donor-grouped CV within each outer training fold (tabular 24 settings, hybrid 72).
- **Training cohorts:** the ECD tree is untuned and trained on K4 tissues; the tuned models are trained on K3 tissues.

All rows are evaluated on the same 470 tissues and are directly comparable with each other and with R5.

| Model | Macro F1 | Balanced accuracy | Accuracy | Grade B recall |
|---|---:|---:|---:|---:|
| ECD tree | 0.796 ± 0.038 | 0.768 ± 0.043 | 0.804 ± 0.031 | 0.790 ± 0.117 |
| Tuned tabular | 0.805 ± 0.034 | 0.781 ± 0.037 | 0.809 ± 0.030 | 0.793 ± 0.115 |
| Tuned hybrid | 0.793 ± 0.047 | 0.775 ± 0.050 | 0.797 ± 0.040 | 0.789 ± 0.130 |

| Comparison (macro F1) | Difference [95% CI] | p | p (Holm) | Folds improved |
|---|---|---:|---:|---:|
| T1: Tuned hybrid − ECD tree | −0.003 [−0.034, +0.029] | 0.873 | 1.00 | 11/25 |
| T2: Tuned tabular − ECD tree | +0.009 [−0.010, +0.028] | 0.342 | 1.00 | 18/25 |
| T3: Tuned hybrid − tuned tabular | −0.012 [−0.045, +0.022] | 0.481 | 1.00 | 8/25 |

- **Selection rule outcome:** the ECD tree. Final cut points 2232 / 2497, fitted on all 470 K4 tissues.
- **Tuning gain over the notebook 05 settings (descriptive):** tabular +0.049 (24/25 folds), hybrid +0.005 (15/25).

Sources: `nested_tuning_fold_scores.csv`, `nested_tuning_results.csv`, `nested_tuning_selections.csv`, `selected_grading_model.json`. The selected-settings table in the notebook was corrected after the run from `nested_tuning_selections.csv`; see its deviations log.

### R7. Superseded results (not comparable with R1–R6b)

Listed for completeness. These designs split fellow eyes across training and test and have no uncertainty estimates.

| Notebook | Cohort / design | Result | Why superseded |
|---|---|---|---|
| 05 | K1 / V0 | Tuned RF holdout macro F1 0.861; 5-fold CV 0.854 | Donor pairs split; holdout informed earlier decisions |
| 05 | K1 / V0 | RF ranked above SVM, Extra Trees, LR (CV macro F1 0.834 / 0.789 / 0.754 / 0.719) | Non-grouped CV; ranking not re-checked with grouping |
| images/05 | K2 / V1 | Test macro F1: tabular RF 0.906, neural multimodal 0.818, CNN 0.371 | Single 152-tissue test set, donor pairs split; fusion confounded with MLP vs RF |
| images/02 | K2 / V1 | Validation macro F1 0.33–0.48 for from-scratch CNNs and partly fine-tuned ResNet-18 | 224-pixel inputs; shows these configurations failed, not that images are uninformative |

Source: notebook outputs only.

## 5. Verification notes

**Verified from saved CSVs:** fold-level means and SDs in R2, R4 and R5; R3 differences, CIs and unadjusted p-values; R5 paired results and cut points; R6 group sizes and SHAP means.

**Available only in notebook outputs** (no CSV saved):

- R1 values.
- R2 paired tests and pooled grade B recall.
- R3 Holm p-values and the by-year table.
- R4 paired tests.
- No-ECD results in R5.
- Raw-data prevalences in R6.
- All of R7.

**Cannot be verified from saved outputs:**

- Donor counts depend on the inferred pairing rule; no donor register was available.
- The provenance of the 2250/2500 thresholds as eye-bank criteria; no documentation was available. They are treated as inferred throughout.
- Whether the notebook 07–08 settings were fixed before results. This is stated in the notebooks but was not committed to git separately, unlike notebooks 09–11.
- Whether the notebook 12 and 13 protocols preceded their analysis code. They were not committed separately; recorded in their deviations logs.
- Exact data versions: SHA-256 hashes of the dataset, folds and embeddings are printed in notebooks 09–12. The data files are not in git.

## 6. Limitations (all results)

- **Hyperparameters:** R2–R6 use Random Forest settings from notebook 05 (non-grouped CV, tabular features). R6b shows these settings disadvantaged the tabular model by about 0.05 macro F1. Comparisons in R2–R6 that involve the tabular arm should be read with this in mind.
- **Donor grouping** is inferred.
- **Generalisability:** the primary cohort excludes 2023 because slit-lamp findings are unavailable. Results may not generalise to 2023 or to periods with similar documentation patterns.
- **Image features** are generic: frozen ImageNet ResNet-50 at full resolution, reduced by PCA. Microscopy-specific representations were not tested.
- **Multiplicity** is corrected only within each notebook's primary comparisons, not across notebooks 07–12.
- **Independence:** no external or prospective validation cohort. Notebooks 09–12 share tissues and folds with the exploratory analyses that motivated them. The future validation plan in notebook 09 (Section 9) is a proposal only.
