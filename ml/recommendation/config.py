"""Load config.yaml, with optional environment-variable overrides.

Override any nested key with REC_<SECTION>__<KEY>, for example:
    REC_SPLIT__SEED=7
    REC_PATHS__RAW_WORKBOOK=/data/nebsl.xlsx
"""
import os
from pathlib import Path

import yaml

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = MODULE_DIR / "config.yaml"
ENV_PREFIX = "REC_"


def _cast(value: str):
    for conv in (int, float):
        try:
            return conv(value)
        except ValueError:
            pass
    return value


def _apply_env(cfg: dict) -> dict:
    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        parts = key[len(ENV_PREFIX):].lower().split("__")
        node = cfg
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = _cast(value)
    return cfg


def load_config(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_CONFIG) as f:
        cfg = yaml.safe_load(f)
    cfg = _apply_env(cfg)
    # resolve relative paths against the module folder
    cfg["paths"] = {k: str((MODULE_DIR / v).resolve()) if not Path(v).is_absolute() else v
                    for k, v in cfg["paths"].items()}
    return cfg
