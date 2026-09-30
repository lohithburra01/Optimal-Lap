"""Banked-corner cornering limit.

Zandvoort's Hugenholtz (T3, ~19 deg) and Arie Luyendyk (T14, ~18 deg) are the
only meaningfully banked corners on the calendar. Banking is TRACK geometry, not
car physics: the frozen 2026 car constants are untouched, a per-station
banking_deg channel on the outline feeds the lateral limit.

The contract that keeps every other track safe: at 0 deg the banked formula must
reduce EXACTLY to the flat one, so an outline without a banking channel is
bit-identical to before.
"""
import math
import os
import sys

import numpy as np
import pytest

from sim_2026_lap import (
    MASS_KG, G, RHO, CL_CORNER_M2, MU_LAT,
    v_grip_static, a_lat_max_banked, downforce, banking_channel_for_arc,
)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "cache"))
from _apply_banking import build_channel, raised_cosine  # noqa: E402


def _flat_reference(kappa):
    """The pre-banking formula, inlined so the test pins behaviour independently."""
    k = abs(kappa)
    if k < 1e-6:
        return 300.0
    denom = k - MU_LAT * 0.5 * RHO * CL_CORNER_M2 / MASS_KG
    if denom <= 0.0:
        return 300.0
    return math.sqrt(MU_LAT * G / denom)


@pytest.mark.parametrize("radius_m", [15.0, 25.0, 50.0, 120.0, 400.0, 1200.0])
def test_zero_banking_is_exactly_the_flat_formula(radius_m):
    """Zero banking must be bit-identical: this is what makes every non-banked
    track (and the LOO backtest) provably unchanged by the feature."""
    kappa = 1.0 / radius_m
    assert v_grip_static(kappa, 0.0) == _flat_reference(kappa)


def test_default_argument_is_flat():
    """Call sites that don't pass a bank angle keep the old behaviour."""
    kappa = 1.0 / 30.0
    assert v_grip_static(kappa) == _flat_reference(kappa)


def test_banking_raises_corner_speed():
    kappa = 1.0 / 30.0
    flat = v_grip_static(kappa, 0.0)
    banked = v_grip_static(kappa, math.radians(19.0))
    assert banked > flat


def test_banking_is_monotone_in_angle():
    kappa = 1.0 / 30.0
    speeds = [v_grip_static(kappa, math.radians(d)) for d in (0, 5, 10, 15, 19)]
    assert all(b > a for a, b in zip(speeds, speeds[1:]))


def test_effective_angle_is_not_the_surveyed_angle():
    """MU_LAT (1.95) is an EFFECTIVE aero-inclusive coefficient calibrated on flat
    tracks, not a mechanical tyre mu. Its friction angle arctan(1/mu) is only
    ~27 deg, so feeding Hugenholtz's surveyed ~19 deg straight in saturates the
    closed form. The banking input is therefore an EFFECTIVE angle, fitted to the
    real apex speed. This test documents that: it is a property of the model, not
    a bug, and it is why the registry stores small fitted angles."""
    kappa = 1.0 / 45.0
    surveyed = v_grip_static(kappa, math.radians(19.0)) * 3.6
    assert surveyed > 500.0, "expected the surveyed angle to saturate this model"


@pytest.mark.parametrize("deg,lo,hi", [(3.0, 1.05, 1.25),
                                       (5.0, 1.10, 1.45),
                                       (7.0, 1.15, 1.75)])
def test_small_effective_angles_give_plausible_gains(deg, lo, hi):
    """The usable range: a few degrees of EFFECTIVE bank buys a believable
    corner-speed gain rather than deleting the corner."""
    kappa = 1.0 / 45.0
    gain = v_grip_static(kappa, math.radians(deg)) / v_grip_static(kappa, 0.0)
    assert lo < gain < hi, f"{deg} deg -> gain {gain:.2f}, want ({lo},{hi})"


def test_negative_banking_is_off_camber_and_slower():
    kappa = 1.0 / 30.0
    assert v_grip_static(kappa, math.radians(-8.0)) < v_grip_static(kappa, 0.0)


def test_bank_beyond_friction_angle_does_not_explode():
    """Past arctan(1/mu) the bank alone holds the car and the closed form's
    denominator flips sign. Must saturate, not return NaN or a negative root."""
    kappa = 1.0 / 30.0
    v = v_grip_static(kappa, math.radians(75.0))
    assert np.isfinite(v) and v > 0.0


def test_a_lat_max_zero_banking_matches_friction_circle():
    """The friction-circle budget used by the brake/forward passes must also
    reduce to mu*(g + DF/m) at zero banking."""
    for v in (20.0, 45.0, 80.0):
        expected = MU_LAT * (G + downforce(v, "CORNER") / MASS_KG)
        assert a_lat_max_banked(v, "CORNER", 0.0) == pytest.approx(expected, rel=1e-12)


def test_a_lat_max_increases_with_banking():
    v = 40.0
    assert a_lat_max_banked(v, "CORNER", math.radians(19.0)) > \
           a_lat_max_banked(v, "CORNER", 0.0)


# --------------------------------------------------------------------------
# Alignment. The bank must sit ON its corner. The bug this guards: the channel
# was built pre-S/F-roll off raw station-index fractions, which slid the bump a
# whole sf_idx upstream (~96 m at Zandvoort) onto the straight before
# Hugenholtz, where it raised v_grip on a piece of track that was never grip
# limited and changed the lap by 0.13 s instead of 1.0 s. Nothing failed
# loudly — the sim still ran and the corner stayed 50 km/h slow.
# --------------------------------------------------------------------------

def _uniform_arc(n, total_len):
    return np.arange(n) / n * total_len


@pytest.mark.parametrize("s_frac", [0.05, 0.185, 0.5, 0.81, 0.97])
def test_channel_peaks_at_the_authored_arc_fraction(s_frac):
    n_outline, n_station, total = 2000, 2087, 4175.6
    chan = build_channel(n_outline, [dict(s_frac=s_frac, half_width_frac=0.02,
                                          deg=8.62)])
    rad = banking_channel_for_arc(chan, _uniform_arc(n_station, total), total)
    peak_frac = float(np.argmax(rad)) / n_station
    assert abs(((peak_frac - s_frac + 0.5) % 1.0) - 0.5) < 0.005, (
        f"bank peaked at {peak_frac:.3f}, authored at {s_frac:.3f}")


def test_channel_survives_differing_station_counts():
    """Outline and raceline station counts differ (2000 vs 2087): the mapping is
    by arc fraction, so the peak must not drift with the resample."""
    total = 4175.6
    chan = build_channel(2000, [dict(s_frac=0.185, half_width_frac=0.02, deg=8.62)])
    for n_station in (1500, 2000, 2087, 4000):
        rad = banking_channel_for_arc(chan, _uniform_arc(n_station, total), total)
        assert abs(float(np.argmax(rad)) / n_station - 0.185) < 0.005


def test_channel_peak_magnitude_is_preserved():
    total = 4175.6
    chan = build_channel(2000, [dict(s_frac=0.3, half_width_frac=0.02, deg=8.62)])
    rad = banking_channel_for_arc(chan, _uniform_arc(2087, total), total)
    assert math.degrees(rad.max()) == pytest.approx(8.62, abs=0.05)


def test_unbanked_track_channel_is_all_zero():
    total = 4175.6
    rad = banking_channel_for_arc(np.zeros(2000), _uniform_arc(2087, total), total)
    assert not np.any(rad)


def test_raised_cosine_is_smooth_and_compact():
    """No step change in lateral capacity, and strictly zero outside the window."""
    frac = np.arange(2000) / 2000
    b = raised_cosine(frac, 0.185, 0.02)
    assert b.max() == pytest.approx(1.0, abs=1e-6)
    assert b[int(0.185 * 2000)] == pytest.approx(1.0, abs=1e-3)
    assert b[int(0.30 * 2000)] == 0.0
    assert np.abs(np.diff(b)).max() < 0.05          # no discontinuity


def test_raised_cosine_wraps_across_start_finish():
    """A corner sitting on the S/F line must not be clipped in half."""
    frac = np.arange(2000) / 2000
    b = raised_cosine(frac, 0.005, 0.02)
    assert b[0] > 0.5 and b[-1] > 0.0
