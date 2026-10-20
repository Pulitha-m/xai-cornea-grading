"""P4 trajectory models: gradient boosting and LSTM, same interface as the P3 baselines.

Both predict the relative decline after the 12-month visit, log(ECD_h / ECD_12m), for
h = 24 / 36 / 60 months, and convert it back to ECD. Learning a ratio instead of raw ECD
puts all grafts on one scale. fit(train) uses training grafts only (including their later
ECD values as targets); predict(table) uses only inputs available at month 12. The
preprocessing (FollowupPreprocessor) is refitted inside fit(), so cross-validation folds
never see statistics from the grafts they are scored on.

  GradientBoosting  LightGBM on the 26 landmark inputs plus "years ahead"; one pooled
                    model for all horizons (row = graft x horizon), so the 60-month
                    horizon borrows strength from the 24/36-month data
  LSTMTrajectory    small LSTM reading the visit sequence (3, 6, 12 months: ECD, CV, HEX,
                    missing flag, time) with donor / procedure / indication / rejection as
                    static inputs; three outputs, loss only on measured horizons
"""
import numpy as np
import pandas as pd

from recommendation.data_prep.followup_dataset import HORIZONS, INPUT_MONTHS, LANDMARK, FollowupPreprocessor


def _ratio_targets(t: pd.DataFrame) -> np.ndarray:
    """log(ECD_h / ECD_12m) per horizon; NaN where ECD_h was not measured."""
    return np.column_stack([np.log(t[f"ECD_{h}m"] / t["ECD_12m"]) for h in HORIZONS])


def _to_ecd(t: pd.DataFrame, ratios: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({f"ECD_{h}m": t["ECD_12m"].to_numpy() * np.exp(ratios[:, i])
                         for i, h in enumerate(HORIZONS)}, index=t.index)


# ---------------------------------------------------------------- gradient boosting
class GradientBoosting:
    name = "Gradient boosting (LightGBM)"

    def __init__(self, n_estimators: int = 300, learning_rate: float = 0.03, num_leaves: int = 7,
                 min_child_samples: int = 20, seed: int = 42):
        self.params = dict(n_estimators=n_estimators, learning_rate=learning_rate, num_leaves=num_leaves,
                           min_child_samples=min_child_samples, subsample=0.8, subsample_freq=1,
                           colsample_bytree=0.8, reg_lambda=1.0, random_state=seed, verbose=-1)

    def _long(self, X: pd.DataFrame):
        parts = []
        for h in HORIZONS:
            parts.append(X.assign(years_ahead=(h - LANDMARK) / 12))
        return pd.concat(parts, ignore_index=True)

    def fit(self, train: pd.DataFrame) -> "GradientBoosting":
        from lightgbm import LGBMRegressor

        self.pre = FollowupPreprocessor().fit(train)
        X = self._long(self.pre.transform(train).reset_index(drop=True))
        y = _ratio_targets(train).T.reshape(-1)          # horizon-major, matches _long
        ok = ~np.isnan(y)
        self.model = LGBMRegressor(**self.params).fit(X[ok], y[ok])
        return self

    def predict(self, t: pd.DataFrame) -> pd.DataFrame:
        X = self._long(self.pre.transform(t).reset_index(drop=True))
        r = self.model.predict(X).reshape(len(HORIZONS), len(t)).T
        return _to_ecd(t, r)


# ---------------------------------------------------------------- LSTM
SEQ_VARS = ("ECD", "CV", "HEX")


def _lstm_net_class():
    import torch
    from torch import nn

    class LSTMNet(nn.Module):
        """Visit sequence -> LSTM -> last hidden state + static inputs -> 3 horizons."""

        def __init__(self, n_seq: int, hidden: int, n_static: int, dropout: float):
            super().__init__()
            self.config = dict(n_seq=n_seq, hidden=hidden, n_static=n_static, dropout=dropout)
            self.lstm = nn.LSTM(n_seq, hidden, batch_first=True)
            self.head = nn.Sequential(nn.Linear(hidden + n_static, 32), nn.ReLU(),
                                      nn.Dropout(dropout), nn.Linear(32, len(HORIZONS)))

        def forward(self, seq, static):
            _, (h, _) = self.lstm(seq)
            return self.head(torch.cat([h[-1], static], dim=1))

    return LSTMNet


def _LSTMNet(*args):
    return _lstm_net_class()(*args)


class LSTMTrajectory:
    name = "LSTM (visit sequence)"

    def __init__(self, hidden: int = 16, epochs: int = 400, lr: float = 0.01, weight_decay: float = 1e-3,
                 dropout: float = 0.1, patience: int = 40, seed: int = 42):
        self.hidden, self.epochs, self.lr, self.wd = hidden, epochs, lr, weight_decay
        self.dropout, self.patience, self.seed = dropout, patience, seed

    # sequence: one step per input visit, features = scaled ECD/CV/HEX, missing flag, time (years)
    def _arrays(self, t: pd.DataFrame):
        X = self.pre.transform(t)
        steps = []
        for m in INPUT_MONTHS:
            cols = [f"{k}_{m}m" for k in SEQ_VARS]
            vals = X[cols].to_numpy()
            missing = t[f"ECD_{m}m"].isna().to_numpy(float)[:, None]
            steps.append(np.hstack([vals * (1 - missing), missing, np.full((len(t), 1), m / 12)]))
        seq = np.stack(steps, axis=1).astype(np.float32)               # (n, 3, 5)
        static = X[self.static_cols].to_numpy(np.float32)
        return seq, static

    def _net(self, n_static: int):
        return _LSTMNet(5, self.hidden, n_static, self.dropout)

    def fit(self, train: pd.DataFrame) -> "LSTMTrajectory":
        import torch

        torch.manual_seed(self.seed)
        rng = np.random.default_rng(self.seed)
        self.pre = FollowupPreprocessor().fit(train)
        seq_cols = {f"{k}_{m}m" for m in INPUT_MONTHS for k in SEQ_VARS}
        self.static_cols = [c for c in self.pre.feature_names if c not in seq_cols and not c.startswith(
            tuple(f"{k}_{m}m_missing" for m in INPUT_MONTHS for k in SEQ_VARS))]
        seq, static = self._arrays(train)
        y = _ratio_targets(train).astype(np.float32)
        self.y_mean = np.nanmean(y, axis=0)
        self.y_std = np.nanstd(y, axis=0) + 1e-6
        y = (y - self.y_mean) / self.y_std

        # early stopping on 15% of the training grafts (inner split, still training data)
        idx = rng.permutation(len(train))
        n_in = max(1, int(round(0.15 * len(idx))))
        inner, fit_idx = idx[:n_in], idx[n_in:]
        net = self._net(static.shape[1])
        opt = torch.optim.Adam(net.parameters(), lr=self.lr, weight_decay=self.wd)
        T = lambda a: torch.from_numpy(np.ascontiguousarray(a))  # noqa: E731

        def loss_on(ix):
            pred = net(T(seq[ix]), T(static[ix]))
            target = T(y[ix])
            mask = ~torch.isnan(target)
            return ((pred - torch.nan_to_num(target)) ** 2)[mask].mean()

        best, best_state, wait = np.inf, None, 0
        for _ in range(self.epochs):
            net.train()
            opt.zero_grad()
            loss = loss_on(fit_idx)
            loss.backward()
            opt.step()
            net.eval()
            with torch.no_grad():
                v = float(loss_on(inner))
            if v < best - 1e-5:
                best, wait = v, 0
                best_state = {k: p.detach().clone() for k, p in net.state_dict().items()}
            else:
                wait += 1
                if wait >= self.patience:
                    break
        net.load_state_dict(best_state)
        net.eval()
        self.net = net
        return self

    def __getstate__(self):
        state = self.__dict__.copy()
        if "net" in state:
            state["net_config"] = self.net.config
            state["net_state"] = {k: v.numpy() for k, v in self.net.state_dict().items()}
            del state["net"]
        return state

    def __setstate__(self, state):
        import torch

        cfg, weights = state.pop("net_config", None), state.pop("net_state", None)
        self.__dict__.update(state)
        if cfg is not None:
            self.net = _LSTMNet(cfg["n_seq"], cfg["hidden"], cfg["n_static"], cfg["dropout"])
            self.net.load_state_dict({k: torch.from_numpy(v) for k, v in weights.items()})
            self.net.eval()

    def predict(self, t: pd.DataFrame) -> pd.DataFrame:
        import torch

        seq, static = self._arrays(t)
        with torch.no_grad():
            z = self.net(torch.from_numpy(seq), torch.from_numpy(static)).numpy()
        return _to_ecd(t, z * self.y_std + self.y_mean)
