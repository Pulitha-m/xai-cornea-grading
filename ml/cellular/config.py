"""
Configuration loader for Component 3 (Corneal Cellular Intelligence Platform).

Reads ``config.yaml`` and returns a plain dict in which every entry under
``paths`` has been turned into an absolute ``pathlib.Path``.

Why this module exists
----------------------
The same code must run on a laptop (data in ``ml/cellular/data``) and on Colab
(data copied to ``/content/data``, outputs saved to Google Drive). Instead of
editing paths per machine, set environment variables before running:

    CELLULAR_DATA_ROOT    overrides paths.data_root
    CELLULAR_OUTPUT_ROOT  overrides paths.outputs_dir
    CELLULAR_MODELS_ROOT  overrides paths.models_dir
    CELLULAR_ANNOT_ROOT   overrides paths.annotations_dir

Usage
-----
Run scripts from ``ml/cellular/`` so this module is importable as ``config``::

    from config import load_config
    cfg = load_config()
    images_dir = cfg["paths"]["images_dir"]

Quick check (prints the resolved config)::

    python config.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# Folder that contains this file, i.e. ml/cellular/. All relative paths in
# config.yaml are resolved against it, regardless of the current directory.
COMPONENT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE = COMPONENT_ROOT / "config.yaml"

# config key -> environment variable that may override it
_ENV_OVERRIDES = {
    "data_root": "CELLULAR_DATA_ROOT",
    "outputs_dir": "CELLULAR_OUTPUT_ROOT",
    "models_dir": "CELLULAR_MODELS_ROOT",
    "annotations_dir": "CELLULAR_ANNOT_ROOT",
}

# Keys whose values are relative to data_root rather than to COMPONENT_ROOT.
_DATA_RELATIVE_KEYS = ("images_dir", "ground_truth_xlsx")


def _resolve(path_value: str | os.PathLike, base: Path) -> Path:
    """Return an absolute path; relative values are joined onto ``base``."""
    p = Path(path_value).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def load_config(config_file: str | os.PathLike | None = None) -> dict[str, Any]:
    """
    Load ``config.yaml`` and resolve all paths.

    Parameters
    ----------
    config_file:
        Optional alternative YAML file (e.g. for experiments). Defaults to
        ``ml/cellular/config.yaml``.

    Returns
    -------
    dict
        The parsed config. ``cfg["paths"][...]`` values are absolute ``Path``s.
    """
    config_file = Path(config_file) if config_file else DEFAULT_CONFIG_FILE
    with open(config_file, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    raw_paths = dict(cfg.get("paths", {}))

    # 1) Apply environment-variable overrides (e.g. on Colab).
    for key, env_var in _ENV_OVERRIDES.items():
        if os.environ.get(env_var):
            raw_paths[key] = os.environ[env_var]

    # 2) data_root first, because other data paths hang off it.
    data_root = _resolve(raw_paths.get("data_root", "data"), COMPONENT_ROOT)

    resolved: dict[str, Path] = {"data_root": data_root}
    for key, value in raw_paths.items():
        if key == "data_root":
            continue
        base = data_root if key in _DATA_RELATIVE_KEYS else COMPONENT_ROOT
        resolved[key] = _resolve(value, base)

    cfg["paths"] = resolved
    return cfg


def ensure_output_dirs(cfg: dict[str, Any]) -> None:
    """Create the writable folders (splits, outputs, models) if missing."""
    for key in ("splits_dir", "outputs_dir", "models_dir"):
        if key in cfg["paths"]:
            cfg["paths"][key].mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    # Sanity check: show resolved paths and whether the inputs exist.
    cfg = load_config()
    print(f"Component root: {COMPONENT_ROOT}")
    for name, path in cfg["paths"].items():
        print(f"  {name:18s} {'OK     ' if path.exists() else 'MISSING'} {path}")
    print(f"Split seed: {cfg['split']['seed']}  |  um_per_px: {cfg['scale']['um_per_px']}")
