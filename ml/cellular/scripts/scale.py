"""
Scale-factor calibration (um per pixel).

The Konan CellChek D magnification is fixed, so um/pixel is a CONSTANT across
the whole dataset. We do NOT have it stated in the .txt, but we can recover it:

Method A (per-image, needs a segmentation of the same cells Konan used):
    Konan AVE = mean cell area in um^2.
    Segment the image, measure mean cell area in px^2.
    um_per_px = sqrt( AVE_um2 / mean_area_px2 )
    Take the MEDIAN across many images as the canonical constant (robust to
    segmentation noise and to region mismatch).

Method B (preferred if available):
    Ask the eye bank / Konan for the device calibration (um/pixel at this
    magnification). One number, applies to all images. Use calibrate_from_pairs
    only to sanity-check it.
"""
import numpy as np


def um_per_px_from_pair(konan_ave_um2, mean_cell_area_px2):
    """Single-image estimate. Returns um/pixel (linear)."""
    if mean_cell_area_px2 <= 0:
        return np.nan
    return float(np.sqrt(konan_ave_um2 / mean_cell_area_px2))


def calibrate_from_pairs(pairs):
    """
    pairs : list of (konan_ave_um2, mean_cell_area_px2) across images.
    Returns (median_um_per_px, per_image_estimates) — use the median as the
    dataset constant and report the spread as a calibration-stability check.
    """
    est = [um_per_px_from_pair(a, p) for a, p in pairs if p and p > 0]
    est = [e for e in est if np.isfinite(e)]
    if not est:
        return np.nan, []
    est = np.array(est)
    return float(np.median(est)), est


if __name__ == "__main__":
    # Illustrative: if cells averaged ~1900 px^2 and Konan AVE=380 um^2,
    # then um/px ~ sqrt(380/1900) = 0.447 um/px  (area scale 0.2 um^2/px^2).
    print("example um/px:", round(um_per_px_from_pair(380, 1900), 4))
