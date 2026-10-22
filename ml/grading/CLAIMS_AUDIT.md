# Claims Audit: Notebooks 01–15

Purpose: decide what the paper can claim before writing the methodology and results. Each claim is traced to its source notebook and rated against the later evidence.

**Status key**

- **Supported:** can be reported as a result, with the stated qualifiers.
- **Qualified:** reportable only with the stated limitation.
- **Superseded:** replaced by a later, more rigorous analysis; mention only as a preliminary baseline, if at all.
- **Not supported:** do not claim.

## 1. Claim-by-claim review

### Data and evaluation

| # | Claim | Source | Status | Notes |
|---|---|---|---|---|
| D1 | 1,036 labelled tissues; 1,009 with a usable image | 02, images/01, images/03 | Supported | |
| D2 | No tabular feature directly encodes the grade | 06 | Supported | `Additional_Findings` contains grades and is excluded |
| D3 | Fellow eyes from one donor share a grade far more often than chance (77.9% vs 39.9%) | 06 | Supported | Donors inferred from consecutive serials and donor details, not a register |
| D4 | Earlier splits separated fellow eyes; donor grouping lowers the tabular estimate (0.858 → 0.844) | 06 | Supported | |
| D5 | Slit-lamp findings are missing for all 2023 tissues and almost none from other years | 08, 09 | Supported | Year from `Tissue_ID` |
| D6 | Recorded 2023 grades agree with ECD thresholds 2250/2500 for 95% of tissues vs 72–84% in other years | 08 | Supported as a description | The thresholds were identified by inspecting 2023 data. Do not claim why the pattern arose |
| D7 | ECD is derived from cell count and area; CV is effectively SD over mean cell area | Audit | Supported | Six Konan features ≈ four independent quantities |

### Tabular model performance

| # | Claim | Source | Status | Notes |
|---|---|---|---|---|
| T1 | Random Forest outperformed LR, SVM and Extra Trees | 05, 14 | Supported (follow-up) | Notebook 05 used non-grouped CV. Re-checked in notebook 14 with donor-grouped nested tuning: all six LR, SVM and Extra Trees arms were worse than the tuned RF hybrid (−0.069 to −0.115 macro F1; Holm p ≤ 0.027) and than the ECD tree. Reuses the notebook 13 folds; not independent confirmation |
| T2 | Tuned RF holdout macro F1 0.861 | 05 | Superseded | 78 donor pairs split across holdout; the holdout informed earlier decisions. Use 06/07 |
| T3 | Tabular RF macro F1 0.906 on the shared split | images/05 | Superseded | Single 152-tissue split, 108 donor pairs split, no uncertainty. Use 07 |
| T4 | Tabular RF macro F1 0.844 (all 1,036) / 0.849 (image cohort), donor-grouped 5×5 CV | 06, 07 | Qualified | Hyperparameters tuned in 05 with non-grouped CV on overlapping tissues. Pooled figure averages 2023 (0.99) and other years (0.73); always report by year |
| T5 | Morphology outperforms ECD alone; adding ECD changes nothing | 04 | Qualified | Morphology features contain ECD implicitly (count / area). Reframe as "the full Konan feature set outperforms ECD alone" |
| T6 | The ML models add value beyond ECD alone | 10, 11 | **Not supported** | Pre-specified (10): Tabular and Hybrid beat an ECD-only Random Forest (+0.048, +0.081; Holm p 0.030, 0.006), but that comparator was weak. Follow-up (11): neither beat a depth-2 ECD tree fitted within training folds (Tabular −0.040, Hybrid −0.007; inconclusive). Report both; claim only that the models outperform an ECD-only Random Forest |
| T7 | Recorded grades are anchored at ECD ≈ 2230 and ≈ 2500 across years | 11 | Supported as a description of the labels | Tree fitted on non-2023 tissues recovered cut points 2232 and 2494–2503 in all 25 folds. Not evidence of a single official protocol, nor of why tissues depart from the thresholds |
| T8 | A tuned tabular model outperforms ECD alone | 13 | **Not supported** | Nested CV: +0.009 [−0.010, +0.028] over the fitted ECD tree, Holm p = 1.00. Tuning raised it by +0.049 over the notebook 05 settings |
| T9 | Gradient boosting grades as well as or better than the Random Forest | 14 | **Not supported as "better"**; not distinguishable | Gradient boosting hybrid − RF hybrid −0.001 [−0.041, +0.038], tabular −0.009 [−0.046, +0.029], Holm p = 1.00. No equivalence margin was set, so "as well as" cannot be claimed formally either |
| T10 | Another model family outperforms ECD alone | 14 | **Not supported** | None of the 8 candidate arms beat the ECD tree. Gradient boosting was inconclusive (−0.011, −0.004; Holm p 0.86); the other six arms were worse (Holm p ≤ 0.017). Extends T6 and T8 across five model families |
| T11 | Quadratic-weighted kappa with the recorded grades is about 0.76–0.78 for the best models | 14 | Supported as a description | Fold-mean kappa: ECD tree 0.771, tuned RF tabular 0.783, tuned RF hybrid 0.764, gradient boosting hybrid 0.764. This measures agreement with one recorded grade per tissue, not inter-rater reliability, which was not measured |

### Image and hybrid models

| # | Claim | Source | Status | Notes |
|---|---|---|---|---|
| I1 | A CNN trained from scratch (and a partly fine-tuned ResNet-18) on 224-pixel images performs poorly (macro F1 0.33–0.48) | images/02, images/04 | Qualified | Shows these configurations failed, not that images are uninformative. Non-grouped splits |
| I2 | The neural multimodal model underperformed tabular RF (0.818 vs 0.906) | images/05 | Superseded | Confounds fusion with MLP vs RF; non-grouped split. Use 07 |
| I3 | Frozen ResNet-50 embeddings carry some grade information (image-only macro F1 0.44) | 07 | Supported | Most of it plausibly overlaps with the Konan measurements; not tested directly |
| I4 | Adding frozen embeddings does not significantly improve the full-feature model (+0.010, CI −0.012 to +0.031) | 07 | Supported | Not robust to PCA size; grade B recall fell 0.851 → 0.819 |
| I5 | Images help when slit-lamp findings are missing | 08 | **Not supported** | C1 is confounded with 2023; C3 is a masking artefact with lower grade B recall; C5 (cleanest) shows no gain |
| I6 | Images can substitute for Konan measurements | 08 | **Not supported** | Both arms collapse (C4); hybrid B recall 0.04 |
| I7 | On non-2023 tissues the hybrid improves macro F1 (+0.038, CI −0.013 to +0.088) | 09 | Qualified: **inconclusive** | Pre-specified sensitivity analysis, not independent of the exploratory 08 result. Direction positive in all repeats and years. Notebook 13: once the tabular model is tuned in nested CV, the hybrid is slightly worse (−0.012, Holm p = 1.00), so the earlier positive direction was largely due to an under-tuned tabular comparator |
| I8 | Tuning the hybrid makes it outperform the ECD tree or the tuned tabular model | 13 | **Not supported** | Nested CV: hybrid − ECD tree −0.003; hybrid − tuned tabular −0.012; both Holm p = 1.00. Tuning raised the hybrid by only +0.005 |
| I9 | Extending the hybrid's search (PCA up to 128, `max_features` up to 0.7) improves it | 15 | **Not supported**: inconclusive | +0.008 [−0.016, +0.033], p = 0.48 against notebook 13's tuned hybrid; +0.006 [−0.019, +0.031] against the ECD tree. Third tuning analysis on the same folds. PCA 128 was never selected; `max_features` 0.7, the new upper edge, was selected in 13/25 folds |

### Explainability (the project's XAI component)

| # | Claim | Source | Status | Notes |
|---|---|---|---|---|
| X1 | ECD is the most important feature, followed by SD and total area | 05 (SHAP) | Superseded | Non-grouped CV, explained on training tissues, derived features splitting credit, dominated by 2023. Replaced by X3–X5 (notebook 12): ECD-derived features carry the largest grouped SHAP when both models are correct (+0.164) |
| X2 | Clinical findings contribute meaningfully to grading decisions | 05 (SHAP) | **Not supported** | In notebook 12, slit-lamp groups other than stroma contribute ≈ 0; stroma contributes modestly (X5). SHAP does not show what drives specialists' decisions |
| X3 | Image features provide reliable additional information about departures from the ECD thresholds | 12 | **Not supported** | Image has the largest grouped SHAP in hybrid-only-correct cases (+0.063), but pushes the model away from the recorded grade in tree-only-correct cases (−0.033) at similar magnitude. Model reliance, not demonstrated signal |
| X4 | The hybrid recovers some grades recorded below the ECD thresholds | 12 | Supported, with its cost | About 29% of downgrade pairs (131 of 445), but 151 incorrect departures, so departures are right about as often as wrong |
| X5 | Endothelial variability and stromal findings are associated with correctly predicted downgrades | 12 | Qualified: exploratory association | Variability SHAP positive in hybrid-only-correct cases in all repeats and ≈ 0 in tree-only-correct cases; stroma similar but smaller. Raw data: downgraded tissues had higher CV/SD, lower HEX, more stromal scar and cell dropout. Selected by the model's predictions; not causal; hypotheses for clinical review |

### Application (engineering claims, not clinical)

| # | Claim | Source | Status | Notes |
|---|---|---|---|---|
| A1 | The application rejects non-corneal images before analysis | `train_domain_validator.py`, ml-service tests | Supported for the evaluated image types | 0 of 1,295 held-out photos, documents, screenshots and content-free images accepted; 197/197 specular images accepted. Regression test for content-free images passes (v2) |
| A2 | The domain validator is clinically validated | — | **Not supported** | Engineering evaluation only. Not tested: other microscopes, near-domain images (other microscopy, eye photographs), image quality |
| A3 | The application assesses image quality or cell visibility | — | **Not supported** | Not implemented; reported as not assessed. Blurred specular images pass the domain check |
| A4 | The deployed grade uses the 24 features and the image (hybrid model) | `train_hybrid_grading_model.py`, ml-service tests | Supported (engineering) | Since Amendment 2 the tuned hybrid RF is served, with every request validated against the exported schema and the backbone checked against the model's reference output; the ECD tree is shown as a reference |
| A5 | The deployed hybrid model grades better than ECD alone or the tabular model | 13 (T1, T3) | **Not supported** | −0.003 [−0.034, +0.029] vs the ECD tree and −0.012 [−0.045, +0.022] vs tuned tabular, Holm p = 1.00. It was the lowest of the three. Served by project decision, not because it was shown superior |
| A6 | The deployed model's probabilities are confidence estimates | — | **Not supported** | Share of trees voting; no calibration assessed. Labelled as such in the API and UI |

## 2. The strongest defensible contribution

The evidence does not support "a model that grades corneas better" or "images improve grading". It does support a careful evaluation study with three findings that matter to anyone building grading models from eye-bank records:

1. **Evaluation must respect donor structure.** Fellow eyes are strongly correlated, and ignoring them inflates performance (D3, D4).
2. **Recorded grades follow different patterns across years, and pooled metrics hide it.** Near-perfect agreement in one year and 0.73 in others average to a misleading 0.85. Missing data is tied to the same year, which also makes test-time masking a misleading robustness check (D5, D6, I5).
3. **Generic image features add little beyond endothelial morphology.** This held with all features available, without slit-lamp findings, and in the non-2023 subset (I4, I5, I7). The non-2023 result is consistently positive but inconclusive, a specific, testable hypothesis for future work.
4. **Multimodal models did not outperform a fitted two-threshold ECD model.** They beat a poorly specified ECD-only learner, which shows how much the choice of baseline matters (T6). The result holds across five model families (notebook 14: Random Forest, gradient boosting, logistic regression, RBF SVM, Extra Trees; T10), so it is not an artefact of choosing Random Forests. The recorded labels are anchored at consistent ECD cut points (T7), and the open question is what explains the departures from them.

A possible framing: *"Evaluating machine learning for donor cornea grading: donor dependence, year-dependent grading patterns and the incremental value of specular microscopy images."*

## 3. Gaps before writing

Ordered by how much they affect the paper's claims.

| # | Gap | Why it matters | Suggested action |
|---|---|---|---|
| G1 | ~~No pre-specified comparison with ECD alone~~ **Closed (notebooks 10–11)** | Determined whether ML adds value beyond ECD | Done: improvement beyond ECD alone was not established (T6). Documented eye-bank criteria remain unavailable; the fitted tree recovered thresholds close to 2250/2500 (T7) |
| G2 | ~~Explainability not redone under the final protocol~~ **Closed for model explanations (notebook 12)** | XAI is the project's stated focus | Done: out-of-fold grouped SHAP on the primary cohort (X3–X5). Not addressed: what drives specialists' downgrades independently of any model. A model-free comparison of all tissues graded below the ECD thresholds would be post hoc and is optional |
| G3 | ~~Hyperparameters tuned on non-grouped CV~~ **Closed (notebook 13)** | The notebook 05 settings turned out to disadvantage the tabular arm, not favour it | Done: nested donor-grouped tuning (I7, I8, T8). The earlier comparisons stand as reported, with this context |
| G8 | ~~Only Random Forests evaluated after notebook 05~~ **Closed (notebook 14, follow-up)** | Results could have reflected the choice of model family | Done: four further families under the notebook 13 design (T1, T9, T10). Gradient boosting matched the Random Forest; the others were worse. Reuses the same outer folds |
| G9 | ~~Hybrid selections at the edge of the notebook 13 grid~~ **Addressed (notebook 15, follow-up)** | `max_features` 0.3 was selected in 25/25 folds and PCA 32 in 16/25, so better settings might lie outside the grid | Done: extended grid, inconclusive (I9). `max_features` 0.7 is again at the edge in 13/25 folds. Any further search should be pre-specified and evaluated on new tissues, since these folds have now been used for three tuning analyses |
| G4 | No consolidated final-results table | Numbers are spread across 05–09 with different cohorts (1,036 vs 1,009 vs 551) | One table: final tabular model, overall and by year, with CIs and per-grade recall; cohort stated for each row |
| G5 | Donor pairing inferred | Affects D3, D4 and every grouped result | State as a limitation; pairing rule documented in `modeling_setup.get_donor_groups` |
| G6 | Images represented only by generic frozen features | Limits I4 and I7 to "generic features" | Future work; any new representation needs its own pre-specified protocol |
| G7 | Earlier notebooks print donor attributes | Matters if the repository or notebooks are shared | Review outputs of 01–05 before publication |

## 4. Recommendation

G1 is closed: improvement beyond ECD alone was not established, so the paper's contribution is the evaluation findings, and the modelling sections should say so.

G2 is closed for model explanations: the earlier SHAP results (X1, X2) are replaced by the notebook 12 findings (X3–X5).

G4 is closed by `RESULTS.md`. G3 is closed by notebook 13, which selected the ECD tree for the application. G8 is closed by notebook 14: no other model family outperformed the deployed RF hybrid, which is retained.

G3, G5 and G7 can be handled as stated limitations or quick checks. G6 is future work.
