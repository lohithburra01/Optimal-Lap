# Canada 2026 Optimal Lap — Revamp Design

**Date:** 2026-05-19
**Branch:** `f1hotlap_lohith_v2`
**Status:** Draft pending user review

## 1. Goal

Replace the Miami-only `make_raceline_video.bat` pipeline with a Canada 2026 video that:
1. Reads the centerline of Circuit Gilles Villeneuve from a hand-drawn SVG and builds a road around it.
2. Generates a physically-defensible "perfect 2026 lap" — slower than 2025 because of the new regulations, but ground-truthed against real 2025 telemetry patterns (braking deceleration, throttle-on acceleration) so the motion looks like a real F1 car.
3. Renders the lap on the optimal racing line with a battery state-of-charge bar and a clipping/superclipping label, so the viewer sees energy management drop the speed mid-straight under 2026 regs.

## 2. Non-Goals

- Beating 2025 lap times. Predicted Canada lap time should land at ~1:13–1:14 (vs ~1:11 in 2025). FIA Bahrain + Melbourne testing shows 2026 cars are 2–3 s slower per lap.
- Live driver tunable parameters in the video.
- Modifying any code under `launch_control_auto_car_rig/`. The Blender addon is the *source of the validated min-time method* but its files are not edited (per `memory/feedback_no_addon_edits_for_exports.md`); the method is **ported** into the standalone pipeline.

## 3. 2026 Regulatory Facts (Vetted)

All vehicle/regulation magnitudes used in the physics sim trace back to one of these:

| Parameter | Value | Source |
|---|---|---|
| Min mass | 768 kg | [F1Chronicle](https://f1chronicle.com/f1-minimum-weigh-2026/) |
| ICE peak power | ~400 kW | [F1.com 2026 PU](https://www.formula1.com/en/latest/article/2026-regulations-explained-all-you-need-to-know-about-f1s-new-power-units.14jfv7a36905uDJDdNyfQd) |
| MGU-K peak deploy | 350 kW (was 120 kW) | [F1.com 2026 PU](https://www.formula1.com/en/latest/article/2026-regulations-explained-all-you-need-to-know-about-f1s-new-power-units.14jfv7a36905uDJDdNyfQd) |
| MGU-K deploy cap outside key zones (pre-Miami 2026) | 250 kW | [Speedcafe superclipping](https://speedcafe.com/f1-news-2026-formula-1-terminology-explained-what-is-superclipping-boost-overtake-mode-full-guide/) — FIA raised this to 350 kW from Miami 2026 onwards to reduce superclipping; this design uses the pre-Miami 250 kW cap because heavier clipping is the phenomenon being visualised |
| MGU-H | removed | [F1.com 2026 PU](https://www.formula1.com/en/latest/article/2026-regulations-explained-all-you-need-to-know-about-f1s-new-power-units.14jfv7a36905uDJDdNyfQd) |
| Per-lap deploy energy budget | ~9 MJ (was ~4 MJ) | [Speedcafe superclipping](https://speedcafe.com/f1-news-2026-formula-1-terminology-explained-what-is-superclipping-boost-overtake-mode-full-guide/) |
| Downforce reduction vs 2025 | −30% | [F1.com aero](https://www.formula1.com/en/latest/article/2026-regulations-explained-all-you-need-to-know-about-f1s-new-aerodynamics.7IAt0auc32UkCEFE5ypkTB) |
| Drag reduction vs 2025 | −40 to −55% | [F1.com aero](https://www.formula1.com/en/latest/article/2026-regulations-explained-all-you-need-to-know-about-f1s-new-aerodynamics.7IAt0auc32UkCEFE5ypkTB) |
| Active aero replaces DRS | yes (auto, no driver action) | [Scuderiafans X/Z mode](https://scuderiafans.com/x-mode-z-mode-and-override-how-f1-2026-active-aerodynamics-system-works/) |
| Wheelbase max | 3400 mm (was 3600) | [F1.com 12 rule changes](https://www.formula1.com/en/latest/article/from-smaller-cars-to-a-bigger-budget-cap-12-rule-changes-you-need-to-know-in.56uUTFhB0z5j3iZfhC0rGP) |
| 2026 lap-time slowdown | 2–3 s per lap vs 2025 | [PlanetF1 Bahrain test data](https://www.planetf1.com/features/f1-2026-2025-lap-times-compared-bahrain-testing) |

### 3.1 Observed 2026 telemetry patterns (vetted from races held so far)

By 2026-05-19, the four races actually held are **Australia (R1) → China (R2) → Japan (R3) → Miami (R4)**. (Bahrain GP was cancelled due to ongoing war in the region; only pre-season testing took place there.) Canada is round 5, next weekend. Multiple analyst publications have dissected FastF1 telemetry from these races + pre-season testing data. Patterns we encode into the simulator and validate against:

| Pattern | Magnitude / location | Source |
|---|---|---|
| Clipping appears in the **final third** of long straights | speed trace **flatlines** while throttle pegged | [PlanetF1 Leclerc Suzuka](https://www.planetf1.com/f1-data/f1-2026-rules-charles-leclerc-suzuka-telemetry-energy-problem) |
| Clipping speed-drop in qualifying | **up to ~50 km/h** worst case (Albert Park Q) | [Scuderiafans — super clipping cost 50 km/h](https://scuderiafans.com/f1-telemetry-analysis-how-super-clipping-cost-teams-up-to-50-km-h-in-australian-gp-qualifying/) |
| "Yo-yo"/"seesaw" speed before final lock-up | smaller dv oscillations during deploy cycles | [Medium — R01–R03 deep dive](https://medium.com/formula-one-forever/a-telemetry-deep-dive-into-the-2026-f1-season-r01-r03-25c57f6f5a37) |
| Strategy variation between teams | Mercedes clips smaller + later; Ferrari clips more despite same PU | [PlanetF1 — Alonso 50 km/h](https://www.planetf1.com/features/2026-f1-cars-speed-loss-explained-telemetry-data) |
| Slower corner speeds vs 2025 to harvest energy | drivers deliberately slow apexes for regen | [GPFans — energy systems game-like](https://www.gpfans.com/en/f1-news/1083949/f1s-2026-energy-systems-add-a-strategic-layer-that-feels-increasingly-gamelike/) |

These give us *quantitative validation targets*: the simulator's clipping zone must land in the final third of Casino Straight, the drop must be in the 15–50 km/h band, and the corner-speed reductions vs 2025 must be visible at apexes.

### Clipping vs Superclipping — definitions used in this design

- **Clipping (regular):** the battery state-of-charge reaches zero mid-straight → MGU-K stops contributing → propulsion drops from ~750 kW combined to ~400 kW (ICE only). The car visibly stops accelerating, often decelerates under drag while throttle remains pinned. This is what is colloquially described as "the car drops speed on the straight".
- **Superclipping:** the driver/ECU **intentionally** harvests under full throttle to refill the battery before the next braking zone. MGU-K runs as a generator. Net propulsion = ICE − harvest rate. Visibly similar speed drop to regular clipping, but the cause is different (chosen, not forced). FIA target: ≤2–4 s/lap of superclipping.

Canada's **Casino Straight** (T9 → final chicane) is the primary location for both — long enough that even with full battery at corner exit, the per-lap budget exhausts before the brake zone.

## 4. Architecture

Three modular Python scripts chained by a single Windows batch file. Each script has one job, communicates via files, and is independently testable. Existing Miami pipeline (`make_raceline_video.bat`) is untouched and still runnable.

```
            CANADA CIRCUIT.svg
                    │
                    ▼
        ┌──────────────────────────┐
        │  svg_to_outline.py        │
        └──────────┬───────────────┘
                    │  outline.json
                    ▼
        ┌──────────────────────────┐
        │  sim_2026_lap.py          │
        │  ─────────────────────    │
        │  1. IQP min-curv (seed)   │   ← reused from raceline_video.py
        │  2. JERK-CONSTRAINED      │   ← ported from
        │     min-curv QP refine    │     f1_track_visualizer_addonLastLastLasttry5.py
        │     (driver-physical)     │     (OBJECT_OT_GenerateRacingLineMinTime)
        │  3. 2026 physics sim      │
        └──────────┬───────────────┘
                    │  raceline.json
                    │  canada_2026_synthetic.csv
                    ▼
        ┌──────────────────────────┐
        │  raceline_video.py        │  ← consumes precomputed raceline + synthetic CSV
        └──────────┬───────────────┘
                    ▼
        canadian_grand_prix_2026_optimal_lap.mp4
```

The racing line is **the validated driver-physical line** (jerk-constrained min-curv QP with slack and α-regularizer), not just IQP min-curv. IQP is the seed that provides `cl_qp`, `alpha_seed`, `wr_safe`, `wl_safe` — exactly the inputs the addon's refinement operator consumes — then the refinement QP imposes asymmetric κ-rate bounds (turn-in tight, unwind loose) so the line resembles a real driver's input rather than a peak-κ-spiking optimal-control output.

## 5. Component 1 — `svg_to_outline.py`

**Purpose:** Parse the hand-drawn Inkscape SVG centerline of Canada, scale it to real-world metres, generate outer and inner road edges, write a JSON in the existing schema.

### Inputs
- `--svg <path>`: the SVG file (we have `CANADA CIRCUIT.svg`, a single `<path>` with `m … c … z` cubic-bezier syntax inside `<g id="track">`)
- `--out <path>`: output JSON path

### Pipeline
1. **SVG path parser** — small state machine over the `d` attribute. Supports `M m L l C c Z z` (everything the Inkscape export uses). ~60 LoC, no extra deps beyond Python stdlib regex.
2. **Bezier sampling** — 40 points per cubic segment. Output: raw polyline ~3000 points.
3. **Y-flip** — SVG y-axis points down; flip to math convention.
4. **Scale to metres** — `scale = 4361.0 / raw_arc_length` so total lap arc matches the real circuit by construction. Sanity check on the *scale factor itself* (not on post-fit error, which is zero by construction): abort if `scale < 0.5` or `scale > 50` m/SVG-unit. Catches the case where the SVG was exported in totally unexpected units (e.g., metres-per-unit instead of pixels-per-unit).
5. **Recentre** — subtract centroid; cosmetic.
6. **Smooth + uniform resample** — periodic cubic spline (`scipy.interpolate.splprep` with `per=True`), resample to `N_OUTPUT_POINTS = 2000` uniformly along arc length. Reuses the existing `smooth_resample_loop` pattern from `raceline_video.py:113`.
7. **Generate outer / inner edges** — at each centerline point, compute the 3-point tangent and the left-normal, then offset by `±W/2` where `W = ROAD_WIDTH_M = 13.0`. One optional override: detect the highest-curvature station and narrow the road to `HAIRPIN_NARROW_M = 10.5` within ±60 m of it.
8. **Detect start/finish location** — find the longest contiguous low-curvature run (`|κ| < 0.001 1/m`); use the midpoint as `s=0`. Roll both edge arrays so index 0 is the S/F line. If you want to override the S/F location manually, that's a one-line edit.
9. **Write JSON**: `{"outer": [[x,y], ...], "inner": [[x,y], ...]}`. This is the existing schema `raceline_video.py` already consumes — backward compatible.

### Constants (all at top of file for codex auditing)
```python
TRACK_LENGTH_M          = 4361.0
ROAD_WIDTH_M            = 13.0
HAIRPIN_NARROW_M        = 10.5
HAIRPIN_HALF_RANGE_M    = 60.0
N_OUTPUT_POINTS         = 2000
BEZIER_SAMPLES_PER_SEG  = 40
SF_LINE_KAPPA_THRESH    = 0.001    # |κ| below this counts as "straight"
SCALE_SANITY_MIN        = 0.5
SCALE_SANITY_MAX        = 50.0
```

### Error handling
- SVG has zero parseable subpaths → exit 2 with explicit message
- Scale factor outside `[SCALE_SANITY_MIN, SCALE_SANITY_MAX]` → exit 3 (unexpected SVG units)
- Output JSON write failure → exit 4

## 6. Component 2 — `sim_2026_lap.py`

**Purpose:** Run the IQP min-curvature racing line on the corridor, then run a 2026-physics-aware velocity profile on top of it. Emit a synthetic telemetry CSV that `raceline_video.py` can render directly.

### Inputs
- `--outline <path>`: outline JSON from stage 1
- `--raceline-out <path>`: where to write the raceline JSON
- `--csv-out <path>`: where to write the synthetic telemetry CSV

### Outputs
- `raceline.json`: `{"raceline": [[x,y], …], "arc_length": [s, …], "kappa": [κ, …], "track_length_m": 4361.0}`
- `canada_2026_synthetic.csv`: columns `frame, time_s, distance, speed, throttle, brake, gear, rpm, soc_pct, mode, power_kw` (first 6 match `fetch_fastest_lap.py` — existing loader works unchanged; last 3 are the new 2026-specific columns)

### Stage A — Build the driver-physical racing line

**Two-step process matching `OBJECT_OT_GenerateRacingLineMinTime` in `f1_track_visualizer_addonLastLastLasttry5.py:1708`.**

**A1. IQP min-curv seed.** Run the existing IQP (`opt_min_curv_sparse` + `run_iqp`) imported from `raceline_video.py:483-643`. Outputs the cached arrays the refinement step needs:
- `cl_qp` — corridor centerline used by the QP
- `alpha_seed` — per-station IQP α (offset from centerline along left-normal)
- `wr_safe`, `wl_safe` — per-station right/left widths (after corridor smoothing + inset)
- `nrm_init` — left-normals computed from `cl_qp` (NOT the tph spline normals — per the validated fix in `memory/project_mintime_jerk_constrained_qp.md`)

**A2. Jerk-constrained min-curv QP refinement.** Port `_opt_curv_kappa_rate` and the surrounding `execute()` logic from the addon (`f1_track_visualizer_addonLastLastLasttry5.py:1717-2211`) verbatim. The QP is structurally a clone of `opt_min_curv_sparse` with the κ-bound rows swapped for κ-RATE rows on a circular forward-difference of κ:

- **Asymmetric κ-rate bounds (slack-relaxed):**
  - `Δκ[i] ≤ rb_up[i]` (turn-in; tight)
  - `−Δκ[i] ≤ rb_dn[i]` (unwind; `rb_dn = rb_up × unwind_ratio`, default 3.0)
  - `rb_up[i] = J_max · ds[i] / max(v_warm[i], 5.0)³`
- **Slack variables** on each κ-rate row, λ = 1e3 — prefers α-changes over slack, uses slack only where widths can't compensate.
- **Per-station α-regularizer**, tent function — full weight `straight_stiff` at κ=0, linearly to 0 at |κ| = `kappa_floor = 0.005`, exactly zero in corners. Suppresses spline-coupled in→out→in→out bumps on straights without touching corner deformations.
- **Defaults from the addon** (validated 2026-05-10): `J_max = 12.0 m/s³`, `unwind_ratio = 3.0`, `straight_stiff = 5.0`, `safety_margin = 0.30 m`, `λ_slack = 1e3`.
- **Warm-velocity `v_warm`** for the κ-rate bound: use a quick `_vel_profile` pass on the IQP seed line (the addon's `_vel_profile`/`_kappa_ds_menger` helpers — also ported). This bound is what makes the line "driver-physical" — fast corners get a tighter κ-rate, slow corners can attack harder.
- **QP solver:** `quadprog` (matches the addon — `pip install quadprog`). The IQP seed still uses cvxopt; the two coexist.

The output of A2 is the **final raceline** that gets resampled by arc length, written to `raceline.json`, and then fed to the physics velocity profile (Stage B onwards).

**Why this is the racing line, not the simple IQP:** A pure min-curv QP produces peak-κ spikes that no real driver can input (yaw bandwidth limits). The κ-rate constraint encodes that bandwidth. This is why the addon work was done — it's the validated min-time line and it's what the optimal-lap video should show.

### Stage B — Physics constants (single block, top of file)

```python
# Vehicle (2026)
MASS_KG              = 768.0
G                    = 9.81
RHO                  = 1.225

# Power
P_ICE_MAX_W          = 400_000        # 400 kW combustion
P_MGU_DEPLOY_MAX_W   = 350_000        # MGU-K key-accel zone
P_MGU_NORMAL_CAP_W   = 250_000        # MGU-K elsewhere
P_MGU_REGEN_MAX_W    = 350_000        # MGU-K regen
E_DEPLOY_BUDGET_J    = 9_000_000      # 9 MJ per lap
E_BATTERY_CAP_J      = 4_000_000      # ~4 MJ usable

# Aero (Cd*A, Cl*A — effective values)
CDA_STRAIGHT_M2      = 0.55           # Straight Mode (active aero open)
CDA_CORNER_M2        = 0.90           # Corner Mode (downforce engaged)
CL_STRAIGHT_M2       = 1.40           # 30% less downforce than 2025
CL_CORNER_M2         = 2.80

# Tire grip (slicks, dry)
MU_LONG, MU_LAT      = 1.60, 1.70

# Mode-switching thresholds
KAPPA_CORNER_THRESH    = 0.005        # |κ| > this → Corner Mode
SOC_SUPERCLIP_THRESH   = 0.30         # below this, harvest on straights
KEY_ACCEL_WINDOW_S     = 5.0          # post-corner-exit window for full deploy
```

Every magnitude either comes directly from the 2026 reg sources cited in §3 or is derived from a published ratio (e.g., `CL_CORNER_M2 = 4.0 × 0.7` from the −30% downforce figure × a 2025 baseline of 4.0 m² that's standard in F1 aero papers). Codex can audit each constant against §3.

### Stage A.5 — Calibrate physics constants from real telemetry

**Why:** the constants in Stage B are physically defensible but are still my best estimates. The user has been explicit: derive vehicle dynamics from real data — "HOW THE BRAKING DROPS THE SPEED, HOW MUCH TIME DOES IT TAKE FOR A CAR TO REACH MAX SPEED AT FULL THROTTLE". Calibration grounds the sim in observed F1 motion, then the 2026 transforms layer on top.

**Inputs (both fetched via `fetch_fastest_lap.py`):**
- `reference_2025_canada_q.csv` — 2025 Canadian GP qualifying pole lap. Used for vehicle dynamics (μ, P/m).
- `reference_2026_china_q.csv` — 2026 Chinese GP qualifying pole lap. Used for clipping/superclipping signature (where on the straight, how big, how long). Picked because: (a) Bahrain 2026 race was cancelled (war), only pre-season testing was held there; (b) Shanghai has the longest back straight of the four 2026 races actually held (Aus/China/Japan/Miami) — maximum clipping signal; (c) China ran under pre-Miami rules (250 kW deploy cap outside key zones), which matches this sim's regulatory baseline.

**Calibration extracts from 2025 Canada Q telemetry** (speed, time, distance only — *no* X/Y because [[feedback_fastf1_xy_unreliable]]):
- **`mu_long_obs`** = peak braking deceleration / `g` — observed from `min(dv/dt)` while `brake > 50%`. F1 cars are typically 4–5 g peak braking.
- **`P_over_m_obs`** = effective propulsion power per unit mass — fit `dv/dt + drag_term` on the longest sustained-full-throttle section after a slow corner (Canada T2 exit on the back straight is a clean test bed).
- **`v_apex_hairpin_obs`** = minimum speed observed in the lowest-speed local-minimum region of the lap. This is the hairpin (T10). Constrains `μ_lat × Cl_corner / m`.

**Validation against 2026 China Q telemetry:**
- Detect clipping zones: sections where speed flatlines (|dv/dt| < 0.3 m/s²) AND throttle = 100% AND we're on a straight (long high-speed section).
- Record: position-in-straight (fraction from 0 to 1), depth (km/h dropped), duration (seconds).
- The simulator's clipping output on Shanghai (when fed the 2026 transforms) must reproduce these patterns within ±20%. If it doesn't, the `E_DEPLOY_BUDGET_J` / `P_MGU_NORMAL_CAP_W` constants need adjustment.

**Output:** a small JSON `F1_Pipeline_Assets/calibration/vehicle_calibration.json`:
```json
{
  "mu_long_obs":        1.65,
  "P_over_m_obs":       720.0,
  "v_apex_hairpin_obs": 22.5,
  "clipping_zones_china_2026": [
    {"frac_in_straight": 0.72, "drop_kmh": 28.4, "duration_s": 1.9},
    ...
  ]
}
```

The simulator's vehicle-constants block (Stage B) reads this JSON if present and **overrides** the corresponding defaults; if the file is missing it falls back to the literal constants. That makes the sim reproducible from constants alone AND ground-truthable from real telemetry.

### Stage C — Static `v_grip(s)` (corner-speed limit, ignoring energy)
At each station with curvature `κ(s)`, the lateral friction circle with active downforce gives:
```
μ_lat · (m·g + 0.5·ρ·Cl_corner · v²) = m · v² · |κ|
→ v_grip² = (μ_lat · g) / (|κ| − μ_lat · 0.5 · ρ · Cl_corner / m)
```
If denominator ≤ 0 (essentially straight), `v_grip` is unbounded by lateral physics — capped only by the powertrain.

### Stage D — Backward pass: braking-limited `v_brake(s)`
Starting from each corner apex and integrating backward, set the maximum speed that the brakes can wash off before the corner. Uses the friction circle with longitudinal grip after subtracting the lateral component:
```
a_x_brake_max = μ_long · (g + Cl/m · v²/2) · √(1 − (κ·v² / a_lat_max)²)
v(s−ds)² = v(s)² + 2 · a_x_brake_max · ds
```

### Stage E — Forward pass: energy-aware acceleration
Walk forward through the lap. At each step the simulator picks **one of 5 modes**:

| Mode | Fires when | Power applied | Battery effect |
|---|---|---|---|
| **DEPLOY** | accelerating, in key-accel window (within `KEY_ACCEL_WINDOW_S = 5.0` s of *integrated lap time* since the last corner exit — tracked via the running time integral inside the forward pass), `SoC > 0`, lap-budget remaining | `P_ICE + min(350 kW, grip-limited)` | SoC ↓, lap_deploy ↑ |
| **NORMAL** | accelerating, outside key-accel window | `P_ICE + min(250 kW, …)` | SoC ↓, lap_deploy ↑ |
| **CLIPPING** | `SoC ≤ 0` or lap-deploy ≥ 9 MJ, still on throttle | `P_ICE` only (~400 kW) | none |
| **SUPERCLIP** | full throttle on a straight AND `SoC < 0.30` AND ≥3 s of straight ahead before next brake zone | `P_ICE − 250 kW` (MGU runs as gen) | SoC ↑, lap_deploy unchanged |
| **REGEN** | braking | brakes + MGU regen at 350 kW | SoC ↑ |

Each step also clamps to `v_grip(s)` and `v_brake(s)` so corner entries and exits are respected. The longitudinal-acceleration cap from the friction circle is:
```
a_x_grip_max = μ_long · (g + Cl/m · v²/2) · √(1 − (κ·v²/a_lat_max)²)
a_x_power_max = P_available / (m · v)
a_x_actual    = min(a_x_grip_max, a_x_power_max) − drag/m
```

### Stage F — Closure iteration
Loop stages D–E until `v(s=L) ≈ v(s=0)` (within 1 m/s) and net battery flow per lap ≈ 0 (deploy + superclip + regen balance within 0.2 MJ). Typically converges in 4–6 iterations.

### Stage G — Resample to time domain
The forward pass already updates `t(s)` incrementally as `t(s + ds) = t(s) + ds / v(s)` (needed inside the loop for the key-accel window check). After the loop, `t(s)` is a strictly monotonic array. Resample uniformly in time at video rate (`fps × T_lap` frames) and write the CSV.

### Built-in sanity assertions (run after sim, fail-loud)

```
T_lap                       in [70, 80] s         (2025 was ~71; 2026 expected 73–75)
peak speed                  in [290, 340] km/h    (2025 was ~340 with DRS)
peak lateral G              in [3.5, 5.0] g       (2025 was ~5.5 with full DF)
total deploy energy         ≤ 9.0 MJ × 1.05       (5% numerical slack)
clipping zones              ≥ 1                    (must clip somewhere — likely Casino)
clipping position-in-straight ≥ 0.55              (final third per §3.1 patterns)
clipping speed drop          in [15, 50] km/h     (per Albert Park / Shanghai 2026 Q telemetry)
v at hairpin                 in [70, 105] km/h    (constrained by calibration apex speed)
```

If any assertion fails, exit non-zero with a clear message and the offending number. The .bat checks errorlevel and refuses to render a wrong-looking video.

## 7. Component 3 — `raceline_video.py` (modified)

**Purpose:** consume the outline, the raceline JSON, and the synthetic CSV; render a 30 fps MP4 with the new HUD elements.

### Changes from the existing file

| Change | Where | Why |
|---|---|---|
| Remove `opt_min_curv_sparse`, `run_iqp` | lines 483–643 | Moved to `sim_2026_lap.py` |
| Remove cvxopt + quadprog stubbing | top of file | Renderer doesn't solve QP anymore |
| Add `--raceline <path>` arg | `main()` | Reads precomputed raceline JSON |
| Rename `load_ver_telemetry` → `load_telemetry` | line 650 | Lap is no longer driver-specific |
| Extend loader to parse `soc_pct`, `mode` columns | line 650 | Old CSVs missing these cols still load fine (graceful fallback) |
| New `draw_battery_bar()` helper | new | HUD element |
| New `draw_mode_label()` helper + `MODE_COLORS` dict | new | HUD element |
| Render-loop additions for bar + label | line 858 area | Drawn after speed_kmh, before lap-time text |
| Skip `align_raceline_to_telemetry()` if `soc` column present | line 933 | Synthetic CSV is degenerate for that alignment routine; trust raceline parameterization instead |

### HUD layout (1080×1920 vertical Reels/Shorts frame)

| Y (px) | Element | New / unchanged |
|---|---|---|
| 320 | TITLE_Y_1 | unchanged |
| 400 | TITLE_Y_2 | unchanged |
| 460 | Minimap top | unchanged |
| **1080** | **Battery bar (W=600, H=32, centred)** | new |
| **1135** | **Mode label** | new (rendered only when mode ∈ {DEPLOY, CLIPPING, SUPERCLIP, REGEN}; NORMAL suppressed for less clutter) |
| 1200 | SPEED_Y | unchanged |
| 1320 | LAP_Y | unchanged |
| 1410 | WATERMARK_Y | unchanged |

### Battery bar visual rules
- Background `(40, 40, 40)`, outline `(200, 200, 200)`, 2 px stroke.
- Fill colour by SoC band, **not** by mode (the mode label conveys mode):
  - SoC > 70%: green `(60, 220, 100)`
  - 30–70%: amber `(255, 200, 60)`
  - < 30%: red `(255, 80, 80)`
- SoC numeric text rendered to the right of the bar.
- During `CLIPPING`, a 4 px red outline is drawn 4 px outside the bar (pulsing not necessary — the red outline is stable and reads clearly on video).

### Mode label colours

| Mode | Colour (RGB) | Why |
|---|---|---|
| DEPLOY | `(60, 220, 100)` green | full hybrid power available |
| CLIPPING | `(255, 60, 60)` red | battery dead, ICE only |
| SUPERCLIP | `(255, 140, 0)` orange | intentional harvest under throttle |
| REGEN | `(255, 230, 0)` yellow | braking, recovering |
| NORMAL | (not drawn) | avoids continuous on-screen clutter |

### Per-frame integration (3 new lines)

After the `SPEED_Y` text draw and before the `LAP_Y` text draw:
```python
if soc is not None:                                       # synthetic CSV path
    soc_now  = float(np.interp(t, ver_t, soc)) / 100.0
    mode_now = mode[int(np.searchsorted(ver_t, t, side='right')) - 1]
    draw_battery_bar(draw, BATT_BAR_X, BATT_BAR_Y, BATT_BAR_W, BATT_BAR_H, soc_now, mode_now)
    draw_mode_label(draw, WIDTH // 2, MODE_LABEL_Y, mode_now, font_mode_label)
```
`np.interp` for the continuous SoC, nearest-neighbour (`searchsorted`) for the categorical mode string — linearly interpolating "CLIPPING" doesn't mean anything.

## 8. Component 4 — `make_canada_2026_lap.bat`

Sequential chain. Fails loud on any non-zero errorlevel.

```bat
@echo off
setlocal enabledelayedexpansion

set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "ROOT=%~dp0"
set "SVG=%ROOT%CANADA CIRCUIT.svg"
set "OUTLINE=%ROOT%F1_Pipeline_Assets\tracks\canadian_grand_prix_outline.json"
set "RACELINE=%ROOT%F1_Pipeline_Assets\tracks\canadian_grand_prix_raceline.json"
set "CSV=%ROOT%F1_Pipeline_Assets\exports\canada_2026_synthetic.csv"
set "OUTMP4=%ROOT%canadian_grand_prix_2026_optimal_lap.mp4"

echo === Stage 1: SVG -^> outline ===
"%PYTHON%" "%ROOT%svg_to_outline.py" --svg "%SVG%" --out "%OUTLINE%"
if errorlevel 1 goto :err

echo === Stage 2: raceline + 2026 physics sim ===
"%PYTHON%" "%ROOT%sim_2026_lap.py" --outline "%OUTLINE%" --raceline-out "%RACELINE%" --csv-out "%CSV%"
if errorlevel 1 goto :err

echo === Stage 3: render video ===
"%PYTHON%" "%ROOT%raceline_video.py" --outline "%OUTLINE%" --raceline "%RACELINE%" --telemetry-csv "%CSV%" --track-name "Canadian Grand Prix" --out "%OUTMP4%"
if errorlevel 1 goto :err

echo Done. -^> %OUTMP4%
pause & exit /b 0

:err
echo FAILED with errorlevel %errorlevel%
pause & exit /b 1
```

`make_raceline_video.bat` (Miami) stays as-is. New artefacts:

| Path | Producer |
|---|---|
| `F1_Pipeline_Assets/tracks/canadian_grand_prix_outline.json` | `svg_to_outline.py` |
| `F1_Pipeline_Assets/tracks/canadian_grand_prix_raceline.json` | `sim_2026_lap.py` |
| `F1_Pipeline_Assets/exports/canada_2026_synthetic.csv` | `sim_2026_lap.py` |
| `canadian_grand_prix_2026_optimal_lap.mp4` | `raceline_video.py` |

## 9. Testing Strategy

| Stage | Test | Passes when |
|---|---|---|
| 1 (SVG) | `python -c "import json,matplotlib.pyplot as plt; d=json.load(open('…outline.json')); [plt.plot(*zip(*p)) for p in (d['outer'],d['inner'])]; plt.axis('equal'); plt.show()"` | The plotted outer/inner loops trace out a recognisable Circuit Gilles Villeneuve. |
| 2 (sim) | Read printed assertions and plot speed vs distance from the CSV. | All §6 assertions pass. SoC trace shows ≥1 sustained dip on the Casino Straight; speed trace shows a visible plateau/dip in the same region. |
| 3 (render) | Play the MP4. | Battery bar drains on long straights, refills under braking; a red `CLIPPING` label fires at least once on the Casino Straight section. Lap time on screen matches what stage 2 reported. |

## 10. Risks and Open Questions

- **Aero coefficient absolutes.** `CDA_STRAIGHT_M2 = 0.55` and `CL_CORNER_M2 = 2.80` are derived from published reduction ratios (−40 to −55% drag, −30% downforce) applied to typical 2025 estimates. The 2025 absolutes themselves aren't published by F1, so these are interval estimates. Mitigation: every magnitude is a single named constant at the top of `sim_2026_lap.py`, so codex (or you) can adjust and rerun in seconds.
- **Key-accel zone definition.** "5 seconds after corner exit" is my interpretation of FIA's "corner exit to braking point" rule. A real 2026 ECU likely uses a different criterion. If codex pushes back, alternative is "until next braking event detected dynamically" — minor code change, no architecture impact.
- **Casino Straight detection for superclipping.** The "≥3 s of straight ahead before next brake zone" rule depends on identifying brake zones during the forward pass. Brake-zone identification is already done as part of the backward pass (Stage D), so this is just a lookup.
- **Closure iteration convergence.** Worst case: energy budget never closes because deploy demand exceeds harvest capacity. Mitigation: assert convergence in ≤10 iterations; if not, fall back to a relaxed strategy that caps deploy harder and reports a warning.
- **No 2026 real telemetry for *Canada specifically*.** The four races held in 2026 are Australia / China / Japan / Miami; Canada is next weekend. We cross-validate the *patterns* (clipping shape, deploy/regen rhythm, corner-speed reduction) using 2026 China Q (§6 Stage A.5), but the absolute lap time for Canada 2026 has no real-data anchor yet. Mitigation: the sanity assertions encode the strongest available bounds, and the constants block is a single edit point if the actual Canada 2026 race reveals a magnitude offset.

## 11. Out-of-Scope (Explicitly Deferred)

- Per-segment variable road width beyond the single hairpin override.
- Multi-driver comparison (only the synthetic lap is rendered).
- Tyre wear, fuel burn, brake temperature, gear shift modelling.
- Trail recolour by power state — `Battery bar + power-mode label` was chosen over `Both — battery bar AND power-state trail` to keep the vertical Reels frame readable.
- Real-time interactive parameter tuning UI.
