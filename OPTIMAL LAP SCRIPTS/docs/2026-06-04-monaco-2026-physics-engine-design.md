# Monaco 2026 Optimal Lap — Physics Engine Design

**Date:** 2026-06-04
**Branch:** `f1hotlap_lohith_v2`
**Status:** Draft pending user review
**Supersedes for Monaco:** the Canada engine in `sim_2026_lap.py` (kept intact for Canada)

## 1. Goal

Produce a physically-defensible "perfect 2026 lap" video of the **Circuit de Monaco**
on the validated driver-physical racing line, with a **new physics engine** that
models the 2026 Monaco-specific regulations correctly. The previous Canada engine
modelled active-aero straight mode and superclipping — **neither exists at Monaco** —
which corrupted the lap time. This engine replaces that model structure, not just its
constants.

## 2. Root cause — why Canada's engine is wrong for Monaco

Canada's `sim_2026_lap.py` is built around two phenomena that are explicitly **absent**
at Monaco 2026:

1. **Active-aero mode switching.** Canada switches between `CDA_STRAIGHT`/`CL_STRAIGHT`
   (active aero open on straights) and corner-mode values. At Monaco active aero is
   **disabled for the entire lap** — the car is locked in **Z-mode (maximum downforce,
   wings closed, high drag)**. The official 2026 Monaco track map contains **no
   straight-mode activation zones**; Monaco also fails the FIA's 3-second minimum
   straight-mode duration requirement.
   Source: [F1.com — why active aero won't be used at Monaco](https://www.formula1.com/en/latest/article/explained-why-active-aero-will-not-be-used-at-the-monaco-grand-prix.4nLtpjM9ZTUbPBQLmeAbj4),
   [The Race](https://www.the-race.com/formula-1/why-f1-cars-wont-run-active-aero-in-monaco/),
   [Speedcafe](https://speedcafe.com/f1-news-2026-monaco-grand-prix-acrive-aero-update-track-map-new-rule-dropped-regulations-overtaking/).

2. **Clipping / superclipping.** Canada models the battery running out on the long
   Casino Straight (clipping) and intentional harvest on the trailing third
   (superclipping). Monaco is the **inverse problem**: short straights + heavy braking
   + slow corners mean the battery **over-harvests** and is essentially always full.
   Teams confirm Monaco needs **minimal lift-and-coast and no superclipping**.
   Source: [MotorBiscuit / Cuquerella data](https://www.motorbiscuit.com/fia-forces-f1-teams-to-slash-electric-power-maps-for-the-first-time-as-monacos-extreme-harvesting-breaks-2026-engine-rules/),
   [The Race — engine mode to cap top speed](https://www.the-race.com/formula-1/new-f1-engine-mode-to-cap-top-speed-potential-in-monaco/).

Because energy is abundant, the binding constraint at Monaco is **not** the per-lap
energy budget — it is the new **speed-dependent deployment cap ("Rev1")**.

## 3. Vetted 2026 Monaco regulatory facts

| Parameter | Value | Source |
|---|---|---|
| Active aero at Monaco | **Disabled** — locked Z-mode (max downforce) all lap | [F1.com](https://www.formula1.com/en/latest/article/explained-why-active-aero-will-not-be-used-at-the-monaco-grand-prix.4nLtpjM9ZTUbPBQLmeAbj4) |
| Superclipping at Monaco | **Eliminated** (minimal lift-and-coast) | [MotorBiscuit](https://www.motorbiscuit.com/fia-forces-f1-teams-to-slash-electric-power-maps-for-the-first-time-as-monacos-extreme-harvesting-breaks-2026-engine-rules/) |
| Rev1 MGU-K cap | **350 kW** | [The Race](https://www.the-race.com/formula-1/new-f1-engine-mode-to-cap-top-speed-potential-in-monaco/) |
| Rev1 taper start | **200 km/h** (Base mode starts at 290) | [The Race](https://www.the-race.com/formula-1/new-f1-engine-mode-to-cap-top-speed-potential-in-monaco/) |
| Rev1 mid-point | **~100 kW at 270 km/h** | [GPBlog](https://www.gpblog.com/en/tech/how-the-fias-changes-to-the-monaco-grand-prix-will-influence-the-next-race) |
| Rev1 zero point | **0 kW at 300 km/h** | [The Race](https://www.the-race.com/formula-1/new-f1-engine-mode-to-cap-top-speed-potential-in-monaco/) |
| Overtake mode | **150 kW at 300 km/h, 0 by 310 km/h** | [The Race](https://www.the-race.com/formula-1/new-f1-engine-mode-to-cap-top-speed-potential-in-monaco/) |
| ICE peak power | ~400 kW | (2026 PU, as Canada) |
| Min mass | 768 kg | (2026, as Canada) |
| Downforce vs 2025 | −30% (but Monaco runs max-DF wing) | (2026 aero, as Canada) |
| Track length | **3.337 km** | [Wikipedia / F1](https://en.wikipedia.org/wiki/Circuit_de_Monaco) |
| Corners | 19 | [Formula Timer](https://formula-timer.com/circuit/monaco) |
| Fairmont hairpin | ~48 km/h — slowest corner in F1 | [TheSportsRush](https://thesportsrush.com/f1-news-monaco-f1-track-circuit-length-top-speed-corners-name-for-circuit-de-monaco/) |
| Tunnel / top speed | ~285–300 km/h (fastest point) | [Oversteer48](https://oversteer48.com/monaco-track-layout-drs-zones-corner-names/) |
| Race direction | **Clockwise** | [Wikipedia](https://en.wikipedia.org/wiki/Circuit_de_Monaco) |
| 2026 format | Traditional (3 practice); 2-stop mandate dropped | [GPBlog](https://www.gpblog.com/en/tech/how-the-fias-changes-to-the-monaco-grand-prix-will-influence-the-next-race) |

## 4. Architecture

New standalone **`sim_monaco_2026_lap.py`**. `sim_2026_lap.py` (Canada) is **not edited**.

```
            Circuit_Monaco.svg
                    │
                    ▼
        ┌──────────────────────────────┐
        │ svg_to_outline.py             │  + optional --track-length / --road-width
        │ (--track-length 3337          │    (defaults = Canada 4361 / 13.0 → Canada
        │  --road-width 9.0)            │     unchanged, byte-for-byte)
        └──────────┬───────────────────┘
                   │  monaco outline.json
                   ▼
        ┌──────────────────────────────┐
        │ sim_monaco_2026_lap.py        │
        │ ─────────────────────────     │
        │ A. raceline builder           │  ← IMPORTED verbatim from sim_2026_lap.py
        │    (IQP + jerk-QP refine)     │    (build_raceline + helpers; track-agnostic)
        │ B. MONACO physics block       │  ← NEW: Z-mode aero, Rev1 deploy, no clip
        │ C. raceline.json + CSV        │
        └──────────┬───────────────────┘
                   │  raceline.json + monaco_2026_synthetic.csv
                   ▼
        ┌──────────────────────────────┐
        │ raceline_video.py (unchanged) │  HUD mode set narrows to DEPLOY/REGEN
        └──────────┬───────────────────┘
                   ▼
        monaco_grand_prix_2026_optimal_lap.mp4
```

### 4.1 Reused verbatim (imported, not duplicated)

From `sim_2026_lap.py`, the **track-agnostic racing-line stack**:
`build_raceline`, `kappa_ds_menger`, `warm_vel_profile`, `opt_curv_kappa_rate`, and the
`raceline_video` imports it pulls. These are already validated and have no Canada-specific
physics. `sim_monaco_2026_lap.py` does `from sim_2026_lap import build_raceline`.

Rationale for import-not-copy: the geometry/QP math is the single source of truth and must
not fork. Only the physics differs between tracks.

### 4.2 Rewritten for Monaco (the new physics block)

Everything from `# 2026 PHYSICS BLOCK` downward in Canada is replaced.

## 5. The Monaco physics model

### 5.1 Aero — single locked Z-mode (no mode switching)

```python
CL_MONACO   = 3.00     # effective Cl·A, max-downforce Monaco wing (post-2026 -30%)
CDA_MONACO  = 1.85     # effective Cd·A, Z-mode locked CLOSED (high drag) all lap
```

`drag_force(v)` and `downforce(v)` take **no `mode` argument** — there is one config.
`aero_mode()` is deleted. This removes the entire `CDA_STRAIGHT`/`CDA_CORNER` split.

### 5.2 Power — Rev1 speed-dependent MGU-K cap + overtake on the fast zone

The headline new physics. MGU-K available power is a function of **speed**, not energy state:

```python
P_ICE_MAX_W       = 400_000

# Rev1 (mandated Monaco baseline) — piecewise-linear through published points:
#   v ≤ 200 km/h        → 350 kW
#   200 → 270 km/h      → 350 → 100 kW (linear)
#   270 → 300 km/h      → 100 → 0 kW  (linear)
#   v ≥ 300 km/h        → 0 kW
def mgu_k_cap_rev1_w(v_ms): ...

# Overtake mode — gentler taper, applied ONLY on the highest-speed zone:
#   v ≤ 300 km/h        → 350 kW down to 150 kW (interpolated; full below 200)
#   300 → 310 km/h      → 150 → 0 kW
#   v ≥ 310 km/h        → 0 kW
def mgu_k_cap_overtake_w(v_ms): ...
```

**Per user decision:** Rev1 base everywhere, **overtake-mode curve only on the single
fastest drive zone** (the tunnel → main straight). That zone is identified the same way
Canada found its superclip zone — the contiguous non-braking zone whose peak speed equals
the lap maximum — but instead of harvesting, it simply uses the gentler deployment curve.
A boolean `overtake_mask` marks those stations.

Total propulsion: `P_total(v) = P_ICE_MAX_W + min(cap(v), grip-limited, SoC-available)`,
where `cap` is the overtake curve on `overtake_mask` stations, Rev1 elsewhere.

### 5.3 Mode logic — collapses to DEPLOY / REGEN

Energy is abundant, so Canada's 5-mode system (DEPLOY/NORMAL/CLIPPING/SUPERCLIP/REGEN)
collapses to two real states:

| Mode | Fires when | Power | Battery |
|---|---|---|---|
| **DEPLOY** | accelerating (not braking) | `P_ICE + mgu_k_cap(v)` (Rev1 or overtake) | SoC ↓ by deployed MGU-K energy |
| **REGEN** | braking zone (`_braking_zones`, reused) | brakes + MGU-K regen | SoC ↑ |

- **No NORMAL, no SUPERCLIP.** Deleted.
- **CLIPPING** is retained only as a *defensive fallback* if `SoC ≤ 0` (ICE-only). At
  Monaco it must never fire; a sanity assert confirms `n_clipping == 0`.
- SoC is integrated and rendered on the HUD, but is not the binding constraint —
  `mgu_k_cap(v)` is.

The forward pass keeps the same friction-circle longitudinal/lateral structure as Canada
(`a_long = min(a_long_grip, a_long_power) − a_drag`), with the single-config aero and the
speed-dependent power cap substituted in.

### 5.4 Cornering & braking

Single high-downforce friction circle (Canada's structure, single aero config):

```python
MU_LONG = 1.60     # ~5 g peak braking with downforce term added separately
MU_LAT  = 1.95     # reproduces a ~46–50 km/h Fairmont hairpin apex
```

`v_grip_static(kappa)` uses `CL_MONACO`. The Fairmont hairpin (global |κ| peak) must land
~46–50 km/h; verified by the sanity band, not hand-tuned.

### 5.5 Start/finish & lap direction

- **S/F line:** Monaco's longest low-κ run **is** the pit/start-finish straight, so the
  geometric proxy already produced by `svg_to_outline.find_start_finish_index` is correct.
  **No reference-telemetry cross-correlation** (`locate_start_finish`) is used — consistent
  with the "published facts only" calibration choice. `sim_monaco_2026_lap.py` takes no
  `--reference-csv`.
- **Direction:** Monaco runs **clockwise**. `build_raceline` reverses the corridor to a
  fixed convention; during implementation the resulting traversal is verified to run the
  real corner order (Sainte Dévote → Massenet → Casino → Mirabeau → Fairmont hairpin →
  tunnel → chicane → Tabac → swimming pool → Rascasse → Anthony Noghès) by inspecting
  where the |κ| peak (hairpin) and the max-speed zone (tunnel) fall — **not** by telemetry.
  If reversed, flip the corridor as Canada does.

### 5.6 Calibration

**Published facts only** (user choice). No `calibrate_from_telemetry`, no
`vehicle_calibration.json` override path in this engine. Every constant is a named literal
at the top of the file, each traceable to §3. (The Canada calibration code stays in
`sim_2026_lap.py`; it is simply not imported here.)

## 6. Sanity assertions (rewritten for Monaco)

Replaces Canada's superclip/clipping asserts:

```
T_lap            in [70, 80] s       (2025 pole ~1:10–1:11; 2026 +2–3 s slower)
peak speed       in [270, 305] km/h  (tunnel/main straight; Rev1 zeroes deploy by 300)
hairpin v (min)  in [42, 60] km/h    (Fairmont ~48 km/h, slowest corner in F1)
peak lateral G   in [3.0, 5.5] g
Rev1 honored     MGU-K deploy == 0 at every station with v ≥ 300 km/h   (NEW, hard)
no superclip     n_superclip == 0    (mode must not exist)              (NEW, hard)
no clipping      n_clipping  == 0    (battery never empties at Monaco)  (NEW, hard)
```

Fail-loud (`sys.exit(10)`) with the offending number; the .bat refuses to render.

## 7. Pipeline — `make_monaco_2026_lap.bat`

Clone of `make_canada_2026_lap.bat`, retargeted. `make_raceline_video.bat` (Miami) and
`make_canada_2026_lap.bat` (Canada) are untouched.

```
SVG       = Circuit_Monaco.svg
OUTLINE   = F1_Pipeline_Assets/tracks/monaco_grand_prix_outline.json
RACELINE  = F1_Pipeline_Assets/tracks/monaco_grand_prix_raceline.json
CSV       = F1_Pipeline_Assets/exports/monaco_2026_synthetic.csv
OUTMP4    = monaco_grand_prix_2026_optimal_lap.mp4

Stage 1: svg_to_outline.py --svg <SVG> --out <OUTLINE> --track-length 3337 --road-width 9.0
Stage 2: sim_monaco_2026_lap.py --outline <OUTLINE> --raceline-out <RACELINE> --csv-out <CSV>
Stage 3: raceline_video.py --outline <OUTLINE> --raceline <RACELINE> --telemetry-csv <CSV>
         --track-name "Monaco Grand Prix" --out <OUTMP4>
```

## 8. Component changes to `svg_to_outline.py`

Backward-compatible only:
- Add `--track-length` (default `TRACK_LENGTH_M = 4361.0`) and `--road-width`
  (default `ROAD_WIDTH_M = 13.0`) CLI args.
- Monaco is narrow: `--road-width 9.0`, and `HAIRPIN_NARROW_M` scales down with it
  (hairpin ~7.0 m). Hairpin narrowing already keys off the global |κ| peak — works
  unchanged for the Fairmont hairpin.
- No other behavioral change; Canada/Miami invocations omit the new flags and run exactly
  as before.

## 9. Testing strategy

| Stage | Test | Passes when |
|---|---|---|
| 1 (SVG) | plot outer/inner from `monaco_grand_prix_outline.json` | traces a recognisable Monaco (hairpin, tunnel curve, swimming-pool chicanes) |
| 2 (sim) | read printed asserts; plot speed vs distance | all §6 asserts pass; hairpin ~48 km/h dip; tunnel ~290–300 km/h peak; deploy kW visibly tapers to 0 near top speed; SoC stays high (no clip) |
| 3 (render) | play MP4 | battery bar stays high, refills on every braking zone; mode alternates DEPLOY/REGEN; **no** CLIPPING/SUPERCLIP labels appear; on-screen lap time matches stage 2 |

Existing `tests/` for the shared raceline stack continue to pass (imported code unchanged).

## 10. Risks & open questions

- **Aero absolutes.** `CL_MONACO = 3.0`, `CDA_MONACO = 1.85` are derived from the −30%
  downforce ratio applied to a max-DF Monaco baseline; the 2025 absolutes aren't published.
  Mitigation: single named constants, adjust-and-rerun. Tune so peak speed lands ~290–300.
- **Lap direction.** Verified geometrically (hairpin/tunnel positions), not by telemetry.
  If the corner order comes out reversed, flip the corridor (one-line, as Canada does).
- **Overtake-zone identification.** Relies on the fastest drive zone being the
  tunnel/main straight — true for Monaco. Reuses Canada's fast-zone detection logic.
- **Top speed vs Rev1.** If the sim's tunnel peak never reaches 300 km/h, the overtake
  curve and the "deploy==0 above 300" assert are simply never exercised — that is
  physically fine for Monaco and not a failure.

## 11. Out of scope

- Editing `sim_2026_lap.py`, the Canada video, or the Miami pipeline.
- HUD/video changes (a Rev1-kW readout could be added later; not required).
- Tyre wear, fuel burn, brake temps, gear modelling, multi-driver comparison.
- Real-telemetry calibration for Monaco (explicitly deferred per user choice).
