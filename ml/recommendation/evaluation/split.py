"""Grouped train/test split for ranking data.

All candidate rows for one request must stay in the same partition; otherwise the
model sees the test request's other candidates during training and scores look better
than they are.
"""
import numpy as np
import pandas as pd


def grouped_split(
    pairs: pd.DataFrame,
    group_col: str = "Request_ID",
    test_size: float = 0.2,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split ``pairs`` into train/test by whole groups."""
    groups = pairs[group_col].drop_duplicates().to_numpy()
    rng = np.random.default_rng(seed)
    rng.shuffle(groups)
    n_test = max(1, int(round(len(groups) * test_size)))
    test_groups = set(groups[:n_test])
    is_test = pairs[group_col].isin(test_groups)
    return pairs[~is_test].copy(), pairs[is_test].copy()
