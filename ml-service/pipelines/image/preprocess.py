"""Image preprocessing shared by domain-validator training and inference.

ml/grading/scripts/train_domain_validator.py imports this module, so the
classifier is trained on exactly the tensors the service produces.

Every image is reduced to greyscale before feature extraction. Specular
microscopy images are greyscale, so without this the classifier could learn
"colour means not corneal" and accept any greyscale photograph.
"""
import numpy as np
from PIL import Image

INPUT_SIZE = 224
RESIZE_SHORT_SIDE = 256
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)


def to_model_input(image: Image.Image) -> np.ndarray:
    """Greyscale -> short side 256 -> centre crop 224 -> 3 channels -> ImageNet normalisation.

    Returns a float32 array of shape (3, 224, 224).
    """
    grey = image.convert("L")
    width, height = grey.size
    scale = RESIZE_SHORT_SIDE / min(width, height)
    resized = grey.resize(
        (max(INPUT_SIZE, round(width * scale)), max(INPUT_SIZE, round(height * scale))),
        Image.Resampling.BILINEAR,
    )
    left = (resized.width - INPUT_SIZE) // 2
    top = (resized.height - INPUT_SIZE) // 2
    cropped = resized.crop((left, top, left + INPUT_SIZE, top + INPUT_SIZE))

    pixels = np.asarray(cropped, dtype=np.float32) / 255.0
    rgb = np.repeat(pixels[np.newaxis, :, :], 3, axis=0)
    return (rgb - IMAGENET_MEAN) / IMAGENET_STD
