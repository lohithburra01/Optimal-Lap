import math

import numpy as np
import pytest

from sim_2026_lap import (
    extract_peak_decel_g,
    extract_apex_speed_ms,
    detect_clipping_zones,
)
from sim_2026_lap import (
    MASS_KG, G, RHO, CL_CORNER_M2, CL_STRAIGHT_M2, CDA_CORNER_M2, CDA_STRAIGHT_M2,
    MU_LAT, MU_LONG, KAPPA_CORNER_THRESH,
    aero_mode, drag_force, downforce, v_grip_static,
)
from sim_2026_lap import compute_v_brake_backward


def _synth_lap(brake_decel_g=4.5, v_apex_ms=20.0, n=400):
    """Synthetic CSV-style lap with one corner: straight → brake → apex →
    re-accelerate → straight. Used to test the calibration extractors."""
    import numpy as np
    G = 9.81
    t = np.linspace(0, 80.0, n)
    v = np.full(n, 90.0)                   # 90 m/s straight
    # Brake from index 100 to 150
    for i in range(100, 150):
        v[i] = max(v_apex_ms, v[i-1] - brake_decel_g * G * (t[i] - t[i-1]))
    v[150:170] = v_apex_ms                 # hold apex
    # Re-accelerate
    for i in range(170, 250):
        v[i] = min(90.0, v[i-1] + 1.5 * G * (t[i] - t[i-1]))
    v[250:] = 90.0
    brake = [100.0 if 100 <= i < 150 else 0.0 for i in range(n)]
    throttle = [0.0 if 100 <= i < 170 else 100.0 for i in range(n)]
    speed_kmh = v * 3.6
    d = np.cumsum(np.concatenate([[0.0], (v[:-1] + v[1:]) / 2.0 * np.diff(t)]))
    rows = [{"time_s": ti, "distance": di, "speed": si, "throttle": th, "brake": br}
            for ti, di, si, th, br in zip(t, d, speed_kmh, throttle, brake)]
    return rows


def test_extract_peak_decel_g():
    rows = _synth_lap(brake_decel_g=4.5)
    g = extract_peak_decel_g(rows)
    assert 4.0 < g < 5.0, f"peak decel = {g:.2f} g"


def test_extract_apex_speed_ms():
    rows = _synth_lap(v_apex_ms=22.5)
    v_apex = extract_apex_speed_ms(rows)
    assert 22.0 < v_apex < 23.5


def test_detect_clipping_zones_finds_flatline_at_top_speed():
    # Synth: a 1-km straight where speed hits 90 m/s, then "clips" (flatlines)
    # in the last 300 m
    import numpy as np
    n = 600
    t = np.linspace(0, 30.0, n)
    v = np.minimum(t * 4.0, 90.0)          # ramp up
    v[400:] = 89.0                          # flatline (clipping)
    rows = [{"time_s": ti, "distance": float(np.cumsum(v)[i] * (t[1]-t[0])),
             "speed": vi * 3.6, "throttle": 100.0, "brake": 0.0}
            for i, (ti, vi) in enumerate(zip(t, v))]
    zones = detect_clipping_zones(rows)
    # Should detect 1 clipping zone with frac_in_straight > 0.5
    assert len(zones) >= 1
    assert zones[0]["frac_in_straight"] > 0.5


def test_extract_peak_decel_g_robust_to_speed_quantization():
    # FastF1's speed channel reports a plateau then dumps the accumulated dv
    # into one normal-dt sample. Point-wise dv/dt misreads this as ~8 g; the
    # windowed extractor must spread it over the window and stay physical.
    import numpy as np
    # 6 s of braking telemetry at ~0.13 s spacing (FastF1-like).
    t = np.arange(0.0, 6.0, 0.13)
    # True physics: a steady 4.5 g decel from 90 m/s.
    v_true = np.maximum(20.0, 90.0 - 4.5 * 9.81 * t)
    # Quantize speed into 12-km/h steps -> plateau-then-jump artifact.
    v_kmh = v_true * 3.6
    v_quant = np.round(v_kmh / 12.0) * 12.0
    rows = [{"time_s": float(ti), "distance": 0.0, "speed": float(vi),
             "throttle": 0.0, "brake": 100.0} for ti, vi in zip(t, v_quant)]
    g = extract_peak_decel_g(rows)
    # True decel is 4.5 g; allow generous band, but the 8+ g quantization
    # artifact must NOT leak through.
    assert 3.5 < g < 6.0, f"quantization artifact leaked: {g:.2f} g"


def test_aero_mode_thresholds():
    assert aero_mode(0.0) == "STRAIGHT"
    assert aero_mode(0.001) == "STRAIGHT"
    assert aero_mode(0.01) == "CORNER"


def test_drag_force_scales_with_v_squared():
    f1 = drag_force(50.0, "STRAIGHT")
    f2 = drag_force(100.0, "STRAIGHT")
    # Drag proportional to v^2 -> 4x when v doubles
    assert f2 / f1 == pytest.approx(4.0, rel=1e-3)


def test_drag_higher_in_corner_mode():
    # Corner Mode has higher CdA (wing closed) than Straight Mode
    assert drag_force(80.0, "CORNER") > drag_force(80.0, "STRAIGHT")


def test_downforce_corner_higher_than_straight():
    assert downforce(80.0, "CORNER") > downforce(80.0, "STRAIGHT")


def test_v_grip_no_downforce_baseline():
    # For a turn of radius R with NO downforce, v^2 = mu_lat * g * R.
    R = 30.0
    v = v_grip_static(1.0 / R)
    expected_no_df = math.sqrt(MU_LAT * G * R)
    # With downforce engaged, v_grip should be HIGHER than the no-DF baseline
    assert v > expected_no_df


def test_v_grip_straight_is_unbounded():
    # A genuine straight (kappa = 0) returns a large fallback, not NaN/inf
    v = v_grip_static(0.0)
    assert v > 200.0  # m/s -- i.e. effectively no corner cap


def test_v_grip_hairpin_realistic():
    # Canada hairpin (T10) driven-line radius ~ 25 m -> kappa ~ 0.04 1/m.
    # (The 15 m geometric kerb radius is far tighter than the line a car
    # actually takes through the apex.) Expected 2026 hairpin speed
    # ~ 70-95 km/h = ~20-26 m/s, consistent with the v_apex calibration
    # (22.5 m/s) and the spec's [70, 105] km/h hairpin window.
    v = v_grip_static(1.0 / 25.0)
    assert 18.0 < v < 30.0, f"hairpin v_grip = {v:.1f} m/s, outside realistic range"


def test_brake_pass_respects_apex_speed():
    # 100 stations, all straight (kappa=0), with one slow corner at index 50
    n = 100
    kappa = np.zeros(n)
    arc = np.linspace(0, 1000.0, n, endpoint=False)   # 10 m spacing, 1000 m total
    v_grip = np.full(n, 100.0)
    v_grip[50] = 30.0    # forced slow corner
    v_brake = compute_v_brake_backward(v_grip, kappa, arc, track_length_m=1000.0)
    # Stations just before index 50 should be braking-limited (lower than 100)
    assert v_brake[48] < 100.0
    assert v_brake[49] < v_brake[48]   # decreasing toward the apex
    assert v_brake[50] == pytest.approx(30.0, abs=0.5)
    # Far from the corner the brake constraint shouldn't apply
    assert v_brake[10] == pytest.approx(100.0, abs=0.5)
