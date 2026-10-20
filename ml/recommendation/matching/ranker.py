"""Machine-learning ranker for donor-tissue matching.

Learns from historical NEBSL allocations which available cornea was chosen for each
recipient request, and ranks candidates by the predicted chance of being chosen.

Two model types are compared, and the one with the best cross-validated MRR on the
TRAINING requests is kept (the test requests are never used to choose):
  - logistic:  regularised logistic regression (pointwise learning-to-rank)
  - lightgbm:  gradient-boosted trees with the LambdaMART ranking objective

Positive-serology tissue is excluded before ranking, exactly as in MCDA.
"""
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from recommendation.evaluation.metrics import ranking_metrics
from recommendation.matching.features import FEATURES, build_features

# Candidate settings. Data are small (~150 training requests), so models are kept simple.
CANDIDATES = [
    {"model": "logistic", "C": 0.01},
    {"model": "logistic", "C": 0.1},
    {"model": "logistic", "C": 1.0},
    {"model": "lightgbm", "num_leaves": 3, "n_estimators": 100},
    {"model": "lightgbm", "num_leaves": 3, "n_estimators": 300},
    {"model": "lightgbm", "num_leaves": 7, "n_estimators": 300},
]


@dataclass
class Ranker:
    settings: dict
    estimator: object = field(default=None, repr=False)
    features: list[str] | None = None  # None = all 23; a subset is used for ablation

    @property
    def cols(self) -> list[str]:
        return self.features or FEATURES

    def fit(self, pairs: pd.DataFrame, seed: int = 42) -> "Ranker":
        p = pairs.sort_values(["Request_ID", "Candidate_Record_ID"])  # LightGBM needs grouped rows
        X, y = build_features(p)[self.cols], p["Label_Allocated"]
        s = self.settings
        if s["model"] == "logistic":
            self.estimator = make_pipeline(
                SimpleImputer(strategy="median"),
                StandardScaler(),
                LogisticRegression(C=s["C"], class_weight="balanced", max_iter=2000),
            )
            self.estimator.fit(X, y)
        else:
            self.estimator = lgb.LGBMRanker(
                objective="lambdarank", learning_rate=0.05, min_child_samples=20,
                subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
                num_leaves=s["num_leaves"], n_estimators=s["n_estimators"],
                random_state=seed, verbose=-1,
            )
            self.estimator.fit(X, y, group=p.groupby("Request_ID", sort=True).size().to_numpy())
        return self

    def score(self, pairs: pd.DataFrame) -> np.ndarray:
        X = build_features(pairs)[self.cols]
        if self.settings["model"] == "logistic":
            return self.estimator.decision_function(X)
        return self.estimator.predict(X)

    def rank(self, pairs: pd.DataFrame, col: str = "ML") -> pd.DataFrame:
        """Return a copy of ``pairs`` with ``{col}_Score`` and ``{col}_Rank`` (1 = best)."""
        df = pairs.copy()
        df[f"{col}_Score"] = self.score(df)
        df.loc[df["Cand_Serology_Clear"].eq("No"), f"{col}_Score"] = np.nan
        df[f"{col}_Rank"] = df.groupby("Request_ID")[f"{col}_Score"].rank(ascending=False, method="first")
        return df

    def weights(self) -> pd.Series | None:
        """Standardised coefficients (logistic only): + pushes a candidate up the list."""
        if self.settings["model"] != "logistic":
            return None
        coef = self.estimator[-1].coef_[0]
        return pd.Series(coef, index=self.cols).sort_values(key=abs, ascending=False)


def cross_validate(pairs: pd.DataFrame, settings: dict, folds: int = 5, seed: int = 42) -> dict:
    """Grouped k-fold CV: every fold holds out whole requests."""
    scores = []
    for tr, va in GroupKFold(n_splits=folds).split(pairs, groups=pairs["Request_ID"]):
        m = Ranker(settings).fit(pairs.iloc[tr], seed)
        scores.append(ranking_metrics(m.rank(pairs.iloc[va]), "ML_Rank"))
    return pd.DataFrame(scores).mean().to_dict()


def select(train: pd.DataFrame, seed: int = 42) -> tuple[dict, pd.DataFrame]:
    """Cross-validate every candidate on the training requests; keep the best MRR."""
    rows = []
    for s in CANDIDATES:
        cv = cross_validate(train, s, seed=seed)
        rows.append({"settings": s, **{f"cv_{k}": round(v, 4) for k, v in cv.items()}})
    table = pd.DataFrame(rows).sort_values("cv_mrr", ascending=False).reset_index(drop=True)
    return table.loc[0, "settings"], table


def repeated_cv_comparison(pairs: pd.DataFrame, settings: dict, repeats: int = 10,
                           folds: int = 5, n_boot: int = 2000, seed: int = 42) -> dict:
    """Compare ML with MCDA on ALL requests using repeated grouped CV.

    More stable than one 37-request test set. Returns mean metrics per method and a
    95% bootstrap interval (resampling requests) for the ML - MCDA difference.
    """
    from recommendation.evaluation.metrics import grade_only_rank

    rows = []
    for rep in range(repeats):
        gkf = GroupKFold(n_splits=folds, shuffle=True, random_state=seed + rep)
        for tr, va in gkf.split(pairs, groups=pairs["Request_ID"]):
            d = Ranker(settings).fit(pairs.iloc[tr], seed).rank(pairs.iloc[va])
            d["Grade_Rank"] = grade_only_rank(d)
            pos = d[d["Label_Allocated"] == 1]
            rows.append(pos[["Request_ID", "ML_Rank", "MCDA_Rank", "Grade_Rank"]])
    r = pd.concat(rows)

    def per_request(col):
        rank = r[col].fillna(np.inf)
        return pd.DataFrame({"top1": rank <= 1, "top3": rank <= 3, "mrr": 1 / rank,
                             "Request_ID": r["Request_ID"]}).groupby("Request_ID").mean()

    methods = {"Grade-only rule": "Grade_Rank", "MCDA": "MCDA_Rank", "ML ranker": "ML_Rank"}
    per = {name: per_request(col) for name, col in methods.items()}
    summary = {name: p.mean().round(4).to_dict() for name, p in per.items()}

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(per["MCDA"]), size=(n_boot, len(per["MCDA"])))
    diff = {}
    for metric in ("top3", "mrr"):
        a, b = per["ML ranker"][metric].to_numpy(), per["MCDA"][metric].to_numpy()
        boot = a[idx].mean(axis=1) - b[idx].mean(axis=1)
        diff[metric] = {"ml_minus_mcda": round(float(a.mean() - b.mean()), 4),
                        "ci95": [round(float(x), 4) for x in np.percentile(boot, [2.5, 97.5])]}
    return {"requests": int(len(per["MCDA"])), "repeats": repeats, "folds": folds,
            "methods": summary, "difference": diff}
