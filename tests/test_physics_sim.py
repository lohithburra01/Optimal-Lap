from sim_2026_lap import (
    extract_peak_decel_g,
    extract_apex_speed_ms,
    detect_clipping_zones,
)


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
