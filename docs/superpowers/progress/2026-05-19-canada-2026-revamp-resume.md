# Canada 2026 Revamp — Session Resume

**Last updated:** 2026-05-19 mid-session, user paused for system memory cleanup.
**Branch:** `f1hotlap_lohith_v2`
**Spec:** `docs/superpowers/specs/2026-05-19-canada-2026-revamp-design.md`
**Plan:** `docs/superpowers/plans/2026-05-19-canada-2026-revamp.md` (21 tasks)

## Where we stopped

Mid-execution under `superpowers:subagent-driven-development`. Implementer + spec reviewer + code-quality reviewer dispatched per task. Two tasks committed, one open follow-up.

## Commits on this branch since start of session

```
71b773d svg_to_outline: tighten d-attribute regex (avoid collision with id=)
7a8c084 svg_to_outline: SVG path d-attribute parser with tests
36f1894 tests: pytest scaffolding for canada-2026 work
```

(Plus the design + plan docs were written and committed earlier in the session if you committed them; if not, they're tracked under `docs/superpowers/{specs,plans}/` as uncommitted files — check with `git status -- docs/`.)

## Open follow-up before resuming Task 3

Code-quality reviewer found a real bug in `svg_to_outline.parse_svg_path_d`:

**Bug:** If an SVG path contains a number after `Z` (e.g., `"M 0,0 Z 20,20"`), the parser enters an infinite loop and eventually OOMs. The Canada SVG doesn't trigger this in practice, but the fix is a 2-line change and should be done before we move on.

**Fix instructions** (single commit on top of `71b773d`):

1. In `svg_to_outline.py`, inside `parse_svg_path_d`'s implicit-repeat else-branch, add a check **before** the `if last_cmd is None` check:

```python
        if last_cmd is None:
            raise ValueError(f"Number {tok!r} with no preceding command")
        if last_cmd in ("Z", "z"):
            raise ValueError(f"Number {tok!r} after Z is invalid SVG (Z must be followed by M)")
```

2. Add a regression test to `tests/test_svg_parser.py`:

```python
def test_number_after_z_raises():
    with pytest.raises(ValueError, match="after Z"):
        parse_svg_path_d("M 0,0 Z 20,20")
```

3. Run `pytest tests/test_svg_parser.py -v` — expect **6 passed**.

4. Commit (no co-author trailer):

```
git add svg_to_outline.py tests/test_svg_parser.py
git commit -m "svg_to_outline: reject number after Z (was infinite loop)"
```

Then mark Task 2 truly complete and move to Task 3.

## Task list (21 tasks)

| # | Task | Status |
|---|---|---|
| 1 | pytest scaffolding | ✅ done (`36f1894`) |
| 2 | SVG path token parser | 🟡 done with open fix (see above) |
| 3 | cubic Bezier sampling | pending |
| 4 | geometry helpers (flip, scale, recentre, resample) | pending |
| 5 | outer/inner edge generation | pending |
| 6 | hairpin narrowing + S/F detection | pending |
| 7 | svg_to_outline main entry point | pending |
| 8 | sim_2026_lap skeleton + port jerk-constrained QP from addon | pending |
| 9 | build_raceline (IQP seed + jerk-constrained refinement) | pending |
| 9b | fetch 2025 Canada Q + 2026 China Q telemetry | pending |
| 9c | calibrate physics from telemetry | pending |
| 10 | vehicle constants + grip/aero helpers | pending |
| 11 | backward-pass `v_brake` | pending |
| 12 | forward-pass energy-aware velocity profile (5 modes) | pending |
| 13 | closure iteration + CSV write | pending |
| 14 | post-sim sanity assertions | pending |
| 15 | raceline_video `--raceline` arg | pending |
| 16 | extend CSV loader for `soc_pct` / `mode` | pending |
| 17 | battery bar + mode label HUD | pending |
| 18 | `make_canada_2026_lap.bat` | pending |
| 19 | final regression check | pending |

## Key context to re-load when resuming

**Pre-existing dirty working tree** has many M-status files (`F1_Pipeline_Assets/cars/...`, `launch_control_auto_car_rig/...`, etc.) from prior unrelated work. **Subagents must only `git add <explicit files>`** named in their task — never `git add -A`.

**Conventions:**
- Commit messages: imperative, lowercase. **NEVER `Co-Authored-By: Claude`** (memory `feedback_no_claude_coauthor`).
- Don't edit files under `launch_control_auto_car_rig/` (memory `feedback_no_addon_edits_for_exports`).
- Python: `C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe` is the project Python. `python` and `pytest` should be on PATH.
- pytest is installed.

**Key user feedback memories loaded:**
- `feedback_use_validated_recent_work_as_foundation` — use the addon's min-time operator as the racing-line foundation, not as an option to be skipped.
- `feedback_stop_overcomplicating_simple_requests` — when user says "take X and apply", don't surface every "which library" decision; just install and execute.
- `project_2026_calendar_actual` — Bahrain 2026 race was cancelled (war); only Aus/China/Japan/Miami actually ran. China is the calibration reference (not Bahrain).

## How to resume after restart

1. Open a new Claude Code session in this directory.
2. Tell it: "Resume the Canada 2026 revamp execution. Read `docs/superpowers/progress/2026-05-19-canada-2026-revamp-resume.md`, then continue from the open Task 2 follow-up fix, then move to Task 3."
3. Claude will invoke `superpowers:subagent-driven-development` and dispatch fresh subagents per remaining task using the prompts already in the plan.

The plan file is self-contained — every task has full code blocks, expected commands, expected outputs, and commit messages. No prior context is needed beyond this resume doc + the plan + the spec.
