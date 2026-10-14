"""
Sub-component 3.1 — Automatic ROI Selection (Phase 6).

Scores overlapping image patches with a lightweight CNN (MobileNetV2 /
EfficientNet-B0) and selects the best contiguous analysable region.

Output: binary ROI mask (.npy) + quality score and exclusion log (.json).
"""
