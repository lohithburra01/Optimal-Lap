import numpy as np
import pytest

from sim_monaco_2026_lap import (
    MASS_KG, G, RHO, CL_MONACO, CDA_MONACO, MU_LAT, MU_LONG,
    drag_force, downforce, v_grip_static,
    mgu_k_cap_rev1_w, mgu_k_cap_overtake_w,
    compute_v_brake_backward, _braking_zones, _overtake_zone_mask,
    forward_pass, assert_sanity,
)


# ── Task 2: aero + grip primitives ──

def test_drag_scales_v_squared():
    assert drag_force(100.0) / drag_force(50.0) == pytest.approx(4.0, rel=1e-3)


def test_downforce_uses_monaco_cl():
    assert downforce(80.0) == pytest.approx(0.5 * RHO * CL_MONACO * 80.0 ** 2, rel=1e-9)


def test_v_grip_straight_unbounded():
    assert v_grip_static(0.0) > 200.0


def test_v_grip_hairpin_fairmont():
    # Fairmont hairpin ~48 km/h ≈ 13.3 m/s; driven-line radius ~9–11 m.
    v = v_grip_static(1.0 / 10.0)
    assert 11.0 < v < 17.0, f"hairpin v_grip = {v:.1f} m/s"


# ── Task 3: deployment curves ──

def test_rev1_full_below_200():
    assert mgu_k_cap_rev1_w(150.0 / 3.6) == pytest.approx(350_000.0)


def test_rev1_zero_at_300():
    assert mgu_k_cap_rev1_w(300.0 / 3.6) == pytest.approx(0.0, abs=1.0)


def test_rev1_midpoint_270():
    assert mgu_k_cap_rev1_w(270.0 / 3.6) == pytest.approx(100_000.0, abs=1.0)


def test_rev1_monotonic_non_increasing():
    speeds = np.linspace(0, 320, 200) / 3.6
    caps = [mgu_k_cap_rev1_w(v) for v in speeds]
    assert all(caps[i + 1] <= caps[i] + 1e-6 for i in range(len(caps) - 1))


def test_overtake_gentler_than_rev1_at_300():
    assert mgu_k_cap_overtake_w(300.0 / 3.6) == pytest.approx(150_000.0, abs=1.0)
    assert mgu_k_cap_overtake_w(300.0 / 3.6) > mgu_k_cap_rev1_w(300.0 / 3.6)


def test_overtake_zero_at_310():
    assert mgu_k_cap_overtake_w(310.0 / 3.6) == pytest.approx(0.0, abs=1.0)


# ── Task 4: brake pass + zone masks ──

def test_brake_pass_respects_apex():
    n = 100
    kappa = np.zeros(n)
    arc = np.linspace(0, 1000.0, n, endpoint=False)
    v_grip = np.full(n, 100.0)
    v_grip[50] = 20.0
    v_brake = compute_v_brake_backward(v_grip, kappa, arc, 1000.0)
    assert v_brake[49] < v_brake[48]
    assert v_brake[50] == pytest.approx(20.0, abs=0.5)
    assert v_brake[10] == pytest.approx(100.0, abs=0.5)


def test_overtake_mask_picks_fastest_zone():
    # Two braking zones → two drive zones: a slow one (around idx 40) and a fast
    # one (around idx 140). Only the fast zone gets the overtake mask.
    n = 200
    braking = np.zeros(n, dtype=bool)
    braking[20:30] = True
    braking[95:105] = True
    v = np.full(n, 50.0)
    v[120:160] = 120.0           # fast zone in the second drive section
    mask = _overtake_zone_mask(v, braking)
    assert mask[140] and not mask[40]


# ── Task 5: forward pass ──

def test_forward_pass_no_clipping_on_short_straight():
    # A short straight (deploy energy well under the 4 MJ store) with a full
    # battery must stay in DEPLOY — no premature clipping. (A 3 km dead straight
    # with zero regen WOULD drain and clip; that is correct Monaco physics, so
    # the realistic case here is a short stretch, like the gaps between Monaco's
    # constant braking/regen zones.)
    n = 150
    kappa = np.zeros(n)
    arc = np.linspace(0, 500.0, n, endpoint=False)
    v_grip = np.full(n, 250.0)
    v_brake = np.full(n, 250.0)
    v, soc, mode, p_kw, mgu_kw, t = forward_pass(
        v_grip, v_brake, kappa, arc, 500.0, v0=50.0, soc0=1.0)
    assert "CLIPPING" not in mode
    assert v[-1] > 60.0


def test_forward_pass_rev1_zeroes_mgu_above_300():
    # A straight that exceeds 300 km/h must show 0 MGU-K under Rev1.
    n = 400
    kappa = np.zeros(n)
    arc = np.linspace(0, 6000.0, n, endpoint=False)
    v_grip = np.full(n, 100.0)   # 100 m/s = 360 km/h
    v_brake = np.full(n, 100.0)
    v, soc, mode, p_kw, mgu_kw, t = forward_pass(
        v_grip, v_brake, kappa, arc, 6000.0, v0=90.0, soc0=1.0, overtake_mask=None)
    above = v * 3.6 >= 300.0
    assert np.all(mgu_kw[above] <= 1e-6), "MGU-K deployed above 300 km/h under Rev1"


# ── Task 6: sanity ──

def test_assert_sanity_rejects_clipping():
    n = 50
    v = np.full(n, 200.0 / 3.6)
    mode = ["CLIPPING"] + ["DEPLOY"] * (n - 1)
    t = np.linspace(0, 75.0, n)
    ot = np.zeros(n, dtype=bool)
    with pytest.raises(SystemExit):
        assert_sanity(v, np.ones(n), mode, np.zeros(n), np.zeros(n), t, ot)
