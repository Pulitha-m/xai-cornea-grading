"""P5 risk models: tree-based and neural survival models, same interface as CoxPH.

Interface (all models): fit(X, time, event), predict_risk(X) (higher = higher hazard),
predict_survival(X, tau) = S(tau | x). X is already scaled (FollowupPreprocessor).

  GradientBoostedCox  LightGBM trees trained on the Cox partial likelihood (custom
                      objective, Breslow ties): a tree-based survival model that needs no
                      extra library
  DeepSurv            Katzman et al. (2018): a small neural network whose output is the
                      log-hazard, trained on the Cox partial likelihood, with dropout,
                      weight decay and early stopping on an inner split of the training data

Both turn their risk score into survival probabilities with a Breslow baseline hazard
estimated on the training grafts.
"""
import numpy as np


def breslow(time, event, risk_score):
    """Baseline cumulative hazard at each event time, given exp(risk score) per graft."""
    t, e = np.asarray(time, float), np.asarray(event, bool)
    w = np.exp(np.asarray(risk_score, float))
    times = np.unique(t[e])
    dH = np.array([((t == u) & e).sum() / w[t >= u].sum() for u in times])
    return times, np.cumsum(dH)


def survival_from(times, cumhaz, risk_score, tau):
    idx = np.searchsorted(times, tau, side="right") - 1
    h0 = cumhaz[idx] if idx >= 0 else 0.0
    return np.exp(-h0 * np.exp(np.asarray(risk_score, float)))


# ---------------------------------------------------------------- gradient-boosted Cox
def _cox_grad_hess(f, time, event):
    """Gradient and Hessian of the negative Cox partial log-likelihood w.r.t. scores f."""
    t, e = np.asarray(time, float), np.asarray(event, bool)
    w = np.exp(f - f.max())
    times = np.unique(t[e])
    d = np.array([((t == u) & e).sum() for u in times], float)
    order = np.argsort(t)
    ts, ws = t[order], w[order]
    at_risk = ws[::-1].cumsum()[::-1]                         # sum of w over t_j >= ts[i]
    S = at_risk[np.searchsorted(ts, times, side="left")]
    c1, c2 = np.cumsum(d / S), np.cumsum(d / S ** 2)
    k = np.searchsorted(times, t, side="right") - 1           # last event time <= t_i
    a = np.where(k >= 0, c1[np.clip(k, 0, None)], 0.0)
    b = np.where(k >= 0, c2[np.clip(k, 0, None)], 0.0)
    grad = w * a - e
    hess = np.maximum(w * a - w ** 2 * b, 1e-6)
    return grad, hess


class GradientBoostedCox:
    name = "Gradient-boosted Cox (LightGBM)"

    def __init__(self, n_estimators: int = 150, learning_rate: float = 0.03, num_leaves: int = 4,
                 min_child_samples: int = 20, seed: int = 42):
        self.params = dict(n_estimators=n_estimators, learning_rate=learning_rate, num_leaves=num_leaves,
                           min_child_samples=min_child_samples, subsample=0.8, subsample_freq=1,
                           colsample_bytree=0.8, reg_lambda=1.0, random_state=seed, verbose=-1)

    def fit(self, X, time, event) -> "GradientBoostedCox":
        from lightgbm import LGBMRegressor

        t, e = np.asarray(time, float), np.asarray(event, bool)
        y = np.where(e, t, -t)                                # sign carries the event flag

        def objective(y_true, y_pred):
            return _cox_grad_hess(y_pred, np.abs(y_true), y_true > 0)

        self.model = LGBMRegressor(objective=objective, **self.params).fit(np.asarray(X, float), y)
        self.base_times, self.base_cumhaz = breslow(t, e, self.predict_risk(X))
        return self

    def predict_risk(self, X):
        return self.model.predict(np.asarray(X, float), raw_score=True)

    def predict_survival(self, X, tau):
        return survival_from(self.base_times, self.base_cumhaz, self.predict_risk(X), tau)


# ---------------------------------------------------------------- DeepSurv
def _deepsurv_net(n_in: int, hidden: tuple, dropout: float):
    from torch import nn

    layers, prev = [], n_in
    for h in hidden:
        layers += [nn.Linear(prev, h), nn.ReLU(), nn.Dropout(dropout)]
        prev = h
    layers.append(nn.Linear(prev, 1, bias=False))
    return nn.Sequential(*layers)


def _neg_partial_loglik(risk, time, event):
    """Negative Cox partial log-likelihood (Breslow), averaged over events (torch)."""
    import torch

    order = torch.argsort(time, descending=True)
    r, e, ts = risk[order], event[order], time[order].numpy()
    log_cum = torch.logcumsumexp(r, dim=0)
    # Breslow ties: everyone with the same time is in the risk set -> use the last tied position
    last = np.searchsorted(-ts, -ts, side="right") - 1
    log_cum = log_cum[torch.from_numpy(last)]
    n_events = e.sum().clamp(min=1)
    return -((r - log_cum) * e).sum() / n_events


class DeepSurv:
    name = "DeepSurv (neural network)"

    def __init__(self, hidden=(32, 16), dropout: float = 0.2, lr: float = 0.005, weight_decay: float = 1e-3,
                 epochs: int = 500, patience: int = 50, seed: int = 42):
        self.hidden, self.dropout, self.lr, self.wd = tuple(hidden), dropout, lr, weight_decay
        self.epochs, self.patience, self.seed = epochs, patience, seed

    def fit(self, X, time, event) -> "DeepSurv":
        import torch

        torch.manual_seed(self.seed)
        rng = np.random.default_rng(self.seed)
        X = np.asarray(X, np.float32)
        t, e = np.asarray(time, np.float32), np.asarray(event, bool)
        # inner split for early stopping, stratified by event so both parts have events
        inner = np.zeros(len(X), bool)
        for flag in (True, False):
            idx = np.where(e == flag)[0]
            rng.shuffle(idx)
            inner[idx[: max(1, int(round(0.15 * len(idx))))]] = True
        T = lambda a: torch.from_numpy(np.ascontiguousarray(a))  # noqa: E731
        Xf, tf, ef = T(X[~inner]), T(t[~inner]), T(e[~inner].astype(np.float32))
        Xi, ti, ei = T(X[inner]), T(t[inner]), T(e[inner].astype(np.float32))

        net = _deepsurv_net(X.shape[1], self.hidden, self.dropout)
        opt = torch.optim.Adam(net.parameters(), lr=self.lr, weight_decay=self.wd)
        best, best_state, wait = np.inf, None, 0
        for _ in range(self.epochs):
            net.train()
            opt.zero_grad()
            loss = _neg_partial_loglik(net(Xf).squeeze(1), tf, ef)
            loss.backward()
            opt.step()
            net.eval()
            with torch.no_grad():
                v = float(_neg_partial_loglik(net(Xi).squeeze(1), ti, ei))
            if v < best - 1e-5:
                best, wait = v, 0
                best_state = {k: p.detach().clone() for k, p in net.state_dict().items()}
            else:
                wait += 1
                if wait >= self.patience:
                    break
        net.load_state_dict(best_state)
        net.eval()
        self.net, self.n_in = net, X.shape[1]
        self.base_times, self.base_cumhaz = breslow(t, e, self.predict_risk(X))
        return self

    def predict_risk(self, X):
        import torch

        with torch.no_grad():
            return self.net(torch.from_numpy(np.asarray(X, np.float32))).squeeze(1).numpy().astype(float)

    def predict_survival(self, X, tau):
        return survival_from(self.base_times, self.base_cumhaz, self.predict_risk(X), tau)

    def __getstate__(self):
        state = self.__dict__.copy()
        if "net" in state:
            state["net_state"] = {k: v.numpy() for k, v in self.net.state_dict().items()}
            del state["net"]
        return state

    def __setstate__(self, state):
        import torch

        weights = state.pop("net_state", None)
        self.__dict__.update(state)
        if weights is not None:
            self.net = _deepsurv_net(self.n_in, self.hidden, self.dropout)
            self.net.load_state_dict({k: torch.from_numpy(v) for k, v in weights.items()})
            self.net.eval()
