# Monaco 2026 Physics Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone `sim_monaco_2026_lap.py` physics engine that correctly models the 2026 Monaco regulations (locked Z-mode max-downforce aero, Rev1 speed-dependent MGU-K deployment cap, no clipping/superclipping), plus a Monaco track-length/width option in `svg_to_outline.py` and a `make_monaco_2026_lap.bat` pipeline.

**Architecture:** Import the validated, track-agnostic racing-line builder (`build_raceline`) and generic helpers (`_clean_runs`, `write_csv`) from `sim_2026_lap.py`; rewrite only the physics block for Monaco. Energy is abundant at Monaco, so the 5-mode Canada system collapses to DEPLOY/REGEN with the Rev1 speed cap as the binding constraint.

**Tech Stack:** Python 3.10, numpy, scipy, quadprog, trajectory_planning_helpers (all already used by the Canada pipeline). pytest for tests.

**Spec:** `docs/2026-06-04-monaco-2026-physics-engine-design.md`

---

## File Structure

- **Modify** `svg_to_outline.py` — add `--track-length` / `--road-width` CLI args (backward-compatible) and scale hairpin narrowing to road width.
- **Create** `sim_monaco_2026_lap.py` — Monaco physics engine (imports `build_raceline`, `_clean_runs`, `write_csv` from `sim_2026_lap`).
- **Create** `tests/test_monaco_physics.py` — unit tests for the Monaco physics.
- **Create** `make_monaco_2026_lap.bat` — SVG → outline → sim → video pipeline.

---

## Task 1: Parametrize track length & width in `svg_to_outline.py`

**Files:**
- Modify: `svg_to_outline.py` (constants block ~line 17, `build_outline_from_svg` ~line 323, `main` ~line 377)
- Test: `tests/test_outline_geometry.py` (add one test)

- [ ] **Step 1: Add a hairpin-narrow ratio constant and CLI plumbing**

In the constants block, add after `HAIRPIN_NARROW_M`:
```python
HAIRPIN_NARROW_RATIO    = HAIRPIN_NARROW_M / ROAD_WIDTH_M   # 0.8077 (10.5/13.0)
```

Change `build_outline_from_svg` signature and body to accept overrides:
```python
def build_outline_from_svg(svg_path, track_length_m=TRACK_LENGTH_M,
                           road_width_m=ROAD_WIDTH_M):
    ...
    scaled, scale = scale_to_length(raw_poly, track_length_m)
    ...
    centerline = smooth_resample_loop(scaled, N_OUTPUT_POINTS, smooth_s=30.0)
    ...
    kappa = compute_curvature(centerline)
    arc_per_step = track_length_m / N_OUTPUT_POINTS
    widths = np.full(N_OUTPUT_POINTS, road_width_m)
    apply_hairpin_narrowing(widths, kappa, arc_per_step,
                            HAIRPIN_HALF_RANGE_M, road_width_m * HAIRPIN_NARROW_RATIO)
```

In `main`, add args and pass them:
```python
ap.add_argument("--track-length", type=float, default=TRACK_LENGTH_M)
ap.add_argument("--road-width", type=float, default=ROAD_WIDTH_M)
...
outer, inner = build_outline_from_svg(args.svg, args.track_length, args.road_width)
```

- [ ] **Step 2: Write a test that a smaller track-length scales the outline**

```python
def test_track_length_override_scales_perimeter(tmp_path):
    import json, numpy as np
    from svg_to_outline import build_outline_from_svg
    svg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "Circuit_Monaco.svg")
    outer, inner = build_outline_from_svg(svg, track_length_m=3337.0, road_width_m=9.0)
    # centerline perimeter ≈ mean of outer/inner perimeters ≈ target
    def perim(p):
        p = np.asarray(p); return float(np.linalg.norm(np.diff(np.vstack([p, p[0]]), axis=0), axis=1).sum())
    mid = (perim(outer) + perim(inner)) / 2.0
    assert 3000.0 < mid < 3700.0, f"centerline perimeter {mid:.0f} m off target 3337"
```

- [ ] **Step 3: Run it**

Run: `python -m pytest tests/test_outline_geometry.py::test_track_length_override_scales_perimeter -v`
Expected: PASS

- [ ] **Step 4: Verify Canada defaults unchanged**

Run: `python -m pytest tests/test_outline_geometry.py -v`
Expected: all PASS (defaults keep Canada behavior identical)

- [ ] **Step 5: Commit**

```bash
git add "OPTIMAL LAP SCRIPTS/svg_to_outline.py" "OPTIMAL LAP SCRIPTS/tests/test_outline_geometry.py"
git commit -m "svg_to_outline: add --track-length/--road-width (backward-compatible)"
```

---

## Task 2: Monaco aero + grip primitives

**Files:**
- Create: `sim_monaco_2026_lap.py`
- Test: `tests/test_monaco_physics.py`

- [ ] **Step 1: Write the module header, constants, and aero/grip functions**

```python
"""sim_monaco_2026_lap.py — Monaco 2026 optimal-lap physics engine.

Reuses the validated, track-agnostic racing-line builder from sim_2026_lap;
rewrites the physics for Monaco 2026:
  * Active aero DISABLED → locked Z-mode (max downforce, high drag) all lap.
  * Rev1 speed-dependent MGU-K cap (350kW→200km/h, 0 by 300km/h); overtake
    mode (150kW@300, 0@310) on the single fastest zone (tunnel/main straight).
  * Energy is abundant → no clipping, no superclipping. Modes = DEPLOY / REGEN.

Spec: docs/2026-06-04-monaco-2026-physics-engine-design.md
"""
import argparse, json, math, os, sys
import numpy as np

from sim_2026_lap import build_raceline, _clean_runs, write_csv

# ── Vehicle (2026) ──
MASS_KG = 768.0
G       = 9.81
RHO     = 1.225

# ── Aero — single locked Z-mode (max downforce, wings closed, high drag) ──
CL_MONACO  = 3.00     # effective Cl·A, max-DF Monaco wing (post-2026 −30%)
CDA_MONACO = 1.85     # effective Cd·A, Z-mode locked closed

# ── Power ──
P_ICE_MAX_W       = 400_000     # 400 kW combustion
P_MGU_REGEN_MAX_W = 350_000     # MGU-K regen ceiling under braking
E_BATTERY_CAP_J   = 4_000_000   # ~4 MJ usable store

# ── Tyre grip ──
MU_LONG = 1.60
MU_LAT  = 1.95

# ── Mode-switching / numerics ──
KAPPA_CORNER_THRESH = 0.005
V_FLOOR_MS          = 5.0
SOC_INIT            = 1.0
BRAKE_DECEL_THRESH  = 4.0


def drag_force(v):
    return 0.5 * RHO * CDA_MONACO * v * v


def downforce(v):
    return 0.5 * RHO * CL_MONACO * v * v


def v_grip_static(kappa):
    """Steady-state cornering speed with the single locked high-downforce config:
        μ_lat (m·g + 0.5·ρ·Cl·v²) = m·v²·|κ|
        v² = μ_lat·g / (|κ| − μ_lat·0.5·ρ·Cl/m)"""
    k = abs(kappa)
    if k < 1e-6:
        return 300.0
    denom = k - MU_LAT * 0.5 * RHO * CL_MONACO / MASS_KG
    if denom <= 0.0:
        return 300.0
    return math.sqrt(MU_LAT * G / denom)
```

- [ ] **Step 2: Write tests for the primitives**

```python
import math
import numpy as np
import pytest
from sim_monaco_2026_lap import (
    MASS_KG, G, RHO, CL_MONACO, CDA_MONACO, MU_LAT, MU_LONG,
    drag_force, downforce, v_grip_static,
)

def test_drag_scales_v_squared():
    assert drag_force(100.0) / drag_force(50.0) == pytest.approx(4.0, rel=1e-3)

def test_downforce_uses_monaco_cl():
    assert downforce(80.0) == pytest.approx(0.5 * RHO * CL_MONACO * 80.0**2, rel=1e-9)

def test_v_grip_straight_unbounded():
    assert v_grip_static(0.0) > 200.0

def test_v_grip_hairpin_fairmont():
    # Fairmont hairpin ~48 km/h ≈ 13.3 m/s. Driven-line radius ~9–11 m.
    v = v_grip_static(1.0 / 10.0)
    assert 11.0 < v < 17.0, f"hairpin v_grip = {v:.1f} m/s"
```

- [ ] **Step 3: Run**

Run: `python -m pytest tests/test_monaco_physics.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add "OPTIMAL LAP SCRIPTS/sim_monaco_2026_lap.py" "OPTIMAL LAP SCRIPTS/tests/test_monaco_physics.py"
git commit -m "monaco sim: aero (locked Z-mode) + grip primitives"
```

---

## Task 3: Rev1 + overtake MGU-K deployment curves

**Files:**
- Modify: `sim_monaco_2026_lap.py`
- Test: `tests/test_monaco_physics.py`

- [ ] **Step 1: Add the two deployment-cap functions**

```python
def mgu_k_cap_rev1_w(v_ms):
    """Mandated Monaco Rev1 MGU-K cap vs speed. Piecewise-linear through the
    published points: 350kW≤200, 100kW@270, 0@300 km/h."""
    kmh = v_ms * 3.6
    if kmh <= 200.0:
        return 350_000.0
    if kmh <= 270.0:
        return 350_000.0 + (kmh - 200.0) * (100_000.0 - 350_000.0) / 70.0
    if kmh <= 300.0:
        return 100_000.0 + (kmh - 270.0) * (0.0 - 100_000.0) / 30.0
    return 0.0


def mgu_k_cap_overtake_w(v_ms):
    """Overtake-mode cap (applied only on the fastest zone): gentler taper —
    350kW≤200, 150kW@300, 0@310 km/h."""
    kmh = v_ms * 3.6
    if kmh <= 200.0:
        return 350_000.0
    if kmh <= 300.0:
        return 350_000.0 + (kmh - 200.0) * (150_000.0 - 350_000.0) / 100.0
    if kmh <= 310.0:
        return 150_000.0 + (kmh - 300.0) * (0.0 - 150_000.0) / 10.0
    return 0.0


def mgu_k_cap_w(v_ms, overtake):
    return mgu_k_cap_overtake_w(v_ms) if overtake else mgu_k_cap_rev1_w(v_ms)
```

- [ ] **Step 2: Tests for the curves**

```python
from sim_monaco_2026_lap import mgu_k_cap_rev1_w, mgu_k_cap_overtake_w

def test_rev1_full_below_200():
    assert mgu_k_cap_rev1_w(150.0 / 3.6) == pytest.approx(350_000.0)

def test_rev1_zero_at_300():
    assert mgu_k_cap_rev1_w(300.0 / 3.6) == pytest.approx(0.0, abs=1.0)

def test_rev1_midpoint_270():
    assert mgu_k_cap_rev1_w(270.0 / 3.6) == pytest.approx(100_000.0, abs=1.0)

def test_rev1_monotonic_non_increasing():
    speeds = np.linspace(0, 320, 200) / 3.6
    caps = [mgu_k_cap_rev1_w(v) for v in speeds]
    assert all(caps[i+1] <= caps[i] + 1e-6 for i in range(len(caps)-1))

def test_overtake_gentler_than_rev1_at_300():
    assert mgu_k_cap_overtake_w(300.0/3.6) == pytest.approx(150_000.0, abs=1.0)
    assert mgu_k_cap_overtake_w(300.0/3.6) > mgu_k_cap_rev1_w(300.0/3.6)

def test_overtake_zero_at_310():
    assert mgu_k_cap_overtake_w(310.0/3.6) == pytest.approx(0.0, abs=1.0)
```

- [ ] **Step 3: Run**

Run: `python -m pytest tests/test_monaco_physics.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add "OPTIMAL LAP SCRIPTS/sim_monaco_2026_lap.py" "OPTIMAL LAP SCRIPTS/tests/test_monaco_physics.py"
git commit -m "monaco sim: Rev1 + overtake MGU-K deployment curves"
```

---

## Task 4: Braking pass, ideal profile, braking-zone & overtake-zone masks

**Files:**
- Modify: `sim_monaco_2026_lap.py`
- Test: `tests/test_monaco_physics.py`

- [ ] **Step 1: Add brake backward pass + ideal profile + zone masks**

```python
def compute_v_brake_backward(v_grip, kappa, arc, track_length_m, n_iters=3):
    n = len(v_grip)
    ds = np.diff(np.concatenate([arc, [track_length_m]]))
    v = v_grip.copy()
    for _ in range(n_iters):
        for i in range(n - 1, -1, -1):
            ip = (i + 1) % n
            a_lat_used = abs(kappa[ip]) * v[ip] * v[ip]
            a_lat_max = MU_LAT * (G + downforce(v[ip]) / MASS_KG)
            if a_lat_max <= 0.0:
                continue
            ratio_sq = min(1.0, (a_lat_used / a_lat_max) ** 2)
            a_long_grip = MU_LONG * (G + downforce(v[ip]) / MASS_KG) * math.sqrt(1.0 - ratio_sq)
            a_decel = a_long_grip + drag_force(v[ip]) / MASS_KG
            v_pred = math.sqrt(max(0.0, v[ip] * v[ip] + 2.0 * a_decel * ds[i]))
            if v_pred < v[i]:
                v[i] = v_pred
    return v


def _ideal_speed_profile(v_grip, v_brake, kappa, ds, v0):
    """Forward profile with full available power (ICE + Rev1 cap) everywhere —
    used only to locate genuine braking zones."""
    n = len(v_grip)
    v = np.empty(n)
    v[0] = min(v0, v_grip[0], v_brake[0])
    for i in range(n):
        vi = v[i]
        a_lat_used = abs(kappa[i]) * vi * vi
        a_lat_max = MU_LAT * (G + downforce(vi) / MASS_KG)
        ratio_sq = min(1.0, (a_lat_used / max(a_lat_max, 1e-6)) ** 2)
        a_long_grip = MU_LONG * (G + downforce(vi) / MASS_KG) * math.sqrt(1.0 - ratio_sq)
        P = P_ICE_MAX_W + mgu_k_cap_rev1_w(vi)
        a_long_power = P / (MASS_KG * max(vi, V_FLOOR_MS))
        a_drag = drag_force(vi) / MASS_KG
        a_long = min(a_long_grip, a_long_power) - a_drag
        v_next = math.sqrt(max(V_FLOOR_MS ** 2, vi * vi + 2.0 * a_long * ds[i]))
        v[(i + 1) % n] = min(v_next, v_grip[(i + 1) % n], v_brake[(i + 1) % n])
    return v


def _braking_zones(v_grip, v_brake, kappa, ds, v0):
    n = len(v_grip)
    v_ideal = _ideal_speed_profile(v_grip, v_brake, kappa, ds, v0)
    raw = np.zeros(n, dtype=bool)
    for i in range(n):
        nxt = (i + 1) % n
        decel = (v_ideal[i] ** 2 - v_ideal[nxt] ** 2) / (2.0 * max(ds[i], 1e-3))
        raw[i] = decel > BRAKE_DECEL_THRESH
    return _clean_runs(raw, min_run=6)


def _overtake_zone_mask(v_profile, braking):
    """Mark every station of the single fastest drive (non-braking) zone — the
    tunnel/main straight — where overtake-mode deployment applies."""
    n = len(braking)
    mask = np.zeros(n, dtype=bool)
    if braking.all() or not braking.any():
        return mask
    start = next(s for s in range(n) if not braking[s] and braking[(s - 1) % n])
    best_zone, best_peak = [], -1.0
    k = 0
    while k < n:
        if braking[(start + k) % n]:
            k += 1
            continue
        zone = []
        while k < n and not braking[(start + k) % n]:
            zone.append((start + k) % n)
            k += 1
        peak = max(v_profile[z] for z in zone)
        if peak > best_peak:
            best_peak, best_zone = peak, zone
    for z in best_zone:
        mask[z] = True
    return mask
```

- [ ] **Step 2: Tests**

```python
from sim_monaco_2026_lap import compute_v_brake_backward, _braking_zones, _overtake_zone_mask

def test_brake_pass_respects_apex():
    n = 100
    kappa = np.zeros(n)
    arc = np.linspace(0, 1000.0, n, endpoint=False)
    v_grip = np.full(n, 100.0); v_grip[50] = 20.0
    v_brake = compute_v_brake_backward(v_grip, kappa, arc, 1000.0)
    assert v_brake[49] < v_brake[48]
    assert v_brake[50] == pytest.approx(20.0, abs=0.5)
    assert v_brake[10] == pytest.approx(100.0, abs=0.5)

def test_overtake_mask_picks_fastest_zone():
    # Two drive zones split by braking; the second is faster → masked.
    n = 200
    braking = np.zeros(n, dtype=bool); braking[95:105] = True
    v = np.full(n, 50.0); v[120:160] = 120.0   # fast zone in the second half
    mask = _overtake_zone_mask(v, braking)
    assert mask[140] and not mask[40]
```

- [ ] **Step 3: Run**

Run: `python -m pytest tests/test_monaco_physics.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add "OPTIMAL LAP SCRIPTS/sim_monaco_2026_lap.py" "OPTIMAL LAP SCRIPTS/tests/test_monaco_physics.py"
git commit -m "monaco sim: brake pass + braking/overtake zone masks"
```

---

## Task 5: Forward pass (DEPLOY/REGEN) + closure loop

**Files:**
- Modify: `sim_monaco_2026_lap.py`
- Test: `tests/test_monaco_physics.py`

- [ ] **Step 1: Add the forward pass and closure loop**

```python
def forward_pass(v_grip, v_brake, kappa, arc, track_length_m,
                 v0=None, soc0=SOC_INIT, overtake_mask=None):
    """Walk the lap forward. Two states: REGEN in braking zones (MGU-K harvests),
    DEPLOY everywhere else (MGU-K gives mgu_k_cap(v); overtake curve on the
    overtake_mask zone). CLIPPING is a defensive fallback if SoC hits 0 — it
    must never fire at Monaco (energy is abundant).

    Returns (v, soc, mode, p_kw, mgu_kw, t)."""
    n = len(v_grip)
    ds = np.diff(np.concatenate([arc, [track_length_m]]))
    v_init = v0 if v0 is not None else min(v_grip[0], v_brake[0])
    braking = _braking_zones(v_grip, v_brake, kappa, ds, v_init)
    if overtake_mask is None:
        overtake_mask = np.zeros(n, dtype=bool)

    v = np.full(n, v_init)
    soc_arr = np.zeros(n)
    mode_arr = ["DEPLOY"] * n
    p_kw_arr = np.zeros(n)
    mgu_kw_arr = np.zeros(n)
    t_arr = np.zeros(n)
    soc = soc0
    t = 0.0

    for i in range(n):
        v_cap = min(v_grip[i], v_brake[i])
        if v[i] > v_cap:
            v[i] = v_cap
        soc_arr[i] = soc

        if braking[i]:
            mode_arr[i] = "REGEN"
            v_next = min(v[i], v_grip[(i + 1) % n], v_brake[(i + 1) % n])
            v[(i + 1) % n] = v_next
            dt = 2.0 * ds[i] / max(v[i] + v_next, 1e-3)
            soc = min(1.0, soc + P_MGU_REGEN_MAX_W * dt / E_BATTERY_CAP_J)
            p_kw_arr[i] = -P_MGU_REGEN_MAX_W / 1000.0
            mgu_kw_arr[i] = 0.0
            t += dt; t_arr[i] = t
            continue

        cap = mgu_k_cap_w(v[i], overtake_mask[i])
        mgu = cap if soc > 0.0 else 0.0
        mode_arr[i] = "CLIPPING" if (soc <= 0.0 and cap > 0.0) else "DEPLOY"
        P_total = P_ICE_MAX_W + mgu

        a_lat_used = abs(kappa[i]) * v[i] * v[i]
        a_lat_max = MU_LAT * (G + downforce(v[i]) / MASS_KG)
        ratio_sq = min(1.0, (a_lat_used / max(a_lat_max, 1e-6)) ** 2)
        a_long_grip = MU_LONG * (G + downforce(v[i]) / MASS_KG) * math.sqrt(1.0 - ratio_sq)
        a_long_power = P_total / (MASS_KG * max(v[i], V_FLOOR_MS))
        a_long = min(a_long_grip, a_long_power) - drag_force(v[i]) / MASS_KG

        v_next = math.sqrt(max(V_FLOOR_MS ** 2, v[i] * v[i] + 2.0 * a_long * ds[i]))
        v_next = min(v_next, v_grip[(i + 1) % n], v_brake[(i + 1) % n])
        v[(i + 1) % n] = v_next
        dt = 2.0 * ds[i] / max(v[i] + v_next, 1e-3)
        soc = min(1.0, max(0.0, soc - mgu * dt / E_BATTERY_CAP_J))
        p_kw_arr[i] = P_total / 1000.0
        mgu_kw_arr[i] = mgu / 1000.0
        t += dt; t_arr[i] = t

    return v, soc_arr, mode_arr, p_kw_arr, mgu_kw_arr, t_arr


def simulate_lap(raceline, arc, kappa, track_length_m, max_iters=8, tol_v=1.0):
    from scipy.ndimage import median_filter
    kappa_smooth = median_filter(np.asarray(kappa, dtype=float), size=5, mode="wrap")
    v_grip = np.array([v_grip_static(k) for k in kappa_smooth])
    ds = np.diff(np.concatenate([arc, [track_length_m]]))
    v0 = 50.0
    v = soc = mode = p_kw = mgu_kw = t_arr = None
    for it in range(max_iters):
        v_brake = compute_v_brake_backward(v_grip, kappa, arc, track_length_m)
        braking = _braking_zones(v_grip, v_brake, kappa, ds, v0)
        v_ns = forward_pass(v_grip, v_brake, kappa, arc, track_length_m,
                            v0=v0, overtake_mask=None)[0]
        ot_mask = _overtake_zone_mask(v_ns, braking)
        v, soc, mode, p_kw, mgu_kw, t_arr = forward_pass(
            v_grip, v_brake, kappa, arc, track_length_m, v0=v0, overtake_mask=ot_mask)
        dv = abs(v[-1] - v[0])
        print(f"  closure iter {it}: v0={v[0]:.1f} vN={v[-1]:.1f} d={dv:.2f} T_lap={t_arr[-1]:.3f}s")
        if dv < tol_v and it >= 1:
            print(f"  closure converged at iter {it}")
            break
        v0 = 0.5 * (v[0] + v[-1])
    return v, soc, mode, p_kw, mgu_kw, t_arr
```

- [ ] **Step 2: Tests**

```python
from sim_monaco_2026_lap import forward_pass

def test_forward_pass_no_clipping_when_full_battery():
    n = 300
    kappa = np.zeros(n)
    arc = np.linspace(0, 3000.0, n, endpoint=False)
    v_grip = np.full(n, 250.0); v_brake = np.full(n, 250.0)
    v, soc, mode, p_kw, mgu_kw, t = forward_pass(
        v_grip, v_brake, kappa, arc, 3000.0, v0=30.0, soc0=1.0)
    assert "CLIPPING" not in mode
    assert v[-1] > 60.0

def test_forward_pass_rev1_zeroes_mgu_above_300():
    # A long straight that exceeds 300 km/h must show 0 MGU-K (Rev1), not overtake.
    n = 400
    kappa = np.zeros(n)
    arc = np.linspace(0, 6000.0, n, endpoint=False)
    v_grip = np.full(n, 100.0); v_brake = np.full(n, 100.0)   # 100 m/s = 360 km/h
    v, soc, mode, p_kw, mgu_kw, t = forward_pass(
        v_grip, v_brake, kappa, arc, 6000.0, v0=90.0, soc0=1.0, overtake_mask=None)
    above = v * 3.6 >= 300.0
    assert np.all(mgu_kw[above] <= 1e-6), "MGU-K deployed above 300 km/h under Rev1"
```

- [ ] **Step 3: Run**

Run: `python -m pytest tests/test_monaco_physics.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add "OPTIMAL LAP SCRIPTS/sim_monaco_2026_lap.py" "OPTIMAL LAP SCRIPTS/tests/test_monaco_physics.py"
git commit -m "monaco sim: forward pass (DEPLOY/REGEN) + closure loop"
```

---

## Task 6: Sanity assertions + `main()`

**Files:**
- Modify: `sim_monaco_2026_lap.py`
- Test: `tests/test_monaco_physics.py`

- [ ] **Step 1: Add `assert_sanity` and `main`**

```python
def assert_sanity(v, soc, mode, p_kw, mgu_kw, t_arr, overtake_mask):
    """Hard-fail (exit 10) if the Monaco lap is out of physical bounds."""
    T_lap = float(t_arr[-1])
    v_kmh = v * 3.6
    v_max = float(np.max(v_kmh)); v_min = float(np.min(v_kmh))
    n_clip = sum(1 for m in mode if m == "CLIPPING")
    n_super = sum(1 for m in mode if m == "SUPERCLIP")

    fails = []
    if not (70.0 <= T_lap <= 80.0):
        fails.append(f"T_lap {T_lap:.2f}s outside [70, 80]")
    if not (270.0 <= v_max <= 305.0):
        fails.append(f"peak v {v_max:.1f} km/h outside [270, 305]")
    if not (42.0 <= v_min <= 60.0):
        fails.append(f"hairpin v {v_min:.1f} km/h outside [42, 60]")
    if n_clip != 0:
        fails.append(f"{n_clip} CLIPPING stations — battery must never empty at Monaco")
    if n_super != 0:
        fails.append(f"{n_super} SUPERCLIP stations — superclipping does not exist at Monaco")
    # Rev1/overtake honored: MGU-K never exceeds the applicable speed cap.
    for i in range(len(v)):
        cap_kw = mgu_k_cap_w(v[i], overtake_mask[i]) / 1000.0
        if mgu_kw[i] > cap_kw + 1e-3:
            fails.append(f"station {i}: MGU-K {mgu_kw[i]:.0f}kW > cap {cap_kw:.0f}kW at {v_kmh[i]:.0f}km/h")
            break

    print(f"[sanity] T_lap={T_lap:.2f}s  v=[{v_min:.0f},{v_max:.0f}] km/h  "
          f"clip={n_clip} super={n_super} overtake_stations={int(overtake_mask.sum())}")
    if fails:
        for f in fails:
            print(f"[sanity] FAIL: {f}", file=sys.stderr)
        sys.exit(10)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--outline", required=True)
    ap.add_argument("--raceline-out", required=True)
    ap.add_argument("--csv-out", required=True)
    args = ap.parse_args()

    with open(args.outline, encoding="utf-8") as f:
        data = json.load(f)
    outer_raw = np.array(data["outer"], dtype=float)
    inner_raw = np.array(data["inner"], dtype=float)
    print(f"[monaco] outline loaded: outer={len(outer_raw)} inner={len(inner_raw)}")

    raceline, arc, kappa, total_len = build_raceline(outer_raw, inner_raw)
    print(f"[monaco] raceline: {len(raceline)} pts, {total_len:.0f} m, "
          f"|κ|max={np.abs(kappa).max():.4f}")

    os.makedirs(os.path.dirname(os.path.abspath(args.raceline_out)), exist_ok=True)
    with open(args.raceline_out, "w", encoding="utf-8") as f:
        json.dump({"raceline": raceline.tolist(), "arc_length": arc.tolist(),
                   "kappa": kappa.tolist(), "track_length_m": float(total_len)}, f)
    print(f"[monaco] wrote raceline -> {args.raceline_out}")

    v, soc, mode, p_kw, mgu_kw, t_arr = simulate_lap(raceline, arc, kappa, total_len)

    # Recompute the overtake mask on the final profile for the sanity check.
    ds = np.diff(np.concatenate([arc, [total_len]]))
    braking = _braking_zones(
        np.array([v_grip_static(k) for k in kappa]),
        compute_v_brake_backward(np.array([v_grip_static(k) for k in kappa]),
                                 kappa, arc, total_len),
        kappa, ds, v[0])
    ot_mask = _overtake_zone_mask(v, braking)

    write_csv(args.csv_out, v, soc, mode, p_kw, t_arr, arc, total_len, fps=30)
    assert_sanity(v, soc, mode, p_kw, mgu_kw, t_arr, ot_mask)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test that a clean synthetic lap passes sanity and a bad one exits**

```python
from sim_monaco_2026_lap import assert_sanity

def test_assert_sanity_rejects_clipping():
    n = 50
    v = np.full(n, 200.0/3.6)
    mode = ["CLIPPING"] + ["DEPLOY"] * (n-1)
    t = np.linspace(0, 75.0, n)
    ot = np.zeros(n, dtype=bool)
    with pytest.raises(SystemExit):
        assert_sanity(v, np.ones(n), mode, np.zeros(n), np.zeros(n), t, ot)
```

- [ ] **Step 3: Run**

Run: `python -m pytest tests/test_monaco_physics.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add "OPTIMAL LAP SCRIPTS/sim_monaco_2026_lap.py" "OPTIMAL LAP SCRIPTS/tests/test_monaco_physics.py"
git commit -m "monaco sim: sanity assertions + main entry point"
```

---

## Task 7: Pipeline batch file + end-to-end run

**Files:**
- Create: `make_monaco_2026_lap.bat`

- [ ] **Step 1: Write the batch file**

```bat
@echo off
setlocal enabledelayedexpansion

set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "ROOT=%~dp0"
set "SVG=%ROOT%Circuit_Monaco.svg"
set "OUTLINE=%ROOT%F1_Pipeline_Assets\tracks\monaco_grand_prix_outline.json"
set "RACELINE=%ROOT%F1_Pipeline_Assets\tracks\monaco_grand_prix_raceline.json"
set "CSV=%ROOT%F1_Pipeline_Assets\exports\monaco_2026_synthetic.csv"
set "OUTMP4=%ROOT%monaco_grand_prix_2026_optimal_lap.mp4"

if not exist "%PYTHON%" goto :err_py
if not exist "%SVG%"    goto :err_svg

echo === Stage 1: SVG -^> outline (Monaco 3337 m, 9.0 m wide) ===
"%PYTHON%" "%ROOT%svg_to_outline.py" --svg "%SVG%" --out "%OUTLINE%" --track-length 3337 --road-width 9.0
if errorlevel 1 goto :err

echo === Stage 2: raceline + Monaco 2026 physics sim ===
"%PYTHON%" "%ROOT%sim_monaco_2026_lap.py" --outline "%OUTLINE%" --raceline-out "%RACELINE%" --csv-out "%CSV%"
if errorlevel 1 goto :err

echo === Stage 3: render video ===
"%PYTHON%" "%ROOT%raceline_video.py" --outline "%OUTLINE%" --raceline "%RACELINE%" --telemetry-csv "%CSV%" --track-name "Monaco Grand Prix" --out "%OUTMP4%"
if errorlevel 1 goto :err

echo.
echo Done. -^> %OUTMP4%
pause & exit /b 0

:err_py
echo ERROR: Python not found at %PYTHON%
pause & exit /b 1
:err_svg
echo ERROR: SVG not found at %SVG%
pause & exit /b 1
:err
echo FAILED with errorlevel %errorlevel%
pause & exit /b 1
```

- [ ] **Step 2: Run stage 1 + 2 directly to validate physics before rendering**

Run:
```
python svg_to_outline.py --svg "Circuit_Monaco.svg" --out "F1_Pipeline_Assets/tracks/monaco_grand_prix_outline.json" --track-length 3337 --road-width 9.0
python sim_monaco_2026_lap.py --outline "F1_Pipeline_Assets/tracks/monaco_grand_prix_outline.json" --raceline-out "F1_Pipeline_Assets/tracks/monaco_grand_prix_raceline.json" --csv-out "F1_Pipeline_Assets/exports/monaco_2026_synthetic.csv"
```
Expected: `[sanity]` line prints, all bands pass, exit 0. If a band fails, tune the named constant it points at (aero for peak speed, MU_LAT for hairpin) and rerun — this is the spec §10 adjust-and-rerun loop.

- [ ] **Step 3: Run the full pipeline**

Run: `make_monaco_2026_lap.bat`
Expected: produces `monaco_grand_prix_2026_optimal_lap.mp4`.

- [ ] **Step 4: Commit**

```bash
git add "OPTIMAL LAP SCRIPTS/make_monaco_2026_lap.bat"
git commit -m "monaco: end-to-end pipeline batch (SVG -> outline -> sim -> video)"
```

---

## Self-Review notes

- **Spec coverage:** §4.1 import-not-copy (Task 2 imports), §5.1 locked aero (Task 2), §5.2 Rev1+overtake (Task 3), §5.3 DEPLOY/REGEN+no-clip (Task 5), §5.4 grip (Task 2/4), §5.5 no reference CSV (Task 6 main omits it), §6 sanity (Task 6), §7 batch (Task 7), §8 svg_to_outline args (Task 1). All covered.
- **Direction risk (§5.5):** handled empirically in Task 7 Step 2 — if the printed speed/κ profile runs backwards (hairpin after tunnel), the corridor reversal in `build_raceline` is the lever; flag and adjust.
- **Type consistency:** `forward_pass` returns a 6-tuple `(v, soc, mode, p_kw, mgu_kw, t_arr)` everywhere; `mgu_k_cap_w(v, overtake)` signature consistent across Tasks 3/5/6.
