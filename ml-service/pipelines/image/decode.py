"""Safe decoding of uploaded images.

Rejects empty, oversized, unsupported, truncated and decompression-bomb
images before any model sees them. Limits come from environment variables
(see ml-service/README.md) so they can be aligned with the backend upload
limits without code changes.
"""
import io
import os
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

# Formats accepted end to end. The domain validator was trained and evaluated
# on JPEG specular microscopy images and PNG/JPEG negatives; other formats are
# rejected rather than decoded on trust.
SUPPORTED_FORMATS = {"JPEG", "PNG"}

MAX_BYTES = int(os.environ.get("IMAGE_MAX_BYTES", 15 * 1024 * 1024))
MIN_SIDE = int(os.environ.get("IMAGE_MIN_SIDE", 224))
MAX_SIDE = int(os.environ.get("IMAGE_MAX_SIDE", 8000))
MAX_PIXELS = int(os.environ.get("IMAGE_MAX_PIXELS", 40_000_000))

# Pillow raises DecompressionBombError above twice this value and warns above it.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ImageRejected(Exception):
    """An uploaded image failed validation. `code` is the public error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class DecodedImage:
    image: Image.Image  # 8-bit greyscale ("L"), EXIF orientation applied
    format: str
    width: int
    height: int


def decode_image(data: bytes) -> DecodedImage:
    if not data:
        raise ImageRejected("IMAGE_DECODE_FAILED", "The uploaded file is empty.")
    if len(data) > MAX_BYTES:
        raise ImageRejected("IMAGE_TOO_LARGE", f"Images must be at most {MAX_BYTES // (1024 * 1024)} MB.")

    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            if fmt not in SUPPORTED_FORMATS:
                raise ImageRejected("UNSUPPORTED_IMAGE_FORMAT", "Upload a JPEG or PNG image.")
            if width * height > MAX_PIXELS or max(width, height) > MAX_SIDE or min(width, height) < MIN_SIDE:
                raise ImageRejected(
                    "IMAGE_DIMENSIONS_INVALID",
                    f"Image sides must be between {MIN_SIDE} and {MAX_SIDE} pixels "
                    f"(at most {MAX_PIXELS:,} pixels in total).",
                )
            probe.verify()  # detects truncation and corrupt structure

        # verify() leaves the file unusable, so decode again for the pixels.
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("L")
    except ImageRejected:
        raise
    except Image.DecompressionBombError as exc:
        raise ImageRejected("IMAGE_DIMENSIONS_INVALID", "The image has too many pixels.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageRejected("IMAGE_DECODE_FAILED", "The image could not be decoded. Upload an uncorrupted JPEG or PNG.") from exc

    return DecodedImage(image=image, format=fmt, width=image.width, height=image.height)
