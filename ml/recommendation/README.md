# Recommendation module (iTRUST Member 4)

**Post-Transplant Trajectory Monitoring and Recommendation Engine** — Vidanage S.N.

## Layout

```
recommendation/
├── main.py              Command-line entry point
├── pipeline.py          End-to-end pipelines (matching implemented; others planned)
├── config.yaml          Central settings: paths, split, MCDA weights
├── config.py            Loads config.yaml (overridable with REC_* env vars)
│
├── trajectory/          1. LSTM forecasting of post-transplant ECD/CV/HEX
├── risk/                2. DeepSurv deterioration risk vs Cox baseline
├── followup/            3. MCDA + Learning-to-Rank of follow-up actions
├── explain/             4. SHAP + constrained counterfactual explanations
├── reporting/           5. LLM-assisted clinician report
├── matching/            Supplementary: donor-tissue ranking for a recipient request
│
├── data_prep/           Builds model-ready tables from raw NEBSL exports
├── evaluation/          Grouped splits and metrics shared by all parts
├── scripts/             One-off utilities
├── notebooks/           Exploration only; clear outputs before committing
├── experiments/         Experiment configs and notes
├── tests/               Unit tests (tiny made-up fixtures, no real data)
│
├── data/                (git-ignored) raw/ and processed/ NEBSL data
├── outputs/             (git-ignored) metrics, figures, reports
└── models/              (git-ignored) trained model files
```

Folders 1–5 are the sub-components in the proposal (Table 4.1). `trajectory`, `risk` and
`followup` need recipient follow-up data from NEBSL and are empty until it arrives.

## Data

Never commit NEBSL data. Place the workbook at
`ml/recommendation/data/raw/dataset_final_labeled.xlsx`. The module's `.gitignore` blocks
`data/`, `outputs/`, `models/` and all `.xlsx`/`.csv` files.

## Run

From `ml/`:

```bash
uv run python -m recommendation.main matching          # build, rank, evaluate
uv run python -m recommendation.main matching --no-rebuild
uv run python -m recommendation.data_prep.eda           # figures + summary
uv run python -m recommendation.main ranker            # train + evaluate ML ranker
REC_SPLIT__SEED=7 uv run python -m recommendation.main matching   # override a setting
uv run python -m pytest recommendation/tests
```

Results are written to `outputs/matching/metrics.json` (including the weights version used)
and EDA figures to `outputs/eda/`. The ML ranker writes `outputs/matching/ranker_metrics.json`
and saves the trained model to `models/matching_ranker.joblib` (git-ignored).

## Conventions

- One sub-component per folder; shared code goes in `evaluation/` or `ml/common/`.
- Split by recipient or request ID, never by row.
- Anything that changes results (weights, thresholds, seeds) lives in `config.yaml`.
- Notebooks are for exploration; move working code into the package.
