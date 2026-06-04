# Canada 2026 Revamp — Session Resume

**Last updated:** 2026-05-19, second session — Tasks 2-followup through 9c complete.
**Branch:** `f1hotlap_lohith_v2`
**Spec:** `docs/superpowers/specs/2026-05-19-canada-2026-revamp-design.md`
**Plan:** `docs/superpowers/plans/2026-05-19-canada-2026-revamp.md` (21 tasks)

## Where we are

Executing under `superpowers:subagent-driven-development`: fresh implementer per task,
then spec + code-quality review. **Tasks 1–9c complete (commit `e8d0201`).**
Next up: **Task 10** (vehicle constants + grip/aero helpers).

## Commits this session (most recent first)

```
e8d0201 sim_2026_lap: resolve calibration JSON path relative to __file__
b2165ac sim_2026_lap: widen calibration window to 0.40s (de-contaminates P/m)
47f8542 sim_2026_lap: window speed differentiation in calibration (FastF1 quantization fix)
80a1c4c sim_2026_lap: calibrate physics constants from 2025 Canada + 2026 China telemetry
26bf3f3 data: reference telemetry — 2025 Canada Q + 2026 China Q
4e28edd sim_2026_lap: IQP seed + jerk-constrained QP refinement (driver-physical raceline)
b5a3e8c sim_2026_lap: port jerk-constrained min-curv QP from addon (verbatim)
62c3f27 svg_to_outline: enforce CCW orientation, exit 4 on write failure
ab30b74 svg_to_outline: end-to-end SVG -> outline JSON for Canada
7032d87 svg_to_outline: curvature, hairpin narrowing, start/finish detection
af7a4c8 svg_to_outline: constant-width edge generation via left-normal offset
f0bea02 svg_to_outline: document smooth_s units (review follow-up)
c1486fd svg_to_outline: geometry helpers (flip, scale, recentre, resample)
d9eeb6a svg_to_outline: cubic bezier sampling and command expansion
efd9281 svg_to_outline: reject number after Z (was infinite loop)
```

## Task list (21 tasks)

| # | Task | Status |
|---|---|---|
| 1 | pytest scaffolding | done (`36f1894`, prior session) |
| 2 | SVG path token parser | done (`7a8c084`/`71b773d`/`efd9281`) |
| 3 | cubic Bezier sampling | done (`d9eeb6a`) |
| 4 | geometry helpers (flip, scale, recentre, resample) | done (`c1486fd`/`f0bea02`) |
| 5 | outer/inner edge generation | done (`af7a4c8`) |
| 6 | hairpin narrowing + S/F detection | done (`7032d87`) |
| 7 | svg_to_outline main entry point | done (`ab30b74`/`62c3f27`) |
| 8 | sim_2026_lap skeleton + port jerk-constrained QP | done (`b5a3e8c`) |
| 9 | build_raceline (IQP seed + jerk-constrained refinement) | done (`4e28edd`) |
| 9b | fetch 2025 Canada Q + 2026 China Q telemetry | done (`26bf3f3`) |
| 9c | calibrate physics from telemetry | done (`80a1c4c`/`47f8542`/`b2165ac`/`e8d0201`) |
| 10 | vehicle constants + grip/aero helpers | **NEXT** |
| 11 | backward-pass `v_brake` | pending |
| 12 | forward-pass energy-aware velocity profile (5 modes) | pending |
| 13 | closure iteration + CSV write | pending |
| 14 | post-sim sanity assertions | pending |
| 15 | raceline_video `--raceline` arg | pending |
| 16 | extend CSV loader for `soc_pct` / `mode` | pending |
| 17 | battery bar + mode label HUD | pending |
| 18 | `make_canada_2026_lap.bat` | pending |
| 19 | final regression check | pending |

## Carry-forward notes for remaining tasks

- **Task 10 — smooth κ before `v_grip`.** `canadian_grand_prix_raceline.json`'s `kappa`
  array is a noisy 3-point estimate; it has a ~2-station spike to ~0.094 at the hairpin
  apex (truer value via 800-station Menger ≈ 0.066). Task 10 should apply a light κ
  smoothing (5-pt median / Savitzky-Golay) before deriving `v_grip`, or a single-station
  spike will cause a spurious `v_grip` dip.
- **quadprog version skew (benign so far).** `trajectory-planning-helpers 0.79` pins
  `quadprog==0.1.7`; `0.1.13` is installed. Task 9's full IQP+QP run worked fine under
  the skew — no downgrade needed. Flag only if a later task hits a runtime error in tph.
- **Generated artifacts are committed:** `canadian_grand_prix_outline.json`,
  `canadian_grand_prix_raceline.json`, `vehicle_calibration.json` are checked in so
  later tasks develop without re-running upstream stages. The `.bat` (Task 18)
  regenerates them.

## Conventions (unchanged)

- Commit messages: imperative, lowercase. **NEVER `Co-Authored-By: Claude`** (memory `feedback_no_claude_coauthor`).
- Do NOT edit anything under `launch_control_auto_car_rig/` or the addon
  `f1_track_visualizer_addonLastLastLasttry5.py` — they are the validated source, read-only
  (memory `feedback_no_addon_edits_for_exports`).
- Pre-existing dirty working tree: many M-status files unrelated to this work.
  **Always `git add <explicit files>`** named in the task — never `git add -A`.
- Project Python: `C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe`. pytest installed; 24 tests currently pass.

## How to resume after a restart

1. New Claude Code session in this directory.
2. "Resume the Canada 2026 revamp execution. Read `docs/superpowers/progress/2026-05-19-canada-2026-revamp-resume.md`, then continue from Task 10 via `superpowers:subagent-driven-development`."
3. The plan file is self-contained — every task has full code blocks, commands, expected outputs, and commit messages.
