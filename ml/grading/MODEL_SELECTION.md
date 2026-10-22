# Model Selection: Application Grading Model

Final decision on the model behind the application's donor cornea grade, and the reasons for it. All figures come from existing results (`RESULTS.md`, including notebook 14's model family comparison); no models were rerun for this document. The decision history is in `ANALYSIS_PLAN.md` (section D and Amendment 2), and the claim status of each result is in `CLAIMS_AUDIT.md`.

## 1. Decision

**Selected model: the tuned hybrid Random Forest.**

- **Inputs:** the 24 recorded features (6 Konan morphology measurements, 18 slit-lamp findings) plus the specular microscopy image.
- **Image representation:** frozen ResNet-50 (ImageNet) embedding, reduced to 32 PCA components.
- **Forest settings:** `min_samples_leaf=1, max_depth=15, max_features=0.3`, no class weighting, chosen by donor-grouped inner CV on the primary cohort (K3, 551 non-2023 tissues).
- **Artefacts:** `ml-service/models/grading_hybrid_rf.joblib`, trained by `scripts/train_hybrid_grading_model.py`.

The fitted ECD tree (cut points 2232 / 2497) is computed for every case and shown next to the hybrid's grade as a reference.

**This is a project decision, not the result of the pre-set selection rule.** Notebook 13's rule chose the ECD tree. The hybrid was chosen afterwards, with that result known (Amendment 2). Section 5 states what this means.

## 2. Candidates and evidence

All three candidates were evaluated on the same 470 primary-cohort tissues that have ECD (K4). The design was nested 5 × 5 donor-grouped cross-validation, with 3-fold donor-grouped tuning inside each outer training fold (notebook 13).

| Model | Inputs | Macro F1 | Balanced accuracy | Accuracy | Grade B recall |
|---|---|---:|---:|---:|---:|
| ECD tree (depth 2) | ECD | 0.796 ± 0.038 | 0.768 ± 0.043 | 0.804 ± 0.031 | 0.790 ± 0.117 |
| Tuned tabular RF | 24 features | 0.805 ± 0.034 | 0.781 ± 0.037 | 0.809 ± 0.030 | 0.793 ± 0.115 |
| **Tuned hybrid RF** | 24 features + image | 0.793 ± 0.047 | 0.775 ± 0.050 | 0.797 ± 0.040 | 0.789 ± 0.130 |

| Comparison (macro F1) | Difference [95% CI] | p (Holm) |
|---|---|---:|
| Tuned hybrid − ECD tree | −0.003 [−0.034, +0.029] | 1.00 |
| Tuned tabular − ECD tree | +0.009 [−0.010, +0.028] | 1.00 |
| Tuned hybrid − tuned tabular | −0.012 [−0.045, +0.022] | 1.00 |

**What the evidence supports:**

- No candidate was shown to grade better than another. All three are within about 0.01 macro F1, and every interval includes zero.
- The intervals limit how much worse the hybrid could plausibly be:
  - compared with the ECD tree, a loss of more than 0.034 macro F1 is unlikely;
  - compared with the tuned tabular model, a loss of more than 0.045 is unlikely.
- No equivalence margin was set in advance, so this is **not** a formal non-inferiority result.

**What it does not support:** any claim that the hybrid grades more accurately than ECD alone or than the tabular model (`CLAIMS_AUDIT.md`: T6, T8, I8, A5).

### 2.1 Other model families (notebook 14, follow-up)

Notebook 14 asked whether another model family, tuned the same way, could grade better than the deployed hybrid.

- **Candidates:** gradient boosting, logistic regression, RBF SVM and Extra Trees, each as tabular and hybrid.
- **Validation:** the same nested donor-grouped design on the same outer folds. It is therefore a follow-up, not independent confirmation.
- **Selection rule, fixed before execution:** replace the deployed model only if a candidate convincingly outperforms it.

| Model | Macro F1 | Accuracy | Grade B recall | Kappa (quadratic) | vs tuned RF hybrid (macro F1) |
|---|---:|---:|---:|---:|---|
| **Tuned RF hybrid** (deployed) | 0.793 | 0.797 | 0.789 | 0.764 | — |
| Gradient boosting hybrid | 0.792 | 0.788 | 0.796 | 0.764 | −0.001 [−0.041, +0.038], inconclusive |
| Gradient boosting tabular | 0.785 | 0.782 | 0.806 | 0.753 | −0.009 [−0.046, +0.029], inconclusive |
| Extra Trees hybrid | 0.724 | 0.754 | 0.717 | 0.737 | −0.069, worse (Holm p 0.027) |
| RBF SVM tabular | 0.715 | 0.731 | 0.673 | 0.699 | −0.078, worse (Holm p 0.027) |
| Logistic regression tabular | 0.698 | 0.709 | 0.690 | 0.675 | −0.095, worse (Holm p 0.027) |

The remaining arms (Extra Trees tabular, SVM hybrid, logistic regression hybrid) were also worse. Full results are in `RESULTS.md`, R6c.

**Outcome:** no candidate convincingly outperformed the deployed model, so **under the pre-set rule the tuned RF hybrid is retained**. Gradient boosting reached the same level. Logistic regression, the SVM and Extra Trees were clearly worse. No family beat the ECD tree.

### 2.2 Extended tuning of the hybrid (notebook 15, follow-up)

**Motivation:** notebook 13's selections reached the edge of its grid: `max_features` 0.3 was chosen in 25/25 folds and PCA 32 in 16/25.

**Design:** notebook 15 extended the search to 48 settings: PCA up to 128, `max_features` up to 0.7. It used the same preprocessing and nested design, with a selection rule fixed before execution.

| Model | Macro F1 | Accuracy | Kappa (quadratic) |
|---|---:|---:|---:|
| Tuned RF hybrid (deployed) | 0.793 | 0.797 | 0.764 |
| Extended RF hybrid | 0.802 | 0.803 | 0.770 |

**Outcome:**

- The difference is +0.008 [−0.016, +0.033], p = 0.48: **inconclusive**.
- Under the rule, **the deployed model is retained**. A higher point estimate on folds already used for two earlier tuning analyses is not a reason to replace it.
- PCA 128 was never selected.
- `max_features` 0.7 was selected in 13/25 folds, so further search above it is listed as future work. It should be evaluated on new tissues.

## 3. Reasons for the hybrid

Performance does not separate the candidates, so the choice rests on what each model offers the specialist using it. Each reason is stated with its limitation.

### 3.1 It uses every source of evidence the specialist uses

Specialists grade from endothelial morphology, slit-lamp findings and the specular image. The hybrid is the only candidate that takes all three, which matches the project objective of a multimodal grading model.

**Limitation:** a measurable benefit from the image was not shown. Adding image features did not significantly change performance in any analysis (I4, I7, T3).

### 3.2 The ECD tree adds nothing beyond the thresholds and cannot flag departures from them

The ECD tree is a restatement of two cut points; a specialist can read the grade off the ECD value directly. By construction it can never predict a grade that departs from them. In its own training data:

- 75 grade A tissues and 6 grade B tissues lie in the band above 2497, where the tree always predicts A+;
- 8 grade B tissues lie in the A band.

The hybrid can depart from the thresholds. In notebook 12, with the untuned hybrid:

- it recovered 131 of 445 downgrade pairs (29%) that the tree missed;
- it made 151 incorrect departures.

So its departures were right about as often as wrong. Variability (CV, SD) and stromal findings were the most consistent associations with the correct downgrades (exploratory, X4–X5). With the ECD tree shown beside it, a disagreement between the two tells the specialist to look more closely at the case.

### 3.3 It gives a per-case explanation over all inputs

For each case, the application shows:

- TreeSHAP contributions for the 24 inputs and the image (`ml-service/pipelines/grading/explain.py`);
- a map of the image regions that raised or lowered the grade's share of votes.

This supports the project's explainability objective. The ECD tree's only explanation is the band the ECD value falls in.

**Limitation:**

- The explanations describe the model, not the cornea.
- The image map's faithfulness has not been evaluated.
- In notebook 12 the image contribution was large in both correct and incorrect departures (X3).

### 3.4 It still produces a grade when ECD is missing

81 of the 551 primary-cohort tissues (15%) have no Konan measurements. The ECD tree cannot grade them. The hybrid can, and the application marks these cases for review.

**Limitation:** performance on these tissues is poor. With the untuned models of notebook 10, macro F1 was 0.468 and grade B recall was 0.164 (R5). The output for these cases is a suggestion for review, not a usable grade.

## 4. Why not the alternatives

**ECD tree.** It is the simplest model, and the pre-set rule selected it. It is kept as the reference shown beside every grade, which preserves its value. Serving it as the main grade would bring three drawbacks:

- it would only repeat the thresholds;
- it could not grade 15% of the primary cohort;
- it would give the explainability component nothing to explain beyond the threshold.

**Tuned tabular RF.** It is numerically the best model (+0.012 macro F1 over the hybrid, not significant), and it is simpler: it needs no image backbone. It was not chosen because it drops the image, which is one of the three sources in the project's multimodal objective, and with it the image explanation. **On performance and simplicity alone, the tabular model or the ECD tree would be the choice.** This trade-off was made deliberately and should be stated as such.

**Gradient boosting.** It grades at the same level as the Random Forest (−0.001), but it is not better. Switching would need a new export, new parity tests and new explanation code for no demonstrated gain. Under notebook 14's rule it is not a replacement.

**Logistic regression, RBF SVM, Extra Trees.** All were significantly worse than the Random Forest hybrid and the ECD tree (−0.07 to −0.12 macro F1, notebook 14).

## 5. Limitations of the decision

- **Choice made after the rule's result was known.** The pre-set rule selected the ECD tree. The hybrid was chosen afterwards by project decision (Amendment 2). The rule is not re-run or reinterpreted.
- **Estimate not independent of earlier decisions.** The outer folds of notebook 13 had already informed earlier analyses. The performance estimate for the selected model (macro F1 0.793 ± 0.047) is therefore not an untouched confirmation.
- **Uncalibrated vote shares.** The hybrid's tree-vote shares have not been calibrated and are shown as vote shares, never as confidence (A6).
- **Generic image features.** The ResNet-50 features are general-purpose. A representation adapted to specular microscopy has not been tested (G6).
- **Untested beyond the training data.** The model has not been evaluated on tissues graded after the dataset, on 2023-type records, or on images from other microscopes.

## 6. Safeguards in the application

- **Grades are decision support** and require specialist confirmation.
- **Review flags.** A case is marked for review when:
  - any input is outside its training range;
  - ECD is inconsistent with cell count and area;
  - the image is not 1296 × 972;
  - the ECD reference cannot be computed.
- **Missing inputs are visible.** Inputs that were not recorded are listed with the result. They are handled as in training and never read as zero or "No".
- **Non-specular images are rejected** before any grade is produced. The domain validator accepted 0 of 1,295 held-out non-corneal images.
- **Model integrity is checked at load:**
  - the model file against its SHA-256;
  - the image backbone against its recorded reference output.

## 7. What would change the decision

- **A new evaluation on independently graded tissues** in which the hybrid underperforms the ECD tree or the tabular model by a clinically relevant margin. The margin should be agreed with NEBSL before the evaluation.
- **Specialist review finding the explanations unhelpful or misleading.** The main non-performance reasons for the hybrid (3.2, 3.3) would then no longer hold, and the tuned tabular model would be the better choice.

## 8. Summary

All three candidates graded equally well within the precision of this dataset. A follow-up comparison of four further model families (notebook 14) found none better than the deployed Random Forest hybrid: gradient boosting matched it, and the others were worse. Extending the hybrid's own search (notebook 15) gave +0.008 macro F1, which is inconclusive, so the deployed model is unchanged. The hybrid was chosen because it uses all three sources of evidence, can depart from the ECD thresholds and explain why, and can still give a suggestion when ECD is missing. The ECD tree is kept beside it as a reference. This is a design choice, not a demonstrated gain in accuracy: on performance and simplicity alone, the ECD tree or the tabular model would be preferred.
