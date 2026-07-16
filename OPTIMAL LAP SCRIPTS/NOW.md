# NOW — resume state (2026-07-16)

## Shipped: Spa 2026 optimal lap, PRE-FP1 (FP1 is Fri 2026-07-17 ~11:30)
`belgian_grand_prix_2026_optimal_lap.mp4` — lap **1:41.91** (2025 pole NOR 1:40.562 +1.35 s),
top 343, honest HUD time (no --display-laptime). Gate 9/9. Shape overlay vs 2025 real:
corr 0.978 (La Source 77=77, mean 269=269). a(v) rate-vs-speed in real-2026 family.
Knobs came from the NEW pre-FP1 method (never saw any 2026 Spa data): cda 0.737, cl 5.355,
rho 1.1764 via `make_spa_2026_lap.bat` stages (predict → autofit → gate → video).

## The method (docs/2026-07-15-prefp1-universal-calibration-design.md)
transfer (cache/_transfer_2026.py, Q pairs only) → predictor (_predict_track.py) →
sim CLI knobs (--cda/--cl/--rho) → autofit (_autofit_2026.py, rail-guarded) →
gate --targets (_gate_2026.py) → leave-one-out backtest (_backtest_2026.py).
Backtest v2: rail 4/4, corr 4/4, FP1-ref tracks 0 fails; residuals documented in
cache/backtest_report.md. Line fix: curvature-adaptive de-wobble in sim_2026_lap.py
(LINE_WOBBLE_ADAPTIVE=0 reverts).

## NEXT (Friday, after FP1 ends — VERIFICATION ONLY, do not recalibrate)
1. `python fetch_openf1_lap.py --year 2026 --country Belgium --session "Practice 1" --out F1_Pipeline_Assets/exports/reference_2026_spa_fp1.csv`
   (OpenF1 needs the session OVER; live returns 401. FastF1 livetiming currently broken.)
2. Overlay: `python cache/_overlay_speed.py F1_Pipeline_Assets/exports/spa_2026_synthetic.csv F1_Pipeline_Assets/exports/reference_2026_spa_fp1.csv 101.91 <fp1_lap> <drv>`
   Expect: FP1 lap ≈ our sim +2..3.5 s (FP1 runs ~+3.2% over eventual Q); corr ≥ 0.95.
3. Watch items recorded in cache/backtest_report.md §Spa: Eau Rouge flat?, gain 220-260,
   drop 140-180. Write a short verification note into the report either way.
4. If verification passes → post/publish; the method graduates to default for every
   future track (Hungaroring next: 2026-07-24, needs only an SVG + this pipeline).

## Open items (not blockers)
- backtest residuals: canada lap-band +0.9s conservative; catalunya vtop −12 (real
  outlier); per-corner ±30-40 at coarse-SVG sweepers (dense SVGs behave: get dense SVGs).
- _overlay_speed.py has a hardcoded "Catalunya" title + output filename (cosmetic).
- tests/test_physics_sim.py::test_forward_pass_clips_when_battery_empty — pre-existing
  failure, unrelated (documented since Catalunya bring-up).
- The uncommitted user files from before this work (blend files, formulyticsScript, etc.)
  were left untouched.
