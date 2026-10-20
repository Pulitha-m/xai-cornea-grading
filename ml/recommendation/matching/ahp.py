"""AHP (Analytic Hierarchy Process): turn clinicians' pairwise judgements into MCDA weights.

Each clinician compares every pair of the five criteria ("which matters more, and how
much, on 1-9?"). From the answers we build a pairwise matrix, take its principal
eigenvector as the weights, and check consistency (CR < 0.10 is acceptable).
Several clinicians are combined with the element-wise geometric mean of their matrices
(aggregation of individual judgements, the usual group-AHP method).
"""
import re
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

CRITERIA = ["grade_fit", "endothelium", "serology", "freshness", "surgery_compatibility"]
LABEL = {"grade_fit": "Tissue grade match (A+/A/B)", "endothelium": "Endothelial quality (ECD/CV/HEX)",
         "serology": "Serology status", "freshness": "Storage duration (freshness)",
         "surgery_compatibility": "Surgery compatibility"}
PAIRS = list(combinations(CRITERIA, 2))       # 10 pairs for 5 criteria
RANDOM_INDEX = {3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32}  # Saaty


def matrix(answers: dict[tuple[str, str], tuple[str, float]]) -> np.ndarray:
    """answers[(a, b)] = ("A" | "B" | "Equal", strength 1-9)."""
    n = len(CRITERIA)
    m = np.ones((n, n))
    for (a, b), (winner, strength) in answers.items():
        i, j = CRITERIA.index(a), CRITERIA.index(b)
        s = 1.0 if str(winner).strip().lower().startswith("e") else float(strength)
        if not 1 <= s <= 9:
            raise ValueError(f"Strength for {a} vs {b} must be 1-9, got {strength}")
        v = s if str(winner).strip().upper().startswith("A") or s == 1 else 1 / s
        m[i, j], m[j, i] = v, 1 / v
    return m


def weights_and_cr(m: np.ndarray) -> tuple[dict[str, float], float]:
    vals, vecs = np.linalg.eig(m)
    k = int(np.argmax(vals.real))
    w = np.abs(vecs[:, k].real)
    w = w / w.sum()
    n = m.shape[0]
    ci = (vals[k].real - n) / (n - 1)
    cr = ci / RANDOM_INDEX[n]
    return dict(zip(CRITERIA, w.round(4))), float(round(cr, 4))


def combine(matrices: list[np.ndarray]) -> np.ndarray:
    """Group judgement: element-wise geometric mean of the clinicians' matrices."""
    return np.exp(np.mean([np.log(m) for m in matrices], axis=0))


def read_form(xlsx: Path, sheet: str = "1_AHP") -> list[dict]:
    """Read the filled AHP sheet of the meeting pack: one answer set per clinician."""
    df = pd.read_excel(xlsx, sheet_name=sheet, header=2)
    sets = []
    for k in range(1, 4):
        win, strength = f"Clinician {k}: more important", f"Clinician {k}: how much (1-9)"
        if win not in df or df[win].isna().all():
            continue
        answers = {}
        for (a, b), (_, row) in zip(PAIRS, df.iterrows()):
            if pd.isna(row[win]):
                raise ValueError(f"Clinician {k} left '{LABEL[a]} vs {LABEL[b]}' blank")
            answers[(a, b)] = (str(row[win]), 1 if pd.isna(row[strength]) else row[strength])
        sets.append(answers)
    if not sets:
        raise ValueError("No answers found in the AHP sheet")
    return sets


def apply_to_config(config_file: Path, weights: dict[str, float], version: str) -> None:
    """Replace the MCDA weights and weights_version in config.yaml, keeping comments."""
    text = config_file.read_text(encoding="utf-8")
    text = re.sub(r"(weights_version:\s*)\S+", rf"\g<1>{version}", text)
    for k, v in weights.items():
        text = re.sub(rf"(\n\s+{k}:\s*)[0-9.]+", rf"\g<1>{v}", text, count=1)
    config_file.write_text(text, encoding="utf-8")
