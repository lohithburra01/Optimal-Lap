# Singapore (Marina Bay) 2026 optimal lap - 2026-10-08 (pre-FP1)

Reproduce: make_singapore_2026_lap.bat. Video singapore_grand_prix_2026_optimal_lap.mp4, zoom 18,
no elevation flyover (flat street circuit).

SVG Marina_Bay_circuit_2023.svg: 6 KB, one stroked centreline, 79 segments (70 cubic + 9 line),
4.2 seg/turn = GOOD. Closes exactly, no self-crossings, post-2023 layout (no Bay grandstand loop).
Outline 4940 m, road 12 m, min R 10.

## Two pipeline traps found here
1. DIRECTION. Marina Bay runs anticlockwise (SVG as-drawn order; speed/curvature corr 0.80 fwd vs
   0.34 rev). sim_2026_lap.build_raceline ALWAYS drives CW (Canada-era reversal). Engine untouched:
   the sim runs on an x-mirrored outline (physics is left/right symmetric, no banking here) and the
   raceline is un-mirrored for the video (cache/_singapore_prep.py prep|mirror|unmirror).
   Registry outline = the MIRROR file.
2. S/F. svg_to_outline's low-curvature S/F guess was 855 m early. Physics-lite speed profile on the
   outline vs 2025 Q trace: corr 0.942 with telemetry d=0 at outline arc 855 m -> rolled.

## Fitted geometry (3 relaxations, rule: |resid| > 20 km/h at default knobs, inset 1.0)
Drawn sharp joins where the real corner is fast. cache/_outline_local_smooth.py:
- T1 near (617.4,375.5) half 70 sigma 24: sim 83 -> 143 (target 137)
- 2653 m near (-749.4,-198.8) half 70 sigma 20: 122 -> 142 (target 146)
- final corner near (635.7,-249.2) half 100 sigma 32: 113 -> 210 (target 199). Steep, non-monotone
  response (sigma 25:169, 30:231, 32:210, 34:228, 40: corner vanishes).
Unrelaxed rolled outline kept: singapore_grand_prix_outline_svgraw.json.

## GAIN guard
Real 2025 Q throttle-on gain median: singapore 23.9 (highest; bahrain 21.0, canada 21.5, hungary
20.2, zandvoort 18.9, spa 18.5). Sim 31.4-33.7 trips the engine's fixed [12,32] sanity guard, which
aborted autofit. cache/_sim_singapore.py wraps the engine with a 36.3 cap (23.9 x 1.52 = top of the
shipped sim/real ratio band); all other sanity checks unchanged. cache/_autofit_singapore.py runs
the standard autofit through it.

## Result
Inset 1.0 (registry; street circuit). Autofit cda 0.570, cl 4.171, rho 1.2232 (ISA 15 m),
converged it2 -> **92.40 s = 1:32.40** (2025 pole RUS 1:29.158; +3.6%, predicted band 89.95-94.22),
top 320 (target 318). Gate 8/9: GAIN 31.4 > fixed 28 (ratio 1.31, inside 1.26-1.52, as Bahrain).
On-track 0/2433 (worst -0.23 m). Corners: corr 0.974, 12/12 paired, worst 17 (T19 area -17,
T7 -16, 2193 m +15), median +2.6.
First autofit used inset 0 by mistake: 90.30 s, 1 pt 0.55 m off-track (kept as
autofit_singapore_inset0.json / _autofit_singapore_inset0.log).

## FP1 (verification only)
fetch_openf1_lap.py --year 2026 --country Singapore --session "Practice 1"; expect FP1 ~+3% over
eventual Q. Do NOT recalibrate to FP1.

## v2 (CURRENT, 2026-10-08): apex-touch line + zoom 25
User: "line is not tight, not touching all the apexes"; zoom 1.3-1.5x -> 25 (from 18).
Bahrain v2b method: cache/bahrain/_opt_line_2026.py --margin 0.3 --apex-w 1.5 on the mirror frame,
knobs refit on the fixed line (cache/singapore/_autofit_rl_in_sg.py = rl-in + GAIN guard), one more
opt+refit round -> fixed point cda 0.599 cl 3.400 -> **92.43 s = 1:32.43**. All 14 apexes <= 0.30 m from
the inside bound (road - 0.3 m); on-track 0/2433 (worst -0.22 m). Video frames checked at 4 apexes.
COST: corner fit worse - gate 7/9 (corner-median +8.2 > 6, GAIN 30.6), corr 0.963, T1 +28, 2774 m +26,
4335 m -17. The T1 relaxation (sigma 24) was tuned for the WIDE line; on the apex line it overshoots.
CL 3.40 is low vs fleet (Bahrain v2b 3.64, same mechanism). Possible fix: re-tune T1 sigma (~16) on the
apex line, then opt+refit again (~35 min). v1 files: cache/singapore/v1_backup/.

## v3 (CURRENT, 2026-10-08): T8 -> T9 wide entry
User (video 36-40 s): after the T8 apex the line should cross back to the far side before T9, as RUS's
2025 pole lap; ours stayed on the inside (0.48 of the way toward T9's outside). The pattern search was
TRAPPED: a single-knot move can't make the coordinated crossing. cache/singapore/_seed_wide.py seeds the
knots in 2010-2140 m 80% toward the opposite bound; the optimiser keeps the crossing (0.85) and it is
FASTER: pure lap 91.730 vs 91.768 s. cache/singapore/_scan_crossings.py checks every opposite-direction
corner pair: T8->T9 was the only stuck one (others 0.83-1.00).
Knob refit on opt3w: cda 0.592 cl 3.400 -> **92.42 s = 1:32.42**. Gate 7/9 (corner median +6.9, GAIN 30.3),
corr 0.966, on-track OK (worst -0.22). T1 +28 / 2774 m +26 too fast remain (T1 relaxation tuned for the
wide v1 line). Video zoom 25; frames 36-40 s show the crossing. v2 backup: cache/singapore/v2_backup/.
Batch fix: knot vectors are offsets from the v1 base line -> saved as cache/singapore/base_v1_rl.json.
Zoom changed to 28 (user, 2026-10-08).

## 2025 vs 2026 dual video (2026-10-08): singapore_2025_vs_2026.mp4 (make_singapore_2025_vs_2026.bat)
Car A = RUS 2025 pole REAL telemetry (OpenF1 session 9892 drv 63 lap 17, raw cached in
cache/singapore/rus2025_car_data.json) incl. DRS (open 26% of samples). Rides OUR 2026 line (position feed is
map-matched); distance warped onto our lap by 11/12 paired speed minima; time scaled to official 89.158.
Mode: DRS / REGEN(brake) / FULL / NORMAL. Car B = shipped 2026 lap 1:32.42 untouched. Gap at flag 3.21 s.
v2 dual (CURRENT): RUS on his OWN 2025-car line (user: lines must differ a little, naturally - no deliberate
tighter lines). era-2017 car model, mass 800, DRS zones from RUS DRS channel, cda 1.5763 / cl 3.0144 fitted to
316 km/h + 89.158 on its own line (fixed point, 2 rounds). Line = cache/singapore/_opt_line_2025.py (copy of the
2026 optimiser, only the cost car swapped), SAME 14 apex corners (--apex-knots seed_wide.npy: a first run that
re-detected corners on the 2026 line added 2 extra apexes = method artefact, discarded as opt2025*).
Result: median 0.02 m, p90 0.50, max 2.3 m apart (3634, 824, 2055 m). Fit vs RUS real: corr 0.975.
Same-line version kept: cache/singapore/singapore_2025_vs_2026_sameline.mp4.

## 2026-10-08 FINDING: SVG corner-to-corner DISTANCES are wrong (explains the odd 2025-vs-2026 gap)
Real (RUS 2025 telemetry, integrated) vs our line, between paired speed minima:
T7->T8 199 vs 231 m (+15.9%), T8->T9 +7.0%, T9->T10 -4.5%, T10->T11 119 vs 99 m (-17.1%), T11->T13 -6.6%,
T19->T22 -7.8%; others within +-3%. The gap counter's big swings (2025 +1.45 s at T7-T8, 2026 +0.8 s back at
T10-T11) are these length errors, not car physics. Real-pair phase analysis (cache/singapore/_delta_phases.py,
_brake_dist.py): traction = 42-86% of real 2026 deficit (ours 49%, OK); real 2026 decel zones 1.34x 2025, ours
only ~1.16x net of sim baseline (superclip under-modelled).
Car-A timing bug: rus2025_on_*_line.csv scaled the whole sample window (0.099 s before .. 0.18 s after) to 89.158
-> 0.12-0.16 s off at the sector lines. Fix: official clock = car_data date - lap date_start.
Retrofit attempt (cache/singapore/_retrofit2025.py): vmin matched to 0.0 km/h but segment times cannot match on
mis-lengthed segments (needed accel factors 3-4x) -> geometry must be fixed first. Proposed: TPS-warp the SVG
onto the official position path anchored at corners (true distances, SVG corner shapes kept).

## 2026-10-08 track-fix investigation (shipped v3 files untouched in place; copies in cache/singapore/v3_backup)
Official path: 10 top-10 Q laps of map-matched location (cache/singapore/path_samples.json, _official_path.py),
4867 m raw -> scaled to FIA 4927 m; Procrustes rms 6.2 m vs the SVG; official S/F 14.6 m from ours.
CORRECTION of the earlier finding: SVG corner POSITIONS are within 5-25 m of official (T5 ~60 m early); the
+-17% minimum-to-minimum length errors come mostly from SVG corner SHAPE - T7/T10/T11/T14/T16 drawn as R 11-15 m
kinks vs official 22-45 m - which moves where/how slow the sim takes them.
Tried: (a) smoothed-displacement warp sigma 20 (_warp_to_official.py): corners rounded, probe 89.0 s, T7 +52;
(b) rigid-anchor warp: 4998 m, T8 +40, corr 0.92; (c) official path as centreline (outline_official.json):
probe corr 0.979 (best), but low-speed corners +13..+21 at default knobs; autofit cannot converge (rail: lap
89.6 s at CL 3.75 while the v25>=130 tier is already -9) -> registry/outline now point at official (length 4927);
(d) hybrid rigid corners (_hybrid_outline.py): corner rotations up to 33 deg, 4984 m - rejected.

## v4 (CURRENT, 2026-10-08): OFFICIAL-GEOMETRY track + street grip + exact 2025 clock
Track: official map-matched path (top-10 2025 Q laps) @ FIA 4927 m, R>=10, **10 m wide** (12 m: worst corner 46,
10 m: 18) - cache/singapore/_build_official_outline.py (reproduces the installed file exactly). S/F = official.
Street grip: car models are ~7 s too fast at Singapore with normal grip (physical 2025 car 82.3 s). Mechanical-only
grip factor k (cache/singapore/_sg_grip.py, env SG_MECH) measured on the physical 2025 car (fleet cl 4.277) vs
RUS: **k = 0.723** -> lap 89.158, corners median |err| 9.6 (cl-trim alternative 12.0). Applied unchanged to 2026.
(A MU_LAT scale knob was tried first: it also scales aero grip -> cl hit 6.5, rejected.)
2026: autofit (k) cda .618 cl 6.327 -> apex line k1 -> refit cda .554 cl 4.348 -> k2 -> refit **cda 0.559 cl 4.363,
92.73 s** (fixed point). Gate 8/9 (GAIN 28.0 at the cap). On-track OK (-0.21). Corners median +4.9, worst 25
(T10 +25, final -22, T16 +20, T5 -17). Crossings all >= 0.91 (T8->T9 natural, no seed).
2025 car A: REAL telemetry on the official clock (_rus2025_exact.py): S1 26.475 / S2 63.804 / lap 89.158 exact;
mapped by real distance (track distance-correct, 4876 vs 4882 m) -> dot speed == shown speed. 2025 line k25:
physical car + k, same optimiser/corners; vs 2026 line median 0.02, max 1.5 m.
Gap now builds 0.24-0.87 s per corner segment (old T7-T8 spike +1.45 -> +0.42). OPEN (engine-wide, not done):
76% of the 2026 deficit is in RUS's braking zones vs 11-27% in real 2026-vs-2025 pairs -> the 2026 car slows
too early/long before corners; needs an engine braking/superclip calibration with full backtest.
v3 (SVG) files: cache/singapore/v3_backup/.
v4b (2026-10-08): 2025 line T8->T9 wide entry (user, RUS 2025 onboard): optimiser alone stayed inside (only 0.4 of
the way back). _opt_line_2025.py --touch 2060,2120,1980 (must reach the side of the T8 apex) from a wide seed ->
k25w: 0.64 m from the far edge at ~2090 m, lap 88.788 vs 88.792 s (no cost). _scan_crossings.py metric was
misleading here (counted T8's own apex side) - check pairs visually / from the exit onward.
2026 line still inside there (not changed; same treatment possible).
v4b 2026 line (2026-10-08, CURRENT): same T8->T9 wide entry (user). _opt_line_2026_sg.py --touch 2060,2120,1980 from a
wide seed -> k3w; costs the 2026 car ~0.08 s (pure lap 92.113 vs 92.034). Refit cda 0.558 cl 4.323 -> **93.01 s**
(1:33.008), gate 9/9, on-track OK, corners median +3.4 / worst 25. Both videos re-rendered (dual b-lap 93.01).
