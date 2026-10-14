"""
End-to-end pipeline for Component 3 (Corneal Cellular Intelligence Platform).

Placeholder created in Phase 0 — stages are implemented in later phases:

    3.1  roi/           Automatic ROI selection        (Phase 6)
    3.2  segmentation/  U-Net cell boundary detection  (Phase 2)
    3.3  extraction/    Individual cell measurement    (Phase 3)
    3.4  biomarkers/    ECD, CV, HEX%, compactness     (Phase 5)

Data handoff between stages (from the research scope):

    image --3.1--> ROI mask + quality score
          --3.2--> binary boundary mask
          --3.3--> labelled cell map + per-cell CSV
          --3.4--> biomarker JSON + report
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run(image_path: str | Path) -> dict[str, Any]:
    """
    Analyse one specular microscopy image.

    Returns (once implemented) a dict with the ROI, the per-cell table and the
    biomarkers. Raises ``NotImplementedError`` until Phases 2–6 are complete.
    """
    raise NotImplementedError(
        "Pipeline stages are added in Phases 2-6; see the module docstring."
    )
