"""Train and evaluate the corneal-image domain validator.

Question answered: is an uploaded image a specular microscopy image of the
corneal endothelium (like the training images), or something else?
It does NOT assess image quality, cell visibility or disease.

Design (fixed before any scores were inspected):
- Positives: the de-duplicated specular microscopy images in
  clean_image_manifest.csv, split 60/20/20 by inferred donor so fellow eyes
  never cross splits.
- Negatives: COCO val2017 photographs (people, animals, vehicles, buildings,
  landscapes, indoor scenes, food) plus synthetic documents and screenshots,
  split 60/20/20 at random.
- Every image is converted to greyscale (pipelines/image/preprocess.py), so
  colour cannot be used as a shortcut.
- Features: ImageNet ResNet-18 (torchvision IMAGENET1K_V1), exported to ONNX
  and run with onnxruntime, i.e. the same backbone the service uses.
- Classifier: StandardScaler + LogisticRegression(C=1.0, balanced class
  weights). No hyperparameter tuning.
- Thresholds, chosen on the validation split only:
    reject  = 0.5 (the classifier's decision boundary)
    accept  = max(0.5, just above the highest validation-negative score)
  Scores in [reject, accept) are "uncertain". Test-split results are
  reported once and not used to change anything.

Revision history:
- v1: negatives were photographs, documents and screenshots only. A
  regression test written before training (tests/test_image_validation.py)
  showed v1 accepted content-free images as corneal: flat grey 0.995,
  black 0.993, random noise 0.94-0.98. Its test-split results are kept in
  evaluation_v1.json.
- v2 (this version): adds synthetic degenerate negatives (uniform levels,
  gradients, pixel noise, salt-and-pepper, low-contrast noise, stripes,
  checkerboards), split 60/20/20 like the other negatives. Classifier,
  preprocessing and threshold rule are unchanged.

Outputs:
- ml-service/models/domain_validator/resnet18_backbone.onnx  (not in git)
- ml-service/models/domain_validator/classifier.json          (weights, thresholds, provenance)
- ml-service/models/domain_validator/evaluation.json          (test-split results)

Requirements beyond ml/pyproject.toml: torch, torchvision (already used by the
image notebooks), onnx and onnxruntime:
    uv pip install --python .venv/Scripts/python.exe onnx onnxruntime
COCO val2017 images and annotations must be unzipped in
ml/grading/data/external/coco/ (images: http://images.cocodataset.org/zips/val2017.zip,
annotations: http://images.cocodataset.org/annotations/annotations_trainval2017.zip).

Usage (from ml/):
    .venv/Scripts/python.exe grading/scripts/train_domain_validator.py
"""
import hashlib
import json
import random
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
import sklearn
import torch
import torchvision
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPTS_DIR.parents[2]
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REPO_DIR / "ml-service"))

import modeling_setup as ms  # noqa: E402
from pipelines.image.decode import decode_image  # noqa: E402
from pipelines.image.preprocess import to_model_input  # noqa: E402

SEED = 42
GRADING_DIR = SCRIPTS_DIR.parent
MANIFEST = GRADING_DIR / "image" / "data" / "processed" / "clean_image_manifest.csv"
COCO_DIR = GRADING_DIR / "data" / "external" / "coco"
SYNTHETIC_DIR = GRADING_DIR / "data" / "external" / "synthetic_negatives"
CACHE_PATH = GRADING_DIR / "data" / "external" / "domain_features.npz"
OUT_DIR = REPO_DIR / "ml-service" / "models" / "domain_validator"
ONNX_PATH = OUT_DIR / "resnet18_backbone.onnx"

N_SYNTHETIC = {"document": 400, "screenshot": 400}
DEGENERATE_KINDS = ["uniform", "gradient", "pixel_noise", "salt_pepper", "low_contrast_noise", "stripes", "checkerboard"]
N_PER_DEGENERATE_KIND = 100
CAPTION_SUBSETS = {
    "buildings": r"\b(house|houses|building|buildings|church|tower|skyscraper|barn|cottage)\b",
    "landscapes": r"\b(mountain|mountains|beach|field|landscape|hill|hills|lake|ocean|forest|valley|desert|countryside)\b",
}


def normalize_id(value):
    return " ".join(str(value).split()).replace("NEB- ", "NEB-").casefold()


# ---------------------------------------------------------------- data
def load_positives():
    manifest = pd.read_csv(MANIFEST)
    dataset = pd.read_excel(ms.DATA_PATH)
    dataset["Donor_Group"] = ms.get_donor_groups(dataset)
    donor_of = dict(zip(dataset["Tissue_ID"].map(normalize_id), dataset["Donor_Group"]))
    grade_of = dict(zip(dataset["Tissue_ID"].map(normalize_id), dataset[ms.TARGET]))

    rows = []
    for _, r in manifest.iterrows():
        key = normalize_id(r["Tissue_ID"])
        rows.append({
            "path": Path(r["Selected_Image"]),
            "group": donor_of.get(key, f"tissue:{key}"),
            "subset": "specular_microscopy",
            "grade": grade_of.get(key),
        })
    return pd.DataFrame(rows)


def load_coco():
    images = COCO_DIR / "val2017"
    annotations = json.loads((COCO_DIR / "annotations" / "instances_val2017.json").read_text())
    captions = json.loads((COCO_DIR / "annotations" / "captions_val2017.json").read_text())

    supercategory = {c["id"]: c["supercategory"] for c in annotations["categories"]}
    supers = {}
    for a in annotations["annotations"]:
        supers.setdefault(a["image_id"], set()).add(supercategory[a["category_id"]])
    text = {}
    for c in captions["annotations"]:
        text[c["image_id"]] = text.get(c["image_id"], "") + " " + c["caption"].lower()

    rows = []
    for info in annotations["images"]:
        image_id = info["id"]
        tags = set(supers.get(image_id, set()))
        for name, pattern in CAPTION_SUBSETS.items():
            if re.search(pattern, text.get(image_id, "")):
                tags.add(name)
        rows.append({"path": images / info["file_name"], "group": f"coco:{image_id}",
                     "subset": "coco", "tags": ";".join(sorted(tags)), "grade": None})
    return pd.DataFrame(rows)


def make_synthetic_negatives():
    """Deterministic synthetic documents and UI screenshots (no third-party content)."""
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    words = ("patient report tissue analysis result summary table value date total status "
             "review approved pending section figure page number name address phone email").split()
    try:
        font = ImageFont.truetype("arial.ttf", 18)
        big = ImageFont.truetype("arial.ttf", 30)
    except OSError:
        font = big = ImageFont.load_default()

    rows = []
    for kind, count in N_SYNTHETIC.items():
        for i in range(count):
            path = SYNTHETIC_DIR / f"{kind}_{i:04d}.png"
            rows.append({"path": path, "group": f"synthetic:{kind}:{i}", "subset": f"synthetic_{kind}", "grade": None})
            if path.exists():
                continue
            width, height = rng.choice([(1240, 1754), (1024, 768), (1366, 768), (1920, 1080), (800, 1000)])
            img = Image.new("RGB", (width, height), "white" if kind == "document" else rng.choice(["#f5f5f5", "#1e1e1e", "#ffffff"]))
            draw = ImageDraw.Draw(img)
            ink = "black" if kind == "document" or img.getpixel((0, 0)) != (30, 30, 30) else "white"
            if kind == "screenshot":
                draw.rectangle([0, 0, width, 48], fill=rng.choice(["#2b579a", "#333333", "#0f766e"]))
                for _ in range(rng.randint(3, 8)):
                    x, y = rng.randint(0, width - 200), rng.randint(60, height - 120)
                    draw.rectangle([x, y, x + rng.randint(120, 400), y + rng.randint(40, 200)],
                                   outline=ink, fill=rng.choice(["#e5e7eb", "#dbeafe", "#fef3c7", None]))
            y = 70 if kind == "screenshot" else 60
            draw.text((60, y), " ".join(rng.choices(words, k=4)).title(), fill=ink, font=big)
            y += 60
            while y < height - 60:
                draw.text((60, y), " ".join(rng.choices(words, k=rng.randint(4, 12))), fill=ink, font=font)
                y += rng.randint(26, 40)
            img.save(path)
    return pd.DataFrame(rows)


def make_degenerate_negatives():
    """Content-free images (v2): the kinds of input v1 wrongly accepted, plus similar patterns."""
    out_dir = SYNTHETIC_DIR / "degenerate"
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED + 100)
    rows = []
    for kind in DEGENERATE_KINDS:
        for i in range(N_PER_DEGENERATE_KIND):
            path = out_dir / f"{kind}_{i:03d}.png"
            rows.append({"path": path, "group": f"degenerate:{kind}:{i}", "subset": "synthetic_degenerate",
                         "tags": kind, "grade": None})
            if path.exists():
                continue
            h, w = int(rng.integers(300, 1200)), int(rng.integers(300, 1600))
            level = rng.uniform(0, 255)
            if kind == "uniform":
                pixels = np.full((h, w), level)
            elif kind == "gradient":
                axis = np.linspace(rng.uniform(0, 128), rng.uniform(128, 255), w if rng.random() < 0.5 else h)
                pixels = np.tile(axis, (h, 1)) if axis.size == w else np.tile(axis[:, None], (1, w))
            elif kind == "pixel_noise":
                pixels = rng.normal(level, rng.uniform(10, 80), (h, w))
            elif kind == "salt_pepper":
                pixels = np.full((h, w), level)
                mask = rng.random((h, w))
                p = rng.uniform(0.01, 0.3)
                pixels[mask < p / 2] = 0
                pixels[mask > 1 - p / 2] = 255
            elif kind == "low_contrast_noise":
                pixels = rng.normal(level, rng.uniform(1, 6), (h, w))
            elif kind == "stripes":
                period = int(rng.integers(4, 60))
                stripe = (np.arange(w) // period) % 2 * 255.0
                pixels = np.tile(stripe, (h, 1))
                if rng.random() < 0.5:
                    pixels = pixels.T[:h, :w] if pixels.T.shape[0] >= h and pixels.T.shape[1] >= w else pixels
            else:  # checkerboard
                cell = int(rng.integers(4, 60))
                yy, xx = np.mgrid[0:h, 0:w]
                pixels = ((yy // cell + xx // cell) % 2) * 255.0
            Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), mode="L").save(path)
    return pd.DataFrame(rows)


def split(frame, seed_offset):
    """60/20/20 split keeping each group in one split."""
    first = GroupShuffleSplit(n_splits=1, test_size=0.4, random_state=SEED + seed_offset)
    train_idx, rest_idx = next(first.split(frame, groups=frame["group"]))
    rest = frame.iloc[rest_idx]
    second = GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=SEED + seed_offset)
    val_rel, test_rel = next(second.split(rest, groups=rest["group"]))
    out = frame.copy()
    out["split"] = "train"
    out.iloc[rest_idx[val_rel], out.columns.get_loc("split")] = "validation"
    out.iloc[rest_idx[test_rel], out.columns.get_loc("split")] = "test"
    return out


# ---------------------------------------------------------------- features
def export_backbone():
    """Same export the Docker build uses (ml-service/scripts/export_domain_backbone.py)."""
    sys.path.insert(0, str(REPO_DIR / "ml-service" / "scripts"))
    from export_domain_backbone import export
    export(ONNX_PATH)


def extract(paths, session):
    features, failed = [], []
    batch, batch_idx = [], []

    def flush():
        if batch:
            out = session.run(None, {"input": np.stack(batch)})[0]
            for i, f in zip(batch_idx, out):
                features[i] = f
            batch.clear()
            batch_idx.clear()

    for i, path in enumerate(paths):
        features.append(None)
        try:
            decoded = decode_image(Path(path).read_bytes())
            batch.append(to_model_input(decoded.image))
            batch_idx.append(i)
        except Exception as exc:  # report, never silently drop
            failed.append((str(path), getattr(exc, "code", type(exc).__name__)))
        if len(batch) == 32:
            flush()
    flush()
    return features, failed


# ---------------------------------------------------------------- main
def main():
    for p in [MANIFEST, COCO_DIR / "val2017", COCO_DIR / "annotations" / "instances_val2017.json"]:
        if not p.exists():
            raise SystemExit(f"Missing input: {p} (see the module docstring)")

    positives = split(load_positives(), 0)
    negatives = pd.concat([split(load_coco(), 1), split(make_synthetic_negatives(), 2),
                           split(make_degenerate_negatives(), 3)], ignore_index=True)
    data = pd.concat([positives.assign(label=1), negatives.assign(label=0)], ignore_index=True)
    data["tags"] = data.get("tags", pd.Series(dtype=str)).fillna("")
    print(pd.crosstab([data["subset"]], data["split"]))

    export_backbone()
    session = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])
    features, failed = extract(data["path"].tolist(), session)
    print(f"Feature extraction failed for {len(failed)} images:", failed[:10])
    keep = np.array([f is not None for f in features])
    data = data[keep].reset_index(drop=True)
    X = np.stack([f for f in features if f is not None])
    y = data["label"].to_numpy()

    train = (data["split"] == "train").to_numpy()
    val = (data["split"] == "validation").to_numpy()
    test = (data["split"] == "test").to_numpy()

    scaler = StandardScaler().fit(X[train])
    clf = LogisticRegression(C=1.0, class_weight="balanced", max_iter=5000, random_state=SEED)
    clf.fit(scaler.transform(X[train]), y[train])
    score = clf.predict_proba(scaler.transform(X))[:, 1]

    # Thresholds from the validation split only.
    reject_threshold = 0.5
    max_val_negative = float(score[val & (y == 0)].max())
    accept_threshold = max(reject_threshold, float(np.nextafter(max_val_negative, 1.0)))

    def outcome(s):
        return np.where(s >= accept_threshold, "accepted", np.where(s >= reject_threshold, "uncertain", "rejected"))

    data["score"] = score
    data["outcome"] = outcome(score)

    # ---------------- test-split evaluation (reported once)
    t = data[test]
    report = {"test_counts": {}, "negatives": {}, "positives": {}}
    neg = t[t["label"] == 0]
    pos = t[t["label"] == 1]
    report["test_counts"] = {"positives": int(len(pos)), "negatives": int(len(neg))}

    def rates(frame):
        n = len(frame)
        counts = frame["outcome"].value_counts()
        return {"n": int(n), **{k: (round(int(counts.get(k, 0)) / n, 4) if n else None)
                                for k in ["accepted", "uncertain", "rejected"]},
                "accepted_count": int(counts.get("accepted", 0))}

    report["negatives"]["all"] = rates(neg)
    for subset in ["coco", "synthetic_document", "synthetic_screenshot", "synthetic_degenerate"]:
        report["negatives"][subset] = rates(neg[neg["subset"] == subset])
    for kind in DEGENERATE_KINDS:
        report["negatives"][f"degenerate:{kind}"] = rates(
            neg[(neg["subset"] == "synthetic_degenerate") & (neg["tags"] == kind)])
    for tag in ["person", "animal", "vehicle", "food", "indoor", "buildings", "landscapes"]:
        report["negatives"][f"coco:{tag}"] = rates(neg[neg["tags"].str.contains(rf"(?:^|;){tag}(?:;|$)")])
    report["positives"]["all"] = rates(pos)
    for grade in ["A+", "A", "B"]:
        report["positives"][f"grade {grade}"] = rates(pos[pos["grade"] == grade])

    # Robustness of test positives to degraded copies (descriptive).
    degraded = {}
    for name, transform in {
        "gaussian_blur_r2": lambda im: im.filter(ImageFilter.GaussianBlur(2)),
        "gaussian_blur_r5": lambda im: im.filter(ImageFilter.GaussianBlur(5)),
        "downscale_25pct": lambda im: im.resize((max(224, im.width // 4), max(224, im.height // 4))),
    }.items():
        inputs = [to_model_input(transform(decode_image(Path(p).read_bytes()).image)) for p in pos["path"]]
        feats = np.concatenate([session.run(None, {"input": np.stack(inputs[i:i + 32])})[0]
                                for i in range(0, len(inputs), 32)])
        degraded[name] = rates(pd.DataFrame({"outcome": outcome(clf.predict_proba(scaler.transform(feats))[:, 1])}))
    report["positives_degraded"] = degraded
    report["feature_extraction_failures"] = failed

    # ---------------- artifacts
    onnx_sha = hashlib.sha256(ONNX_PATH.read_bytes()).hexdigest()
    classifier = {
        "model": "corneal_domain_validator",
        "version": 2,
        "revision_note": "v1 accepted content-free images (flat grey, black, noise); v2 adds synthetic degenerate "
                         "negatives. v1 test results: evaluation_v1.json.",
        "question": "Is this a specular microscopy image of the corneal endothelium?",
        "not_assessed": ["image quality", "cell visibility / cell detail", "disease"],
        "backbone": {
            "file": ONNX_PATH.name,
            "sha256": onnx_sha,
            "source": "torchvision resnet18 IMAGENET1K_V1, fc removed, ONNX opset 17",
            "output_dim": int(X.shape[1]),
        },
        "preprocessing": "pipelines/image/preprocess.py: greyscale, short side 256, centre crop 224, "
                         "3 channels, ImageNet normalisation",
        "scaler_mean": scaler.mean_.astype(float).tolist(),
        "scaler_scale": scaler.scale_.astype(float).tolist(),
        "coef": clf.coef_[0].astype(float).tolist(),
        "intercept": float(clf.intercept_[0]),
        "thresholds": {
            "reject_below": reject_threshold,
            "accept_at_or_above": accept_threshold,
            "rule": "reject_below = 0.5 (decision boundary); accept_at_or_above = max(0.5, just above "
                    "the highest validation-negative score). Chosen on the validation split only.",
            "max_validation_negative_score": max_val_negative,
        },
        "training": {
            "counts": {s: {str(k): int(v) for k, v in data[data["split"] == s].groupby("subset").size().items()}
                       for s in ["train", "validation", "test"]},
            "classifier": "StandardScaler + LogisticRegression(C=1.0, class_weight='balanced')",
            "seed": SEED,
            "positives": "clean_image_manifest.csv, split by inferred donor",
            "negatives": "COCO val2017 (Flickr images, see COCO terms of use) + synthetic documents/screenshots "
                         "+ synthetic degenerate images (uniform, gradient, noise, stripes, checkerboard)",
            "data_sha256": hashlib.sha256(ms.DATA_PATH.read_bytes()).hexdigest(),
            "versions": {"torch": torch.__version__, "torchvision": torchvision.__version__,
                         "onnxruntime": ort.__version__, "scikit_learn": sklearn.__version__},
            "trained_on": date.today().isoformat(),
        },
    }
    (OUT_DIR / "classifier.json").write_text(json.dumps(classifier, indent=2) + "\n")
    (OUT_DIR / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    np.savez_compressed(CACHE_PATH, X=X, y=y, split=data["split"].to_numpy(), subset=data["subset"].to_numpy())

    print(json.dumps({"thresholds": classifier["thresholds"], "test": {
        "negatives": report["negatives"], "positives": report["positives"],
        "positives_degraded": report["positives_degraded"]}}, indent=2))


if __name__ == "__main__":
    main()
