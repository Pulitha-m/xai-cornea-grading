"""Explanation of one hybrid-model grade: TreeSHAP attributions and a SHAP-weighted image map.

SHAP. Path-dependent TreeSHAP (shap.TreeExplainer) on the Random Forest, in the
model's own input space: 64 preprocessed tabular columns and 32 PCA components of
the image embedding. Each value is the column's contribution to the share of
trees voting for the predicted grade, relative to the training average
(`baseline`); baseline + all contributions = the prediction exactly. Columns are
summed back to the 24 recorded inputs (a one-hot-encoded finding becomes one
input) and the 32 image components to one image contribution.

Image map. Grad-CAM needs the gradient of the class score with respect to the
last convolutional feature maps; a Random Forest has none. But everything between
those maps and the forest is linear: the 2048-d embedding is the spatial mean of
ResNet-50's layer4 maps, then standardised and projected by PCA (no whitening).
So each PCA score z_j is the mean over image locations of a per-location score
z_j(x, y), and component j's SHAP value phi_j is split over locations in
proportion to z_j(x, y) / z_j. The map M(x, y) = sum_j phi_j * z_j(x, y) / (z_j * HW)
sums to the components' SHAP values. Components with |z_j| below 0.1 of their
training standard deviation are left out (the proportions are unstable near 0);
`localisedShare` reports the share of the image attribution that is mapped. The
positive and negative parts are drawn as two overlays (regions that raised and
lowered the grade's share of votes), each scaled to its own maximum as for
Grad-CAM; `supportingTotal` and `opposingTotal` give their sizes.

This explains the model, not the cornea: it shows what the model relied on, which
may not be clinically meaningful. Its faithfulness has not been evaluated.
"""
import base64
import io
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

from pipelines.grading import hybrid

METHOD = "tree_shap_path_dependent"
MAP_METHOD = "shap_weighted_layer4_map"
MIN_SCORE_SD = 0.1
DISPLAY_SIZE = (648, 486)


@lru_cache
def load_explainer():
    """The TreeExplainer and, for each model column, the input it belongs to (a feature name or "image")."""
    import shap  # imported lazily: slow to import and only needed once a grade is explained

    pipeline, meta = hybrid.load_classifier()
    columns = pipeline.named_steps["features"].get_feature_names_out()
    owners = []
    for column in columns:
        group, _, rest = column.partition("__")
        if group == "image":
            owners.append("image")
            continue
        rest = rest.partition("__")[2]
        matches = [f for f in meta["features"] if rest == f or rest.startswith(f + "_")]
        if not matches:
            raise ValueError(f"Model column {column} does not belong to any input feature")
        owners.append(max(matches, key=len))
    return shap.TreeExplainer(pipeline.named_steps["classifier"]), np.asarray(owners)


def explain(values: dict, embedding: np.ndarray, maps: np.ndarray | None, schema: dict, grade: str,
            display_image: Image.Image) -> dict:
    """SHAP explanation of `grade` for this input; `maps` (2048 × h × w) enables the image map."""
    pipeline, meta = hybrid.load_classifier()
    transformer = pipeline.named_steps["features"]
    forest = pipeline.named_steps["classifier"]
    explainer, owners = load_explainer()

    row = transformer.transform(hybrid.to_frame(values, embedding, meta, schema))
    k = list(forest.classes_).index(grade)
    contributions = np.asarray(explainer.shap_values(row))[0][:, k]
    baseline = float(np.atleast_1d(explainer.expected_value)[k])

    features = [
        {"name": name, "value": values.get(name), "contribution": round(float(contributions[owners == name].sum()), 4)}
        for name in meta["features"]
    ]
    features.sort(key=lambda f: abs(f["contribution"]), reverse=True)
    image_contribution = float(contributions[owners == "image"].sum())

    return {
        "method": METHOD,
        "explainedGrade": grade,
        "baseline": round(baseline, 4),
        "prediction": round(baseline + float(contributions.sum()), 4),
        "features": features,
        "imageContribution": round(image_contribution, 4),
        "imageMap": None if maps is None else image_map(maps, contributions[owners == "image"], display_image),
        "message": "Contributions are to the share of trees voting for this grade, relative to the training "
                   "average. They explain the model, not the cornea, and are not causal. Specialist review required.",
    }


def location_scores(maps: np.ndarray) -> np.ndarray:
    """Per-location PCA scores z_j(x, y), shape (h, w, 32); their spatial mean is the model's PCA scores."""
    pipeline, _ = hybrid.load_classifier()
    image = pipeline.named_steps["features"].named_transformers_["image"]
    scaler, pca = image.named_steps["scaler"], image.named_steps["pca"]
    channels, height, width = maps.shape
    local = maps.reshape(channels, -1).T.astype(np.float64)
    scores = ((local - scaler.mean_) / scaler.scale_ - pca.mean_) @ pca.components_.T
    return scores.reshape(height, width, -1)


def attribution_map(maps: np.ndarray, phi: np.ndarray) -> tuple[np.ndarray, float]:
    """M(x, y) (h × w; sums to the mapped components' SHAP values) and the share of |phi| that is mapped."""
    pipeline, _ = hybrid.load_classifier()
    pca = pipeline.named_steps["features"].named_transformers_["image"].named_steps["pca"]
    local = location_scores(maps)
    # The model's PCA scores, in float64 (the model computes them in float32, equal to ~1e-7 relative).
    scores = local.mean(axis=(0, 1))
    mapped = np.abs(scores) >= MIN_SCORE_SD * np.sqrt(pca.explained_variance_)
    weights = np.where(mapped, phi / np.where(mapped, scores, 1.0), 0.0)
    total = np.abs(phi).sum()
    share = float(np.abs(phi[mapped]).sum() / total) if total > 0 else 1.0
    return (local @ weights) / (local.shape[0] * local.shape[1]), share


def image_map(maps: np.ndarray, phi: np.ndarray, display_image: Image.Image) -> dict:
    attribution, share = attribution_map(maps, phi)
    supporting, opposing = np.clip(attribution, 0, None), np.clip(-attribution, 0, None)
    return {
        "method": MAP_METHOD,
        "supportingPng": overlay_png(display_image, supporting),
        "opposingPng": overlay_png(display_image, opposing),
        "supportingTotal": round(float(supporting.sum()), 4),
        "opposingTotal": round(float(-opposing.sum()), 4),
        "localisedShare": round(share, 3),
    }


def overlay_png(image: Image.Image, heat: np.ndarray) -> str | None:
    """Base64 PNG: the image with `heat` scaled to its own maximum (jet, 40% opacity), as for Grad-CAM.
    Each map's strength is reported separately (supportingTotal / opposingTotal). None if all zero."""
    scale = float(heat.max())
    if scale <= 0:
        return None
    grey = np.asarray(image.convert("L").resize(DISPLAY_SIZE, Image.Resampling.BILINEAR), dtype=np.float32)
    heat = cv2.resize((heat / scale).astype(np.float32), DISPLAY_SIZE, interpolation=cv2.INTER_LINEAR)
    colour = cv2.applyColorMap(np.uint8(np.clip(heat, 0, 1) * 255), cv2.COLORMAP_JET)[:, :, ::-1].astype(np.float32)
    blended = np.uint8(np.clip(0.6 * grey[:, :, np.newaxis] + 0.4 * colour, 0, 255))
    buffer = io.BytesIO()
    Image.fromarray(blended, mode="RGB").save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")
