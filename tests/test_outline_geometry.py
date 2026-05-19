import math
import numpy as np
import pytest

from svg_to_outline import (
    smooth_resample_loop,
    y_flip,
    scale_to_length,
    recentre,
)


def test_y_flip():
    pts = np.array([[1.0, 2.0], [3.0, -4.0]])
    flipped = y_flip(pts)
    assert flipped[0, 1] == -2.0
    assert flipped[1, 1] == 4.0
    # x is untouched
    assert flipped[0, 0] == 1.0


def _circle_polyline(R, n=512):
    th = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    return np.column_stack([R * np.cos(th), R * np.sin(th)])


def test_scale_to_length_circle():
    R = 1.0
    poly = _circle_polyline(R)
    raw_arc = 2 * math.pi * R
    target_arc = 100.0
    scaled, scale = scale_to_length(poly, target_arc)
    assert scale == pytest.approx(target_arc / raw_arc, rel=1e-3)
    # Verify scaled arc length matches target
    seg = np.linalg.norm(np.diff(np.vstack([scaled, scaled[0]]), axis=0), axis=1)
    assert seg.sum() == pytest.approx(target_arc, rel=1e-3)


def test_recentre_zero_mean():
    poly = np.array([[10.0, 20.0], [20.0, 30.0], [30.0, 40.0]])
    centred = recentre(poly)
    assert centred.mean(axis=0) == pytest.approx([0.0, 0.0], abs=1e-9)


def test_smooth_resample_loop_count_and_periodicity():
    poly = _circle_polyline(1.0, n=400)
    out = smooth_resample_loop(poly, n_out=256, smooth_s=0.01)
    assert out.shape == (256, 2)
    # First and last should be nearly equal under the periodic spline
    assert np.linalg.norm(out[0] - out[-1]) > 0   # not literally equal (not duplicated)
    # And the loop should still be roughly circular (radii ≈ 1.0)
    radii = np.linalg.norm(out, axis=1)
    assert radii.min() == pytest.approx(1.0, abs=0.05)
    assert radii.max() == pytest.approx(1.0, abs=0.05)
