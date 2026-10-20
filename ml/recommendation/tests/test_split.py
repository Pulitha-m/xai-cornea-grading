import pandas as pd

from recommendation.evaluation.split import grouped_split


def _pairs(n_requests=20, per_request=5):
    rows = [{"Request_ID": f"Q{q}", "x": i} for q in range(n_requests) for i in range(per_request)]
    return pd.DataFrame(rows)


def test_no_request_in_both_partitions():
    train, test = grouped_split(_pairs(), test_size=0.25, seed=0)
    assert set(train["Request_ID"]).isdisjoint(test["Request_ID"])


def test_all_rows_kept():
    df = _pairs()
    train, test = grouped_split(df, seed=1)
    assert len(train) + len(test) == len(df)


def test_test_size_counts_requests_not_rows():
    train, test = grouped_split(_pairs(n_requests=20), test_size=0.2, seed=2)
    assert test["Request_ID"].nunique() == 4


def test_same_seed_same_split():
    a = grouped_split(_pairs(), seed=7)[1]["Request_ID"].unique()
    b = grouped_split(_pairs(), seed=7)[1]["Request_ID"].unique()
    assert list(a) == list(b)
