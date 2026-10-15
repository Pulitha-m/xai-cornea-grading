# Claims Audit: Notebooks 01–11

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
| T1 | Random Forest outperformed LR, SVM and Extra Trees | 05 | Qualified | Non-grouped CV; ranking is likely to hold but was not re-run with donor grouping |
| T2 | Tuned RF holdout macro F1 0.861 | 05 | Superseded | 78 donor pairs split across holdout; the holdout informed earlier decisions. Use 06/07 |
| T3 | Tabular RF macro F1 0.906 on the shared split | images/05 | Superseded | Single 152-tissue split, 108 donor pairs split, no uncertainty. Use 07 |
| T4 | Tabular RF macro F1 0.844 (all 1,036) / 0.849 (image cohort), donor-grouped 5×5 CV | 06, 07 | Qualified | Hyperparameters tuned in 05 with non-grouped CV on overlapping tissues. Pooled figure averages 2023 (0.99) and other years (0.73); always report by year |
| T5 | Morphology outperforms ECD alone; adding ECD changes nothing | 04 | Qualified | Morphology features contain ECD implicitly (count / area). Reframe as "the full Konan feature set outperforms ECD alone" |
| T6 | The ML models add value beyond ECD alone | 10, 11 | **Not supported** | Pre-specified (10): Tabular and Hybrid beat an ECD-only Random Forest (+0.048, +0.081; Holm p 0.030, 0.006), but that comparator was weak. Follow-up (11): neither beat a depth-2 ECD tree fitted within training folds (Tabular −0.040, Hybrid −0.007; inconclusive). Report both; claim only that the models outperform an ECD-only Random Forest |
| T7 | Recorded grades are anchored at ECD ≈ 2230 and ≈ 2500 across years | 11 | Supported as a description of the labels | Tree fitted on non-2023 tissues recovered cut points 2232 and 2494–2503 in all 25 folds. Not evidence of a single official protocol, nor of why tissues depart from the thresholds |

### Image and hybrid models

| # | Claim | Source | Status | Notes |
|---|---|---|---|---|
| I1 | A CNN trained from scratch (and a partly fine-tuned ResNet-18) on 224-pixel images performs poorly (macro F1 0.33–0.48) | images/02, images/04 | Qualified | Shows these configurations failed, not that images are uninformative. Non-grouped splits |
| I2 | The neural multimodal model underperformed tabular RF (0.818 vs 0.906) | images/05 | Superseded | Confounds fusion with MLP vs RF; non-grouped split. Use 07 |
| I3 | Frozen ResNet-50 embeddings carry some grade information (image-only macro F1 0.44) | 07 | Supported | Most of it plausibly overlaps with the Konan measurements; not tested directly |
| I4 | Adding frozen embeddings does not significantly improve the full-feature model (+0.010, CI −0.012 to +0.031) | 07 | Supported | Not robust to PCA size; grade B recall fell 0.851 → 0.819 |
| I5 | Images help when slit-lamp findings are missing | 08 | **Not supported** | C1 is confounded with 2023; C3 is a masking artefact with lower grade B recall; C5 (cleanest) shows no gain |
| I6 | Images can substitute for Konan measurements | 08 | **Not supported** | Both arms collapse (C4); hybrid B recall 0.04 |
| I7 | On non-2023 tissues the hybrid improves macro F1 (+0.038, CI −0.013 to +0.088) | 09 | Qualified: **inconclusive** | Pre-specified sensitivity analysis, not independent of the exploratory 08 result. Direction positive in all repeats and years |

### Explainability (the project's XAI component)

| # | Claim | Source | Status | Notes |
|---|---|---|---|---|
| X1 | ECD is the most important feature, followed by SD and total area | 05 (SHAP) | Qualified | Model trained with non-grouped CV, explained on 200 training tissues. ECD, SD, area and count are derived from one another, so SHAP splits credit among them. Importance is dominated by the 2023 subset |
| X2 | Clinical findings contribute meaningfully to grading decisions | 05 (SHAP) | Not yet supported | Slit-lamp features exist only outside 2023; their SHAP values reflect half the data. Needs a by-year analysis |

## 2. The strongest defensible contribution

The evidence does not support "a model that grades corneas better" or "images improve grading". It does support a careful evaluation study with three findings that matter to anyone building grading models from eye-bank records:

1. **Evaluation must respect donor structure.** Fellow eyes are strongly correlated, and ignoring them inflates performance (D3, D4).
2. **Recorded grades follow different patterns across years, and pooled metrics hide it.** Near-perfect agreement in one year and 0.73 in others average to a misleading 0.85. Missing data is tied to the same year, which also makes test-time masking a misleading robustness check (D5, D6, I5).
3. **Generic image features add little beyond endothelial morphology.** This held with all features available, without slit-lamp findings, and in the non-2023 subset (I4, I5, I7). The non-2023 result is consistently positive but inconclusive, a specific, testable hypothesis for future work.
4. **Multimodal models did not outperform a fitted two-threshold ECD model.** They beat a poorly specified ECD-only learner, which shows how much the choice of baseline matters (T6). The recorded labels are anchored at consistent ECD cut points (T7), and the open question is what explains the departures from them.

A possible framing: *"Evaluating machine learning for donor cornea grading: donor dependence, year-dependent grading patterns and the incremental value of specular microscopy images."*

## 3. Gaps before writing

Ordered by how much they affect the paper's claims.

| # | Gap | Why it matters | Suggested action |
|---|---|---|---|
| G1 | ~~No pre-specified comparison with ECD alone~~ **Closed (notebooks 10–11)** | Determined whether ML adds value beyond ECD | Done: improvement beyond ECD alone was not established (T6). Documented eye-bank criteria remain unavailable; the fitted tree recovered thresholds close to 2250/2500 (T7) |
| G2 | **Explainability not redone under the final protocol** | XAI is the project's stated focus, and the existing SHAP (X1, X2) predates donor grouping and the year finding | Exploratory analysis of grades that depart from the ECD thresholds: held-out tissues where the hybrid is correct and the ECD tree is not, with grouped SHAP (derived Konan features grouped; image components as one source). See `ANALYSIS_PLAN.md`, analysis B |
| G3 | Hyperparameters tuned on non-grouped CV | Slight optimism in T4; may favour the tabular arm in 07 and 09 | Nested donor-grouped tuning as a sensitivity check, or state as a limitation |
| G4 | No consolidated final-results table | Numbers are spread across 05–09 with different cohorts (1,036 vs 1,009 vs 551) | One table: final tabular model, overall and by year, with CIs and per-grade recall; cohort stated for each row |
| G5 | Donor pairing inferred | Affects D3, D4 and every grouped result | State as a limitation; pairing rule documented in `modeling_setup.get_donor_groups` |
| G6 | Images represented only by generic frozen features | Limits I4 and I7 to "generic features" | Future work; any new representation needs its own pre-specified protocol |
| G7 | Earlier notebooks print donor attributes | Matters if the repository or notebooks are shared | Review outputs of 01–05 before publication |

## 4. Recommendation

G1 is closed: improvement beyond ECD alone was not established, so the paper's contribution is the evaluation findings, and the modelling sections should say so.

1. **Close G2** next, refocused on grades that depart from the ECD thresholds. The explainability component is part of the project's stated aim, and the existing SHAP results cannot be reported as they stand.
2. **Then G4**, which mostly gathers existing numbers into one table, now including the ECD tree.

G3, G5 and G7 can be handled as stated limitations or quick checks. G6 is future work.
