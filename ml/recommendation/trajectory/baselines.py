"""P3 trajectory baselines: predict ECD at 24 / 36 / 60 months at the 12-month visit.

All models share fit(train) / predict(table) on the P2 landmark table (unscaled values).
fit() only reads training grafts, including their later ECD values (the targets), which is
allowed for training; predict() only reads inputs available at month 12.

  LastValue         ECD stays at the 12-month value (carry forward)
  PopulationDecay   12-month value declines at the median chronic rate of its procedure
  OwnTrendDecay     12-month value continues the graft's own 6->12-month rate
  MixedEffects      empirical-Bayes random-slope model: each graft's chronic rate is its
                    procedure's mean rate, shifted towards its own early rate by the amount
                    the training grafts justify (best linear unbiased predictor of a
                    random slope given the early slope)

Rates are on the log scale (exponential cell loss), per year.
"""
import numpy as np
import pandas as pd

from recommendation.data_prep.followup_dataset import HORIZONS, LANDMARK


def _years(h: int) -> float:
    return (h - LANDMARK) / 12


def _early_rate(t: pd.DataFrame) -> pd.Series:
    """log rate between the 6- and 12-month visits (per year)."""
    return np.log(t["ECD_12m"] / t["ECD_6m"]) / 0.5


def _chronic_rate(t: pd.DataFrame) -> pd.Series:
    """Mean observed log rate after month 12 (per year); NaN if no later ECD (training only)."""
    rates = [np.log(t[f"ECD_{h}m"] / t["ECD_12m"]) / _years(h) for h in HORIZONS]
    return pd.concat(rates, axis=1).mean(axis=1, skipna=True)


def _from_rate(t: pd.DataFrame, rate: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({f"ECD_{h}m": t["ECD_12m"] * np.exp(rate * _years(h)) for h in HORIZONS}, index=t.index)


class LastValue:
    name = "Last value carried forward"

    def fit(self, train: pd.DataFrame) -> "LastValue":
        return self

    def predict(self, t: pd.DataFrame) -> pd.DataFrame:
        return _from_rate(t, pd.Series(0.0, index=t.index))


class PopulationDecay:
    name = "Population decay (procedure median rate)"

    def fit(self, train: pd.DataFrame) -> "PopulationDecay":
        r = _chronic_rate(train)
        self.rates = r.groupby(train["procedure"]).median().to_dict()
        self.overall = float(r.median())
        return self

    def predict(self, t: pd.DataFrame) -> pd.DataFrame:
        return _from_rate(t, t["procedure"].map(self.rates).fillna(self.overall))


class OwnTrendDecay:
    name = "Own 6-12 month trend continued"

    def fit(self, train: pd.DataFrame) -> "OwnTrendDecay":
        return self

    def predict(self, t: pd.DataFrame) -> pd.DataFrame:
        return _from_rate(t, _early_rate(t))


class MixedEffects:
    name = "Mixed-effects (empirical-Bayes random slope)"

    def fit(self, train: pd.DataFrame) -> "MixedEffects":
        d = pd.DataFrame({"chronic": _chronic_rate(train), "early": _early_rate(train),
                          "procedure": train["procedure"]}).dropna()
        self.mean_chronic = d.groupby("procedure")["chronic"].mean().to_dict()
        self.mean_early = d.groupby("procedure")["early"].mean().to_dict()
        # pooled within-procedure covariance -> shrinkage weight on the graft's own early rate
        dc = d["chronic"] - d["procedure"].map(self.mean_chronic)
        de = d["early"] - d["procedure"].map(self.mean_early)
        self.weight = float(np.clip((dc * de).sum() / (de ** 2).sum(), 0.0, 1.0)) if (de ** 2).sum() else 0.0
        self.overall = (float(d["chronic"].mean()), float(d["early"].mean()))
        self.n_train = int(len(d))
        return self

    def predict(self, t: pd.DataFrame) -> pd.DataFrame:
        mc = t["procedure"].map(self.mean_chronic).fillna(self.overall[0])
        me = t["procedure"].map(self.mean_early).fillna(self.overall[1])
        return _from_rate(t, mc + self.weight * (_early_rate(t) - me))


BASELINES = [LastValue, PopulationDecay, OwnTrendDecay, MixedEffects]


def forecast_errors(table: pd.DataFrame, pred: pd.DataFrame) -> dict:
    """MAE / RMSE (cells/mm2) per horizon on grafts whose ECD was measured at that horizon."""
    out = {}
    for h in HORIZONS:
        y, p = table[f"ECD_{h}m"], pred[f"ECD_{h}m"]
        ok = y.notna() & p.notna()
        err = (p[ok] - y[ok]).to_numpy()
        out[f"{h}m"] = {"n": int(ok.sum()), "mae": float(np.abs(err).mean()) if ok.any() else float("nan"),
                        "rmse": float(np.sqrt((err ** 2).mean())) if ok.any() else float("nan")}
    errs = np.concatenate([(pred[f"ECD_{h}m"] - table[f"ECD_{h}m"]).dropna().to_numpy() for h in HORIZONS])
    out["all"] = {"n": int(len(errs)), "mae": float(np.abs(errs).mean()), "rmse": float(np.sqrt((errs ** 2).mean()))}
    return out
