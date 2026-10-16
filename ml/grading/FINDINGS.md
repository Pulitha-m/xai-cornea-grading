# Grading Model: Findings to Date

Checkpoint of the evidence from notebooks `images/06`–`images/13`. The notebooks contain the full analysis and outputs; this file records what they establish and what they do not.

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

Later analysis (section 10) found that a tree fitted only on non-2023 tissues recovers nearly the same thresholds, so other years are anchored at similar cut points but depart from them more often.

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

On non-2023 tissues the hybrid gains +0.036 macro F1 [−0.004, +0.075], p = 0.078 (unadjusted), larger than in 2023 (interaction p = 0.03). This was found after seeing the data and is not a confirmed benefit. It motivated the pre-specified sensitivity analysis in notebook 09.

### 6. Non-2023 sensitivity analysis: inconclusive (notebook 09)

Pre-specified (protocol committed before analysis code); trained and evaluated on non-2023 tissues only (551 tissues, 312 donors, year from `Tissue_ID`). Run once; no deviations.

| Hybrid − Tabular | Tabular | Hybrid | Difference [corrected 95% CI] | p |
|---|---:|---:|---|---:|
| Macro F1 (primary) | 0.711 | 0.748 | +0.038 [−0.013, +0.088] | 0.135 |
| Balanced accuracy | 0.705 | 0.734 | +0.029 [−0.018, +0.077] | 0.215 |
| Grade B recall | 0.722 | 0.714 | −0.008 [−0.105, +0.089] | 0.869 |

- Verdict under the protocol's rules: **inconclusive**. Grade B recall and per-year qualifiers were not triggered.
- The direction was positive in all 5 repeats and in every year, but this analysis shares tissues, folds and features with the exploratory result and is not independent confirmation.

## Observations from the evidence audit (descriptive)

### 7. Konan features are partly derived from one another

- ECD equals `Total_Cell_Count / Total_Area_um2` (all 940 tissues within 1%), and CV is effectively `SD / mean cell area` (r = 0.998). The six Konan features carry about four independent quantities.
- This explains why notebook 04 found that adding ECD to the morphology features changed no predictions, and it means feature-level SHAP values split credit between derived features.

### 8. A two-threshold ECD rule matches the tabular model on non-2023 tissues

On the 470 non-2023 tissues with an ECD value (out-of-fold predictions from notebook 09):

| Predictor | Macro F1 | Balanced accuracy | Accuracy | Grade B recall |
|---|---:|---:|---:|---:|
| ECD rule: B < 2250 ≤ A < 2500 ≤ A+ | 0.800 | 0.770 | 0.806 | 0.791 |
| ECD rule: B < 2000 ≤ A < 2500 ≤ A+ | 0.671 | 0.636 | 0.749 | 0.388 |
| Tabular RF | 0.758 | 0.754 | 0.758 | 0.818 |
| Hybrid RF | 0.791 | 0.782 | 0.797 | 0.806 |

- The 2250/2500 thresholds were identified from the 2023 data after it had been inspected, so this is a descriptive comparison, not a test. They were not fitted to the non-2023 tissues.
- It shows that the added value of the Random Forest over a simple ECD threshold rule has not been demonstrated, even in the subset where recorded grades depart more often from the thresholds.
- This unmatched check was replaced by the matched, donor-grouped comparisons in sections 9 and 10.

## Comparison with ECD alone (primary cohort: non-2023 tissues with ECD)

Both analyses below use the 470 non-2023 tissues with an ECD value (280 donors), the same 5 × 5 donor-grouped folds, and the same Tabular and Hybrid models as notebook 09 (predictions reproduced exactly). Primary metric: macro F1; corrected repeated-CV t-test; Holm correction across the two comparisons in each notebook.

### 9. Pre-specified: models vs an ECD-only Random Forest (notebook 10)

| Comparison (macro F1) | Model | ECD-only RF | Difference [95% CI] | Holm p |
|---|---:|---:|---|---:|
| Tabular − ECD-only RF | 0.756 | 0.707 | +0.048 [+0.005, +0.092] | 0.030 |
| Hybrid − ECD-only RF | 0.789 | 0.707 | +0.081 [+0.031, +0.132] | 0.006 |

- Verdict under the protocol: **both models improved on the ECD-only Random Forest**. Grade B recall and per-year qualifiers were not triggered.
- **Limitation:** the ECD-only Random Forest was a weak comparator. In the same notebook, the descriptive 2250/2500 rule scored 0.797 using ECD alone.

### 10. Follow-up: models vs a fitted ECD-only threshold tree (notebook 11)

Motivated by the weak comparator in notebook 10, so it is a follow-up, not independent confirmation. The baseline is a depth-2 decision tree on ECD alone (`min_samples_leaf=10`, balanced class weights), fixed in advance and fitted within each training fold.

| Comparison (macro F1) | Model | ECD tree | Difference [95% CI] | Holm p | Folds improved |
|---|---:|---:|---|---:|---:|
| Tabular − ECD tree | 0.756 | 0.796 | −0.040 [−0.084, +0.004] | 0.141 | 2/25 |
| Hybrid − ECD tree | 0.789 | 0.796 | −0.007 [−0.046, +0.031] | 0.702 | 11/25 |

- Verdict under the protocol: **inconclusive for both**. No qualifier was triggered.
- **Improvement beyond ECD alone was not established.** The models outperformed a poorly specified ECD-only learner (section 9), but not a properly fitted two-threshold ECD model.

**Thresholds recovered from the labels (descriptive):**

- In all 25 training folds, using non-2023 tissues only, the tree learned cut points of 2232 and 2494–2503, close to the 2250/2500 thresholds inferred from 2023. It scored 0.796 against 0.797 for the inferred rule.
- This supports the consistency of these thresholds in the recorded labels across years. It does not show that every year followed an identical official protocol, and it does not explain why individual tissues depart from the thresholds.

**Different error patterns (pooled over repeats, descriptive):**

| Recall | ECD tree | Tabular | Hybrid |
|---|---:|---:|---:|
| A+ | 0.988 | 0.846 | 0.890 |
| A | 0.528 | 0.599 | 0.649 |
| B | 0.791 | 0.818 | 0.806 |

The tree assigns A+ to almost every tissue with ECD of about 2500 or more, and identifies about half of grade A tissues. The hybrid recovers more grade A tissues that depart from the thresholds, at the cost of A+ recall. Its balanced accuracy is 0.014 higher, which is not significant.

## Explainability of threshold departures

### 11. Where the hybrid departs from the ECD tree (notebook 12, exploratory)

Exploratory and descriptive: no hypothesis tests. SHAP values describe associations within the fitted model, not clinical explanations or causal evidence. Same 470 tissues, folds, hybrid and ECD tree as notebook 11 (reproduced exactly). Each tissue is explained by the fold model that did not train on it, for the probability of its recorded grade, with SHAP summed within eight feature groups. The protocol was not committed separately before execution (recorded in the notebook's deviations log).

**Disagreements between the models** (470 tissues × 5 repeats = 2,350 tissue–repeat pairs):

| Group | Pairs | Unique tissues | Typical case |
|---|---:|---:|---|
| Hybrid-only correct | 133 | 37 | Recorded A where the tree predicts A+ (119 pairs) |
| Both correct | 1,739 | 366 | |
| Tree-only correct | 151 | 58 | Recorded A+ where the hybrid predicts A (121 pairs) |
| Both wrong | 327 | 78 | Recorded A where both predict A+ (256 pairs) |

- 131 of 133 hybrid-only-correct pairs are **downgrades**: the recorded grade is below the tree's ECD-based prediction. 30 tissues fall in this group in at least 3 of 5 repeats, and 14 in all 5.
- The hybrid recovers 131 of the 445 downgrade pairs (about 29%), but makes a **similar number of incorrect departures** (151 tree-only-correct pairs). Its departures from the ECD thresholds are right about as often as wrong.

**Grouped SHAP toward the recorded grade** (mean signed value):

| Feature group | Hybrid-only correct | Both correct | Tree-only correct |
|---|---:|---:|---:|
| ECD-derived | +0.029 | +0.164 | +0.075 |
| Variability (CV, SD) | +0.027 | +0.056 | −0.000 |
| HEX | +0.008 | +0.004 | −0.004 |
| Slit-lamp: stroma | +0.019 | +0.017 | +0.009 |
| Other slit-lamp groups | ≈ 0 | ≈ 0 to +0.006 | ≈ 0 |
| Image | +0.063 | +0.050 | −0.033 |

- **Image dominates both kinds of disagreement.** It ranks first in hybrid-only-correct cases in all 5 repeats, but pushes the model away from the recorded grade in tree-only-correct cases, and its magnitude is similar in every group (mean |SHAP| 0.060–0.073). This reflects model reliance, not useful image signal. Image components have no clinical labels and are not interpreted.
- **Variability is the more consistent association.** It is positive in hybrid-only-correct cases in every repeat (+0.020 to +0.029) and roughly zero in tree-only-correct cases, so it does not drive the hybrid's incorrect departures. Stromal findings show a smaller version of the same pattern.

**Downgraded tissues in the raw data (descriptive, hypothesis-generating):**

Hybrid-only-correct downgrades where the tree predicted A+ (33 tissues), compared with both-correct tissues where the tree predicted A+ (230 tissues):

| | Downgrades | Both correct |
|---|---:|---:|
| Median ECD | 2611 | 2821 |
| Median CV / SD | 40 / 149 | 37 / 130 |
| Median HEX | 50 | 55 |
| Stromal scar | 15% | 0% |
| Endothelial cell dropout | 27% | 12% |
| Epithelial arcus | 70% | 55% |
| Stromal edema / epithelial haze | 6% / 9% | 1% / 3% |

- These differences are clinically plausible reasons for downgrading but are **hypotheses for clinical review**, not explanations of the specialists' grades.
- **Selection effect:** the downgrade tissues were selected because the hybrid predicted the recorded A, so features the model uses differ by construction. A model-free comparison of all tissues graded below the ECD thresholds was not run (possible post hoc work).

## Nested tuning and application model

### 12. Tuned models vs the ECD tree (notebook 13)

A new nested cross-validation analysis. It uses the same outer folds as notebooks 09–12, which influenced earlier decisions, so it is **not an untouched confirmation**. The protocol was not committed separately before execution. Hyperparameters were tuned by 3-fold donor-grouped inner CV within each outer training fold: tabular 24 settings, hybrid 72 (including PCA size and class weighting). The ECD tree was not tuned and reproduced notebook 11 exactly. Evaluated on the 470 tissues with ECD.

| Comparison (macro F1) | Model | Baseline | Difference [95% CI] | Holm p | Folds improved |
|---|---:|---:|---|---:|---:|
| T1: Tuned hybrid − ECD tree | 0.793 | 0.796 | −0.003 [−0.034, +0.029] | 1.00 | 11/25 |
| T2: Tuned tabular − ECD tree | 0.805 | 0.796 | +0.009 [−0.010, +0.028] | 1.00 | 18/25 |
| T3: Tuned hybrid − tuned tabular | 0.793 | 0.805 | −0.012 [−0.045, +0.022] | 1.00 | 8/25 |

- **Neither tuned model convincingly outperformed the ECD tree.** Under the pre-set rule, the **ECD tree was selected for the application**. Tuning did not establish improvement beyond ECD alone.
- **Tuning raised the tabular model by +0.049 macro F1** (higher in 24 of 25 folds) but the hybrid by only +0.005. Every fold in both arms selected `max_features=0.3`, and the tabular arm mostly selected no class weighting.
- **Once the tabular model is tuned, the hybrid's advantage disappears** (−0.012). The hybrid's earlier edge over tabular (notebooks 09–11) was largely due to an under-tuned tabular comparator: the notebook 05 settings. Those results stand as reported but should be read with this context.

**Final application tree** (fitted on all 470 primary-cohort tissues with ECD; recorded grades in each band):

| ECD band (cells/mm²) | Grade | A+ | A | B |
|---|---|---:|---:|---:|
| ≤ 2232 | B | 0 | 0 | 53 |
| 2232–2497 | A | 2 | 84 | 8 |
| > 2497 | A+ | 242 | 75 | 6 |

Six grade B tissues have ECD above 2497 and are graded A+ by the tree. ECD alone cannot identify them, which is why the application presents the grade as decision support requiring specialist confirmation.

### 13. Application integration

- `ml/grading/scripts/train_grading_model.py` rebuilds the tree, checks it against notebook 13 (cohort, cut points, dataset hash) and exports `ml-service/models/grading_ecd_tree.json`. The spec holds cut points and per-band counts only, no tissue-level data.
- `ml-service` grades from an `ecd` request field, never from the cellular placeholder. It returns `review_required` without a grade when ECD is missing, and reports the band's training grade distribution instead of a confidence value, since no calibration was assessed.
- The cellular pipeline now reports `not_implemented` instead of fixed placeholder values.
- Tests check that API grades match the fitted scikit-learn tree, including at the cut points, and that the backend DTOs accept the service's responses.
- The frontend analysis page collects case ID, image URL and optional ECD (validated to the API range). It shows the grade with its ECD band, the band's training grade distribution (labelled as not model confidence) and the specialist-confirmation caveat, or a manual-grading notice when ECD is missing.
- The backend passes `ml-service` validation errors (HTTP 422) through instead of returning 500.
- **End-to-end check:** frontend request contract → backend → `ml-service` from a clean, Dockerfile-equivalent copy (`app/`, `pipelines/`, `models/`, no dev dependencies). Grades at and around both cut points matched the tree. The backend ran with database auto-configuration disabled, since its analysis endpoints do not use the database. A real `docker build` was not run because Docker was not running.

## Limitations

- Donor pairs are inferred from consecutive serial numbers and donor details, not confirmed against a register.
- RF hyperparameters in notebooks 07–12 came from notebook 05 (tabular features, non-grouped CV). Notebook 13 showed these settings disadvantaged the tabular model: tuned within donor-grouped folds, it gained +0.049 macro F1.
- Image features are generic (ImageNet, frozen); a representation adapted to specular microscopy has not been tested.
- 2023 slit-lamp findings are permanently missing; their absence is tied to a subset with a distinct grade pattern.

## Next steps

See `CLAIMS_AUDIT.md` for the claim-by-claim review and the remaining gaps before writing.
