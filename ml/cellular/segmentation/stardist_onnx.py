"""
StarDist inference without TensorFlow: the network as ONNX, the rest with the stardist package's own functions.

Reproduces StarDist2D.predict_instances(x) of stardist 0.9 for one 2D single-channel image, no tiling, sparse
(the defaults used by segmentation.infer_full.make_predictor):
  1. pad bottom / right by reflection to a multiple of div_by     (StarDistPadAndCropResizer.before)
  2. network -> prob (h, w), dist (h, w, n_rays)                   (here: an onnxruntime session)
  3. dist >= 1e-3; candidates = prob > prob_thresh, 2 px border     (_predict_sparse_generator, _ind_prob_thresh)
  4. drop candidates in the padding                                 (StarDistPadAndCropResizer.filter_points)
  5. sparse non-maximum suppression -> polygons -> label image     (_instances_from_prediction)

Used by export_web.py (checked against predict_instances on real images) and copied to the web ML service.
"""

from __future__ import annotations

import numpy as np


def pad_to(x: np.ndarray, div_by: tuple[int, int]) -> tuple[np.ndarray, tuple[tuple[int, int], ...]]:
    """Pad at the end of each axis (reflect) so that every size is a multiple of div_by."""
    pad = tuple((0, (d - s % d) % d) for s, d in zip(x.shape, div_by))
    return np.pad(x, pad, mode="reflect"), pad


def candidates(prob: np.ndarray, dist: np.ndarray, prob_thresh: float, grid: tuple[int, int],
               shape: tuple[int, int], b: int = 2) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """prob (h, w), dist (h, w, n_rays) at grid resolution -> (prob, dist, points) of the candidate pixels
    inside the unpadded image (points in image pixels)."""
    from stardist.nms import _ind_prob_thresh
    dist = np.maximum(1e-3, dist)
    inds = _ind_prob_thresh(prob, prob_thresh, b=b)
    probs, dists = prob[inds].copy(), dist[inds].copy()
    points = np.stack(np.where(inds), axis=1) * np.asarray(grid).reshape(1, 2)
    keep = np.where(np.all(points < np.asarray(shape), 1))
    return probs[keep], dists[keep].reshape(-1, dist.shape[-1]), points[keep].reshape(-1, 2)


def instances(probs: np.ndarray, dists: np.ndarray, points: np.ndarray, nms_thresh: float,
              shape: tuple[int, int]) -> tuple[np.ndarray, dict]:
    """Candidates -> (label image, details with points, prob, coord) - as StarDist2D._instances_from_prediction."""
    from stardist import dist_to_coord
    from stardist.geometry import polygons_to_label
    from stardist.nms import non_maximum_suppression_sparse
    points, probi, disti, _ = non_maximum_suppression_sparse(dists, probs, points, nms_thresh=nms_thresh,
                                                             verbose=False)
    labels = polygons_to_label(disti, points, prob=probi, shape=shape, scale_dist=(1, 1))
    return labels, {"points": points, "prob": probi, "coord": dist_to_coord(disti, points, scale_dist=(1, 1))}


class StarDistOnnx:
    """predict_instances for one normalised 2D image (float32, H x W) with an onnxruntime session."""

    def __init__(self, session, grid: tuple[int, int], div_by: tuple[int, int], prob_thresh: float,
                 nms_thresh: float, outputs: tuple[str, str] = ("prob", "dist")):
        self.session, self.grid, self.div_by, self.outputs = session, tuple(grid), tuple(div_by), list(outputs)
        self.prob_thresh, self.nms_thresh = float(prob_thresh), float(nms_thresh)
        self.input_name = session.get_inputs()[0].name

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Network outputs at grid resolution for the padded image: prob (h, w), dist (h, w, n_rays)."""
        xp, _ = pad_to(x.astype(np.float32), self.div_by)
        prob, dist = self.session.run(self.outputs, {self.input_name: xp[None, ..., None]})
        return prob[0, ..., 0], dist[0]

    def predict_instances(self, x: np.ndarray) -> tuple[np.ndarray, dict]:
        prob, dist = self.predict(x)
        probs, dists, points = candidates(prob, dist, self.prob_thresh, self.grid, x.shape)
        return instances(probs, dists, points, self.nms_thresh, x.shape)
