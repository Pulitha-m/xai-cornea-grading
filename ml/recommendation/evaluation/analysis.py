"""Model analysis for the ML ranker: ablation, learning curve, subgroups, errors.

All four use repeated 5-fold grouped cross-validation over all requests, so every
request is tested by a model that never saw it, and results are averaged over
several random fold assignments.

  ablation        remove one reason's features at a time (grade match, freshness, ...)
                  and measure how much worse the ranking gets
  learning curve  train on 25 / 50 / 75 / 100 % of the training requests in each fold:
                  would more NEBSL data help?
  subgroups       accuracy by surgery type, urgency, requested grade and pool size
  errors          requests where the allocated cornea ranked low: how did it differ
                  from the model's #1?
"""
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from recommendation.evaluation.metrics import grade_only_rank
from recommendation.explain.shap_explain import REASON_OF, REASONS
from recommendation.matching.features import FEATURES, build_features
from recommendation.matching.ranker import Ranker


def _summary(ranks: pd.Series) -> dict:
    r = ranks.fillna(np.inf)
    return {"top1": float((r <= 1).mean()), "top3": float((r <= 3).mean()), "mrr": float((1 / r).mean())}


def cv_ranks(pairs: pd.DataFrame, settings: dict, features: list[str] | None = None,
             train_fraction: float = 1.0, repeats: int = 5, folds: int = 5,
             seed: int = 42) -> pd.DataFrame:
    """Rank of the allocated cornea for every request in every repeat.

    One row per (repeat, request) with ML, MCDA and grade-only ranks.
    ``pairs`` must already contain MCDA_Rank (from mcda.score).
    """
    rows = []
    for rep in range(repeats):
        rng = np.random.default_rng(seed + rep)
        gkf = GroupKFold(n_splits=folds, shuffle=True, random_state=seed + rep)
        for tr, va in gkf.split(pairs, groups=pairs["Request_ID"]):
            train = pairs.iloc[tr]
            if train_fraction < 1.0:
                ids = train["Request_ID"].unique()
                keep = rng.choice(ids, size=max(2, int(round(len(ids) * train_fraction))), replace=False)
                train = train[train["Request_ID"].isin(keep)]
            d = Ranker(settings, features=features).fit(train, seed).rank(pairs.iloc[va])
            d["Grade_Rank"] = grade_only_rank(d)
            pos = d[d["Label_Allocated"] == 1]
            rows.append(pos.assign(repeat=rep)[["repeat", "Request_ID", "ML_Rank", "MCDA_Rank", "Grade_Rank"]])
    return pd.concat(rows, ignore_index=True)


def ablation(pairs: pd.DataFrame, settings: dict, **kw) -> pd.DataFrame:
    """Drop each reason's features in turn; report metrics and the loss vs all features."""
    rows = {"all features": _summary(cv_ranks(pairs, settings, **kw)["ML_Rank"])}
    for reason in REASONS:
        keep = [f for f in FEATURES if REASON_OF.get(f) != reason]
        rows[f"without {reason}"] = _summary(cv_ranks(pairs, settings, features=keep, **kw)["ML_Rank"])
    t = pd.DataFrame(rows).T
    t["mrr_change"] = t["mrr"] - t.loc["all features", "mrr"]
    t["top3_change"] = t["top3"] - t.loc["all features", "top3"]
    return t


def learning_curve(pairs: pd.DataFrame, settings: dict,
                   fractions=(0.25, 0.5, 0.75, 1.0), **kw) -> pd.DataFrame:
    """Accuracy when the model sees only part of each fold's training requests."""
    n_requests = pairs["Request_ID"].nunique()
    folds = kw.get("folds", 5)
    rows = []
    for f in fractions:
        r = cv_ranks(pairs, settings, train_fraction=f, **kw)
        rows.append({"train_fraction": f,
                     "train_requests": int(round(n_requests * (folds - 1) / folds * f)),
                     **{f"ml_{k}": v for k, v in _summary(r["ML_Rank"]).items()},
                     **{f"mcda_{k}": v for k, v in _summary(r["MCDA_Rank"]).items()}})
    return pd.DataFrame(rows)


def subgroups(pairs: pd.DataFrame, ranks: pd.DataFrame, min_requests: int = 8) -> pd.DataFrame:
    """ML vs MCDA accuracy per subgroup (only groups with enough requests)."""
    req = pairs.drop_duplicates("Request_ID").set_index("Request_ID")
    pool = pairs.groupby("Request_ID").size()
    info = pd.DataFrame({
        "surgery type": req["Surgery_Type"],
        "urgency": req["Request_Urgency"].fillna("Not recorded"),
        "requested grade": req["Requested_Grade"],
        "pool size": pd.cut(pool, [0, 10, 20, 30, 1000], labels=["2-10", "11-20", "21-30", "over 30"]),
    })
    r = ranks.join(info, on="Request_ID")
    rows = []
    for by in info.columns:
        for level, g in r.groupby(by, observed=True):
            n = g["Request_ID"].nunique()
            if n < min_requests:
                continue
            ml, mc = _summary(g["ML_Rank"]), _summary(g["MCDA_Rank"])
            rows.append({"subgroup": by, "level": str(level), "requests": n,
                         "ml_top3": ml["top3"], "mcda_top3": mc["top3"],
                         "ml_mrr": ml["mrr"], "mcda_mrr": mc["mrr"]})
    return pd.DataFrame(rows)


def errors(pairs: pd.DataFrame, ranks: pd.DataFrame, settings: dict,
           worse_than: int = 5) -> dict:
    """Compare the allocated cornea with the model's #1 in requests the model got badly wrong.

    Uses each request's average rank over repeats; a 'miss' is an allocated cornea
    ranked below ``worse_than`` on average.
    """
    avg = ranks.groupby("Request_ID")["ML_Rank"].mean()
    missed = avg[avg > worse_than].index
    model = Ranker(settings).fit(pairs)
    ranked = model.rank(pairs[pairs["Request_ID"].isin(missed)])
    X = build_features(ranked)
    cols = {"Grade_Exact": "exact grade match", "Grade_Below": "below requested grade",
            "Cand_Days_In_Storage": "days in storage", "ECD_if_Endo": "ECD (endothelial surgery)",
            "Serology_Unknown": "serology not confirmed"}
    allocated = X.loc[ranked["Label_Allocated"] == 1, list(cols)].mean()
    top1 = X.loc[ranked["ML_Rank"] == 1, list(cols)].mean()
    table = pd.DataFrame({"allocated cornea": allocated, "model's #1": top1}).rename(index=cols)
    return {"requests": int(avg.size), "missed": int(len(missed)),
            "missed_share": float(len(missed) / avg.size), "comparison": table}
