"""
XAI — Grad-CAM / Grad-CAM++ for the Phase 6 ROI tile classifier (EfficientNet-B0).

The CNN outputs one logit, the log-odds of ANALYSABLE. By default the explained score is
-logit ("poor"): the heatmap shows the pixels that make a tile poor, i.e. why a region is
left out of the ROI.

  cam(model, x, layer, method)     class activation maps for a batch of network inputs
  tile_cams(...)                   uint8 tiles -> P(analysable), heatmaps at tile size (max 1 per tile, or raw)
  image_map(...)                   whole image: window heatmaps weighted by P(poor), averaged per pixel
  top_mask / rolled / delete       deletion test: top heatmap pixels, the same mask shifted,
                                   pixels replaced by neutral lit tissue

Grad-CAM:   weights = mean gradient per channel                      (Selvaraju et al. 2017)
Grad-CAM++: weights = sum(alpha * relu(gradient)), alpha from the 2nd / 3rd powers of the
            gradient (exponential-score form, as in Chattopadhay et al. 2018 and pytorch-grad-cam);
            better when a tile has several separate problem areas (e.g. several bubbles).
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F

from roi.cnn import to_input
from roi.roimap import window_grid
from roi.tiles import crop


def get_layer(model: torch.nn.Module, path: str) -> torch.nn.Module:
    """'features.8' -> model.features[8]."""
    m = model
    for part in path.split("."):
        m = m[int(part)] if part.lstrip("-").isdigit() else getattr(m, part)
    return m


def cam(model: torch.nn.Module, x: torch.Tensor, layer: torch.nn.Module, method: str = "gradcam++",
        target: str = "poor") -> tuple[torch.Tensor, torch.Tensor]:
    """(heatmaps (N, h, w) at the layer's resolution, >= 0; P(analysable) (N,)). Float32, no autocast."""
    store = {}
    hook = layer.register_forward_hook(lambda _m, _i, out: store.__setitem__("a", out))
    try:
        model.eval()
        with torch.enable_grad():
            logit = model(x).squeeze(1).float()
            score = -logit if target == "poor" else logit
            (grad,) = torch.autograd.grad(score.sum(), store["a"])   # samples independent (eval mode)
    finally:
        hook.remove()
    a, g = store["a"].detach().float(), grad.detach().float()
    if method == "gradcam":
        w = g.mean(dim=(2, 3))
    elif method == "gradcam++":
        g2, g3 = g ** 2, g ** 3
        denom = 2 * g2 + a.sum(dim=(2, 3), keepdim=True) * g3
        alpha = torch.where(denom != 0, g2 / torch.where(denom != 0, denom, torch.ones_like(denom)),
                            torch.zeros_like(g))
        w = (alpha * F.relu(g)).sum(dim=(2, 3))
    else:
        raise ValueError(f"unknown method {method!r}")
    return F.relu((w[:, :, None, None] * a).sum(1)), torch.sigmoid(logit.detach())


def tile_cams(model: torch.nn.Module, tiles: np.ndarray, hp: dict, device: torch.device, layer_path: str,
              method: str = "gradcam++", target: str = "poor", batch: int = 64,
              normalise: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """uint8 tiles (N, 3, s, s) -> (P(analysable) (N,), heatmaps (N, s, s)): scaled to max 1 per tile,
    or raw (normalise=False; comparable between windows, for whole-image maps)."""
    layer = get_layer(model, layer_path)
    s = tiles.shape[-1]
    probs, maps = [], []
    for i in range(0, len(tiles), batch):
        x = to_input(torch.from_numpy(np.ascontiguousarray(tiles[i:i + batch])).to(device), hp["input_px"])
        m, p = cam(model, x, layer, method, target)
        m = F.interpolate(m[:, None], size=(s, s), mode="bilinear", align_corners=False)[:, 0]
        if normalise:
            mx = m.amax(dim=(1, 2), keepdim=True)
            m = torch.where(mx > 0, m / torch.where(mx > 0, mx, torch.ones_like(mx)), torch.zeros_like(m))
        maps.append(m.cpu().numpy())
        probs.append(p.cpu().numpy())
    if not maps:
        return np.zeros(0, np.float32), np.zeros((0, s, s), np.float32)
    return np.concatenate(probs).astype(np.float32), np.concatenate(maps).astype(np.float32)


def windows(planes: np.ndarray, size: int, stride: int) -> tuple[list[tuple[int, int]], np.ndarray]:
    """The ROI scorer's windows (same grid as roi.run.RoiScorer) and their tiles."""
    h, w = planes.shape[1:]
    wins = window_grid(h, w, size, stride)
    return wins, np.stack([crop(planes, y, x, size) for y, x in wins])


def image_map(probs: np.ndarray, cams: np.ndarray, wins: list[tuple[int, int]],
              shape: tuple[int, int]) -> np.ndarray:
    """Per-pixel 'poor evidence': mean over covering windows of P(poor) x heatmap. Windows the model
    calls analysable contribute ~0, so a clean region stays dark. Use raw heatmaps (tile_cams
    normalise=False) so overlapping windows blend without seams; scale the result afterwards."""
    size = cams.shape[-1]
    acc = np.zeros(shape, np.float32)
    cnt = np.zeros(shape, np.float32)
    for p, m, (y, x) in zip(probs, cams, wins):
        acc[y:y + size, x:x + size] += (1 - p) * m
        cnt[y:y + size, x:x + size] += 1
    return acc / np.maximum(cnt, 1)


def top_mask(cams: np.ndarray, share: float) -> np.ndarray:
    """Exactly round(share * s * s) highest pixels of each heatmap (ties broken by order)."""
    n, h, w = cams.shape
    k = int(round(share * h * w))
    flat = cams.reshape(n, -1)
    idx = np.argsort(-flat, axis=1, kind="stable")[:, :k]
    out = np.zeros_like(flat, dtype=bool)
    np.put_along_axis(out, idx, True, axis=1)
    return out.reshape(n, h, w)


def rolled(masks: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Each mask shifted circularly by a random 1/4..3/4 of the tile in both directions:
    same shape and area, another place (the deletion test's baseline)."""
    s = masks.shape[-1]
    out = np.empty_like(masks)
    for i, m in enumerate(masks):
        dy, dx = rng.integers(s // 4, 3 * s // 4 + 1, size=2)
        out[i] = np.roll(m, (int(dy), int(dx)), axis=(0, 1))
    return out


def delete(tiles: np.ndarray, masks: np.ndarray) -> np.ndarray:
    """Masked pixels -> neutral lit tissue: raw / flat planes = their mean over the tile's lit
    pixels (whole tile if none), lit plane = lit."""
    out = tiles.copy()
    for t, m in zip(out, masks):
        lit = t[2] > 0
        ref = lit if lit.any() else np.ones_like(lit)
        for c in (0, 1):
            t[c][m] = np.uint8(round(float(t[c][ref].mean())))
        t[2][m] = 255
    return out
