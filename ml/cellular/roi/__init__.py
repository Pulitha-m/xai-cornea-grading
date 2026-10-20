"""
Sub-component 3.1 — Automatic ROI Selection (Phase 6).

Tiles are classified analysable vs poor (lit-area rule, quality features +
logistic regression, or a fine-tuned EfficientNet-B0 — chosen by a
pre-registered cross-validation rule, roi/run.py); window scores are averaged
into a probability map and thresholded inside the lit area (roi/roimap.py).
All analysable regions form the ROI.

Output: binary ROI mask (.png) per image + quality score (roi_<split>.csv).
"""
