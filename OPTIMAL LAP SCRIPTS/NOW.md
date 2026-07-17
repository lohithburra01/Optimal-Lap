# NOW.md — operating manual for the pre-FP1 2026 optimal-lap pipeline
(last update 2026-07-16, after shipping Spa pre-FP1. Read this fully before touching anything.)

## What this project produces
One vertical video per race weekend: `<track>_2026_optimal_lap.mp4` — a physics-simulated
"perfect" 2026 lap animated on the track map with speed/mode HUD (@formulytics). The whole
point of the current system: the video is produced BEFORE the weekend starts, with **zero
dependency on that track's 2026 sessions**. FP1/Q data is used afterwards only to VERIFY.

## The core idea (the "math engine") — all committed and working
Per-track car knobs (CDA = straight-line drag, CL = corner downforce, RHO = air density)
are PREDICTED from data that exists pre-weekend:
1. the track's own **2025 quali lap** (OpenF1) → where the real car braked, cornered, topped out;
2. an **empirical 2025→2026 transfer** fitted from tracks where we hold BOTH years' real laps:
   corner-speed ratio r(v25) (monotone, ~0.975 at 80 km/h → ~0.904 at 200+), top-speed delta
   (mean +4.7 km/h), lap-delta band (mean +2.55% sd 1.61);
3. a closed-loop **autofit** that runs the sim until it hits the predicted targets, with a hard
   rail: lap must be > 2025 pole + 0.8 s (a 2026 car can NEVER beat 2025 — non-negotiable).
Proof = **leave-one-out backtest**: fit the transfer without a track, predict it blind, score
vs its real 2026 lap. v2 scores: rail 4/4, trace corr 4/4 (0.94–0.985), FP1-ref tracks 0 fails.
Full evidence + per-corner tables: `cache/backtest_report.md`. Design rationale:
`docs/2026-07-15-prefp1-universal-calibration-design.md` (+ same-date plan file).

## File map (everything lives in "OPTIMAL LAP SCRIPTS/")
- `cache/_track_registry.py` — THE single source of truth: TRACKS dict (per track: outline
  path, csv25/csv26 refs, kind26 Q|FP1, altitude_m, length_m) + shared numerics
  (rho_isa, load_ref, corner_minima, pair_minima, align_pair, pava_nonincreasing).
  Unit tests: `tests/test_transfer.py` (6 tests).
- `cache/_transfer_2026.py [--exclude SLUG]` → `cache/transfer_2026.json`. Q pairs anchor the
  fit; FP1 pairs are validation-only (non-push). Guard: major-corner (prom ≥15) pairing
  rate < 0.8 aborts = layout change / bad ref.
- `cache/_predict_track.py --track SLUG` → `cache/predicted_<slug>.json` (corner targets via
  r(v), vtop target, lap band, rho, knob seeds). Sanity: ref distance vs official ±2%/5%,
  2024 fallback.
- `cache/_autofit_2026.py --track SLUG` → `cache/autofit_<slug>.json` + fitted sim csv/raceline
  in cache/. ≤6 sims. Window-min corner scoring (±1.5% lap fraction), trimmed-median objective,
  CL may only DECREASE from a rail-violating state, reports the BEST rail-passing state.
  Sim sanity-failure = boundary → halves the step back. rc 0 = completed, 2 = nothing ran.
- `cache/_gate_2026.py <csv> <t25_pole_s> --targets cache/predicted_<slug>.json` — 9 checks:
  predicted lap band + top ±6 + corner median ±6, plus the cross-track signature rails
  (gain/drop medians+peaks, superclip shape, T > t25+0.8). Without --targets = legacy bands.
- `cache/_backtest_2026.py [--tracks a,b,c]` — the LOO proof; ALSO the regression suite: rerun
  it after ANY physics/line/transfer change and append to `cache/backtest_report.md`.
- `sim_2026_lap.py --outline X --raceline-out Y --csv-out Z --reference-csv <2025ref> --inset 0
  --cda A --cl B --rho C` — the 2026 physics. Defaults = last hardcoded constants, so old
  batches still work. The 2026 CAR physics (deploy taper 200/270/300 km/h, corner-aero braking,
  trail-brake, MU_LONG 1.35 / MU_DRIVE 1.00, win_s 0.45, superclip 0.96) is FROZEN — per-track
  changes go through the three CLI knobs ONLY, never code edits.
  Line smoothing is curvature-ADAPTIVE (preserves apexes R<80 m, smooths R>250 m fully;
  env LINE_WOBBLE_ADAPTIVE=0 reverts to the old uniform gaussian, LINE_WOBBLE_SIG still works).
- `fetch_openf1_lap.py --year Y --country C [--circuit X] --session "Qualifying" --out csv` —
  THE data fetcher (OpenF1 covers 2023+; works for history AND fresh sessions once they END;
  live session = 401). `--circuit` disambiguates multi-GP countries (US: Miami/Austin/Las Vegas).
  ⚠️ FastF1 (`fetch_fastest_lap.py`) livetiming is BROKEN since ~2026-07-10 — don't burn time on it.
- `svg_to_outline.py --svg F --out J --track-length L --road-width W --min-corner-radius 9.0`
  + verify with `cache/_verify_outline.py <outline.json>` (pinch check + PNG).
- `raceline_video.py --outline .. --raceline .. --telemetry-csv .. --track-name ".." --zoom N
  --out X.mp4` — render. HONEST sim lap time on the HUD; `--display-laptime` exists but is
  a last resort the user must ask for.
- `make_spa_2026_lap.bat` — the reference per-track pipeline (stages 0-5); copy+adapt per track.
- Diagnostics: `cache/_overlay_speed.py sim.csv real.csv <sim_lap> <real_lap> <label>` (shape
  overlay; title/filename hardcoded "catalunya" — cosmetic bug), `cache/_rate_vs_speed.py
  "csv::label" ...` (a(v) binned by speed — the curve to match, not just medians).

## Per-weekend recipe (returning track, ~1h mostly compute)
1. Get the DENSEST circuit SVG you can (Inkscape/Wikimedia style, thousands of path points —
   Spa's 21 KB/4136-pt SVG scored far better than hand-drawn 2 KB ones; SVG quality is the #1
   accuracy lever). Drop in repo root.
2. Add the registry entry (outline path under F1_Pipeline_Assets/tracks/, csv25 name, csv26=None,
   altitude_m, official length_m). Fetch the 2025 Q ref via fetch_openf1_lap.py; verify the
   printed lap time vs the known 2025 pole and distance ≈ official ±2%.
3. svg_to_outline (+_verify_outline, eyeball the PNG) → predict → autofit → gate → video
   (mirror make_spa_2026_lap.bat; road-width ~13-15, min-corner-radius 9.0, zoom ~21-23).
4. SHIP CHECKS (all three, every time — non-negotiable, this is what "verified" means):
   gate 9/9; `_overlay_speed.py` vs the 2025 ref (corr ≥ 0.95, eyeball dips corner-by-corner:
   2026 must be SLOWER mid-corner, can be HIGHER on straights); `_rate_vs_speed.py` vs 2-3 real
   2026 Q csvs (gain must peak mid-speed and collapse >300; drop must grow with speed).
   Record results + watch items in cache/backtest_report.md. Extract 2-3 video frames (ffmpeg)
   and look at them (car on track, HUD sane).
5. AFTER the weekend: fetch the track's real 2026 Q, add as csv26/kind26="Q" in the registry
   → the transfer gets one more pair and the whole system improves for the remaining calendar.

## Invariants (the ⛔ lessons — violating these is THE recurring historical failure)
- **2026 is ALWAYS slower than the 2025 pole** (+0.8 s hard rail, expect +1..+3 s). A faster
  lap means the LINE or a fit broke — never ship it, never "fix" it with more grip.
- **Match the whole a(v) curve and the medians, not just peaks.** MGU-K deploy is a regs power
  cap (350 kW@200 → 0@300), not conservatism to be beaten.
- **CL cannot fix geometry.** Per-corner errors of ±30-40 in BOTH directions at fixed CL = SVG
  fidelity problem (get a denser SVG), not a physics knob problem.
- Check every ref CSV's provenance: fetch date vs session date (a "q" file fetched before quali
  IS FP1 — this poisoned Catalunya once), integrated distance vs official length, lap vs known pole.
- Monaco is isolated (`sim_monaco_2026_lap.py`) — none of this applies there.

## Elevation capability (added 2026-07-16, Spa first)
Real altitude comes from the OpenF1 `location` z-channel (true m ASL x10; Spa verified:
365.5-467.6 m, span 102.0 vs documented ~102, closure +0.4 m). Three artifacts per track:
- `cache/_fetch_elevation.py --track X` → `F1_Pipeline_Assets/tracks/<x>_elevation.json`
  (dist_frac/elev_m grid + raceline stations lifted to [x,y,z] — Blender-ready 3D model).
  Validation gates + landmark PNG (`cache/elevation_<x>.png`). Needs the raceline json to
  exist first. Domain = distance from S/F in driving direction (same as sim csv).
- `cache/_build_3d_viewer.py --track X --name "..."` → `<x>_elevation_3d.html`: interactive
  3D ribbon (altitude color ramp, drop curtain, animated optimal-lap car, follow-cam,
  vertical-exaggeration slider). Fully self-contained: three.js r160 vendored in `vendor/`
  and embedded as data-URL modules — works offline, double-click to open. Includes an
  interval fallback for RAF-throttled webviews. New tracks: add the slug to SIM_CSV in
  the builder.
- `raceline_video.py --elevation-json <json>`: **in-video 3D elevation flyover** in the
  bottom third (the silhouette panel was replaced 2026-07-17 on user direction): software-
  projected 3D track, sequential-orange altitude ramp, SOLID walls both sides, no background;
  drone camera = lagged follow (EMA 2.5 s) + continuous rotation (1.25 rev/lap) at 33°;
  the 3D car and the 2D dot share the same telemetry sample per frame (EL3D_* constants).
  Wired into make_spa_2026_lap.bat stage 5.

## State right now / next actions
- **SHIPPED: Spa** `belgian_grand_prix_2026_optimal_lap.mp4` — 1:41.91 (2025 pole 1:40.562
  +1.35 s), top 343, cda 0.737 / cl 5.355 / rho 1.1764, gate 9/9, overlay corr 0.978 vs 2025,
  a(v) in family. Committed through `412e312`.
- **Fri 2026-07-17, after FP1 ENDS (~1h after start): VERIFICATION ONLY — do not recalibrate.**
  `python fetch_openf1_lap.py --year 2026 --country Belgium --session "Practice 1" --out F1_Pipeline_Assets/exports/reference_2026_spa_fp1.csv`
  then `_overlay_speed.py` sim vs it. Expect FP1 ≈ sim +2..3.5 s (FP1 runs ~+3.2% over its Q),
  corr ≥ 0.95. Watch items (in backtest_report.md §Spa): Eau Rouge flat vs lift; gain@220-260;
  drop@140-180. Write the verdict into the report. If something is BADLY off (>1.5 s the wrong
  way, corr < 0.9), diagnose layer-by-layer (geometry → targets → fit), don't twiddle constants.
- **Next track: Hungaroring (weekend of 2026-07-24)** — needs only an SVG + registry entry
  (length 4381 m, altitude ~250 m); then the recipe above. After its quali: add Spa AND Hungary
  2026 Q refs as transfer pairs.
- **Unbuilt tier-2 case:** brand-new circuits (Madring, Sept) have no 2025 lap — spec'd as
  physics-inversion-only fallback, not implemented. Decide when it gets close.

## Residual known limitations (measured, documented — don't re-litigate silently)
- canada backtest lap-band +0.9 s conservative (sim slower than real Q); catalunya vtop −12
  (its real 2026 top is a +13 outlier no LOO fit can see); per-corner worst ±30-40 on
  coarse-SVG sweepers. Accuracy envelope to quote: lap ±~1 s, top ±10, corners ±10-15.
- `tests/test_physics_sim.py::test_forward_pass_clips_when_battery_empty` — pre-existing
  failure, unrelated (since Catalunya bring-up). Everything else: 57 passed.
- Sim ≈ 40 s/run; autofit ≤6 sims; full backtest ~15 min → ALWAYS run_in_background, filter
  output with `grep --line-buffered -E "backtest|autofit|Traceback|Error"` (plain grep buffers
  and eats crashes), and never edit sim_2026_lap.py while sims are running.
- Big artifacts (mp4, >200 KB PNGs) are NOT committed by this pipeline's convention; the
  user's older mp4s being tracked predates it. User's unrelated uncommitted files (blends,
  formulyticsScript.py etc.) — leave untouched.

## Session protocol reminder (user's global rule)
One task per session; bulk output stays in files; update THIS file + auto-memory
(`prefp1-transfer-calibration` has the method's history; `fp1-calibration-playbook` has the
frozen car physics) before the user /clears.
