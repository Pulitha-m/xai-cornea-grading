"""
Phase 3, Step 3.5 — unit tests of the cell extraction on synthetic images whose
answers are known: a regular hexagonal tessellation, random Voronoi cells,
borders / unanalysable areas / holes, and simple shapes.

Run (from ml/cellular/):  python -m pytest tests/test_extraction.py -q
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.spatial import Voronoi, cKDTree
from skimage.draw import disk
from skimage.segmentation import find_boundaries

from data_prep.check_annotations import INTERIOR, WALL
from extraction.cells import ExtractionParams, extract_cells, instances_from_mask, summarise_cells

SHAPE = (480, 480)
P = ExtractionParams()


def voronoi_labels(points: np.ndarray, shape=SHAPE) -> np.ndarray:
    """Exact Voronoi tessellation: every pixel gets the label of its nearest point (1..n)."""
    yy, xx = np.mgrid[:shape[0], :shape[1]]
    _, idx = cKDTree(points).query(np.c_[yy.ravel(), xx.ravel()])
    return (idx + 1).reshape(shape).astype(np.int32)


def as_mask(labels: np.ndarray) -> np.ndarray:
    """Draw ~2-px walls between cells, like the reference annotations."""
    return np.where(find_boundaries(labels, mode="inner"), WALL, INTERIOR).astype(np.uint8)


def hex_points(spacing: float, shape=SHAPE) -> np.ndarray:
    rows = []
    dy = spacing * np.sqrt(3) / 2
    for j in range(int(shape[0] / dy) + 2):
        for i in range(int(shape[1] / spacing) + 2):
            rows.append((j * dy, i * spacing + (spacing / 2 if j % 2 else 0)))
    return np.array(rows)


@pytest.fixture(scope="module")
def hexagons():
    s = 30.0
    df, _, _ = extract_cells(instances_from_mask(as_mask(voronoi_labels(hex_points(s)))), p=P)
    return s, df


def test_hexagons_are_six_sided(hexagons):
    _, df = hexagons
    known = df["sides"].dropna()
    assert len(known) > 100
    assert (known == 6).mean() >= 0.95


def test_hexagon_area_is_the_wall_centred_cell(hexagons):
    s, df = hexagons
    true_area = np.sqrt(3) / 2 * s ** 2                     # area of a hexagonal Voronoi cell
    assert abs(df["area_px"].mean() / true_area - 1) < 0.05
    assert summarise_cells(df)["cv_area_pct"] < 5


def test_hexagon_compactness(hexagons):
    _, df = hexagons
    assert 0.85 < df["compactness"].median() < 0.97          # regular hexagon: 0.907


def test_random_voronoi_side_counts():
    rng = np.random.default_rng(0)
    pts = hex_points(30.0) + rng.uniform(-6, 6, size=(len(hex_points(30.0)), 2))
    vor = Voronoi(pts)
    truth = {}                                               # neighbours sharing an edge >= 5 px
    for (a, b), verts in zip(vor.ridge_points, vor.ridge_vertices):
        if -1 in verts:
            continue
        if np.linalg.norm(vor.vertices[verts[0]] - vor.vertices[verts[1]]) >= 5:
            truth[a + 1] = truth.get(a + 1, 0) + 1
            truth[b + 1] = truth.get(b + 1, 0) + 1

    labels = voronoi_labels(pts)
    df, _, complete = extract_cells(instances_from_mask(as_mask(labels)), p=P)
    df = df.dropna(subset=["sides"])
    # map extracted cells back to Voronoi points via their centroid
    point_of = labels[df["cy"].round().astype(int), df["cx"].round().astype(int)]
    agree = np.array([s == truth.get(pt, -1) for s, pt in zip(df["sides"], point_of)])
    assert len(agree) > 100
    assert agree.mean() >= 0.85


def test_border_and_unanalysable_cells_are_excluded():
    labels = voronoi_labels(hex_points(30.0))
    analysable = np.ones(SHAPE, bool)
    analysable[150:250, 150:250] = False                     # e.g. a dark area
    _, _, complete = extract_cells(instances_from_mask(as_mask(labels)), analysable, P)
    assert not complete[[0, -1], :].any() and not complete[:, [0, -1]].any()
    assert not complete[148:252, 148:252].any()


def test_cells_next_to_a_hole_get_no_side_count():
    labels = voronoi_labels(hex_points(30.0))
    hole = labels[240, 240]
    inst = instances_from_mask(as_mask(labels))
    inst[labels == hole] = 0                                 # a missing cell (segmentation gap)
    df, _, complete = extract_cells(inst, p=P)
    yy, xx = np.nonzero(labels == hole)
    near = (np.hypot(df["cy"] - yy.mean(), df["cx"] - xx.mean()) < 35)
    assert near.sum() >= 5
    assert df.loc[near, "sides"].isna().all()


def test_simple_shapes():
    img = np.zeros((200, 400), np.int32)
    img[disk((100, 100), 40)] = 1
    img[60:140, 240:320] = 2
    df, _, _ = extract_cells(img, p=ExtractionParams(grow_px=0))
    by_id = df.set_index("cell_id")
    assert 0.88 < by_id.loc[1, "compactness"] < 1.08        # circle: 1
    assert 0.70 < by_id.loc[2, "compactness"] < 0.90        # square: pi/4 = 0.785
    assert by_id.loc[2, "compactness"] < by_id.loc[1, "compactness"]


def test_flags_not_removed():
    labels = voronoi_labels(hex_points(30.0))
    inst = instances_from_mask(as_mask(labels))
    tiny = inst == inst[240, 240]
    inst[tiny] = 0
    yy, xx = np.nonzero(tiny)
    inst[int(yy.mean()) - 2:int(yy.mean()) + 2, int(xx.mean()) - 2:int(xx.mean()) + 2] = inst.max() + 1
    df, _, _ = extract_cells(inst, p=ExtractionParams(grow_px=0))
    assert df["flag_small"].sum() >= 1                     # flagged ...
    assert summarise_cells(df)["n_cells"] == len(df)       # ... but still counted
