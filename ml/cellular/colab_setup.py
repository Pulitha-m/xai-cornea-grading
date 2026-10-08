"""
One-line environment setup for Component 3 notebooks.

On Colab, put this as the FIRST cell of every notebook (works after any restart):

    from google.colab import drive; drive.mount("/content/drive")
    %run "/content/drive/MyDrive/Colab Notebooks/Research_Project/xai-cornea-grading/ml/cellular/colab_setup.py"

What it does
------------
Colab:  pulls the latest code, copies images + ground truth to the fast local
        disk (once per session), sets the CELLULAR_* environment variables that
        config.py reads, changes directory to ml/cellular and makes it importable.
Local:  only changes directory to ml/cellular and makes it importable.

Variables left in the notebook: IN_COLAB, COMPONENT_DIR, RESEARCH, REPO_DIR, LOCAL_DATA.

Note: the file runs *before* it pulls, so a change to colab_setup.py itself takes
effect from the next run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Google Drive layout (see the Colab setup steps).
RESEARCH = "/content/drive/MyDrive/Colab Notebooks/Research_Project"
REPO_DIR = f"{RESEARCH}/xai-cornea-grading"
LOCAL_DATA = "/content/data"                       # fast local disk on the Colab VM
OUTPUT_ROOT = f"{RESEARCH}/cellular_outputs"        # persistent results on Drive
MODELS_ROOT = f"{RESEARCH}/cellular_models"         # persistent checkpoints on Drive


def _in_colab() -> bool:
    try:
        import google.colab  # noqa: F401
        return True
    except ImportError:
        return False


def _run(cmd: list[str]) -> None:
    """Run a shell command, echoing it; failures are reported but not fatal."""
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    out = (result.stdout + result.stderr).strip()
    if out:
        print(out)


def setup(pull: bool = True, copy_data: bool = True) -> Path:
    """Prepare the session and return the ml/cellular directory."""
    if _in_colab():
        if not Path("/content/drive/MyDrive").exists():
            from google.colab import drive
            drive.mount("/content/drive")

        if pull:
            _run(["git", "-C", REPO_DIR, "pull", "--ff-only"])

        images_local = Path(LOCAL_DATA, "Finalized_images")
        if copy_data and not images_local.exists():
            print("Copying images to local disk (1-2 min, once per session)...")
            Path(LOCAL_DATA).mkdir(parents=True, exist_ok=True)
            _run(["cp", "-r", f"{RESEARCH}/Finalized_images", LOCAL_DATA])
            _run(["cp", f"{RESEARCH}/validation_ground_truth_dataset.xlsx", LOCAL_DATA])

        os.environ["CELLULAR_DATA_ROOT"] = LOCAL_DATA
        os.environ["CELLULAR_OUTPUT_ROOT"] = OUTPUT_ROOT
        os.environ["CELLULAR_MODELS_ROOT"] = MODELS_ROOT
        component = Path(REPO_DIR, "ml", "cellular")
    else:
        component = Path(__file__).resolve().parent

    os.chdir(component)
    if str(component) not in sys.path:
        sys.path.insert(0, str(component))

    n_images = len(list(Path(os.environ.get("CELLULAR_DATA_ROOT", component / "data"),
                              "Finalized_images").glob("*")))
    print(f"Component dir : {component}")
    print(f"Images found  : {n_images}")
    return component


IN_COLAB = _in_colab()
COMPONENT_DIR = setup()
