"""SHAP values of the CellChek numbers for the v2 disease and severity outputs.

Exact Shapley values (all 2^5 coalitions) of the five inputs ECD (with its derived
ECD_Deficit, one player), SD, CV, HEX % and donor age. The image is held fixed: the
backbone features of the image and its flip are computed once (model.predict) and only
the layers after the backbone are re-run here, with the weights exported by
ml/disease-new/scripts/export_onnx_models.py.

An input left out of a coalition takes its training median, the value the model uses
when it is not recorded, so a value that was not recorded contributes exactly 0. The
explained output is the served probability (mean of the image and flip sigmoid), so the
contributions add up to probability(these values) - probability(typical values).
"""
from itertools import combinations
from math import factorial

import numpy as np

from pipelines.disease import model
from pipelines.disease.checks import MEASUREMENTS
from pipelines.disease.config import load_config

# Players and the columns of the scaled number vector each one sets.
PLAYERS = {
    "ECD_CD_cells_per_mm2": ("ECD_CD_cells_per_mm2", "ECD_Deficit"),
    "SD": ("SD",),
    "CV": ("CV",),
    "HEX_percent": ("HEX_percent",),
    "Donor_Age": ("Donor_Age",),
}


def _relu(a):
    return np.maximum(a, 0.0)


def _dense(h, x, name):
    return x @ h[f"{name}_w"].T + h[f"{name}_b"]


def head_probabilities(pooled_disease: np.ndarray, pooled_severity: np.ndarray, tabs: np.ndarray):
    """Probabilities (mean over image and flip) for each row of scaled numbers.

    pooled_*: (2, 1024); tabs: (n, 6). Returns disease (n, 5) and severity (n, n_heads).
    """
    h = load_models_heads()
    n = tabs.shape[0]
    tab = np.repeat(tabs.astype(np.float64), 2, axis=0)                  # rows: t0 img, t0 flip, t1 img, ...
    dis_feat = np.tile(pooled_disease.astype(np.float64), (n, 1))
    sev_feat = np.tile(pooled_severity.astype(np.float64), (n, 1))

    t = _relu(_dense(h, _relu(_dense(h, tab, "dis_tab1")), "dis_tab2"))
    dis = _dense(h, _relu(_dense(h, np.concatenate([dis_feat, t], 1), "dis_head1")), "dis_head2")
    t = _relu(_dense(h, _relu(_dense(h, tab, "sev_tab1")), "sev_tab2"))
    sev = _dense(h, _relu(_dense(h, np.concatenate([sev_feat, t], 1), "sev_shared")), "sev_severity")
    to_prob = lambda logits: model.sigmoid(logits).reshape(n, 2, -1).mean(axis=1)
    return to_prob(dis), to_prob(sev)


def load_models_heads() -> dict:
    return model.load_models().heads


def explain_numbers(values: dict, prediction: model.Prediction) -> dict:
    """SHAP values per output: {"disease": {code: {...}}, "severity": {head: {...}}}."""
    config = load_config()
    features = config["features"]
    players = list(PLAYERS)
    n = len(players)

    actual = model.scale_numbers(values)[0].astype(np.float64)
    baseline = ((np.asarray(config["imputer_median"]) - np.asarray(config["scaler_mean"]))
                / np.asarray(config["scaler_scale"]))
    columns = {p: [features.index(c) for c in PLAYERS[p]] for p in players}
    for p in players:  # not recorded = the training median exactly (no float32 rounding)
        if values.get(p) is None:
            actual[columns[p]] = baseline[columns[p]]

    coalitions = [frozenset(c) for k in range(n + 1) for c in combinations(range(n), k)]
    tabs = np.tile(baseline, (len(coalitions), 1))
    for row, coalition in enumerate(coalitions):
        for i in coalition:
            tabs[row, columns[players[i]]] = actual[columns[players[i]]]
    dis, sev = head_probabilities(prediction.pooled_disease, prediction.pooled_severity, tabs)
    index = {c: row for row, c in enumerate(coalitions)}

    def shapley(outputs: np.ndarray) -> np.ndarray:       # outputs: (n_coalitions, k) -> (n_players, k)
        phi = np.zeros((n, outputs.shape[1]))
        for i in range(n):
            for coalition in coalitions:
                if i in coalition:
                    continue
                weight = factorial(len(coalition)) * factorial(n - len(coalition) - 1) / factorial(n)
                phi[i] += weight * (outputs[index[coalition | {i}]] - outputs[index[coalition]])
        return phi

    empty, full = index[frozenset()], index[frozenset(range(n))]

    def describe(outputs: np.ndarray, phi: np.ndarray, k: int) -> dict:
        return {
            "baseline": float(outputs[empty, k]),
            "prediction": float(outputs[full, k]),
            "values": [{
                "input": p,
                "value": values.get(p),
                "imputed": values.get(p) is None,
                "contribution": float(phi[i, k]),
            } for i, p in enumerate(players)],
        }

    phi_dis, phi_sev = shapley(dis), shapley(sev)
    return {
        "disease": {c: describe(dis, phi_dis, k) for k, c in enumerate(config["diseases"])},
        "severity": {h: describe(sev, phi_sev, k) for k, h in enumerate(config["severity_heads"])},
    }


assert list(PLAYERS) == list(MEASUREMENTS), "SHAP players must follow the measurement order"
