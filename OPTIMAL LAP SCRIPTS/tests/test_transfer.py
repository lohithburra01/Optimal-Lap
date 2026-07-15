"""Unit tests for cache/_track_registry.py (pre-FP1 calibration utilities)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cache"))
from _track_registry import (  # noqa: E402
    TRACKS,
    align_pair,
    corner_minima,
    pair_minima,
    pava_nonincreasing,
    rho_isa,
)


def test_rho_isa_sea_level_and_mexico():
    assert abs(rho_isa(0.0) - 1.225) < 1e-9
    assert 0.95 < rho_isa(2240.0) < 1.00  # Mexico City


def test_corner_minima_finds_two_dips():
    s = np.linspace(0, 4000, 2001)
    v = (300.0
         - 150.0 * np.exp(-((s - 1000.0) / 120.0) ** 2)
         - 120.0 * np.exp(-((s - 3000.0) / 150.0) ** 2))
    m = corner_minima(s, v)
    assert len(m) == 2
    assert abs(m[0][0] - 1000.0) < 30.0 and abs(m[1][0] - 3000.0) < 30.0


def test_pair_minima_matches_shifted_corners():
    m25 = [(1000.0, 150.0), (3000.0, 180.0)]
    m26 = [(1030.0, 138.0), (2985.0, 160.0), (3900.0, 240.0)]  # extra unmatched dip
    pairs, rate = pair_minima(m25, m26, s_total=4000.0)
    assert len(pairs) == 2
    assert rate >= 2.0 / 3.0
    # matched to the right partners, ordering (s25, v25, s26, v26)
    assert pairs[0] == (1000.0, 150.0, 1030.0, 138.0)
    assert pairs[1] == (3000.0, 180.0, 2985.0, 160.0)


def test_pava_nonincreasing_is_monotone():
    v = np.array([90.0, 120.0, 150.0, 200.0, 250.0, 280.0])
    r = np.array([1.00, 0.97, 1.01, 0.90, 0.84, 0.86])
    knots = np.array([80.0, 140.0, 200.0, 260.0, 320.0])
    rk = pava_nonincreasing(v, r, np.ones_like(r), knots)
    assert rk.shape == knots.shape
    assert np.all(np.diff(rk) <= 1e-9)


def test_align_pair_recovers_circular_shift():
    n = 1500
    s = np.linspace(0.0, 4000.0, n, endpoint=False)
    v = 250 - 100*np.sin(2*np.pi*s/4000.0)**2 - 60*np.exp(-((s-2200)/150.0)**2)
    shift_m = 120.0                      # trace b starts 120 m later on track
    vb = np.interp((s + shift_m) % 4000.0, s, v)
    s_grid, va_g, vb_g, shift = align_pair(s, v, s, vb, length_m=4000.0)
    assert abs(shift - shift_m/4000.0) < 0.003
    assert np.corrcoef(va_g, vb_g)[0, 1] > 0.995


def test_registry_paths_exist_for_backtest_tracks():
    for slug in ("canada", "catalunya", "austria", "silverstone"):
        t = TRACKS[slug]
        assert os.path.exists(t["outline"]), t["outline"]
        assert os.path.exists(t["csv25"]), t["csv25"]
        assert os.path.exists(t["csv26"]), t["csv26"]
