"""The v2 disease and severity models (DenseNet121 image + numbers fusion), served with onnxruntime.

Ported from ml/disease-new/notebooks/10_Inference_Final_Models_v2.ipynb:
- image: greyscale -> (optional CLAHE) -> resize 384 x 288 (PIL bilinear, as torchvision
  Resize on a PIL image) -> 3 channels -> ImageNet normalisation;
- numbers: ECD, ECD_Deficit = max(0, 2500 - ECD), SD, CV, HEX %, donor age -> training
  median for missing values -> training standardisation;
- prediction: mean of the sigmoid outputs for the image and its horizontal flip;
- Grad-CAM of the disease model's DenseNet `features` layer on the unflipped image,
  computed inside the ONNX graph (see export_onnx_models.py).
"""
import base64
import io
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

from pipelines.disease.config import checked_file, load_config


@dataclass
class Models:
    disease: object       # onnxruntime.InferenceSession
    severity: object
    ood_reference: np.ndarray  # (n_train, 1024) L2-normalised training embeddings


@dataclass
class Prediction:
    disease_probabilities: np.ndarray   # (5,)
    severity_probabilities: np.ndarray  # (n_heads,)
    cams: np.ndarray                    # (5, h, w), unflipped image, before resizing
    embedding: np.ndarray               # (1024,), unflipped image, L2-normalised


@lru_cache
def load_models() -> Models:
    """Both ONNX sessions and the unusual-image reference; loaded once per process."""
    config = load_config()
    disease_path = checked_file(config["models"]["disease"]["file"], config["models"]["disease"]["sha256"])
    severity_path = checked_file(config["models"]["severity"]["file"], config["models"]["severity"]["sha256"])
    ood_path = checked_file(config["ood"]["file"], config["ood"]["sha256"])

    import onnxruntime as ort

    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = ["CPUExecutionProvider"]
    with np.load(ood_path) as ood:
        reference = ood["ref"].astype(np.float32)
    return Models(
        disease=ort.InferenceSession(str(disease_path), options, providers=providers),
        severity=ort.InferenceSession(str(severity_path), options, providers=providers),
        ood_reference=reference,
    )


def prepare(gray: np.ndarray) -> np.ndarray:
    """notebook prepare_raw(): the raw greyscale image, or CLAHE on a 512 x 384 copy if enabled."""
    image = load_config()["image"]
    if not image["apply_clahe"]:
        return gray
    clahe = image["clahe"]
    clahe_op = cv2.createCLAHE(clipLimit=clahe["clip_limit"], tileGridSize=tuple(clahe["tile_grid_size"]))
    return clahe_op.apply(cv2.resize(gray, (clahe["prep_width"], clahe["prep_height"]), interpolation=cv2.INTER_AREA))


def to_tensor(prepared: np.ndarray) -> np.ndarray:
    """notebook TF_EVAL: (1, 3, 288, 384) float32."""
    image = load_config()["image"]
    resized = Image.fromarray(prepared, mode="L").resize(
        (image["input_width"], image["input_height"]), Image.Resampling.BILINEAR)
    pixels = np.asarray(resized, dtype=np.float32) / 255.0
    mean = np.asarray(image["imagenet_mean"], dtype=np.float32).reshape(3, 1, 1)
    std = np.asarray(image["imagenet_std"], dtype=np.float32).reshape(3, 1, 1)
    rgb = np.repeat(pixels[np.newaxis], 3, axis=0)
    return ((rgb - mean) / std)[np.newaxis].astype(np.float32)


def feature_row(values: dict) -> dict:
    """The six model inputs by name, with the derived ECD_Deficit (None = not recorded)."""
    config = load_config()
    ecd = values.get("ECD_CD_cells_per_mm2")
    row = dict(values)
    row["ECD_Deficit"] = None if ecd is None else max(0.0, config["ecd_deficit_reference"] - ecd)
    return {name: row.get(name) for name in config["features"]}


def scale_numbers(values: dict) -> np.ndarray:
    """notebook make_tab(): median imputation and standardisation fitted on the training rows."""
    config = load_config()
    row = feature_row(values)
    raw = np.asarray([np.nan if row[n] is None else float(row[n]) for n in config["features"]], dtype=np.float64)
    filled = np.where(np.isnan(raw), np.asarray(config["imputer_median"]), raw)
    scaled = (filled - np.asarray(config["scaler_mean"])) / np.asarray(config["scaler_scale"])
    return scaled.astype(np.float32)[np.newaxis]


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x.astype(np.float64)))


def predict(prepared: np.ndarray, tab: np.ndarray) -> Prediction:
    models = load_models()
    x = to_tensor(prepared)
    batch = np.concatenate([x, x[:, :, :, ::-1]], axis=0).copy()   # image and horizontal flip
    tabs = np.repeat(tab, 2, axis=0)

    logits, cams, embedding = models.disease.run(None, {"image": batch, "tab": tabs})
    _, severity_logits = models.severity.run(None, {"image": batch, "tab": tabs})
    return Prediction(
        disease_probabilities=sigmoid(logits).mean(axis=0),
        severity_probabilities=sigmoid(severity_logits).mean(axis=0),
        cams=cams[0],
        embedding=embedding[0],
    )


def unusual_distance(embedding: np.ndarray) -> float:
    """notebook knn_distance(): 1 - mean cosine similarity of the k nearest training images."""
    k = load_config()["ood"]["k"]
    similarities = load_models().ood_reference @ embedding.astype(np.float32)
    return float(1 - np.sort(similarities)[-k:].mean())


def gradcam_map(cam: np.ndarray) -> np.ndarray:
    """notebook gradcam(): resized to the model input size and scaled to [0, 1]."""
    image = load_config()["image"]
    cam = cv2.resize(cam.astype(np.float32), (image["input_width"], image["input_height"]))
    return (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)


def overlay_png(prepared: np.ndarray, cam: np.ndarray) -> str:
    """Base64 PNG of the input image with the Grad-CAM heat map (jet, 40% opacity), as in the notebook."""
    image = load_config()["image"]
    display = cv2.resize(prepared, (image["input_width"], image["input_height"]))
    heat = cv2.applyColorMap(np.uint8(np.clip(gradcam_map(cam), 0, 1) * 255), cv2.COLORMAP_JET)[:, :, ::-1]
    grey = np.repeat(display[:, :, np.newaxis], 3, axis=2).astype(np.float32)
    blended = np.uint8(np.clip(0.6 * grey + 0.4 * heat.astype(np.float32), 0, 255))
    buffer = io.BytesIO()
    Image.fromarray(blended, mode="RGB").save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")
