"""
XAI step 3 — Seg-Grad-CAM for StarDist (Vinogradova et al. 2020): which pixels make the model see ONE cell?

Explained score of a cell = sum of StarDist's object probability over the cell's instance (at the resolution of
the probability map). Grad-CAM weighting as in step 1 (mean gradient per channel) at a late layer — StarDist's
'features' conv after the U-Net, the last layer before the output heads.

  two_outputs(keras_model, layer)   model x -> (layer activations, object probability)
  seg_cam(model2, x, region_g)      heatmap at the layer's resolution (>= 0) and the score
  scores(model2, xs, region_g)      the score for a batch of (modified) inputs
  window / top_in_window / rolled_in_window / delete    deletion test inside the cell's neighbourhood
  shares(heat, win, region, ring)   heat on the cell + ring and on the wall band vs their area shares

TensorFlow is imported only inside the functions that need it (the numpy helpers run without it).
"""

from __future__ import annotations

import cv2
import numpy as np
from scipy import ndimage as ndi


class _Hooked:
    """km with `layer` hooked: calling it returns (the layer's activations, the first output). Used when a
    functional sub-model cannot be built (StarDist's model mixes Keras versions: 'KerasTensor has no node')."""

    def __init__(self, km, layer: str):
        self.km, self.store = km, {}
        lay = km.get_layer(layer)
        orig = lay.call

        def call(*args, **kwargs):
            out = orig(*args, **kwargs)
            self.store["a"] = out
            return out
        lay.call = call

    def __call__(self, x, training: bool = False):
        self.store.clear()
        out = self.km(x, training=training)
        if "a" not in self.store:
            raise RuntimeError("layer hook not called - the model does not run the layer's call() eagerly")
        return self.store["a"], out[0] if isinstance(out, (list, tuple)) else out


def two_outputs(km, layer: str):
    """Callable: input -> (activations of `layer`, first output (StarDist: object probability))."""
    try:
        try:
            import tf_keras as K                 # StarDist with TF >= 2.16 builds Keras-2 models
            if not isinstance(km, K.Model):
                raise ImportError
        except ImportError:
            from tensorflow import keras as K
        return K.Model(km.inputs, [km.get_layer(layer).output, km.outputs[0]])
    except (AttributeError, TypeError, ValueError):
        return _Hooked(km, layer)


def pad_to(a: np.ndarray, div: int, mode: str = "reflect") -> np.ndarray:
    """Pad bottom / right to a multiple of div (the U-Net needs divisible sizes)."""
    ph, pw = (-a.shape[0]) % div, (-a.shape[1]) % div
    if not (ph or pw):
        return a
    return np.pad(a, ((0, ph), (0, pw)), mode=mode) if mode == "reflect" else np.pad(a, ((0, ph), (0, pw)))


def to_grid(region: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Image-resolution region -> the probability map's resolution (area share > 0.5; at least one pixel)."""
    r = cv2.resize(region.astype(np.float32), (shape[1], shape[0]), interpolation=cv2.INTER_AREA) > 0.5
    if not r.any():
        cy, cx = np.argwhere(region).mean(0) * np.array(shape) / np.array(region.shape)
        r[min(int(cy), shape[0] - 1), min(int(cx), shape[1] - 1)] = True
    return r


def seg_cam(model2, x: np.ndarray, region_g: np.ndarray) -> tuple[np.ndarray, float]:
    """x (H, W) float32 network input; region_g bool at the probability map's resolution.
    Returns (Grad-CAM heatmap at the layer's resolution, >= 0; score = sum of probability over region_g)."""
    import tensorflow as tf
    inp = tf.convert_to_tensor(x[None, ..., None], tf.float32)
    m = tf.convert_to_tensor(region_g[None, ..., None], tf.float32)
    with tf.GradientTape() as tape:
        a, prob = model2(inp, training=False)
        score = tf.reduce_sum(tf.cast(prob, tf.float32) * m)
    g = tape.gradient(score, a)
    a = np.asarray(a, np.float32)[0]
    g = np.asarray(g, np.float32)[0]
    w = g.mean((0, 1))
    return np.maximum((a * w).sum(-1), 0), float(score)


def scores(model2, xs, region_g: np.ndarray, batch: int = 8) -> np.ndarray:
    """Score (sum of probability over region_g) for each input in xs."""
    out = []
    for i in range(0, len(xs), batch):
        _, p = model2(np.asarray(xs[i:i + batch], np.float32)[..., None], training=False)
        out.append((np.asarray(p, np.float32)[..., 0] * region_g).sum((1, 2)))
    return np.concatenate(out)


def upsample(cam: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    return cv2.resize(cam.astype(np.float32), (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)


def window(region: np.ndarray, ctx: int, hw: tuple[int, int]) -> tuple[slice, slice]:
    """Bounding box of region + ctx on each side, clipped to hw."""
    ys, xs = np.nonzero(region)
    return (slice(max(int(ys.min()) - ctx, 0), min(int(ys.max()) + ctx + 1, hw[0])),
            slice(max(int(xs.min()) - ctx, 0), min(int(xs.max()) + ctx + 1, hw[1])))


def top_in_window(heat: np.ndarray, win, share: float) -> np.ndarray:
    """Exactly round(share * window size) hottest pixels of the window (ties broken by order)."""
    sub = heat[win]
    k = int(round(share * sub.size))
    flat = np.zeros(sub.size, bool)
    flat[np.argsort(-sub.ravel(), kind="stable")[:k]] = True
    out = np.zeros(heat.shape, bool)
    out[win] = flat.reshape(sub.shape)
    return out


def rolled_in_window(mask: np.ndarray, win, rng: np.random.Generator, n: int) -> list[np.ndarray]:
    """The window's mask rolled (circularly, inside the window) by a random 1/4..3/4 of the window in both
    directions: same shape and area, another place (as in step 1)."""
    sub = mask[win]
    h, w = sub.shape
    out = []
    for _ in range(n):
        dy, dx = int(rng.integers(h // 4, 3 * h // 4 + 1)), int(rng.integers(w // 4, 3 * w // 4 + 1))
        m = np.zeros_like(mask)
        m[win] = np.roll(sub, (dy, dx), axis=(0, 1))
        out.append(m)
    return out


def delete(x: np.ndarray, mask: np.ndarray, win) -> np.ndarray:
    """Masked pixels -> the window's mean intensity (no edges, no cell walls)."""
    out = x.copy()
    out[mask] = float(x[win].mean())
    return out


def shares(heat: np.ndarray, win, region: np.ndarray, ring_px: int) -> dict:
    """Heat share and area share (inside the window) of the cell + ring and of the wall band."""
    sub = heat[win]
    tot = float(sub.sum())
    cell = ndi.binary_dilation(region, iterations=ring_px)[win]
    wall = cell & ~ndi.binary_erosion(region, iterations=ring_px)[win]
    h = (lambda m: float(sub[m].sum()) / tot) if tot > 0 else (lambda m: float("nan"))
    return {"heat_cell": h(cell), "area_cell": float(cell.mean()),
            "heat_wall": h(wall), "area_wall": float(wall.mean())}
