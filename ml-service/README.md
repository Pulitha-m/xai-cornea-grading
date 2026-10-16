# ML Service

FastAPI inference service for Corneal-AI. `POST /analyze` returns cellular, grading, disease and recommendation results for a case.

## Grading

Grading uses an **ECD threshold tree**: a depth-2 decision tree on endothelial cell density (ECD), selected in `ml/grading/notebooks/images/13_nested_tuning_model_selection.ipynb`. In nested donor-grouped cross-validation, neither a tuned tabular model nor a tuned tabular + image model convincingly outperformed it (`ml/grading/RESULTS.md`).

| ECD (cells/mm²) | Grade |
|---|---|
| ≤ 2232 | B |
| > 2232 and ≤ 2497 | A |
| > 2497 | A+ |

**Decision support only.** The grade uses ECD alone. Slit-lamp findings and other morphology are not considered and may justify a lower grade, so a specialist must confirm every grade.

### Request

`ecd` (cells/mm², `0 < ecd ≤ 6000`) is an optional field of the request, entered from the specular microscopy report. Grading never uses the cellular pipeline's output.

### Response (`grading`)

| Field | Meaning |
|---|---|
| `status` | `completed`; `review_required` when no ECD is supplied (no grade is given); `failed` on error |
| `grade` | A+, A or B |
| `method` | `ecd_threshold_tree` |
| `ecdUsed`, `ecdBand` | The ECD value and the band (`lowerExclusive` < ECD ≤ `upperInclusive`) it fell in |
| `bandDistribution`, `bandTrainingTissues` | Recorded grades of the training tissues in that band, as proportions. **This is not model confidence**; no calibration has been assessed |
| `reviewRequired` | `true` when no ECD is supplied or ECD is outside the training range |
| `message` | Human-readable caveats to show with the grade |

An out-of-range ECD (≤ 0 or > 6000) is rejected with HTTP 422. The backend passes this status and its validation details through to the client.

### Model spec

`models/grading_ecd_tree.json` holds the cut points, band grades and per-band training counts. It contains no tissue-level data. To regenerate it and the golden test file (needs the git-ignored grading dataset):

```
cd ../ml
.venv/Scripts/python.exe grading/scripts/train_grading_model.py
```

The script checks that the cohort, cut points and dataset hash match notebook 13, and that the spec reproduces the fitted scikit-learn tree.

## Cellular

Not implemented yet. The service returns `status: "not_implemented"` with null values instead of placeholder numbers.

## Tests

```
uv sync
uv run pytest
```

`tests/test_grading.py` checks that API grades match predictions of the fitted scikit-learn tree (`tests/fixtures/grading_golden.json`, including values at and around each cut point), plus missing, invalid and out-of-range ECD handling. The backend's `MlServiceContractTest` checks that a captured response deserialises into the backend DTOs. The frontend's `analysis-page.test.tsx` renders the same captured responses. When the grading schema changes, regenerate `backend/src/test/resources/contracts/ml_service_analyze_responses.json` from this service.
