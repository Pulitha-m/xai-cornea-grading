"""Ranking evaluation against historical allocations.

Metrics are computed per request and averaged:
  - Top-1 / Top-3 hit rate: was the allocated tissue ranked 1st / in the top 3?
  - MRR: mean reciprocal rank of the allocated tissue.
  - NDCG@k: with one relevant item per request.

These measure agreement with what NEBSL actually did, not clinical optimality.
Requests with a single candidate are skipped (nothing to rank).
"""
import numpy as np
import pandas as pd


def _per_request(df: pd.DataFrame, rank_col: str) -> pd.DataFrame:
    sizes = df.groupby("Request_ID").size()
    multi = sizes[sizes > 1].index
    pos = df[(df["Label_Allocated"] == 1) & df["Request_ID"].isin(multi)]
    out = pos[["Request_ID", rank_col]].rename(columns={rank_col: "rank"}).copy()
    out["pool_size"] = out["Request_ID"].map(sizes)
    return out


def ranking_metrics(df: pd.DataFrame, rank_col: str, ks=(3, 5)) -> dict:
    r = _per_request(df, rank_col)
    ranks = r["rank"].to_numpy(dtype=float)  # NaN = allocated tissue was excluded
    found = ~np.isnan(ranks)
    rr = np.where(found, 1.0 / np.where(found, ranks, 1), 0.0)
    out = {
        "requests": int(len(r)),
        "mean_pool_size": round(float(r["pool_size"].mean()), 1),
        "top1": float(np.mean(found & (ranks <= 1))),
        "top3": float(np.mean(found & (ranks <= 3))),
        "mrr": float(np.mean(rr)),
    }
    for k in ks:
        gain = np.where(found & (ranks <= k), 1.0 / np.log2(np.where(found, ranks, 1) + 1), 0.0)
        out[f"ndcg@{k}"] = float(np.mean(gain))  # ideal DCG = 1 with one relevant item
    return out


def random_baseline(df: pd.DataFrame, ks=(3, 5)) -> dict:
    """Expected metrics if candidates were ordered at random."""
    sizes = df.groupby("Request_ID").size()
    sizes = sizes[sizes > 1].to_numpy()
    out = {
        "requests": int(len(sizes)),
        "mean_pool_size": round(float(sizes.mean()), 1),
        "top1": float(np.mean(1 / sizes)),
        "top3": float(np.mean(np.minimum(3, sizes) / sizes)),
        "mrr": float(np.mean([np.mean(1 / np.arange(1, n + 1)) for n in sizes])),
    }
    for k in ks:
        out[f"ndcg@{k}"] = float(np.mean([
            sum(1 / np.log2(r + 1) for r in range(1, min(k, n) + 1)) / n for n in sizes
        ]))
    return out


def grade_only_rank(df: pd.DataFrame) -> pd.Series:
    """Baseline: closest grade match first (exact > exceeds > below), ties by ECD."""
    key = df["Grade_Gap"].abs() + (df["Grade_Gap"] < 0) * 0.5
    tmp = df.assign(_k=key.fillna(9), _e=-df["Cand_ECD"].fillna(0))
    tmp = tmp.sort_values(["Request_ID", "_k", "_e"])
    tmp["_r"] = tmp.groupby("Request_ID").cumcount() + 1
    return tmp["_r"].reindex(df.index)


def compare(df: pd.DataFrame) -> pd.DataFrame:
    """Table of MCDA vs grade-only vs random on the same rows."""
    d = df.copy()
    d["Grade_Rank"] = grade_only_rank(d)
    rows = {
        "Random (expected)": random_baseline(d),
        "Grade-only rule": ranking_metrics(d, "Grade_Rank"),
        "MCDA": ranking_metrics(d, "MCDA_Rank"),
    }
    return pd.DataFrame(rows).T
