"""Full-resolution image input for the hybrid grading model's ResNet-50 backbone.

Reproduces the preprocessing that produced the training embeddings
(ml/grading/notebooks/images/07_hybrid_evaluation.ipynb): 8-bit greyscale at full
resolution, scaled to [0, 1], repeated to 3 channels, ImageNet mean/std
normalisation. No resizing or cropping was applied in training, where every image
was 1296 x 972. An image of another size is resized to that size, and the caller
reports it, because its image features are then not comparable with training.
"""
import numpy as np
from PIL import Image

from pipelines.image.preprocess import IMAGENET_MEAN, IMAGENET_STD


def to_embedding_input(image: Image.Image, training_size: tuple[int, int]) -> tuple[np.ndarray, bool]:
    """Returns a float32 array of shape (1, 3, height, width) and whether the image was resized."""
    grey = image.convert("L")
    resized = grey.size != training_size
    if resized:
        grey = grey.resize(training_size, Image.Resampling.BILINEAR)
    pixels = np.asarray(grey, dtype=np.float32) / 255.0
    rgb = np.repeat(pixels[np.newaxis, :, :], 3, axis=0)
    return ((rgb - IMAGENET_MEAN) / IMAGENET_STD)[np.newaxis].astype(np.float32), resized
