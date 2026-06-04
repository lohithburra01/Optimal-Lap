"""sim_monaco_2026_lap.py — Monaco 2026 optimal-lap physics engine.

Reuses the validated, track-agnostic racing-line builder from sim_2026_lap;
rewrites the physics for Monaco 2026:
  * Active aero DISABLED → locked Z-mode (max downforce, high drag) all lap.
    There is ONE aero config — no STRAIGHT/CORNER mode switching.
  * Rev1 speed-dependent MGU-K cap (350 kW ≤ 200 km/h, ~100 kW @ 270, 0 @ 300);
    overtake mode (150 kW @ 300, 0 @ 310) applied on the single fastest zone
    (tunnel/main straight).
  * Energy is abundant at Monaco → no clipping, no superclipping. The binding
    constraint is the Rev1 speed cap, not the energy budget. Modes collapse to
    DEPLOY / REGEN (CLIPPING kept only as a defensive fallback that must never
    fire — a sanity assert confirms it doesn't).

Spec:  docs/2026-06-04-monaco-2026-physics-engine-design.md
Plan:  docs/2026-06-04-monaco-2026-physics-engine-plan.md
"""
import argparse
import json
import math
import os
import sys

import numpy as np

# Track-agnostic, already-validated pieces — single source of truth, imported
# (NOT copied) from the Canada engine:
#   build_raceline — IQP seed + jerk-constrained min-curv QP refinement
#   _clean_runs    — circular morphological cleanup of a boolean mask
#   write_csv      — resample-to-time + CSV writer (vehicle-agnostic)
from sim_2026_lap import build_raceline, _clean_runs, write_csv


# ════════════════════════════════════════════════════════════════════════
# MONACO 2026 PHYSICS BLOCK
# ════════════════════════════════════════════════════════════════════════
# Every magnitude is justified in the spec §3 / §5 against vetted 2026 sources.

# ── Vehicle (2026) ──
MASS_KG = 768.0        # FIA 2026 min mass
G       = 9.81
RHO     = 1.225

# ── Aero — single locked Z-mode (max downforce, wings closed, high drag) ──
# Monaco runs active aero DISABLED for the whole lap (no straight-mode zones on
# the FIA track map; fails the 3-second minimum straight-mode duration). So
# there is ONE config everywhere: a max-downforce Monaco wing with the −30%
# 2026 downforce reduction already baked in. CDA is the high (closed-wing) value
# all lap. Tuned so the tunnel/main-straight peak lands ~290–300 km/h.
CL_MONACO  = 3.00      # effective Cl·A
CDA_MONACO = 1.85      # effective Cd·A

# ── Power ──
P_ICE_MAX_W       = 400_000     # 400 kW combustion (2026 PU)
P_MGU_REGEN_MAX_W = 350_000     # MGU-K regen ceiling under braking
E_BATTERY_CAP_J   = 4_000_000   # ~4 MJ usable store

# ── Tyre grip ──
# MU_LONG: braking decel = MU_LONG·(g + downforce/m) + drag/m, so downforce and
#   drag are added separately — MU_LONG is the pure-tyre coefficient (~5 g peak).
# MU_LAT: tuned so the Fairmont hairpin (slowest corner in F1, ~48 km/h) lands
#   in band. At ~13 m/s downforce is negligible, so MU_LAT carries the apex.
MU_LONG = 1.60
MU_LAT  = 1.95

# ── Mode-switching / numerics ──
KAPPA_CORNER_THRESH = 0.005     # |κ| > this → a corner (for diagnostics)
V_FLOOR_MS          = 5.0       # never let v drop below this in numerics
SOC_INIT            = 1.0
BRAKE_DECEL_THRESH  = 4.0       # m/s² demanded decel above this = genuine braking
# KAPPA_MEDIAN_SIZE — light median filter on κ before deriving v_grip, to reject
#   single-station refinement-QP spikes at the apex. Monaco uses 3 (NOT Canada's
#   5): the Fairmont hairpin is a GENUINELY sharp ~8 m-radius corner, and a
#   size-5 window (≈10 m) over-smooths it, lifting the apex from a realistic
#   ~46 km/h to ~59 km/h. Size 3 preserves the real corner while still killing
#   isolated 1-station spikes (raw |κ|max≈0.18 → 0.12, R 5.5→8.3 m).
KAPPA_MEDIAN_SIZE   = 3


# ── Aero & grip primitives (single locked config — no `mode` argument) ──

def drag_force(v):
    return 0.5 * RHO * CDA_MONACO * v * v


def downforce(v):
    return 0.5 * RHO * CL_MONACO * v * v


def v_grip_static(kappa):
    """Steady-state cornering speed with the single locked high-downforce config:
        μ_lat (m·g + 0.5·ρ·Cl·v²) = m·v²·|κ|
        v² = μ_lat·g / (|κ| − μ_lat·0.5·ρ·Cl/m)
    Long radius (denom ≤ 0) → effectively no lateral cap; powertrain decides."""
    k = abs(kappa)
    if k < 1e-6:
        return 300.0
    denom = k - MU_LAT * 0.5 * RHO * CL_MONACO / MASS_KG
    if denom <= 0.0:
        return 300.0
    return math.sqrt(MU_LAT * G / denom)


# ── Rev1 + overtake MGU-K deployment curves (the headline new physics) ──

def mgu_k_cap_rev1_w(v_ms):
    """Mandated Monaco Rev1 MGU-K cap as a function of speed. Piecewise-linear
    through the published points: 350 kW ≤ 200 km/h, ~100 kW @ 270, 0 @ 300."""
    kmh = v_ms * 3.6
    if kmh <= 200.0:
        return 350_000.0
    if kmh <= 270.0:
        return 350_000.0 + (kmh - 200.0) * (100_000.0 - 350_000.0) / 70.0
    if kmh <= 300.0:
        return 100_000.0 + (kmh - 270.0) * (0.0 - 100_000.0) / 30.0
    return 0.0


def mgu_k_cap_overtake_w(v_ms):
    """Overtake-mode cap (applied only on the fastest zone): a gentler taper —
    350 kW ≤ 200 km/h, 150 kW @ 300, 0 @ 310."""
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


# ── Braking pass, ideal profile, zone masks ──

def compute_v_brake_backward(v_grip, kappa, arc, track_length_m, n_iters=3):
    """Backward pass: each station's speed must be low enough to brake to
    v_grip(s+ds) by the next station. Friction circle with active downforce."""
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
    used only to locate genuine braking zones (where achieved speed falls)."""
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
        a_long = min(a_long_grip, a_long_power) - drag_force(vi) / MASS_KG
        v_next = math.sqrt(max(V_FLOOR_MS ** 2, vi * vi + 2.0 * a_long * ds[i]))
        v[(i + 1) % n] = min(v_next, v_grip[(i + 1) % n], v_brake[(i + 1) % n])
    return v


def _braking_zones(v_grip, v_brake, kappa, ds, v0):
    """Boolean mask: True where the car is genuinely braking for a corner,
    cleaned to contiguous blocks (no per-station flicker)."""
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
    tunnel/main straight — where overtake-mode deployment applies. The car uses
    the manual override on the one fast section; Rev1 base applies elsewhere."""
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


# ── Forward pass (DEPLOY / REGEN) + closure loop ──

def forward_pass(v_grip, v_brake, kappa, arc, track_length_m,
                 v0=None, soc0=SOC_INIT, overtake_mask=None):
    """Walk the lap forward. Two real states:
      * REGEN in braking zones — MGU-K harvests, SoC ↑.
      * DEPLOY everywhere else — MGU-K gives mgu_k_cap(v) (overtake curve on the
        overtake_mask zone, Rev1 elsewhere), SoC ↓.
    CLIPPING is a defensive fallback if SoC hits 0; at Monaco it must never fire.

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
            # Braking zone: follow v_brake down, MGU-K regenerates. v[i+1] is
            # DERIVED here, never read from the stale slot (the Canada bug).
            mode_arr[i] = "REGEN"
            v_next = min(v[i], v_grip[(i + 1) % n], v_brake[(i + 1) % n])
            v[(i + 1) % n] = v_next
            dt = 2.0 * ds[i] / max(v[i] + v_next, 1e-3)
            soc = min(1.0, soc + P_MGU_REGEN_MAX_W * dt / E_BATTERY_CAP_J)
            p_kw_arr[i] = -P_MGU_REGEN_MAX_W / 1000.0
            mgu_kw_arr[i] = 0.0
            t += dt
            t_arr[i] = t
            continue

        # Drive station: deploy MGU-K up to the speed cap (overtake or Rev1) —
        # but only DEBIT the battery for the power the tyres actually accept.
        # Most of Monaco is slow-corner exits where the car is grip/traction-
        # limited: the ICE's 400 kW already exceeds what the tyres can put down,
        # so the MGU-K delivers little or nothing. Debiting the full cap there
        # (the old bug) drained the battery ~4 MJ/lap and forced spurious
        # clipping; in reality Monaco over-harvests precisely because deploy is
        # grip-limited at low speed. MGU-K energy actually used = the propulsive
        # power above the ICE that the grip limit allows, capped by Rev1.
        cap = mgu_k_cap_w(v[i], overtake_mask[i])
        mgu_avail = cap if soc > 0.0 else 0.0
        P_avail = P_ICE_MAX_W + mgu_avail

        a_lat_used = abs(kappa[i]) * v[i] * v[i]
        a_lat_max = MU_LAT * (G + downforce(v[i]) / MASS_KG)
        ratio_sq = min(1.0, (a_lat_used / max(a_lat_max, 1e-6)) ** 2)
        a_long_grip = MU_LONG * (G + downforce(v[i]) / MASS_KG) * math.sqrt(1.0 - ratio_sq)
        a_long_power = P_avail / (MASS_KG * max(v[i], V_FLOOR_MS))
        a_long = min(a_long_grip, a_long_power) - drag_force(v[i]) / MASS_KG

        # Propulsive power the grip limit accepts vs what's available.
        P_grip = MASS_KG * a_long_grip * max(v[i], V_FLOOR_MS)
        P_used = min(P_grip, P_avail)
        mgu = max(0.0, min(cap, P_used - P_ICE_MAX_W))   # MGU fills only above ICE
        # CLIPPING fires only if the battery is empty AND the car is genuinely
        # power-starved (grip wants more than the ICE alone can give).
        mode_arr[i] = "CLIPPING" if (soc <= 0.0 and cap > 0.0 and P_grip > P_ICE_MAX_W) else "DEPLOY"

        v_next = math.sqrt(max(V_FLOOR_MS ** 2, v[i] * v[i] + 2.0 * a_long * ds[i]))
        v_next = min(v_next, v_grip[(i + 1) % n], v_brake[(i + 1) % n])
        v[(i + 1) % n] = v_next
        dt = 2.0 * ds[i] / max(v[i] + v_next, 1e-3)
        soc = min(1.0, max(0.0, soc - mgu * dt / E_BATTERY_CAP_J))
        p_kw_arr[i] = P_used / 1000.0
        mgu_kw_arr[i] = mgu / 1000.0
        t += dt
        t_arr[i] = t

    return v, soc_arr, mode_arr, p_kw_arr, mgu_kw_arr, t_arr


def simulate_lap(raceline, arc, kappa, track_length_m, max_iters=8, tol_v=1.0):
    """Forward-backward closure until v(end) ≈ v(start). Two forward passes per
    iteration: a no-overtake pass to find the fastest zone, then the final pass
    with overtake mode on that zone."""
    from scipy.ndimage import median_filter
    # The raceline κ is a noisy 3-point Menger estimate with a spike at the
    # hairpin apex; a light 5-point median rejects the spike for v_grip while
    # the raw κ (written to json) is untouched. mode='wrap' for the closed loop.
    kappa_smooth = median_filter(np.asarray(kappa, dtype=float),
                                 size=KAPPA_MEDIAN_SIZE, mode="wrap")
    v_grip = np.array([v_grip_static(k) for k in kappa_smooth])
    ds = np.diff(np.concatenate([arc, [track_length_m]]))

    v0 = 50.0
    result = None
    ot_mask = np.zeros(len(kappa), dtype=bool)
    for it in range(max_iters):
        v_brake = compute_v_brake_backward(v_grip, kappa, arc, track_length_m)
        braking = _braking_zones(v_grip, v_brake, kappa, ds, v0)
        v_ns = forward_pass(v_grip, v_brake, kappa, arc, track_length_m,
                            v0=v0, overtake_mask=None)[0]
        ot_mask = _overtake_zone_mask(v_ns, braking)
        result = forward_pass(v_grip, v_brake, kappa, arc, track_length_m,
                              v0=v0, overtake_mask=ot_mask)
        v, soc, mode, p_kw, mgu_kw, t_arr = result
        dv = abs(v[-1] - v[0])
        print(f"  closure iter {it}: v0={v[0]:.1f} vN={v[-1]:.1f} "
              f"d={dv:.2f} T_lap={t_arr[-1]:.3f}s")
        if dv < tol_v and it >= 1:
            print(f"  closure converged at iter {it}")
            break
        v0 = 0.5 * (v[0] + v[-1])
    # Return the overtake mask actually used, so the sanity check verifies the
    # exact same deployment caps the forward pass applied (no recomputation drift).
    return (*result, ot_mask)


# ── Sanity assertions ──

def assert_sanity(v, soc, mode, p_kw, mgu_kw, t_arr, overtake_mask):
    """Hard-fail (exit 10) if the Monaco lap is out of physical bounds.
    Replaces Canada's clipping/superclip asserts with Monaco-correct ones."""
    T_lap = float(t_arr[-1])
    v_kmh = np.asarray(v) * 3.6
    v_max = float(np.max(v_kmh))
    v_min = float(np.min(v_kmh))
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
    # Rev1/overtake honored: MGU-K deploy never exceeds the applicable speed cap.
    for i in range(len(v)):
        cap_kw = mgu_k_cap_w(v[i], overtake_mask[i]) / 1000.0
        if mgu_kw[i] > cap_kw + 1e-3:
            fails.append(f"station {i}: MGU-K {mgu_kw[i]:.0f}kW > cap {cap_kw:.0f}kW "
                         f"at {v_kmh[i]:.0f}km/h (Rev1 violated)")
            break

    print(f"[sanity] T_lap={T_lap:.2f}s  v=[{v_min:.0f},{v_max:.0f}] km/h  "
          f"clip={n_clip} super={n_super} overtake_stations={int(np.sum(overtake_mask))}")
    if fails:
        for f in fails:
            print(f"[sanity] FAIL: {f}", file=sys.stderr)
        sys.exit(10)


def main():
    # Status lines contain Unicode (κ); force UTF-8 stdout so they don't crash
    # on Windows' default cp1252 console codec.
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

    # Reused verbatim — the validated, track-agnostic racing-line builder.
    raceline, arc, kappa, total_len = build_raceline(outer_raw, inner_raw)
    print(f"[monaco] raceline: {len(raceline)} pts, {total_len:.0f} m, "
          f"|κ|max={np.abs(kappa).max():.4f}")

    # Monaco's longest low-κ run IS the pit/start-finish straight, so the
    # geometric S/F proxy from svg_to_outline is already correct — no reference
    # telemetry cross-correlation (published-facts-only calibration).

    os.makedirs(os.path.dirname(os.path.abspath(args.raceline_out)), exist_ok=True)
    with open(args.raceline_out, "w", encoding="utf-8") as f:
        json.dump({
            "raceline":       raceline.tolist(),
            "arc_length":     arc.tolist(),
            "kappa":          kappa.tolist(),
            "track_length_m": float(total_len),
        }, f)
    print(f"[monaco] wrote raceline -> {args.raceline_out}")

    v, soc, mode, p_kw, mgu_kw, t_arr, ot_mask = simulate_lap(
        raceline, arc, kappa, total_len)

    write_csv(args.csv_out, v, soc, mode, p_kw, t_arr, arc, total_len, fps=30)
    assert_sanity(v, soc, mode, p_kw, mgu_kw, t_arr, ot_mask)


if __name__ == "__main__":
    main()
