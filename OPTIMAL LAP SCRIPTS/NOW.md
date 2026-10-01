# >>> CURRENT STATE (2026-09-30) - read this block first <<<
- The Baku 2026 work (09-24/25) was done by a GPT agent and is REJECTED by the user. Never use it.
  Its engine edits are quarantined in _quarantine_gpt_baku_2026-09-25/ (copies; never delete anything).
- Engine restored to committed HEAD + banking physics; proven bit-identical on Zandvoort.
  The Madring section below was a Codex-started run finished via cache/_madring_* scripts only.
- THIS WEEK: "Bahrain GP" is held at SEPANG (OpenF1: country Bahrain, circuit "Kuala Lumpur", FP1 2026-10-02).
  Sepang shipped pre-FP1 via the NO-REFERENCE method: see cache/sepang_2026_noref.md + make_sepang_2026_lap.bat.
  Video malaysian_grand_prix_2026_optimal_lap.mp4, lap 1:31.772 (T1 late-apex FITTED edit), zoom 18 (user: 0.6x of 30), no elevation (user OK).
  Sepang T1: late apex pulled onto the kerb (cache/_sepang_t1_apex.py, sim --raceline-in), 1:31.772.
  User tested "earlier inside" vs 2017 onboard; physics says +0.28..0.50 s slower -> KEEP current line.
- BAHRAIN (Sakhir) SHIPPED 2026-10-01: bahrain_grand_prix_2026_optimal_lap.mp4, lap 1:32.186 (+2.34 s vs
  2025 pole), zoom 18 + 3D elevation flyover (2025 Q z, span 16.4 m). make_bahrain_2026_lap.bat reproduces it.
  SVG = ..._Grand_Prix_Layout_with_DRS.svg; registry inset 1.2 (T10 drawn as a sharp V). Gate 8/9: GAIN
  median 30.5 > fixed 28 cap, justified by sim/real ratio 1.44 inside shipped 1.26-1.52. Full record:
  cache/bahrain_2026.md. New tools: cache/_corner_compare.py (SVG/geometry per-corner test),
  cache/_outline_local_smooth.py (one-corner road rebuild; tested, not used for Bahrain).
- NEXT: Sepang FP1 (Fri 2026-10-02) verification: fetch --country Bahrain --circuit "Kuala Lumpur".
  Deferred: line optimiser is min-curvature not min-time at hairpin combos (Sepang T1) - engine-wide fix
  needs the full backtest.

# NOW.md — operating manual for the pre-FP1 2026 optimal-lap pipeline
(last update 2026-08-20: Zandvoort shipped pre-FP1 + banking capability. Read fully before touching anything.)

## Active session update — 2026-09-11: Madring
- **FP1 elevation preview VERIFIED COMPLETE:** `madring_2026_FP1_ELEVATION_PREVIEW.mp4`,
  exit0; 1080x1920,30fps,2823frames; sampled frames and final frame decoded and inspected.
  Preferred interactive deliverable: `madring_fp1_elevation_3d_overview.html` (browser-verified).
  Actual Russell FP1 replay94.077s; **not the final simulated optimal lap**. Next calibration
  evidence: baseline speed corr0.9483, with local deficits around44%,61%,79% of lap; do not
  raise CL globally to hide them. Full current evidence in the report linked below.
- **LATEST: user now authorizes Madring practice data and wants the 3D ELEVATION flyover,
  not the banking panel.** This supersedes the original pre-session-only scope for this track.
- FP1 obtained from Formula 1's official archive via FastF1 (`backend="f1timing"`, caching
  disabled with `Cache.set_disabled()`): Russell lap 20, 94.077 s; reference CSV
  `F1_Pipeline_Assets/exports/reference_2026_madring_fp1.csv`. OpenF1 still gave live-lockout 401;
  FP2 had no published archive path at the latest check. Do not repeat the old blanket claim
  that FastF1 is unusable: this current FP1 archive extraction succeeded.
- Read `cache/madring_fp1_elevation_2026-09-11.md` for current data/provenance, aligned S/F,
  artifacts and next steps. FP1 XY registers well (9.18 m RMS); origin is station2590/2665.
- Measured relative elevation: raw span24.6 m, smoothed23.98 m. Absolute datum is unverified;
  label height ABOVE LOW POINT, not ASL. Interactive overview is
  `madring_fp1_elevation_3d_overview.html`; video `madring_2026_FP1_ELEVATION_PREVIEW.mp4`
  is an actual-FP1 reference preview, not a calibrated optimal lap. Check its render log
  and the current report's final verification before treating the video as completed.
- **Madring is now active. Monza is set aside.** Older Monza state below is retained as history.
- **User constraint: never delete anything.** Preserve all existing files and unrelated work.
- Read `cache/madring_bringup_2026-09-11.md` for full SVG provenance, verification, and next steps.
- User SVG `Madring_(2026).svg` passes density screening (379 segments / 22 turns). Provisional
  outline `F1_Pipeline_Assets/tracks/madring_grand_prix_outline_provisional.json` built at 5414 m
  using the current F1 guide; measured perimeter 5408.9 m. Simple, non-crossing edges and valid
  corridor verified with Shapely; provisional 12 m base width narrows locally to 9.69 m.
- Verified default-knob, UNBANKED geometry probe completed exit 0: 97.537 s, v 70–312 km/h,
  sanity passed; all 2665 raceline points on track. This is **not a calibrated prediction**.
  Outputs/log: `cache/madring_geometry_verified*`; previews `_verify_madring_provisional.png`
  and `_ontrack_madring_provisional.png`. Original interrupted probe files also retained.
- Next: verify final layout/direction/real S/F, resolve widths, map La Monumental banking,
  set altitude/rho, and implement/validate a no-2025-reference calibration method. Existing
  predictor/autofit/gate depend on a 2025 lap; the proposed Madring fallback is not built.
- **Madring banking is 24% slope (~13.5 degrees), not 24 degrees.** The Zandvoort-only banking
  statement below is historical. Existing model angles are EFFECTIVE, so physical angle
  must not silently be treated as calibrated. Current probe has no banking or elevation.
- **No-ref simulation trap:** explicitly pass a confirmed nonexistent Madring reference path;
  omission defaults to Canada telemetry. Current S/F remains an unverified straight proxy.
- No pipeline code or shared calibration files changed during this SVG bring-up.

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
   corner-speed ratio r(v25) (monotone; 7-pair fit 2026-09-04: 0.967 at 80 km/h → 0.926 at
   200+), top-speed delta (mean +2.4 km/h), lap-delta band (mean +2.99% sd 1.29);
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
- `cache/_svg_density.py <svg> --track-length M --turns N` (or `--table`) — SCREEN a
  candidate SVG before building on it. Verdict runs on **Bezier segments per TURN**, not
  per km: seg/km penalises straight-heavy circuits (Monza is 74% straight, so a faithful
  Monza scores badly on it) while corners are the actual failure mode. Anchors from this
  repo's own outcomes: Catalunya-2021 12.7, Spa 5.6, Canada 5.2, Zandvoort 4.4, Hungary
  3.7 = every clean ship; Catalunya-2023 2.6 needed two global car-constant fixes;
  Silverstone 1.9 was the weakest ship (corr 0.945). GOOD >=3.5, MARGINAL >=2.4.
  It RANKS, it does not decide — confirm a marginal candidate with the geometry probe
  in recipe step 1.
- `cache/_fetch_when_open.py [--minutes N --every S]` — waits out OpenF1's live-session
  lockout, then pulls the queued refs and prints lap time + integrated distance for each.
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
   accuracy lever). Drop in repo root, then SCREEN it: `python cache/_svg_density.py <svg>
   --track-length M --turns N` — want **>=3.5 Bezier segments/TURN**, and a stroked
   `fill:none` centreline rather than a filled road ribbon. Byte size is a poor proxy both
   ways (Canada's 2.7 KB SVG is 16.7 seg/km; Monza's 10.2 KB one is 4.7).
   GEOMETRY PROBE for a marginal candidate, no network needed: build the outline, list the
   curvature-peak radii in track order, and run `sim_2026_lap.py` with DEFAULT knobs
   (`--reference-csv` is optional) — a chicane circuit must show PAIRED tight radii, and the
   default-knob lap / min speed / tightest line radius rank two candidates decisively.
   Do all of this BEFORE predict/autofit, not after.
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
- **A one-directional corner-speed deficit is NOT automatically a CL problem.** Check the
  per-corner spread first: if a FEW ADJACENT corners carry the whole median error while the
  rest are fine, it is localized geometry/physics, and raising CL just inflates the healthy
  corners to hide it. At Zandvoort 5 of 8 corners were within ±7.4 while three adjacent early
  ones were −20/−29/−50. Also remember the backward brake pass PROPAGATES a wrong apex
  upstream: fixing Hugenholtz alone moved Gerlach +16 km/h with no change of its own.

## Banking (added 2026-08-20, Zandvoort only)
Zandvoort is the only meaningfully banked track on the calendar. Banking is **TRACK geometry**,
so it lives on the outline (optional per-station `banking_deg`), NOT in the frozen car physics.
- `cache/_apply_banking.py --track X [--fit|--clear]` — writes the channel from the registry's
  `banking=[...]` spec (raised-cosine bumps). `--fit` solves the effective angle from the
  corner's predicted apex target and prints the registry block to paste back.
- Lateral limit: `v² = g(μcosθ+sinθ) / [|κ|(cosθ−μsinθ) − μρCl/2m]`, which at θ=0 reduces
  EXACTLY to the flat form ⇒ **tracks with no channel are bit-identical** (proven by
  exact-equality tests). `tests/test_banking.py`, 27 tests.
- ⛔ **The angles are EFFECTIVE, not surveyed.** MU_LAT 1.95 is aero-inclusive and its friction
  angle arctan(1/μ) is only ~27°, so the surveyed ~19° saturates the closed form (corner stops
  binding, 6.85× gain). Fitted: Hugenholtz **8.62°**, Luyendyk **0.45°**.
- ⛔ **Banked corners become FITTED, not predicted** — they stop being independent validation
  stations. Always report the unbanked-only corner median as the honest check (Zandvoort:
  unbanked-6 −5.1 vs all-8 −5.5, so the gate is not being carried by the fitted corners).
- ⛔ The channel is indexed by **S/F-referenced ARC fraction and built AFTER the S/F roll**
  (`banking_channel_for_arc`). Building it pre-roll off station-index fractions slides the bump
  a whole sf_idx upstream (~96 m) onto the straight, where it silently does nothing.

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
  projected 3D track, sequential-orange altitude ramp, SOLID walls both sides, no background.
  Camera (final, 2026-07-17): orbit azimuth **locked to the car's own bearing** around the
  track center — rotates WITH the car, at the car's angular speed, car always on the near
  side (no watching the empty far side); constant distance = constant scale (no zoom wander),
  15° skyline angle, EL3D_EXAG 2.6 so highs/lows are the star. HUD compacted (mode 1050 /
  speed 1112 / lap 1240 / wm 1288); 3D band centered in rows 1310-1670 = above the platform-UI
  cut zone (whole-lap frame scan clean except a 9px graze at t=0). 3D car and 2D dot share the
  same telemetry sample per frame. All knobs are `EL3D_*` constants at the top of the file
  (YAW_OFFSET adds a fixed azimuth bias; FOCAL/CY_FRAC size+place the object; ELEV_ANGLE/EXAG
  shape the skyline). Wired into make_spa_2026_lap.bat stage 5.
- ⛔ `--banking-json` **REPLACES** the 3D elevation band with the Zandvoort banking
  cross-section panel. Elevation is the default look; pass banking ONLY on a genuinely
  banked track. Monza and every other flat circuit: `--elevation-json` only.
- **2D main-view zoom**: `raceline_video.py --zoom N` scales the road ribbon (higher = wider
  road, car-followed). Spa ships at **30** (walked up 22→26→30 on user request for a wider
  road). It does NOT affect the 3D band (separate EL3D_FOCAL).

## State right now / next actions
- **IN PROGRESS: Monza (Italian GP, weekend of 2026-09-04)** — bring-up started 2026-09-04.
  Registry entry `monza` added (italian_grand_prix_*, 5793 m verified, altitude 162 m
  PLACEHOLDER to re-pin from the z-channel, `circuit="Monza"`). `make_monza_2026_lap.bat`
  written (stages 0-6, **elevation flyover, no banking** — user's explicit call).
  **SVG settled: `Monza_track_map.svg`** (10229 B, 27 cubic segments, stroked centreline,
  2.5 seg/turn = MARGINAL/Catalunya-2023 level). A first candidate at 2.2 seg/turn was
  rejected on the geometry probe. Outline built + `_verify_outline` clean: perimeter 5792.1 m
  vs 5793 official, width med 14.0 / min 11.31, no pinch. Default-knob geometry probe:
  lap 78.30 s, v [87, 326], tightest line radius 21.4 m, radii show the chicane pairs
  (23/23, 17/20, 10/15). Still waiting on: (a) OpenF1 — see lockout below; (b) POLE25 in the
  batch is deliberately EMPTY until the 2025 ref is fetched (the run aborts rather than guess
  the gate rail).
- ⛔ **Monza's autofit ABORTS on the stock seed — use a low-downforce seed.** With the
  predicted seed (cda0 0.75 / cl0 4.6) iteration 0 sanity-fails
  (`DROP rate median 65.4 outside [28,60]`) and `_autofit_2026.py` gives up before exploring
  anything (`ABORT: initial knobs already unphysical`). The fix is a per-track SEED, not a
  physics edit and NOT a widened band: copy `predicted_monza.json`, lower `cda0`/`cl0`, and
  pass it via `--targets`.
- **The band was NOT too narrow — that guess was wrong, and the audit is how we know.**
  New tool `cache/_drop_rate_audit.py "csv::label" ...` reproduces assert_sanity's exact
  statistic (30 fps resample, 0.5 s window, median |rate| over braking samples) on ANY csv,
  so a sim value can be judged against REAL traces instead of argued about. Measured
  2026-09-04: REAL Monza 2025 Q **41.8** — mid-pack in a real spread of 29.3-43.3 (Zandvoort
  32.9, China 29.3, Miami 35.0, Hungary 37.2, Spa 41.7, Canada 43.3). Only Monza's drop_p90
  (135.8) leads the calendar, i.e. the most violent PEAK braking but an ordinary median.
  Shipped sims run ~+8-9 over their own real trace (Zandvoort sim 42.0 vs real 32.9, Spa
  49.8 vs 41.7), so a healthy Monza sim should land near **50**, not 66. Braking is
  aero-assisted and the force scales with v²·CL, and Monza carries the calendar's highest
  entry speeds, so a generic wing over-brakes THERE specifically — the same seed that also
  capped the sim at 332 km/h against a real 348.
- ⛔ **OpenF1 401s EVERYTHING while any F1 session is live** — historical endpoints included
  ("Live F1 session in progress... restricted to authenticated users until the session ends").
  On a race Friday the whole fetch layer is down, not just the live session. `cache/
  _fetch_when_open.py [--minutes N --every S]` polls and then pulls 2025 Monza Q + 2026
  Zandvoort Q, printing lap time + integrated distance vs official for provenance.
- **General fix (helps every multi-GP country):** `cache/_fetch_elevation.py` took
  `sessions[0]` with no circuit filter — for Italy that is IMOLA, not Monza. It now honours
  the registry's `circuit` key / a `--circuit` flag and aborts on an ambiguous set.
- **Watch item for Monza's 3D band:** Monza is nearly flat (a few m of span vs Spa's 102).
  EL3D_EXAG 2.6 was tuned on Spa; expect to raise it for Monza or the flyover reads as a
  pancake. Decide after `_fetch_elevation.py` prints the real span.
- **Still pending from the Zandvoort weekend:** add its 2026 Q as csv26/kind26="Q" and refit
  the transfer (6 -> 7 pairs) BEFORE Monza's predict/autofit. The fetch is queued in
  `_fetch_when_open.py`; the registry edit + `_transfer_2026.py` rerun are not done yet.
- **SHIPPED: Zandvoort** `dutch_grand_prix_2026_optimal_lap.mp4` — **1:11.31** (2025 pole
  1:08.662 +2.64 s = +3.95%), top 331, cda 0.563 / cl 4.968 / rho 1.2185, **gate 9/9**,
  overlay corr 0.967 vs 2025, a(v) in family. First track to use BANKING (see below).
  Full evidence + residuals + FP1 watch items: `cache/backtest_report.md` §Zandvoort.
- **Fri 2026-08-21, after FP1 ENDS: VERIFICATION ONLY — do not recalibrate.**
  `python fetch_openf1_lap.py --year 2026 --country Netherlands --session "Practice 1" --out F1_Pipeline_Assets/exports/reference_2026_zandvoort_fp1.csv`
  then `_overlay_speed.py` sim vs it. Expect FP1 ≈ sim +2..3.5 s, corr ≥ 0.95. The three watch
  items are in the report; **Tarzan (frac 0.077, sim −20.7 vs target) is the #1 question** —
  it decides whether the SVG or the 2025-derived target is wrong.
- **Transfer now has 7 Q pairs** (Zandvoort 2026 Q added 2026-09-04): canada, catalunya,
  miami, china, spa, hungary, zandvoort; austria + silverstone stay FP1 validation-only.
  lap_delta +2.83%→**+2.99%** sd 1.33→**1.29**; vtop delta mean **+2.4 km/h**; r(v25) high-speed
  end **0.904→0.926** (2026 corner speeds are closer to 2025 than the 6-pair fit thought —
  matters most on fast circuits). All pairing rates ≥0.86, no abort.
- ✅ **THE 6-PAIR CORRECTION IS PROVEN.** Zandvoort was the first ship fitted with it, and its
  real 2026 quali (fetched 2026-09-04, lap_duration **71.163 s**, 4248 m integrated vs 4259
  official −0.3%) lands **+0.15 s from our pre-FP1 sim of 71.31 s — a 0.2% error, the best
  pre-FP1 result to date.** Prior ships under the optimistic 4-pair fit both came in FAST:
  Spa 1:41.91 vs real 1:44.361 (−2.46 s), Hungary 1:16.36 vs real 1:17.207 (−0.85 s). The
  "watch that the autofit doesn't land on the fast edge" concern is now evidence-backed as
  ADDRESSED, not merely suspected. Zandvoort's own pair: vtop 326→315 (−10.5), lap +3.97%.
- **Hungary shipped 2026-07-23** (`hungarian_grand_prix_2026_optimal_lap.mp4`, cda 0.614 /
  cl 4.789 / rho 1.1959, lap 76.355) but was never written up here. Its Spa-FP1 verification
  step (2026-07-17) was also never run — that window has passed; the 2026 Q refs now serve
  the same purpose.
- **Next: after Zandvoort quali (Sat 2026-08-22)** add its 2026 Q as csv26/kind26="Q" →
  7 pairs. Then the next calendar track needs only an SVG + registry entry.
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
