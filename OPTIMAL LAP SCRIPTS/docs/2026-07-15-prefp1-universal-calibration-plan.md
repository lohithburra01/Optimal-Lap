# Pre-FP1 Universal Calibration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026 optimal-lap sims calibrated from the target track's 2025 data + an empirically fitted 2025→2026 transfer — no target-track FP1 needed — proven by leave-one-out back-test on 4 tracks, then shipped for Spa before Friday's FP1.

**Architecture:** Small standalone scripts in `cache/` (the established calibration-harness home) sharing a track registry module. The sim gains 3 CLI knobs (`--cda --cl --rho`); an autofit loop drives the sim via subprocess to hit predicted targets; a back-test harness is the accuracy proof and permanent regression suite.

**Tech Stack:** Python 3.10 (`C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe`), numpy/scipy/matplotlib only (no sklearn), pytest for unit tests. All commands run from repo root `D:\f1_hot_lap\OPTIMAL LAP SCRIPTS`.

## Global Constraints

- **Spec:** `docs/2026-07-15-prefp1-universal-calibration-design.md` — read it first.
- **Frozen car constants (NEVER per-track, never edit):** deploy taper 200/270/300, trail-brake 235/0.40/1.6, `MU_LONG=1.35`, `MU_DRIVE=1.00`, `A_ACC_LONG_MAX=1.65g`, `smooth win_s=0.45` (continuous, no brake mask), `SUPERCLIP_SPEED_FRAC=0.96`.
- Per-track knobs are ONLY `--cda`, `--cl`, `--rho`, produced by predictor+autofit — never hand edits.
- Reference CSV schema (both fetchers): `frame,time_s,distance,speed,throttle,brake,gear,rpm,ers_deploy` (speed km/h, distance m).
- Quali pairs anchor every fit; FP1 pairs (`kind26="FP1"`) validate only.
- Monaco is out of scope (isolated sim).
- Hard rail everywhere: sim lap `T > T_2025_ref + 0.8 s`.
- Commit after every task; never commit the big mp4/csv artifacts, only scripts/docs/json ≤ 200 KB.

---

### Task 1: Track registry + shared analysis utilities (+ fetch missing 2025 refs)

**Files:**
- Create: `cache/_track_registry.py`
- Test: `tests/test_transfer.py`
- Data: fetch `F1_Pipeline_Assets/exports/reference_2025_miami_q.csv` and `reference_2025_china_q.csv`

**Interfaces (Produces):**
```python
TRACKS: dict[str, dict]  # keys: canada, catalunya, austria, silverstone, miami, china, spa
# each: outline (path|None), csv25, csv26 (path|None), kind26 ("Q"|"FP1"|None),
#        altitude_m: float, length_m: float
def rho_isa(altitude_m: float) -> float            # 1.225*(1-2.25577e-5*h)**4.2561
def load_ref(path: str) -> tuple[np.ndarray, np.ndarray, float]   # (s_m, v_kmh, t_lap_s), monotone s
def corner_minima(s, v, prominence_kmh=8.0, min_sep_m=80.0) -> list[tuple[float, float]]  # [(s_i, v_i)]
def pair_minima(m25, m26, s_total, tol_frac=0.015) -> tuple[list[tuple], float]  # pairs (s25,v25,s26,v26), rate
def pava_nonincreasing(v: np.ndarray, r: np.ndarray, w: np.ndarray, knots: np.ndarray) -> np.ndarray  # r at knots
```

- [ ] **Step 1.1: Write failing unit tests** in `tests/test_transfer.py`:

```python
import numpy as np, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cache"))
from _track_registry import rho_isa, corner_minima, pair_minima, pava_nonincreasing

def test_rho_isa_sea_level_and_mexico():
    assert abs(rho_isa(0.0) - 1.225) < 1e-9
    assert 0.95 < rho_isa(2240.0) < 1.00      # Mexico City

def test_corner_minima_finds_two_dips():
    s = np.linspace(0, 4000, 2001)
    v = 300 - 150*np.exp(-((s-1000)/120)**2) - 120*np.exp(-((s-3000)/150)**2)
    m = corner_minima(s, v)
    assert len(m) == 2
    assert abs(m[0][0] - 1000) < 30 and abs(m[1][0] - 3000) < 30

def test_pair_minima_matches_shifted_corners():
    m25 = [(1000.0, 150.0), (3000.0, 180.0)]
    m26 = [(1030.0, 138.0), (2985.0, 160.0), (3900.0, 240.0)]  # extra unmatched dip
    pairs, rate = pair_minima(m25, m26, s_total=4000.0)
    assert len(pairs) == 2 and rate >= 2/3

def test_pava_nonincreasing_is_monotone():
    v = np.array([90, 120, 150, 200, 250, 280.]); r = np.array([1.0, .97, 1.01, .90, .84, .86])
    knots = np.array([80, 140, 200, 260, 320.])
    rk = pava_nonincreasing(v, r, np.ones_like(r), knots)
    assert np.all(np.diff(rk) <= 1e-9)
```

- [ ] **Step 1.2: Run tests, verify FAIL** (`module not found`):
  `& "C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe" -m pytest tests/test_transfer.py -v`
- [ ] **Step 1.3: Implement `cache/_track_registry.py`.** TRACKS values: canada(alt 13, len 4361), catalunya(alt 130, len 4657, csv25=`reference_2025_spain_q.csv`), austria(outline=`austrian_grand_prix.json`, alt 680, len 4318, csv26 FP1), silverstone(alt 150, len 5891, csv26 FP1), miami(outline None, alt 2, len 5412), china(outline None, alt 4, len 5451), spa(outline `belgian_grand_prix_outline.json`, alt 420, len 7004, csv26 None). `load_ref`: read csv, sort/dedupe distance monotone, return arrays + `t_lap = time_s.max()-time_s.min()`. `corner_minima`: `scipy.signal.find_peaks(-v, prominence=prominence_kmh, distance=max(1, int(min_sep_m/median_ds)))`. `pair_minima`: for each m26 minimum take nearest m25 within `tol_frac*s_total`, one-to-one greedy by distance; `rate = len(pairs)/max(len(m25), len(m26))`. `pava_nonincreasing`: bin points to nearest knot, weighted means, then pool-adjacent-violators enforcing non-increasing (negate + standard PAVA).
- [ ] **Step 1.4: Tests pass:** same pytest command, 4 passed. Existing suite untouched: run `-m pytest tests/ -x -q` (pre-existing known failure `test_forward_pass_clips_when_battery_empty` is NOT yours — leave it).
- [ ] **Step 1.5: Fetch the two missing 2025 refs.** First `--help` on `fetch_fastest_lap.py` (FastF1-based, works for past years) to see its exact args, then fetch 2025 Miami GP Qualifying → `F1_Pipeline_Assets/exports/reference_2025_miami_q.csv` and 2025 Chinese GP Qualifying → `reference_2025_china_q.csv`. Verify each: schema header matches, integrated distance within 2% of registry length, plausible lap (Miami Q ~86–89 s, China Q ~90–92 s).
- [ ] **Step 1.6: Commit** `feat(cache): track registry + transfer utilities + 2025 miami/china refs`

### Task 2: Transfer builder

**Files:**
- Create: `cache/_transfer_2026.py`
- Output: `cache/transfer_2026.json`, `cache/transfer_overlay_<slug>.png`

**Interfaces:**
- Consumes: everything from `_track_registry.py` (Task 1).
- Produces CLI: `python cache/_transfer_2026.py [--exclude SLUG] [--out cache/transfer_2026.json]`
- Produces JSON schema (later tasks rely on these exact keys):

```json
{"knots_v25": [80,140,200,260,320], "r_knots": [..5 floats..],
 "lap_delta_pct": {"mean": 0.0, "sd": 0.0, "per_track": {"canada": 0.0}},
 "vtop_delta_kmh": {"mean": 0.0, "sd": 0.0, "per_track": {}},
 "pairs_used": ["canada","catalunya","miami","china"], "excluded": null,
 "fp1_validation": {"austria": {"r_residual_median": 0.0}, "silverstone": {}}}
```

- [ ] **Step 2.1: Implement.** For every registry track with both csv25+csv26 (minus `--exclude`): load refs, corner minima, pair (abort loudly if rate < 0.8 on a Q pair). Q pairs → pooled (v25, v26/v25) points → `pava_nonincreasing` on knots [80,140,200,260,320]; `lap_delta_pct` and `vtop_delta_kmh` (v_top = 99.5th percentile of speed) from Q pairs only. FP1 pairs: evaluate fitted r on their corner points → residual medians into `fp1_validation` (never into the fit). Per-track overlay PNG: speed-vs-distance 2025 vs 2026 with matched minima marked.
- [ ] **Step 2.2: Run on all pairs, eyeball diagnostics.** Expect: r(80)≈0.95–1.02 falling to r(320)≈0.80–0.92 monotone; lap_delta_pct mean ≈ +1.5…+3.0; pairing rates ≥ 0.8; FP1 residual medians within ±0.04 of the Q-fit. If any expectation breaks, STOP and diagnose (bad ref csv? pairing tolerance?) before proceeding — do not tune constants to force it.
- [ ] **Step 2.3: Also run `--exclude canada`** (smoke-test the leave-one-out path; pairs_used drops canada).
- [ ] **Step 2.4: Commit** `feat(cache): 2025->2026 empirical transfer builder` (include transfer_2026.json; PNGs only if < 200 KB each).

### Task 3: Sim CLI knobs `--cda --cl --rho`

**Files:**
- Modify: `sim_2026_lap.py` (argparse block ~l.1542; constants `WARM_RHO` l.56, `RHO` l.702, `CDA_STRAIGHT_M2` l.724, `CL_CORNER_M2` l.754)

**Interfaces (Produces):** `--cda FLOAT (default 0.80) --cl FLOAT (default 4.20) --rho FLOAT (default 1.225)`; after parse, `main()` reassigns the module globals (`globals()['CDA_STRAIGHT_M2']=args.cda`, same for CL; `RHO` and `WARM_RHO` both = args.rho) BEFORE any physics runs. All physics reads are runtime module-global reads (verified l.831/836/848/893), so reassignment is sufficient — but grep every use of the four names to confirm none is captured in a default arg or computed at import into a derived constant; if one is, recompute it after override.

- [ ] **Step 3.1: Implement** the three args + override function `_apply_car_overrides(args)`.
- [ ] **Step 3.2: Regression — defaults byte-identical behavior.** Rerun Silverstone with NO new flags:
  `& $PY sim_2026_lap.py --outline F1_Pipeline_Assets/tracks/british_grand_prix_outline.json --raceline-out cache/_tmp_rl.json --csv-out cache/_tmp_sim.csv --reference-csv F1_Pipeline_Assets/exports/reference_2026_silverstone_fp1.csv --inset 0`
  Expected: lap time printed ≈ 87.97 s (match current `silverstone_2026_synthetic.csv` duration to <0.01 s), sanity passes.
- [ ] **Step 3.3: Knob sanity:** rerun with `--cda 1.10` → top speed drops by >10 km/h; with `--rho 0.98` (Mexico-ish) → top speed rises. Print both tops in the log.
- [ ] **Step 3.4: Commit** `feat(sim): per-track --cda/--cl/--rho CLI knobs (defaults unchanged)`

### Task 4: Per-track predictor

**Files:**
- Create: `cache/_predict_track.py`
- Output: `cache/predicted_<slug>.json`

**Interfaces:**
- Consumes: `_track_registry.py`, `transfer_2026.json` (Task 2 schema).
- Produces CLI: `python cache/_predict_track.py --track SLUG [--transfer PATH] [--out PATH]`
- Produces JSON (exact keys; autofit + gate v2 consume this):

```json
{"track": "spa", "rho": 1.176, "t25_s": 0.0, "lap_band_s": [0.0, 0.0],
 "vtop_target_kmh": 0.0,
 "corners": [{"s_m": 0.0, "s_frac": 0.0, "v25_kmh": 0.0, "v26_target_kmh": 0.0}],
 "cda0": 0.75, "cl0": 4.6, "ref_used": "2025_q", "warnings": []}
```

- [ ] **Step 4.1: Implement.** Load track's csv25; sanity: integrated distance within 2% of `length_m` (else warning + still proceed if within 5%, abort beyond), `t25` recorded from the csv itself (no hardcoded poles). Corners: `corner_minima` → each gets `v26_target = interp(v25, knots, r_knots) * v25`. `vtop_target = v_top25 + vtop_delta.mean`. `lap_band_s = [t25*(1+max(0.008, (mean-2sd)/100)), t25*(1+(mean+2sd)/100)]` — floor keeps the +0.8 s rail implied even for short laps. `rho = rho_isa(altitude_m)`. `cda0/cl0`: previous-track defaults 0.75/4.6 (autofit refines; no fragile inversion in v1).
- [ ] **Step 4.2: Run for canada, catalunya, austria, silverstone** and eyeball: corner counts ≈ real corner counts (Canada ~14, Catalunya ~14, Austria ~9, Silverstone ~15), targets all BELOW their v25 at high speed, lap bands ~ +1.5–3 s over t25.
- [ ] **Step 4.3: Commit** `feat(cache): pre-FP1 per-track target predictor`

### Task 5: Autofit loop

**Files:**
- Create: `cache/_autofit_2026.py`
- Output: `cache/autofit_<slug>.json` + the fitted sim csv/raceline under `cache/`

**Interfaces:**
- Consumes: `predicted_<slug>.json` (Task 4), sim knobs (Task 3), registry outlines.
- Produces CLI: `python cache/_autofit_2026.py --track SLUG [--targets PATH] [--max-iters 4]`
- Produces JSON: `{"cda": 0.0, "cl": 0.0, "rho": 0.0, "iters": 0, "converged": true, "top_err_kmh": 0.0, "hs_median_err_kmh": 0.0, "lap_s": 0.0, "csv": "cache/autofit_<slug>_sim.csv"}`

- [ ] **Step 5.1: Implement.** Objectives from a sim csv: `sim_vtop` (99.5th pct), sim corner minima matched to target corners by `s_frac` (±1.5%); high-speed set = targets with `v25_kmh > 170`; `f1 = sim_vtop - vtop_target`, `f2 = median(sim_min - v26_target)` over the HS set. Alternating secant: run sim at (cda0, cl0); then per iteration update `cda -= f1 * dcda/df1` (initialize sensitivity with a bump run at cda0+0.08, then secant from history; clamp cda∈[0.45,1.3]) and `cl -= f2 * dcl/df2` (bump cl0+0.4; clamp cl∈[3.0,6.5]). Converged when |f1|≤2 and |f2|≤3. ≤ `--max-iters` refinement rounds (each round = 1 sim run after the 2 initial sensitivity runs). Sim via subprocess with `--cda --cl --rho --inset 0`, parse csv. Report low-speed (v25≤170) residual median in the log — NOT fitted.
- [ ] **Step 5.2: Single-track sanity — silverstone:** run it; expect converged=true within budget, lap in predicted band, and log the fitted (cda, cl) vs the old hand pins (0.80, 4.20) for interest (need not match — targets differ from FP1 pins; the SCORE that matters is Task 6's).
- [ ] **Step 5.3: Commit** `feat(cache): closed-loop autofit of cda/cl to predicted targets`

### Task 6: Leave-one-out back-test — the proof (v1 report)

**Files:**
- Create: `cache/_backtest_2026.py`
- Output: `cache/backtest_report.md`, `cache/backtest_<slug>.png`

**Interfaces:**
- Consumes: all previous tasks' CLIs (subprocess) + registry.
- Produces CLI: `python cache/_backtest_2026.py [--tracks canada,catalunya,austria,silverstone]`

- [ ] **Step 6.1: Implement.** Per track T: `_transfer_2026.py --exclude T --out cache/transfer_loo_T.json` → `_predict_track.py --track T --transfer that` → `_autofit_2026.py --track T --targets that` → score fitted sim csv vs T's REAL csv26: `top_err`; per-corner errs (match by s_frac) with median + worst; distance-resampled speed corr; lap check — Q tracks: `t26_real - 1.5 ≤ lap ≤ t26_real`, FP1 tracks: `t_fp1 - 3.5 ≤ lap ≤ t_fp1 - 1.0`; rail `lap > t25 + 0.8`. PASS bands: |top_err| ≤ 5, |corner median| ≤ 5, worst ≤ 12, corr ≥ 0.94, lap in band. Emit a markdown table (track × metric, PASS/FAIL) + per-track overlay PNG (sim vs real 2026 vs 2025).
- [ ] **Step 6.2: Run it. Iterate honestly.** Expected first-run outcome: some FAILs. Diagnose per failure class: pairing/misalignment → registry utils; systematic corner bias at low v → note for line-fix task (do NOT absorb via μ); top-speed bias on FP1 tracks → check vtop_delta Q-vs-FP1. Only change fit logic/tolerances with a stated reason in the report. Target: 4/4 pass on every metric EXCEPT lap-time rail misses attributable to line wobble (expected for Austria pre-Task-7; mark `KNOWN — line fix pending`).
- [ ] **Step 6.3: Commit** `feat(cache): leave-one-out backtest harness + v1 report`

### Task 7: Curvature-adaptive line de-wobble + back-test v2

**Files:**
- Modify: `sim_2026_lap.py` (`build_raceline` de-wobble block, ~l.443)

**Interfaces (Produces):** env `LINE_WOBBLE_ADAPTIVE=1` (default ON; `0` restores old uniform behavior), `LINE_WOBBLE_SIG` keeps meaning = the strong/straight-region σ.

- [ ] **Step 7.1: Implement.** On the closed raceline XY: κ_ref = |Menger κ| of a σ=3-prefiltered copy (weight signal, wrap-aware). Weight `w = clip((KAPPA_HI - κ_ref)/(KAPPA_HI - KAPPA_LO), 0, 1)` with `KAPPA_LO=0.005` (R=200 m), `KAPPA_HI=0.0167` (R=60 m). Output line = `w*gaussian(σ=LINE_WOBBLE_SIG) + (1-w)*gaussian(σ=0.8)` pointwise (light σ kills pixel noise at apexes without rounding R). Log: sign-flips before/after, |κ|max before/after, min corner R.
- [ ] **Step 7.2: Austria acceptance:** rerun Austria sim (registry outline, autofit constants from Task 6). Expected: honest lap **> 64.77 s** (2025 ref 63.97 + 0.8), sign-flips ≤ 60, off-track 0, |κ|max within ~10% of pre-smoothing. If lap still under the rail, re-run the Austria AUTOFIT (line changed ⇒ CL re-fits to the same corner targets — the self-correcting coupling; see spec §3.6) before judging.
- [ ] **Step 7.3: Re-run FULL back-test** (it re-autofits every track on the new line — this is the regression gate): `4/4` including lap rails now. Save as v2 section in `backtest_report.md`.
- [ ] **Step 7.4: Commit** `fix(sim): curvature-adaptive de-wobble preserves genuine apexes; backtest v2 4/4`

### Task 8: Gate v2 — predicted-target bands

**Files:**
- Modify: `cache/_gate_2026.py`

**Interfaces (Produces):** `python cache/_gate_2026.py <sim_csv> <t25_s> [--targets cache/predicted_<slug>.json]` — with `--targets`: replaces Catalunya-hardcoded bands with top ±6 km/h, corner-minima median ±6 km/h vs targets, lap ∈ `lap_band_s`; KEEPS cross-track signature rails (gain median [12,32], drop median [28,60], drop peak ≥85, superclip shape, `T > t25 + 0.8`). Without `--targets`: behavior unchanged.

- [ ] **Step 8.1: Implement + run on all 4 back-test tracks' fitted csvs** — expect 4/4 gate pass consistent with the back-test report.
- [ ] **Step 8.2: Commit** `feat(gate): per-track predicted-target bands via --targets`

### Task 9: Spa — the deliverable

**Files:**
- Create: `make_spa_2026_lap.bat`; `F1_Pipeline_Assets/tracks/belgian_grand_prix_outline.json` (+raceline); `F1_Pipeline_Assets/exports/reference_2025_spa_q.csv`, `spa_2026_synthetic.csv`; `belgian_grand_prix_2026_optimal_lap.mp4`
- **BLOCKER:** Spa SVG — user drops it in repo root OR explicitly approves fetching the Wikimedia circuit SVG. Do not fetch without that approval.

- [ ] **Step 9.1:** Fetch 2025 Belgian GP Q ref via `fetch_fastest_lap.py` → `reference_2025_spa_q.csv`; verify distance ≈ 7004 m ±2%, lap ≈ 100–107 s.
- [ ] **Step 9.2:** SVG → outline: `svg_to_outline.py --svg <spa.svg> --out F1_Pipeline_Assets/tracks/belgian_grand_prix_outline.json --track-length 7004 --road-width 14.0 --min-corner-radius 9.0`; verify with `cache/_verify_outline.py` (no pinch) and centerline plot (`cache/_diag_*` pattern).
- [ ] **Step 9.3:** Predict (full transfer, no exclude) → autofit → gate v2 with `--targets cache/predicted_spa.json`. Also overlay vs 2025 ref (`cache/_overlay_speed.py`) — corr ≥ 0.94 confirms SVG geometry (vs 2025! shape check only — levels differ by regs).
- [ ] **Step 9.4:** `make_spa_2026_lap.bat` mirroring `make_silverstone_2026_lap.bat` stages but: stage 0 = 2025 ref fetch (FastF1) + predict + autofit; sim stage passes the autofit's `--cda --cl --rho`; video stage `--track-name "Belgian Grand Prix"`, zoom per preview, honest sim lap displayed (NO `--display-laptime` unless the user asks).
- [ ] **Step 9.5:** Render `belgian_grand_prix_2026_optimal_lap.mp4`; spot-check frames (start/Eau Rouge/Pouhon/chicane) for on-track car + sane HUD.
- [ ] **Step 9.6: Commit** `feat: Spa 2026 pre-FP1 optimal lap (predicted calibration, gate-passed)`

### Task 10: Close-out

- [ ] **Step 10.1:** Write `NOW.md` (repo root): state = method built, back-test 4/4, Spa shipped pre-FP1; next = Friday FP1 verification (`fetch_openf1_lap.py --year 2026 --country Belgium --session "Practice 1"` → overlay + gate as VERIFICATION; document errors, do not recalibrate).
- [ ] **Step 10.2:** Update memory: new memory `prefp1-transfer-calibration.md` (method + back-test numbers + Spa result); update `fp1-calibration-playbook.md` pointing to it (FP1 now verification-only).
- [ ] **Step 10.3: Commit** `docs: NOW.md resume state + memory`

## Self-Review (done)

1. **Spec coverage:** §3.1→T2, §3.2→T4, §3.3→T3, §3.4→T5, §3.5→T6, §3.6→T7, §3.7→T8, §3.8→T9, failure modes→T4 sanity/T2 guard, Friday verification→T10. Covered.
2. **Placeholders:** none — every step has code, exact commands, or explicit expected numbers.
3. **Type consistency:** JSON keys (`r_knots`, `knots_v25`, `vtop_target_kmh`, `corners[].s_frac`, `lap_band_s`) used identically in T2/T4/T5/T6/T8. Function signatures fixed in T1 and consumed unchanged.
