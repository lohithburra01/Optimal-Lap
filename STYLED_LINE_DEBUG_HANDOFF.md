# F1 Hot Lap — Session Handoff (2026-04-27)

Hand this whole document to the next model. It captures everything from today's session: what was fixed, what's still broken, what's been tried and rejected, and what the user explicitly does not want.

---

## Project context

- **Repo:** `C:\Users\91910\Downloads\cricket\f1_hot_lap` (Windows 11, bash + PowerShell available)
- **Branch:** `f1hotlap_lohith_v2` (main = `main`)
- **Two addons in this repo:**
  1. `f1_track_visualizer_addonLastLastLasttry5.py` (root) — single-file Blender addon. **The user calls this "the main addon" / "the visualizer".** Generates centerline → Q_RACING_LINE → styled racing line; aligns driving paths.
  2. `launch_control_auto_car_rig/launch_control_auto_car_rig/launch_control/` — multi-file extension. F1 Studio panel, multi-car scene generation, telemetry baking, trails, minimap, style export.
- **User's git identity:** lohithburra01. **They do not want `Co-Authored-By: Claude` trailers** (already in `~/.claude/.../memory/feedback_no_claude_coauthor.md`).
- **User's situation (verbatim):** "I started this project and created v1 in 1 day and for 3 months I have just been debugging." They are tired and frustrated. Be terse, concrete, and ship fixes rather than philosophizing.

---

## What was completed and committed-ready in this session

All edits below pass `python -c "import ast; ast.parse(open(<path>).read())"`. None have been git-committed (the user hasn't asked).

### 1. Multi-car perpendicular-paths bug — FIXED

**Symptom:** When 2+ cars were queued and "Generate Scene" was clicked, Car 1's path appeared on the track but Cars 2+ appeared at ~90° to it.

**Root cause:** Timing race in `OBJECT_OT_f1_generate_scene.execute()` (in `launch_control_auto_car_rig/.../operators/f1_pipeline.py`):
- Car 1 is processed inline.
- Cars 2+ are scheduled via `bpy.app.timers` (`first_interval=1.0`) — they load 1s+ later.
- `_apply_saved_alignment` was called **between** the timer registration and execute() returning. It writes to `props.align_offset_x/_y`, `align_rotation`, `align_scale`. Those slider writes fire `_on_alignment_changed` (in `data/f1_properties.py:460`) which iterates `_get_f1_path_curves(scene)` and applies the transform.
- At that moment, only Car 1's curve existed → Car 1 got rotated. Cars 2+ loaded later at identity transform with no further callback firing.
- Bahrain's saved alignment in `F1_Pipeline_Assets/database/tracks.json` has `rotation: -1.529432` rad ≈ −87.6° → "perpendicular" symptom.

**Fix applied:**
- Removed `self._apply_saved_alignment(context, track_id)` call from `execute()` (the old call site after the timer registration).
- Created module-level helper `_apply_saved_alignment_to_scene(scene, track_id)` (currently at `f1_pipeline.py:299`).
- Added a call to it inside `_pipeline_finish()` (~line 334), which runs after the LAST car has loaded — so the slider writes hit every loaded path uniformly.
- Deleted the now-unused `_apply_saved_alignment` method from the operator class.

**Verification user should do tomorrow:**
1. Queue HAM + VER for Bahrain → Generate Scene → both paths sit on the track aligned.
2. Queue 1 driver only → still aligned (single-car path).
3. Queue 2 cars for Australia (`tracks.json` rotation=0) → no regression.

### 2. Dependency-install fixes for the visualizer addon — APPLIED

User's teammate produced `Blender Dependency Fix Report.docx` (extracted text now also at `dep_report.txt`). Five code changes from Section 1 of that report were applied to `f1_track_visualizer_addonLastLastLasttry5.py`:

| # | Function | Change |
|---|----------|--------|
| 1 | `get_modules_path()` | Returns isolated `modules/f1_track_visualizer_deps` instead of shared `modules` (prevents pollution that was breaking `launch_control_auto_car_rig` via stale numpy 2.4.x) |
| 2 | `append_modules_to_sys_path()` | `sys.path.insert(0, …)` (prepend) instead of `.append(…)` so isolated wheels shadow stale ones |
| 3 | `check_dependencies()` | Reordered: `quadprog` before `trajectory_planning_helpers`, pinned to `quadprog>=0.1.12` (avoids transitive dep pulling unpinned latest with no cp311 win_amd64 wheel) |
| 4 | `install_package_to_blender()` | Added `--only-binary=:all: --prefer-binary` flags so pip refuses source builds against Blender's header-less Python |
| 5 | `OBJECT_OT_InstallF1Dependencies.execute()` | Error message now mentions the "Access is denied .pyd → restart Blender" hint |

**Not implemented (per the report's own "not implemented" Section 1.6):** Clean & Reinstall operator, pre-flight wheel check, in-process file lock detection, `--disable-pip-version-check`, ABI guard for numpy.

**Not implemented (Section 2 cosmetic):** wrapping `import numpy` in `launch_control` panels with a clearer error message. The report explicitly says no code changes are needed in `launch_control`.

**One-time machine cleanup still required for already-affected machines** (cannot be solved in code): teammate's PowerShell snippet from Section 2.3 removes stale packages from `…/Blender/4.5/scripts/modules/`. The user knows about this.

### 3. Style JSON export now iterates the lap queue — APPLIED

**Symptom:** User had 2 drivers queued, clicked the "Export Driver Style (JSON)" button, only got 1 JSON. The button was reading only `props.sel_driver` (the dropdown selection), ignoring the queue.

**Fix applied** in `launch_control_auto_car_rig/.../operators/f1_pipeline.py`:
- Refactored `OBJECT_OT_ExportDriverStyle` to:
  - Iterate `scene.f1_lap_queue` if non-empty, writing one JSON per queued driver.
  - Fall back to single-driver mode (using `props.sel_*`) if queue is empty.
- Extracted `_extract_and_write_style_for_driver(year_str, race, session, driver, q_seg, is_testing, test_number, test_session_arg, base_dir)` — reusable per-driver helper.
- Extracted `_resolve_style_output_dir()` — uses `<db.root>/style_params/` with tempdir fallback.
- FastF1 cache enabled once per click, not per driver.
- Q-segment for queued items uses `props.sel_q_segment` as a global default (queue items don't carry per-driver Q1/Q2/Q3 selection).

---

## The UNSOLVED problem — styled racing line looks bad at corners

This is what the user was angry about at the end of the session. **Do not start tomorrow by suggesting fixes that were already rejected.** Re-read this section carefully.

### What the user wants

- Q_RACING_LINE (the IQP min-curvature line) is good. The user calls it "perfect". **Do not modify the Q_RACING_LINE generator.**
- The "styled racing line" should be a **synthetic, visibly-different racing line** derived from Q_RACING_LINE + style sliders / per-driver style JSON.
- It should look like a *proper racing line* (smooth, not pinned to the kerb, not wobbly).
- The user's word: it "fucks up at corners… it's not a proper racing line".

### What the user has explicitly REJECTED

| Option | What it was | Why rejected |
|---|---|---|
| **A** | Drop the warp; use the driver's actual telemetry hifi-path JSON as the styled line | "fuck you, that's not a solution" — they want a *synthetic* styled line, not telemetry replay |
| **B** | Reparameterize Q_RACING_LINE phase along arc length | "I don't fucking understand that" — also (verified after) reparameterization alone doesn't change the geometry, only the parameter labels, so visually identical anyway |
| **C** | Style-modulated IQP solver (re-run min-curv with style-modulated weights per driver) | "we are not fucking with generate racing line, that one works" |

### Constraints for any future fix

1. Must produce a **synthetic** styled line (not telemetry replay).
2. Must **not** modify `OBJECT_OT_GenerateRacingLine` or its IQP solver.
3. Must read the same sliders / same JSON schema (`style_params` + `corners[]` from `f1_style_extract.py`).
4. Must produce a curve that's a **visibly different shape** from Q_RACING_LINE *and* looks like a real racing line.

### What was tried and failed today

#### V1: existing `OBJECT_OT_GenerateStyledRacingLine` (line ~1615)
- Detects corners on the **centerline**, lifts to Q_RACING_LINE via cKDTree nearest-neighbor `nn`.
- Computes lateral offset α(s) per station from style params.
- Warps along Q_RACING_LINE's right-normals: `styled = raceline + α * nv_r_right`.
- Post-hoc safety clip in **centerline-normal frame** (different basis from warp).
- splprep periodic resample.

User said: bad at corners.

#### V2 attempt 1: `OBJECT_OT_GenerateStyledRacingLineV2` (line ~1795 area, currently in file)
Helpers added: `_v2_detect_corners_arclen`, `_v2_smoothed_right_normals`, `_v2_periodic_smooth_xy`, `_v2_compute_alpha`. New button "Generate Styled Racing Line (v2)" in the Style Layer panel. Output curves: `Q_RACING_LINE_STYLED_V2_{driver}` + alias `Q_RACING_LINE_STYLED_V2`.

Differences from V1:
- Corners detected directly on Q_RACING_LINE (its own κ).
- Phase = arc-length within corner (not station count).
- Smoothed tangent → smoothed right-normals (kills zigzag).
- Single-basis warp + clip.
- Light periodic gaussian XY smooth at end.

User tested: **"nope, no change its bad"**.

#### V2 attempt 2 (CURRENT STATE OF FILE): budget-aware alpha
Edited V2 in place (currently in the file as committed-ready). Diagnostic theory:
- Q_RACING_LINE at corner apex sits at the inside kerb (within `vehicle_half_width`) by construction of the IQP solver.
- The α formula was using `w_in = wr_safe[s]` (centerline-to-edge width, ~6 m) as the magnitude scale.
- At apex, `apex_tightness × 0.80 × 6m ≈ 2-3m` of inside push, but only ~1m of room exists.
- Safety clamp pinned the styled point onto the inside kerb → flat kerb-hugging segment → "looks like shit at corners".

Fix in current V2 code:
- Computes `right_budget` and `left_budget` per Q_RACING_LINE station (the *actual* room between Q_RACING_LINE and each kerb).
- Passes these as `wr` and `wl` to `_v2_compute_alpha` instead of the centerline widths.
- At apex, budget ≈ 0 → α ≈ 0 → no push, no kerb-pinning.
- Final correction step accounts for `cos(theta)` between racing-line normal and centerline normal.

User tested: **"nope its still bad"**. Then went to sleep.

### My current best hypothesis on what's still wrong

(Speculation — not verified. The user has the visual; I don't.)

After the budget fix, α at apex is near-zero. The styled line stays as Q_RACING_LINE through the apex. So whatever the user sees as "still bad" is one of:

1. **Styled line is now visually too similar to Q_RACING_LINE** — no kerb-pinning, but no visible style either. Possible because:
   - The JSON's `entry_width` and `exit_width` are 0 (the extractor in `f1_style_extract.py` hardcodes them to 0 — it has no centerline reference from telemetry alone).
   - With apex effect throttled by budget AND entry/exit zero, the only visible signal is `straight_bias` and `lr_asymmetry`, both subtle.

2. **Visible style is now in the wrong places** — entry/exit zones get α applied (because they have budget), but those zones were already "correct" in Q_RACING_LINE; bending them looks weird.

3. **The corner detection on Q_RACING_LINE is finding different corners** than the JSON's corner count, falling back to lap-wide globals, giving uniform mediocre style across all corners.

4. **Something else entirely** — I haven't seen the visual output.

### The architectural pickle

The user has rejected A, B, C. They want a synthetic styled line that:
- Is visibly different from Q_RACING_LINE
- Is a proper racing line (not kerb-pinned, not wobbly)
- Doesn't come from telemetry replay
- Doesn't re-run the IQP solver

This is a hard constraint set. **The honest read:** lateral warping of Q_RACING_LINE has a low ceiling on visible effect because Q_RACING_LINE is at the kerb at apex. To get visible style without kerb-pinning, the styled line needs **geometric reshaping**, not lateral pulling.

Concrete idea I floated but didn't implement (call it **Option D**):
- Detect the κ-peak of each corner on Q_RACING_LINE → that's the natural apex index `A_0`.
- For each corner, compute a *shifted apex index* `A_new = A_0 + shift` where `shift` is derived from `apex_phase` (positive = late, negative = early).
- Reshape the corner so the κ-peak sits at `A_new` instead of `A_0`. Practically: integrate a redistributed κ profile back to coords (∫ tangent angle dθ = κ ds; reconstruct via cumulative tangent), or use a smoother bezier through entry / new-apex / exit control points.
- For `apex_tightness`: scale the κ-peak height before reintegration (sharper peak = tighter corner).
- For `vu_shape`: control the κ-profile width vs. height (V = narrow tall peak, U = wide low plateau).

This is **~40-60 lines of new code in the operator + helpers**. It changes corner geometry without lateral pushing, so kerb-pinning can't happen. It respects all four user constraints. The user has not yet seen this proposal in this concrete form — only vague mentions buried in earlier responses.

**However,** the user is frustrated with options. Tomorrow's session should probably:
1. Ask the user one targeted question to confirm the visual symptom after the budget fix (still kerb-pinned? now too similar to Q_RACING_LINE? wrong shape somewhere else?).
2. Based on the answer, pick exactly one direction and ship it. No more option menus.

---

## Code state cheat sheet

### Files modified today (uncommitted)

```
f1_track_visualizer_addonLastLastLasttry5.py
  - Dependency block at top (functions get_modules_path, append_modules_to_sys_path,
    check_dependencies, install_package_to_blender, OBJECT_OT_InstallF1Dependencies.execute)
  - V2 block: helpers _v2_detect_corners_arclen, _v2_smoothed_right_normals,
    _v2_periodic_smooth_xy, _v2_compute_alpha (after V1 operator, before
    OBJECT_OT_LoadStyleFromJson)
  - V2 operator OBJECT_OT_GenerateStyledRacingLineV2 (after the helpers, currently
    has the budget-aware alpha logic)
  - classes tuple at bottom now includes OBJECT_OT_GenerateStyledRacingLineV2
  - Panel UI has a "Generate Styled Racing Line (v2)" button under the V1 button

launch_control_auto_car_rig/launch_control_auto_car_rig/launch_control/operators/f1_pipeline.py
  - New module-level helper _apply_saved_alignment_to_scene at line ~299
  - _pipeline_finish (line ~325) now calls it
  - OBJECT_OT_f1_generate_scene.execute() no longer calls _apply_saved_alignment
  - Old _apply_saved_alignment method on the class deleted
  - New module-level helpers _resolve_style_output_dir and
    _extract_and_write_style_for_driver near the bottom (~line 2384 area)
  - OBJECT_OT_ExportDriverStyle rewritten to iterate scene.f1_lap_queue or fall
    back to single-driver mode
```

### Untracked but already in repo (created earlier, before this session)

```
launch_control_auto_car_rig/.../operators/f1_style_extract.py  (style param extractor)
F1_Pipeline_Assets/exports/NOR_telemetry.csv
F1_Pipeline_Assets/exports/SAI_telemetry.csv
formulyticsScript.py (don't know what this is, untouched)
```

### Files I created in repo root for reference (safe to delete)

```
dep_report.txt — extracted text from "Blender Dependency Fix Report.docx"
STYLED_LINE_DEBUG_HANDOFF.md — this document
```

### Important data files

```
F1_Pipeline_Assets/database/tracks.json
  - bahrain_grand_prix.alignment.rotation = -1.529432 rad (≈ -87.6°) — the
    smoking gun for the perpendicular bug
  - pre-season_test_1 has the same alignment
  - australian_grand_prix has rotation 0 (good regression test for multi-car fix)

F1_Pipeline_Assets/temp_data/{driver}_{slot_id}_hifi_path.json
  - Per-driver baked telemetry. The user rejected using these as the styled line.

<db.root>/style_params/{driver}_{gp}_{year}_lap{N}.json
  - Where the export-style operator now writes per-driver style JSONs. Schema
    documented in launch_control_auto_car_rig/.../operators/f1_style_extract.py:
    write_style_json(). Has style_params (8 lap-wide aggregates) and corners[]
    (per-corner overrides).
```

---

## How the user wants to be communicated with

- **Terse.** They get angry at long option menus. Ship code; ask focused questions only when needed.
- **No "you're right, I was wrong" performative agreement.** They explicitly said: "do not kiss my ass saying you're right, I'm sorry". Push back if you disagree, but only with evidence.
- **Don't claim something works without testing.** I burned credibility earlier by claiming the multi-car pipeline worked based on code inspection only. The user said: "fuck you the multi car pipeline broke… wtf did you do?". That was a real lesson. Anything I claim now I prefix with "I haven't run this; here's what would happen mathematically and structurally".
- **They are technically capable.** Don't dumb things down too much; do explain anything they say they don't understand (they did flag B as not understandable).
- **No emojis.** Default Claude Code rule.
- **No `Co-Authored-By: Claude` trailer in commits** (it's in their auto-memory).

---

## Suggested first action tomorrow

Open the conversation with something like:

> Picking up from yesterday's handoff. The V2 styled line had a budget-aware fix applied at the end (alpha now scales to Q_RACING_LINE's actual lateral room, not centerline-to-edge widths). You said it was still bad before you went to sleep. One question so I can target the right fix:
>
> **After the fix, when you click V2, is the styled line:**
> **(i) still pinned flat against the kerb at apex, or**
> **(ii) now smooth but visually nearly identical to Q_RACING_LINE, or**
> **(iii) something else — describe the shape briefly?**

If (i): the budget fix didn't take effect; investigate whether the V2 button is even being invoked, whether the cache custom-properties on Q_RACING_LINE are being read correctly, or whether there's still a clipping path I missed.

If (ii): kerb-pinning is gone (good), but visible style is too small. Time to implement Option D (geometric corner reshape via apex-index shift). Roughly:
- Pull `corners_r` and `phase_r` from the existing V2 detection.
- For each corner, find `A_0 = corner['apex']`.
- Compute `shift = round(apex_phase * (corner['L'] / 4))` (cap at maybe quarter-corner-length).
- Build a smooth interpolation: take entry, the Q_RACING_LINE point at `A_0 + shift` as the new apex, and exit; fit a clamped cubic / bezier through them.
- Replace the racing-line stations within the corner with samples from the new curve.
- Smooth-blend at corner boundaries to avoid kinks at entry/exit transition.
- Skip lateral warping entirely (or keep it as a second-order tweak).

If (iii): user describes the actual visual; route to a fix matching that description.

---

## Outstanding risks / things I'm not sure about

- Whether V2's corner detection on Q_RACING_LINE is finding the same number of corners as `corners[]` from the JSON. If counts differ, the per-corner override array falls back to lap-wide globals (warning is reported). User has not confirmed whether they see the warning.
- Whether `props.racing_line_veh_width` is set sensibly. If it's huge (e.g., 4 m), the budget at apex is even smaller / negative, and alpha gets fully zeroed.
- Whether the centerline (`_cl_qp`) cached on Q_RACING_LINE is actually evenly-spaced or has gaps at corners that affect the cKDTree mapping.
- The launch_control multi-car alignment fix (Section 1) hasn't been verified by the user yet either. Still hypothetical until they actually queue 2 cars and click Generate Scene.

---

## Glossary (for the next model)

- **Q_RACING_LINE** — the IQP min-curvature racing line. Output of `OBJECT_OT_GenerateRacingLine` in the visualizer addon.
- **Q_RACING_LINE_STYLED** — V1 styled line, written by `OBJECT_OT_GenerateStyledRacingLine`.
- **Q_RACING_LINE_STYLED_V2** — V2 styled line, written by `OBJECT_OT_GenerateStyledRacingLineV2`.
- **`_cl_qp`, `_wr_safe`, `_wl_safe`** — custom properties cached on Q_RACING_LINE by the racing-line generator. Centerline coords (`_cl_qp_x/y`) and per-station track-edge widths (right/left) in centerline-normal frame.
- **Hifi path** — per-driver baked telemetry path JSON (from `F1_HiFi_Baker_Pro`). Used by the launch_control rig as the actual driving path.
- **Style JSON** — the per-driver style param payload written by `OBJECT_OT_ExportDriverStyle` and consumed by `OBJECT_OT_LoadStyleFromJson` in the visualizer.
- **Alignment sliders** — `align_offset_x/_y`, `align_rotation`, `align_scale` in `f1_pipeline_props`. They transform telemetry path curves to fit the Blender track model. Saved per track in `tracks.json`.
- **Slot ID** — index of a driver in the lap queue (0, 1, 2…). Lets the same driver appear twice (e.g. HAM Day 1 + HAM Day 2) without name collisions.

End of handoff.
