# Cleaned research notebooks: viva guide

**Explainable Multimodal Analysis of Expert Donor Cornea Grading Beyond Endothelial Cell Density (ECD)**

These 15 notebooks are a clean, ordered version of `ml/grading/notebooks/` (notebooks 01–05 and images/01–15), plus one notebook (H10) that documents the scripts in `ml/grading/scripts/`. They keep the code needed to reproduce the essential analyses and drop exploratory, debugging and repeated cells. The original notebooks are unchanged and remain the full record.

- Wherever the original notebooks saved results (cleaned dataset, predictions, fold scores, comparisons, selected settings, image hashes), the cleaned notebook **recomputes them and checks for an exact match**, stopping if anything differs. T2 is descriptive. I2's tabular RF has only a recorded output to compare with, and it matches (0.906).
- **Nothing is written.** The notebooks only read data and results; no dataset, fold file, result CSV or model is created or overwritten.
- Interpretation and claim status follow `../RESULTS.md`, `../CLAIMS_AUDIT.md`, `../FINDINGS.md`, `../ANALYSIS_PLAN.md` and `../MODEL_SELECTION.md`.

## How to run

- **Kernel:** the project environment `ml/.venv` (Python 3.11, scikit-learn 1.9.1, pandas 3.0.6, shap 0.51.0, torch 2.14). Open a notebook from its own folder and run all cells. Paths are found from the notebook's location, so no working-directory setup is needed.
- **Shared code:** `cleaned_setup.py` holds the cohort definitions, feature matrix, model settings and paired statistics that notebooks 06–15 each repeated. It reproduces the original code exactly, including row order, which Random Forest results depend on. `../scripts/modeling_setup.py` is used unchanged.
- **Inputs (git-ignored, must exist locally):**
  - `data/combined_dataset_labeled.xlsx` (Tabular 01 only);
  - `data/processed/cleaned_grading_dataset.xlsx`, `holdout_split.csv`, `donor_grouped_folds.csv`;
  - `image/data/processed/clean_image_manifest.csv`, `duplicate_review.csv`, `images/*.jpg`, `splits/multimodal_shared_split.csv`, `embeddings/resnet50_imagenet_fullres.npz`;
  - the result CSVs in `data/processed/` written by the original notebooks 07–15, used for the reproduction checks.
- **Inputs in git:** `ml-service/models/grading_hybrid_rf.{joblib,json}` and `grading_ecd_tree.json` (Hybrid 09).
- **Network:** torchvision downloads the ImageNet ResNet-50 (Hybrid 01) and ResNet-18 (Images 02, optional) weights on first use, if they are not cached.

## Status labels

| Label | Meaning |
|---|---|
| **Superseded** | Earlier design that split fellow eyes across partitions (V0, V1). Shown to explain the history; not a performance estimate |
| **Pre-specified** | Protocol committed to git before the analysis code (notebooks 09–11) |
| **Planned** | Settings fixed before running but not committed separately (07–08, 13–15) |
| **Follow-up** | Motivated by an earlier result on the same folds (11, 14, 15); not independent confirmation |
| **Exploratory / diagnostic** | Descriptive, no hypothesis tests (12; 06 and 08 §10) |

## The ECD rule and the 24 features in brief

**ECD grading rule:**

| ECD (endothelial cells per mm²) | Grade by ECD alone |
|---|---|
| below 2250 | B |
| 2250 to below 2500 | A |
| 2500 and above | A+ |

- Notebook 03's early EDA used a **wrong** rule (2000 / 2500 / 3000) that matched only ≈28–30% of recorded grades. The 2250 / 2500 rule matches 87.7% (T2 §6). Every analysis from notebook 08 onward uses the correct rule (`cleaned_setup.ecd_rule`).
- The analysis documents report it descriptively, without tests, because no written copy of the criteria was available. The tested ECD baseline is a depth-2 tree fitted in the training folds; it learns almost the same cut points from the labels (≈2232 / ≈2497).
- **Cite the source of the rule in the viva.**

**The 24 features** (plain-language table with recording rates in T2 §2):

- **6 Konan specular-microscope measurements of the endothelium.**
  - ECD: cells per mm², the main grading measure.
  - CV and SD: how unequal the cell sizes are.
  - HEX %: share of regular six-sided cells.
  - Cell count and analysed area: ECD = count ÷ area.
  - Recorded for 91% of tissues.
- **18 slit-lamp findings by corneal layer**, recorded for about 55% of tissues (none in 2023), each as yes / no / not recorded.
  - Stroma: clear, compact, arcus (with severity), oedema, scar.
  - Epithelium: arcus, defect, exposure (with severity), haze.
  - Endothelium: stress lines (with location), red blood cells, cell dropout.
  - Descemet's membrane: folds, fold severity, relative number of folds.
- Not recorded is never treated as "no".

## Cohorts and validation designs

| ID | Cohort | Tissues | Grades A+ / A / B |
|---|---|---:|---|
| K1 | All labelled | 1,036 | 545 / 319 / 172 |
| K2 | With a usable image | 1,009 | 530 / 314 / 165 |
| K3 | **Primary cohort:** K2 with `Tissue_ID` year ≠ 2023 (312 donors) | 551 | 277 / 196 / 78 |
| K4 | **Evaluation set:** K3 with ECD (280 donors) | 470 | 244 / 159 / 67 |
| K5 | K3 without ECD (no Konan values at all) | 81 | 33 / 37 / 11 |

- **V0:** 80/20 row-level holdout. Superseded.
- **V1:** 70/15/15 row-level shared split. Superseded.
- **V2:** 5 repeats × 5 donor-grouped stratified folds (`donor_grouped_folds.csv`). Current design. Tuning (06–08) adds 3-fold donor-grouped inner CV inside each outer training fold.

**Compare numbers only within one cohort and design.**

## Execution order and index

Run top to bottom. Each notebook is self-contained, so any one can be opened alone during the viva. Runtimes were measured on this machine (12 CPU cores, RTX 3050) with the default settings.

| # | Notebook | Question it answers | Derived from | Runtime |
|---|---|---|---|---:|
| T1 | `tabular/01_data_cleaning_and_grades.ipynb` | How were grades resolved and findings parsed, keeping "not recorded" ≠ "No"? Rebuilds the cleaned dataset in memory: 0 of 25 columns differ from the saved file | 01, 02 | 15 s |
| T2 | `tabular/02_eda_and_ecd_thresholds.ipynb` | How were the 24 features selected from 116 columns? What do the grades and features look like; how closely do grades follow ECD thresholds? | 02 (feature-role audit), 03, 04 (candidate audit), FINDINGS §7, images/08 §10 | 20 s |
| T3 | `tabular/03_preliminary_models_and_superseded_holdout.ipynb` | How was the tabular Random Forest chosen, and why is the 0.861 holdout optimistic? (**superseded**) | 04, 05 | 1 min |
| I1 | `images/01_image_validation.ipynb` | Are the images intact, uniform and correctly linked to their grades? | images/01–03 | 35 s |
| I2 | `images/02_superseded_shared_split_baselines.ipynb` | First multimodal attempt: CNN, ResNet-18, neural fusion, tabular RF on one shared split (**superseded**). The networks show recorded results unless `TRAIN_NEURAL_MODELS = True`; a test retrain gave CNN 0.412, fusion 0.788, ResNet-18 0.394 test macro F1 (recorded: 0.371, 0.818, validation-only 0.418), which does not change the conclusions | images/02–05 | 20 s (≈11 min with `TRAIN_NEURAL_MODELS = True`, GPU) |
| H1 | `hybrid/01_multimodal_alignment_and_image_embeddings.ipynb` | How are records and images aligned; how does the frozen ResNet-50 + PCA image branch work? | images/03, 07 | 30 s |
| H2 | `hybrid/02_donor_leakage_audit_and_grouped_folds.ipynb` | Does any feature leak the grade? How was donor leakage found and corrected? | images/06 | 2 min |
| H3 | `hybrid/03_all_years_missing_information_and_2023.ipynb` | Do images help (all years, missing information)? Why were 2023 tissues excluded? | images/07, 08 | 3 min |
| H4 | `hybrid/04_primary_cohort_beyond_ecd.ipynb` | Non-2023: image vs tabular; models vs ECD-only RF and vs fitted ECD tree | images/09, 10, 11 | 1 min |
| H5 | `hybrid/05_threshold_departure_shap.ipynb` | What is associated with the hybrid's departures from the ECD thresholds? (SHAP) | images/12 | 1 min |
| H6 | `hybrid/06_nested_tuning_primary_comparison.ipynb` | Tuned tabular and hybrid vs ECD tree; the pre-set selection rule | images/13 | 3 min (≈72 min full) |
| H7 | `hybrid/07_model_family_comparison.ipynb` | Does another model family beat the RF hybrid? (follow-up) | images/14 | 1 min (≈42 min full) |
| H8 | `hybrid/08_extended_hybrid_tuning.ipynb` | Does a wider PCA / `max_features` search help? (follow-up) | images/15 | 2 min (≈12 min full) |
| H9 | `hybrid/09_final_model_selection.ipynb` | Which model is deployed, how was it built, and why the hybrid? | MODEL_SELECTION.md, `scripts/train_hybrid_grading_model.py`, `ml-service` | 2.5 min |
| H10 | `hybrid/10_scripts_and_application_artefacts.ipynb` | What does each script in `scripts/` do, and are its saved outputs (image set, feature schema, ECD tree spec, domain validator) consistent with the data? Read-only: runs no script | `scripts/*.py`, `ml-service/models/` | 15 s |

**The scripts** (details and checks in H10). Pipeline order:

1. `extract_sp_images.py`, `audit_sp_images.py`, `prepare_image_dataset.py`: build the one-image-per-tissue set (1,024).
2. `modeling_setup.py`: the shared features, preprocessing, donor inference and folds.
3. `export_feature_schema.py`: input validation for the app.
4. `train_grading_model.py`: the ECD reference tree.
5. `train_hybrid_grading_model.py`: the deployed hybrid.
6. `train_domain_validator.py`: the "is this a specular image?" gate.

**Every script except `modeling_setup.py` writes or overwrites files** (git-ignored data, or the deployed artefacts in `ml-service/models/`), so the notebooks never run them. H9 re-runs the hybrid training in memory only.

**Long experiments (H6–H8).** By default each re-runs **one complete outer fold** live, checks it against the saved fold scores and selected settings, then recomputes every statistic from the saved 25-fold scores. Set `RUN_FULL_NESTED_CV`, `RUN_FULL_FAMILY_COMPARISON` or `RUN_FULL_EXTENDED_TUNING` to `True` to recompute all 25 folds in memory.

## Key results

Fold-level mean ± SD over 25 folds unless stated. All values were recomputed in these notebooks and match `RESULTS.md`. The documents round 4-decimal values to 3 decimals; for example, T1 is −0.0025, shown as −0.003.

**Primary comparison** (K4, nested CV; H6):

| Model | Macro F1 | Accuracy | Balanced accuracy | Grade B recall |
|---|---:|---:|---:|---:|
| Fitted ECD tree (depth 2) | 0.796 ± 0.038 | 0.804 ± 0.031 | 0.768 ± 0.043 | 0.790 ± 0.117 |
| Tuned tabular RF | 0.805 ± 0.034 | 0.809 ± 0.030 | 0.781 ± 0.037 | 0.793 ± 0.115 |
| Tuned hybrid RF (**deployed**) | 0.793 ± 0.047 | 0.797 ± 0.040 | 0.775 ± 0.050 | 0.789 ± 0.130 |

**Paired comparisons** (H6): macro F1, corrected 95% CI, Holm.

- Hybrid − tree: −0.003 [−0.034, +0.029].
- Tabular − tree: +0.009 [−0.010, +0.028].
- Hybrid − tabular: −0.012 [−0.045, +0.022].
- All Holm p = 1.00. **No model beat the ECD tree.**

**Per-grade results** (H6, pooled over the 5 repeats, precision / recall):

| Model | A+ | A | B |
|---|---|---|---|
| ECD tree | 0.748 / 0.988 | 0.884 / 0.528 | 1.000 / 0.791 |
| Tuned tabular | 0.779 / 0.943 | 0.805 / 0.609 | 0.978 / 0.794 |
| Tuned hybrid | 0.788 / 0.906 | 0.761 / 0.635 | 0.936 / 0.791 |

**Follow-ups on the same folds** (not independent confirmation):

- **Extended hybrid** (H8): macro F1 0.802, accuracy 0.803, grade B recall 0.793. Against the deployed hybrid: +0.008 [−0.016, +0.033], p = 0.48. **Inconclusive.**
- **Model families** (H7): gradient boosting is indistinguishable from the RF hybrid. Logistic regression, the RBF SVM and Extra Trees are worse (−0.07 to −0.12, Holm p ≤ 0.027). None beat the ECD tree.

**History of the estimate** (different cohorts and designs, so not directly comparable):

| Step | Value | Notebook |
|---|---|---|
| V0 holdout, K1 | 0.861 | T3 |
| Same RF, donor-grouped V2, K1 | 0.844 | H2 |
| All years, K2 | Tabular 0.849, hybrid 0.859; tabular by year: 2023 0.99 vs other years 0.73 | H3 |
| Non-2023, untuned, K3 | Tabular 0.711, hybrid 0.748 (inconclusive) | H4 |
| K4, untuned vs ECD tree | Tabular 0.756, hybrid 0.789, tree 0.796 | H4 |
| K4, tuned | Tabular 0.805, hybrid 0.793 | H6 |

**Explainability** (H5, exploratory):

- The hybrid recovers 131 of 445 downgrade pairs (29%) but departs wrongly in 151.
- The image contribution is large in **both** directions, so it shows model reliance, not demonstrated signal.
- Endothelial variability (CV, SD) is the most consistent association with correct downgrades, and stromal findings a smaller one.

**Deployed model** (H9):

- PCA 32 + RF (`min_samples_leaf=1, max_depth=15, max_features=0.3`, no class weighting), trained on all 551 K3 tissues.
- `ml-service/models/grading_hybrid_rf.joblib`: the SHA-256 is verified, and re-running the deployment tuning in memory selects the same setting and gives identical predictions.
- **Chosen by project decision after the pre-set rule selected the ECD tree.**

## Viva guide

| Question | Open | Short answer |
|---|---|---|
| Why did earlier accuracy estimates decrease? | T3 §6, H2 §3, H3 §6, H4, H6 | Each drop removes an optimistic element: fellow-eye leakage (0.861 → 0.844); the pooled near-perfect 2023 subset (0.99 vs 0.73); then honest nested tuning on the non-2023 cohort. The model did not get worse; the estimate got stricter. See "History of the estimate" |
| How was donor leakage identified and corrected? | H2 | Fellow eyes share a grade 77.9% of the time (chance 39.9%). 78/258 (V0) and 108/239 (V1) pairs were split. Donors were inferred from consecutive serials + donor details; all later work uses donor-grouped folds (verified, regenerated from seeds) and grouped inner folds |
| What do the 24 features mean? | T2 §2 (feature guide), README "The ECD rule and the 24 features in brief" | 6 Konan endothelial measurements (density, cell-size variation, cell shape, count, area) and 18 slit-lamp findings across stroma, epithelium, endothelium and Descemet's membrane, each yes / no / not recorded |
| Why is the ECD rule 2250 / 2500 and not what notebook 03 used? | T2 §6 | The rule is B below 2250, A from 2250 to below 2500, A+ from 2500. Notebook 03's 2000 / 2500 / 3000 rule was wrong (28% agreement vs 87.7%) and was never used in any model or comparison |
| How were the 24 features selected? | T2 §2, T1, T3 §2 | Every column got a role. Leakage/downstream fields (e.g. suitability, `Additional_Findings` quoting grades), identifiers, recipient/surgery context and the duplicate form ECD were excluded. Of the candidates, the 6 Konan measurements and 18 of 24 parsed slit-lamp findings were kept; 4 sparse severity/type details and 2 categorical fields with categories seen in 2–5 tissues were dropped. Donor age was a candidate but was never evaluated; no reason is recorded |
| Why were 2023 tissues excluded? | H3 §1, §6; T2 §5–6 | All 2023 tissues lack slit-lamp findings (unrecoverable), so a multimodal analysis is impossible there. Their grades also follow ECD thresholds in 95% of tissues vs 72–84%. Decided after seeing results (disclosed, Amendment 1) |
| Why a hybrid Random Forest? | H9 §6, H7, T3 §3 | RF ranked first in early comparisons and again under nested donor-grouped tuning (only gradient boosting matched it). The hybrid was chosen for multimodality and explainability, not for accuracy |
| How does the image branch work? | H1 §2–4, H9 §3, §5 | Full-resolution greyscale → frozen ImageNet ResNet-50 → 2048-d average-pooled embedding → standardise → PCA (fitted per training fold) → joined with the 24 features in one RF. In the app, the same backbone runs as ONNX |
| Why PCA? | H1 §4, H3 §4, H8 §4 | 2048 dimensions vs ~440 training tissues per fold. PCA is unsupervised, fitted inside each training fold, and was tuned (8–128). 32 was chosen most often; 128 never |
| What does the ECD tree tell us? | H4 §5, H6 §5 | Recorded grades are anchored at ECD ≈2232 and ≈2497 in every fold, close to the eye bank's 2250 / 2500 rule. The tree matches the ML models (0.796) but finds only half of grade A, and cannot flag 6 grade B tissues above 2497 |
| What did SHAP reveal? | H5 | Departures from ECD are right about as often as wrong. The image group dominates both directions (reliance, not signal). Variability and stromal findings are consistent associations, as hypotheses for clinical review. SHAP describes the model, not causation |
| Why did further tuning not establish an improvement? | H6, H8 | Three tuning analyses on the same folds all land at ≈0.79–0.80. +0.008 [−0.016, +0.033], p = 0.48 is within noise, and every reuse of the folds raises chance findings |
| Why the hybrid if its accuracy is slightly lower? | H9 §2, §6 | The differences are not significant. The hybrid uses all three evidence sources, can depart from the thresholds with the ECD tree shown beside it, and explains each case. It is an explicit project decision after the rule picked the tree; on accuracy and simplicity alone the tree or tabular model would win |
| What do the scripts do? How does the app reject non-corneal images? | H10 | Three scripts built the image set; the rest export the schema, the ECD reference tree, the hybrid and the domain validator. The validator (frozen ResNet-18 + logistic regression, thresholds set on validation data) accepted 0 of 1,295 non-corneal test images and 197 of 197 specular images. It also accepts blurred specular images: it checks the kind of image, not its quality |
| Main limitations and next steps? | H9 (end) | Inferred donors; reused folds; no external, prospective or other-microscope validation; generic image features; post-hoc cohort and model choices; uncalibrated vote shares. Next: new independently graded tissues, microscopy-specific image features, a pre-specified search above `max_features` 0.7 |

## What was removed or consolidated

- **Tabular 01–05:**
  - Removed: exploratory printouts; repeated `value_counts`, plots and imports; recipient, graft-size and request cleaning (not grading features); the wrong early ECD rule (2000/2500/3000, ≈30% agreement; replaced by the eye bank's 2250/2500 rule and compared with it in T2 §6); intermediate logistic-regression baselines; error-analysis case listings with tissue details; the training-set SHAP plots of notebook 05 (superseded by H5).
  - Kept: the essential cleaning code, the ablation, model comparison and tuning code, and the superseded holdout (labelled as such).
- **Image notebooks 01–05:** debugging cells and repeated training loops were merged into one dataset class, three architectures and one training function. Notebook 02's class-weighted and 448-pixel CNN variants are summarised, not retrained.
- **Hybrid 06–15:**
  - The protocol text is condensed to the design, the search spaces and the selection rules.
  - The cohort, feature-matrix and statistics code that each notebook repeated is now in `cleaned_setup.py`.
  - Removed: printed hashes beyond the inputs that matter, tissue-level outputs and long selection listings. The pandas `value_counts` miscount of `None` selections (notebooks 13 and 15) is corrected in place.
  - Per-year leave-one-year-out tables of notebooks 09–11 are dropped; their qualifiers were not triggered.

## Issues found during the cleanup (unresolved; originals unchanged)

1. **"None" categories read as missing.** In `cleaned_grading_dataset.xlsx`, `Endo_Stress_Line_Location`, `Stroma_Arcus_Severity` and `Epi_Exposure_Severity` store "recorded, finding absent" as the string `"None"`. `pd.read_excel` (used by `modeling_setup.load_labelled_data`) treats it as missing. So in all models, 63 / 102 / 271 "absent" values were merged with "not recorded" for these three features.
   - The paired binary flags keep the distinction, and the deployed schema matches training.
   - Fixing it would change every result, so it is documented (T1 §6) rather than changed.
2. **One blank image.** One image in the manifest is constant white. Its tissue (grade A, no Konan values) is in K2 and K3, so it was in the training folds and in the deployed model's training data, but not in the K4 evaluation set (I1 §2).
3. **Stale output in notebook 01.** Notebook 01's saved output shows an older version of the raw dataset ("Labelling part 2", rule-predicted grades). The current file contains only eye-bank-form grades (T1).
4. **One SD value without a recorded source.** Notebook 02 set SD = 229 for one tissue without recording where the value came from (T1 §2).
5. **Scripts with absolute paths.** `extract_sp_images.py`, `audit_sp_images.py` and `prepare_image_dataset.py` hard-code Windows paths, including the raw image folder outside the repository. They cannot be re-run elsewhere without editing (H10 §1).
6. **Outdated schema description.** `grading_feature_schema.json` still lists `deployed_model_uses: ["ECD_CD_cells_per_mm2"]`, which dates from before Amendment 2. The features, categories and ranges themselves match the training data (H10 §2).
7. **Redundant review-ID filter.** The two tissues with conflicting duplicate images are already left out of `clean_image_manifest.csv` by `prepare_image_dataset.py`. The extra `REVIEW_IDS` exclusion in the notebooks changes nothing; K2 = 1,024 − 15 unlabelled = 1,009 (I1, H10).
8. **Last-digit rounding.** A few means fall on a rounding boundary, so the last digit can differ by 0.001 from `RESULTS.md`. For example, image-only accuracy 0.5045 prints as 0.504 here and as 0.505 there.
