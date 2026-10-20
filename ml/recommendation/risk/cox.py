"""Cox proportional-hazards model with a ridge penalty (P3 risk baseline).

Small, dependency-free version (numpy + scipy) so the same code runs in research and,
later, in the ML service. Ties are handled with Breslow's method. Inputs are expected
to be already scaled (FollowupPreprocessor), so one penalty strength fits all features.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize


@dataclass
class CoxPH:
    penalty: float = 1.0
    coef: np.ndarray = field(default=None, repr=False)
    base_times: np.ndarray = field(default=None, repr=False)
    base_cumhaz: np.ndarray = field(default=None, repr=False)
    features: list = field(default_factory=list)

    def fit(self, X, time, event) -> "CoxPH":
        X = np.asarray(X, float)
        t, e = np.asarray(time, float), np.asarray(event, bool)
        order = np.argsort(-t, kind="stable")          # descending time: risk sets are prefixes
        Xs, ts, es = X[order], t[order], e[order]
        lam = self.penalty

        def nll(beta):
            eta = Xs @ beta
            m = eta.max()
            w = np.exp(eta - m)
            cum_w = np.cumsum(w)
            cum_wx = np.cumsum(w[:, None] * Xs, axis=0)
            # Breslow: for tied times use the risk set of the last (smallest-index-in-desc) row with that time
            last = np.searchsorted(-ts, -ts, side="right") - 1
            log_risk = np.log(cum_w[last]) + m
            ll = (eta[es] - log_risk[es]).sum()
            grad = (Xs[es] - cum_wx[last][es] / cum_w[last][es, None]).sum(axis=0)
            return -ll + 0.5 * lam * beta @ beta, -grad + lam * beta

        res = minimize(nll, np.zeros(X.shape[1]), jac=True, method="L-BFGS-B")
        self.coef = res.x
        # Breslow baseline cumulative hazard
        risk = np.exp(X @ self.coef)
        times = np.unique(t[e])
        dH = [((t == u) & e).sum() / risk[t >= u].sum() for u in times]
        self.base_times, self.base_cumhaz = times, np.cumsum(dH)
        return self

    def predict_risk(self, X) -> np.ndarray:
        """Linear predictor; higher = higher hazard."""
        return np.asarray(X, float) @ self.coef

    def predict_survival(self, X, tau: float) -> np.ndarray:
        """S(tau | x) = exp(-H0(tau) * exp(x'beta))."""
        idx = np.searchsorted(self.base_times, tau, side="right") - 1
        h0 = self.base_cumhaz[idx] if idx >= 0 else 0.0
        return np.exp(-h0 * np.exp(self.predict_risk(X)))

    def to_dict(self) -> dict:
        return {"penalty": self.penalty, "coef": self.coef.tolist(), "features": list(self.features),
                "base_times": self.base_times.tolist(), "base_cumhaz": self.base_cumhaz.tolist()}
