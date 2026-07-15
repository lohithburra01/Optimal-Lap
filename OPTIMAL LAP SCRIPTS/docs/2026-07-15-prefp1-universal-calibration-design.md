# Pre-FP1 universal calibration — design

**Date:** 2026-07-15 · **Deadline context:** Belgian GP FP1 is Fri 2026-07-17; the Spa video ships BEFORE it.
**Goal:** realistic ("accurate every time") 2026 optimal-lap sims with ZERO dependency on the target track's 2026 sessions. FP1, when it later exists, is verification — never calibration.

## 1. Problem

The 2026 car model in `sim_2026_lap.py` (MGU-K deploy taper 200/270/300, corner-aero braking,
trail-brake release, MU_LONG/MU_DRIVE, superclip) is track-independent and already validated
against real 2026 data on 6 circuits. The only per-track unknowns that forced us to wait for FP1:

| Knob | Meaning | Pinned values so far |
|---|---|---|
| `CDA_STRAIGHT_M2` | X-mode drag area (wing level + air density) | Austria 0.60, Silverstone 0.80 |
| `CL_CORNER_M2` | Z-mode downforce (setup + line-error absorption) | Austria 5.00, Silverstone 4.20 |

Both are hardcoded module constants (sim_2026_lap.py:724,754) — every track was a code edit.
Additionally the gate bands in `cache/_gate_2026.py` are Catalunya-hardcoded, and the uniform
line de-wobble (gaussian σ=2.5) rounds genuine apexes, which (a) made Austria's honest lap
faster than the 2025 pole (impossible; masked with `--display-laptime`) and (b) forces CL to
absorb line error, making it less predictable.

## 2. Insight

What FP1 provided is derivable pre-weekend from:

1. **The track's own 2025 quali telemetry** (FastF1; always available before the weekend):
   per-corner minimum speeds, straight-end top speed, lap time, geometry validation overlay.
2. **A 2025→2026 transfer function** — a property of the regs change, not the track — fitted
   empirically from the real 2025+2026 lap pairs we already hold:

| Track | 2025 ref | 2026 ref | Pair kind | Full SVG pipeline? |
|---|---|---|---|---|
| Canada | `reference_2025_canada_q.csv` | `reference_2026_canada_q.csv` | Q–Q | yes |
| Catalunya | `reference_2025_spain_q.csv` | `reference_2026_spain_q.csv` | Q–Q | yes |
| Miami | fetch `reference_2025_miami_q.csv` | `reference_2026_miami_q.csv` | Q–Q | csv-only |
| China | fetch `reference_2025_china_q.csv` | `reference_2026_china_q.csv` | Q–Q | csv-only |
| Austria | `reference_2025_austria_q.csv` | `reference_2026_austria_fp1.csv` | Q–FP1 | yes |
| Silverstone | `reference_2025_silverstone_q.csv` | `reference_2026_silverstone_fp1.csv` | Q–FP1 | yes |

Both CSV schemas are identical (`frame,time_s,distance,speed,throttle,brake,gear,rpm,ers_deploy`).

The transfer has three parts:
- **Corner-speed ratio `r(v25) = v26/v25`** at matched corner minima. Physically: low-speed
  corners are mechanical-grip dominated (r ≈ 1.0), high-speed corners are downforce dominated
  (r ≈ 0.85 with ≈−30% DF). Fit piecewise-linear in v25, constrained monotone non-increasing.
  Quali pairs anchor the fit; FP1 pairs are shape-validation only (non-push laps).
- **Top-speed / drag mapping with per-track air density.** ρ from altitude (ISA model).
  Austria's 680 m elevation explains most of the 0.60-vs-0.80 CDA gap; Mexico (2240 m) makes
  ρ(altitude) mandatory later this season regardless. Residual after ρ-correction = wing level,
  mapped from the track's 2025 effective drag (derived from its 2025 top-speed/power balance).
- **Lap-delta band** `(T26−T25)/T25` from Q–Q pairs (observed ≈ +1.7…+2.4%) → per-track gate
  band, replacing hardcoded seconds.

## 3. Components

Each is a small standalone script, testable alone; `cache/` is the established home for the
calibration harness.

### 3.1 `cache/_transfer_2026.py`
- Input: the pair table above (per-track: 2025 csv, 2026 csv, kind Q|FP1, altitude m).
- Resample speed vs normalized distance; detect corner minima (prominence ≥ 8 km/h, min
  separation 80 m); pair 2025↔2026 minima by nearest normalized distance.
- **Guard:** pairing rate < 80% → abort loudly (layout change / bad data).
- Output `cache/transfer_2026.json`: r(v25) knots, lap-delta stats, per-track effective-drag
  table, fit diagnostics + a per-pair overlay PNG for eyeballing.

### 3.2 `cache/_predict_track.py`
- Input: target track's 2025 Q csv, official length, altitude, 2025 pole time.
- Sanity-check the ref (integrated distance within 2% of official; lap within 3% of pole;
  else fall back to 2024 ref with a warning).
- Output `cache/predicted_<track>.json`: per-corner 2026 minima targets (r(v)·v25 at each 2025
  corner), top-speed target, lap-time band, ρ, and initial CDA/CL guesses via physics inversion
  (CDA from drag=power balance at predicted top with the 2026 PU curve incl. deploy=0 > 300;
  CL from the DF-dominated corner targets at fixed MU_LAT).

### 3.3 Sim CLI knobs (`sim_2026_lap.py`)
- Add `--cda`, `--cl`, `--rho` (defaults = current constants; existing batches unaffected).
- Unify `RHO` (l.702) and `WARM_RHO` (l.56) under the single `--rho`.
- Per-track values move from code edits into batch-file arguments.

### 3.4 `cache/_autofit_2026.py`
- Closed loop, no human: run sim → measure sim top speed + corner minima at predicted corner
  locations → secant-update CDA (target: top speed) and CL (target: median of high-speed-corner
  minima, defined as corners with v25 > 170 km/h) → converge ≤ 4 sim runs (top ±2 km/h,
  corner median ±3 km/h).
- Low-speed corners stay governed by global μ (frozen). Their residual is REPORTED, not
  absorbed — if back-test shows a consistent low-v bias we add a bounded per-track μ trim in v2.

### 3.5 `cache/_backtest_2026.py` — the proof + permanent regression suite
Leave-one-out over the 4 SVG-ready tracks (Canada, Catalunya, Austria, Silverstone):
fit transfer WITHOUT the track → predict from its 2025 ref alone → autofit → full sim →
score vs its real 2026 csv. Acceptance (v1):
- top speed |Δ| ≤ 5 km/h; corner-minima median |Δ| ≤ 5 km/h, worst ≤ 12;
- lap time: Q-ref tracks in `[T26_real − 1.5 s, T26_real]` (optimal beats the human, within
  reason); FP1-ref tracks in `[T_fp1 − 3.5, T_fp1 − 1.0]` (FP1 laps are non-push);
- hard rail everywhere: `T > T_2025_pole + 0.8 s`;
- distance-resampled speed-trace correlation ≥ 0.94.
Output: `cache/backtest_report.md` + per-track overlay PNGs. Any future physics/line change
reruns this harness.

### 3.6 Line-solver source fix (curvature-adaptive de-wobble)
Replace the uniform gaussian (σ=2.5, `LINE_WOBBLE_SIG`, sim_2026_lap.py:443) with a
curvature-weighted blend: full smoothing where |κ| is straight-line noise, →0 at genuine
apexes (R below ~60 m preserved). Acceptance: Austria honest lap returns above the
`2025 pole + 0.8 s` rail with sign-flips ≤ 60 and 0 off-track points; all 4 back-test tracks
re-pass. Removes the need for `--display-laptime` and stops CL absorbing line error.

### 3.7 Gate v2 (`cache/_gate_2026.py`)
Accept `--targets cache/predicted_<track>.json`: per-track bands (top ±6 km/h, corner minima
±6 km/h, lap band from transfer Δ% stats) + keep the cross-track hard rails (gain/drop medians,
superclip shape, `T > 2025 pole`).

### 3.8 Spa bring-up (the deliverable)
- Ref: fetch 2025 Belgian GP Q via FastF1 (`reference_2025_spa_q.csv`); official length 7004 m;
  altitude ≈ 430 m (ρ ≈ 1.176); road width ~14 m (min-corner-radius 9, La Source ≈ R11).
- SVG: **user drops one in the repo (as for all previous tracks) or explicitly approves a fetch
  of the Wikimedia Spa circuit SVG.** Blocking item flagged in chat; everything else proceeds.
- Pipeline: `make_spa_2026_lap.bat` = fetch-2025-ref → outline → predict → autofit → sim →
  gate → `belgian_grand_prix_2026_optimal_lap.mp4`, honest sim lap time displayed.
- Post-FP1 Friday: overlay + gate as VERIFICATION of the method (documented, not recalibrated).

## 4. Frozen (the car — never per-track)
Deploy 200/270/300 kW-taper, trail-brake 235/0.40/1.6, MU_LONG 1.35, MU_DRIVE 1.00,
A_ACC_LONG_MAX 1.65 g, smoothing win_s 0.45 (continuous, no brake mask), superclip frac 0.96.
Only CDA, CL, ρ are per-track, and they come from the predictor — never hand edits.

## 5. Failure modes
- **2025 quali wet/red-flagged/missing** → sanity check fails → 2024 ref fallback (warning).
- **Layout changed since 2025** → corner-pairing rate guard aborts with a clear message.
- **Brand-new track (Madring, Sept)** → out of scope v1; tier-2 = physics inversion only,
  labelled lower-confidence. Noted, not built.
- **FP1-pair bias** (Austria/Silverstone refs are non-push): quali pairs anchor the fit; FP1
  pairs never set the level, only confirm the shape.

## 6. Execution order
1. Transfer builder + predictor (csv-only, fast to verify) — incl. fetching 2025 Miami/China refs.
2. Sim CLI knobs + autofit.
3. Back-test harness → iterate until 4/4 tracks pass. ← the "no silly mistakes" proof
4. Line-solver adaptive de-wobble → re-run back-test (regression).
5. Gate v2.
6. Spa: predict → sim → video (needs SVG; everything else independent).
7. Friday: FP1 verification report.
