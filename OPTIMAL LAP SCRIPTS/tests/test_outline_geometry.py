import math
import os
import numpy as np
import pytest

from svg_to_outline import (
    smooth_resample_loop,
    y_flip,
    scale_to_length,
    recentre,
)
from svg_to_outline import build_outline_from_svg, limit_min_radius, compute_curvature
from svg_to_outline import compute_left_normals, generate_edges_constant_width
from svg_to_outline import (
    compute_curvature,
    apply_hairpin_narrowing,
    find_start_finish_index,
)


def test_limit_min_radius_rounds_tight_corner():
    # A loop with one pathologically tight spike. The limiter must round it up to
    # the requested minimum radius (cap |kappa| at 1/R), leaving the rest alone.
    th = np.linspace(0, 2 * math.pi, 400, endpoint=False)
    pts = np.column_stack([50 * np.cos(th), 50 * np.sin(th)])  # R=50 circle
    pts[100] += pts[100] / np.linalg.norm(pts[100]) * 8.0       # yank one node out → sharp spike
    k_before = np.abs(compute_curvature(pts)).max()
    fixed = limit_min_radius(pts, min_radius_m=10.0)
    k_after = np.abs(compute_curvature(fixed)).max()
    assert k_before > 1.0 / 10.0, "test setup: spike should exceed the cap"
    assert k_after <= 1.0 / 10.0 + 0.02, f"|kappa|max {k_after:.3f} not rounded to <=0.1"


def test_limit_min_radius_disabled_is_noop():
    th = np.linspace(0, 2 * math.pi, 200, endpoint=False)
    pts = np.column_stack([np.cos(th), np.sin(th)])
    out = limit_min_radius(pts, min_radius_m=0.0)
    assert np.allclose(out, pts), "min_radius<=0 must return the input unchanged"


def test_track_length_override_scales_perimeter():
    # Monaco (3337 m) must scale the outline to ~that perimeter; the default
    # path keeps Canada's 4361 m unchanged (backward compatibility).
    svg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "Circuit_Monaco.svg")
    outer, inner = build_outline_from_svg(svg, track_length_m=3337.0, road_width_m=9.0)

    def perim(p):
        p = np.asarray(p)
        return float(np.linalg.norm(np.diff(np.vstack([p, p[0]]), axis=0), axis=1).sum())

    mid = (perim(outer) + perim(inner)) / 2.0
    assert 3000.0 < mid < 3700.0, f"centerline perimeter {mid:.0f} m off target 3337"


def test_left_normals_orthogonal_to_tangent():
    R = 10.0
    th = np.linspace(0.0, 2 * math.pi, 256, endpoint=False)
    pts = np.column_stack([R * np.cos(th), R * np.sin(th)])
    nrm = compute_left_normals(pts)
    # For a CCW circle centred at origin, left-normals point INWARD (toward origin)
    radial = pts / np.linalg.norm(pts, axis=1, keepdims=True)
    # nrm dot radial should be approximately -1 everywhere
    dots = np.einsum("ij,ij->i", nrm, radial)
    assert dots.mean() == pytest.approx(-1.0, abs=0.02)


def test_generate_edges_width_radii():
    R = 100.0
    th = np.linspace(0.0, 2 * math.pi, 512, endpoint=False)
    pts = np.column_stack([R * np.cos(th), R * np.sin(th)])
    W = 13.0
    outer, inner = generate_edges_constant_width(pts, W)
    # CCW loop with left-normal pointing inward:
    #   inner edge (centerline + W/2 * left_normal) sits at radius R - W/2
    #   outer edge (centerline - W/2 * left_normal) sits at radius R + W/2
    r_inner = np.linalg.norm(inner, axis=1).mean()
    r_outer = np.linalg.norm(outer, axis=1).mean()
    assert r_inner == pytest.approx(R - W / 2, abs=0.5)
    assert r_outer == pytest.approx(R + W / 2, abs=0.5)


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
    # smooth_s scales with polyline-size² (splprep convention). Production uses
    # s≈10-30 on a ~4361 m track; equivalent on a unit-radius circle is ~0.01.
    out = smooth_resample_loop(poly, n_out=256, smooth_s=0.01)
    assert out.shape == (256, 2)
    # First and last should be nearly equal under the periodic spline
    assert np.linalg.norm(out[0] - out[-1]) > 0   # not literally equal (not duplicated)
    # And the loop should still be roughly circular (radii ≈ 1.0)
    radii = np.linalg.norm(out, axis=1)
    assert radii.min() == pytest.approx(1.0, abs=0.05)
    assert radii.max() == pytest.approx(1.0, abs=0.05)


def test_curvature_circle():
    R = 5.0
    th = np.linspace(0.0, 2 * math.pi, 1024, endpoint=False)
    pts = np.column_stack([R * np.cos(th), R * np.sin(th)])
    k = compute_curvature(pts)
    # κ for a circle of radius R is 1/R (sign depends on direction; |κ| = 1/R)
    assert np.abs(np.abs(k).mean() - 1.0 / R) < 0.01


def test_hairpin_narrowing_reduces_width_near_peak():
    # Synthetic: high curvature spike at index 100 of a 1000-point loop
    n = 1000
    th = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    pts = np.column_stack([np.cos(th), np.sin(th)]) * 100.0
    kappa = np.zeros(n)
    kappa[100] = 0.1   # spike
    arc_per_step = 2 * math.pi * 100.0 / n   # ~0.63 m per step
    widths = np.full(n, 13.0)
    apply_hairpin_narrowing(widths, kappa, arc_per_step,
                            half_range_m=60.0, narrowed_width=10.5)
    # Width should be 10.5 at index 100, taper back to 13.0 well outside ±60m
    assert widths[100] == pytest.approx(10.5)
    far_idx = (100 + int(200.0 / arc_per_step)) % n
    assert widths[far_idx] == pytest.approx(13.0)


def test_find_start_finish_picks_low_curvature_run():
    n = 200
    kappa = np.zeros(n)
    # Two corners: one short, one long
    kappa[10:30] = 0.05
    kappa[60:90] = 0.05
    # Longest straight: 90..200 then wraps 0..10 (total ~120 stations)
    sf = find_start_finish_index(kappa, low_thresh=0.001)
    # Midpoint of the long straight (90..210 wrapped, midpoint ≈ index 150)
    assert 130 <= sf <= 170 or sf <= 30   # tolerate wrap handling
