# Cross-Track-Coordinate Styled Racing Lines — Design

**Date:** 2026-05-01
**Branch:** `f1hotlap_lohith_v2`
**Author:** lohithburra01 (with Claude Opus 4.7)

---

## 1. Problem

`Q_RACING_LINE_STYLED_{driver}` curves currently look near-identical between drivers. Three independent failures compound:

1. **Extraction** in `f1_style_extract.py` saturates `apex_phase`, `vu_shape`, `smoothness` at hard clamps for the majority of corners — so different drivers' real differences end up at the same clamped value.
2. **The BATCH operator** (`F1_OT_GenerateAllStyledRacingLines`) consumes only 3 of the 8 style axes (`apex_phase`, `apex_tightness`, `vu_shape`); `entry_width`, `exit_width`, `straight_bias`, `smoothness`, `lr_asymmetry` are ignored.
3. **The reshape kernel** `_v3_reshape_corner` is structurally bounded to ±1.5 m of inside push, then clipped against `inside_budget` which is ~0 at apex (Q already hugs the kerb). Almost no displacement reaches the visible curve.

In addition, **all three styled-line code paths in the file** (`_v3_reshape_corner`, `_styled_line_from_driver_path`, `_styled_line_for_driver_legacy`) share one design property: outside corner indices, the offset from Q is hard-zeroed. The straights are pinned to Q while corners get displaced, which produces visible "chunk-pulled" artifacts at corner entry/exit boundaries when displacements are large enough to be visible at all.

## 2. Goals

- Per-driver styled curves that visibly differ from each other in shape, smoothly across the whole lap (not just at corners).
- Output remains a "proper racing line" — smooth, bounded by track edges, no kerb-pinning, no kinks.
- No change to `Q_RACING_LINE` generation. Q remains the optimal min-curvature line.
- No dependence on driver telemetry XY (FastF1 XY is unreliable).
- No global numerical optimization per driver. Per-driver compute stays O(N) over Q's stations, no QP, no IQP.

## 3. Non-Goals

- Replacing `OBJECT_OT_GenerateRacingLine` or its IQP solver (rejected by user).
- Modifying the alignment / Z-snap / Kabsch logic that lives in `_OT_AlignPathToRacingLine` and friends.
- Replaying telemetry XY directly as the styled line.
- Per-track manual tuning. Algorithm must be track-agnostic.

## 4. Approach

Express the styled line in **cross-track coordinate** instead of as a perturbation of Q.

For each station `s` along the lap (Q's arc-length parameterisation), define:

```
d(s) ∈ [0, 1]    where 0 = inner kerb, 1 = outer kerb
styled_xy(s) = inner_xy(s) × (1 − d(s))  +  outer_xy(s) × d(s)
```

The styled line is a smooth interpolation between the two physical track edges at every station. `d(s)` is a single periodic function defined for every station — there is no corner/straight branching anywhere in the algorithm.

### 4.1 Per-driver `d(s)` decomposition

```
d_driver(s) = clip(d_Q(s) + Δd_driver(s),  0.0,  1.0)
```

- `d_Q(s)` is Q's own cross-track position. Computed once per track.
- `Δd_driver(s)` is a small per-driver delta derived from reliable telemetry signals (speed, brake, throttle).
- Clipping to `[0, 1]` is the physical track-edge bound. A styled line is allowed to hug the inner kerb at apex (because Q does, by IQP design — `d_Q ≈ 0` at every apex). What it cannot do is leave the track.

When `Δd_driver = 0` everywhere, `d_driver = d_Q` exactly (no clipping triggers, since `d_Q ∈ [0, 1]` by construction) and `styled_xy = Q_xy` to numerical tolerance. Q is the natural fixed point; drivers hover around it.

### 4.2 Why this avoids the artifact pattern

| Past failure | Cause | How this avoids it |
|---|---|---|
| Kerb-pinning at apex *as a buggy artifact* | Lateral push clipped against `budget ≈ 0` collapsed every driver to the same on-kerb point | Inside kerb-hugging at apex is preserved (it's correct — that's where Q sits) but per-driver style now manifests on entry/exit/straights where Q has room. Drivers no longer collapse to the same point because differences live in the part of the lap where there's track width to express them. |
| "Chunk pulled at corner, straights stay at Q" | Algorithm zeros the offset outside corner indices | `d(s)` is a single global function defined for every station; straights have nonzero deviation that smoothly evolves between corners |
| Kinks at corner boundary | Bump anchored to 0 at corner entry/exit, derivative discontinuous | No anchor points anywhere; smoothness comes from low-pass over `s` |
| Bumps in unexpected places | Corner detection on driver telemetry XY misclassifies | No corner detection in this algorithm |
| Lines too similar | Style axes saturated by extraction; kernel bounded to 1.5 m | `Δd` magnitudes are bounded by track width, not by an arbitrary 1.5 m cap |

## 5. Inputs

### 5.1 Track outlines (per track, computed once)

Already produced by the existing `extract_track_outline.py`:

```json
{
  "outer": [[x, y], ...],
  "inner": [[x, y], ...]
}
```

Output path: `<blend_dir>/<blend_stem>_outline.json` (the script's existing convention).

The script welds duplicate verts, walks boundary loops, picks the two largest-bbox loops, labels them `outer` (largest) and `inner` (second-largest).

### 5.2 Q (per track, already exists)

`Q_RACING_LINE` curve object in the scene, with custom properties already cached:

- `_cl_qp_x`, `_cl_qp_y` — centerline coords
- `_wr_safe`, `_wl_safe` — per-station right/left half-widths in centerline-normal frame

### 5.3 Per-driver telemetry (already loaded by current pipeline)

Reliable FastF1 channels, sampled vs lap-distance:

- `Speed` (sensor-derived)
- `Throttle` (input)
- `Brake` (input)

We **do not** read `X` or `Y` for any per-driver computation. We do not run corner detection on driver telemetry.

## 6. Algorithm

### 6.1 Per-track bake (once per Q regeneration)

Triggered automatically by `F1_OT_GenerateAllStyledRacingLines.execute()` if Q is missing the cross-track cache. Cached on Q as new custom properties.

```
INPUTS: Q_RACING_LINE (n_q stations), <blend_stem>_outline.json
OUTPUTS (cached on Q):
  _inner_xy_aligned : (n_q, 2) inner kerb point paired with each Q station
  _outer_xy_aligned : (n_q, 2) outer kerb point paired with each Q station
  _d_q              : (n_q,)    Q's cross-track coordinate per station
```

Steps:

1. Load `outer` and `inner` polygons from the outline JSON.
2. Verify orientation: signed-area sign of each polygon. If opposite to Q's lap direction, reverse it.
3. Resample `outer` and `inner` periodically with a periodic cubic spline to a high density (~5× Q station count) so cKDTree pairing is precise.
4. For each Q station `i`:
   - `inner_xy_aligned[i] = nearest point on inner polygon to Q[i]`
   - `outer_xy_aligned[i] = nearest point on outer polygon to Q[i]`
5. Compute `d_q[i] = ‖Q[i] − inner_xy_aligned[i]‖ / ‖outer_xy_aligned[i] − inner_xy_aligned[i]‖`
6. Sanity-check: `d_q ∈ [0, 1]` for all stations except possibly minor numerical tolerance. Print a warning + clamp if violated (e.g., near pit lane spurs).
7. Write all three arrays to Q's custom properties.

This bake is O(n_q) cKDTree queries × constant. Sub-second on a typical 1000-station Q.

### 6.2 Per-driver `Δd(s)` (called once per styled line)

```
INPUTS:
  speed_d (n_t,)     — driver's speed timeseries vs lap distance
  brake_d (n_t,)     — driver's brake timeseries
  throttle_d (n_t,)  — driver's throttle timeseries
  field_aggregates   — median speed/brake/throttle across queue, vs lap distance
  d_q (n_q,)         — Q's baseline d
OUTPUT:
  delta_d (n_q,)     — additive delta in cross-track coordinate, per Q station
```

Steps:

1. Resample driver `speed_d`, `brake_d`, `throttle_d` from their native lap-distance grid onto Q's station grid (linear interp on lap fraction).
2. Resample field-median signals identically.
3. Compute three signed contributions, each scaled to a small d-unit budget:
   - **Speed delta** `c_v(s) = K_v × (speed_driver(s) − speed_median(s)) / speed_max_field`
     - Faster driver → wider line (positive d shift toward outside)
   - **Brake-state delta** `c_b(s) = K_b × (brake_driver(s) − brake_median(s))`
     - Brake-on-when-others-aren't → late braker → wider entry (positive)
   - **Throttle-state delta** `c_t(s) = −K_t × (throttle_driver(s) − throttle_median(s))`
     - Throttle-up-when-others-aren't → tighter exit (negative; toward inside)
4. Sum `Δd_raw(s) = c_v + c_b + c_t`.
5. Low-pass filter `Δd_raw` along `s` with a periodic gaussian, sigma = 30 stations (~3% of lap), to ensure smooth global evolution and kill telemetry-sampling micro-features.
6. Clamp `|Δd|` to a configurable cap (default 0.20 = 20% of track width — typical real F1 driver-line spread).
7. Return `Δd`.

Constants `K_v`, `K_b`, `K_t` are tuned once on the Miami test (target: each contribution maxes at ~0.10 d-units before summation, so total typically 0.05–0.15 with occasional peaks at 0.20).

**Solo-driver fallback**: if the queue has only one driver, `field_median` would equal `driver` and `Δd = 0`. In that case, fall back to a "neutral driver" baseline computed from Q's curvature alone (a simple physically-derived target speed `v_target(s) = sqrt(a_lat / |κ_Q(s)|)`) and use that as the median substitute. Documented behaviour: solo-driver styled line equals Q exactly minus a small curvature-derived correction (the styled line will look very close to Q, which is correct — there's no comparison driver).

### 6.3 Per-driver styled curve assembly

```
INPUTS:
  Q's _inner_xy_aligned (n_q, 2)
  Q's _outer_xy_aligned (n_q, 2)
  d_q (n_q,)
  delta_d (n_q,)
OUTPUTS:
  styled_xy (n_q, 2)
```

Steps:

1. `d_driver = np.clip(d_q + delta_d, 0.0, 1.0)`
2. `styled_xy = inner_xy_aligned * (1 − d_driver)[:, None] + outer_xy_aligned * d_driver[:, None]`
3. Z column copies from Q (already raycast-aligned by upstream pipeline).
4. Write as `Q_RACING_LINE_STYLED_{driver}` curve, replacing any existing object of that name.

Per-driver compute: a few vectorised numpy ops over n_q ≈ 1000 stations. Sub-50ms per driver.

## 7. Integration

### 7.1 New function (added near `_v3_reshape_corner`)

```python
def _v4_bake_cross_track_cache(q_obj, outline_json_path):
    """Compute and cache _inner_xy_aligned, _outer_xy_aligned, _d_q on Q.
    Idempotent — bails early if cache is fresh and outline JSON hasn't changed."""

def _v4_compute_delta_d(driver_signals, field_signals, n_q):
    """Per-driver smooth Δd(s) on Q's station grid, in cross-track units."""

def _v4_assemble_styled(q_obj, delta_d):
    """Apply Δd to cached d_Q and interpolate inner↔outer to produce styled XY."""
```

### 7.2 Modified operator

`F1_OT_GenerateAllStyledRacingLines.execute()` rewrites to:

1. Verify Q exists and has style cache (existing checks unchanged).
2. **NEW**: locate `<blend_stem>_outline.json` (sibling of the .blend); if missing, run `extract_track_outline`-equivalent inline. Bake cross-track cache onto Q if not already cached or stale.
3. Compute field-median signals from queued drivers (or use the curvature-derived neutral baseline if solo).
4. For each style JSON in the directory matching `filter_gp + filter_yr`:
   - Load driver telemetry (speed/brake/throttle) — already happens for the existing match step.
   - Compute `Δd_driver` via `_v4_compute_delta_d`.
   - Compute `styled_xy` via `_v4_assemble_styled`.
   - Write `Q_RACING_LINE_STYLED_{driver}` curve.

The legacy `_v3_reshape_corner` and the surrounding inside-bump logic in `execute()` is **deleted**, not gated. Same for the unreferenced `_styled_line_from_driver_path` and `_styled_line_for_driver_legacy`. Dead code removal is part of this change.

### 7.3 Operator for outline extraction

Add `F1_OT_ExtractTrackOutline` operator — Blender-side equivalent of `extract_track_outline.py`. Triggered:

- Manually via a new "Extract Track Outline" button under the "Generate Racing Line" button in the F1 Track Setup panel.
- Automatically invoked by `F1_OT_GenerateAllStyledRacingLines` if outline JSON is missing.

Output: `F1_Pipeline_Assets/tracks/<gp_slug>_outline.json` (matches existing tracks/ convention; preferred over the default `<blend_stem>_outline.json` for project organisation).

### 7.4 No changes to

- `OBJECT_OT_GenerateRacingLine` — Q generator stays untouched.
- `OBJECT_OT_AlignPathToRacingLine` — alignment/Z-snap stays untouched.
- `f1_style_extract.py` — left as-is for now (the existing JSON's `style_params` and `corners[]` are unused by the new flow but the extractor is harmless and may be reused for diagnostics).

## 8. Failure Modes & Mitigations

| Failure | Detection | Mitigation |
|---|---|---|
| Outline JSON missing | File not found at expected paths | Auto-run extraction operator; if Track mesh missing, error with clear message |
| Track mesh has non-ribbon topology (pit-lane spurs etc.) | Outline extraction returns >2 large loops | Script already picks 2 largest by bbox; log all loops for diagnosis |
| Inner / outer mislabeled (rare, but possible if pit lane is bigger than infield) | `d_q` out of [0, 1] for >5% of stations | Auto-swap inner/outer roles; re-bake; log warning |
| Q has stations that map to a pit-lane region | `d_q` out of [0, 1] for a small contiguous range | Clamp `d_q` to [0, 1] for those stations; log range; result will look like Q in the affected zone |
| Solo driver in queue | Field median = driver | Use curvature-derived neutral baseline (documented as expected solo behaviour) |
| Speed/brake/throttle channels missing for a driver | Loaded telemetry has no `Speed` / `Brake` / `Throttle` | Skip that driver; log; styled line not generated |
| Q regenerated, cache stale | Cache version property mismatches Q's modification timestamp | Re-bake on next styled-line generation |

## 9. Validation

### 9.1 Mathematical checks (automated, run during execution)

- **Round-trip identity**: with `Δd = 0` for every station, `styled_xy ≈ Q_xy` to within 1e-3 m. Assert in the bake step.
- **Boundedness**: `min(d_driver) ≥ 0.0` and `max(d_driver) ≤ 1.0` after clipping. Assert.
- **Continuity**: `max(‖styled_xy[i+1] − styled_xy[i]‖)` should be within 1.2× of Q's max station spacing. Assert (catches discontinuities).
- **Cache freshness**: `_d_q` length matches Q station count.

### 9.2 Visual validation (Miami test)

Run the queue (NOR + SAI) for Miami at `master = 1.0`. Expected:

- Both styled curves visibly different at every corner — apex offsets differ by 0.3–1.5 m.
- Smooth evolution on straights (small ~0.1–0.4 m offsets between drivers).
- No kinks at any station boundary.
- No kerb-pinning at apex.
- Driving paths after alignment with `blend = 0.9` track each driver's styled line.

### 9.3 Regression check (Bahrain)

Re-run Bahrain queue (HAM + VER, or whoever the user has tested before). Verify:

- Saved alignment in `tracks.json` still applies.
- Styled lines produced; no errors.
- Visual: lines are different per driver, smooth, on-track.

## 10. Out of Scope

- **Better extraction of `apex_tightness` etc. from speed**: the existing `f1_style_extract.py` is left alone. The new flow doesn't read its JSON output. If we want richer per-corner style features in the future, that's a separate iteration.
- **A Blender UI to tune `K_v`, `K_b`, `K_t`**: constants are baked once via Miami calibration. If the user wants sliders later, that's a follow-up.
- **Lateral asymmetry per driver based on left-vs-right preference**: deferred. Field-relative encoding already captures most asymmetry implicitly.
- **Removing the FastF1 hifi-path bake step**: that's still needed for the alignment pipeline (Kabsch fits on driver XY). It's only the *styled line* that no longer reads driver XY.

## 11. Files Touched

```
launch_control_auto_car_rig/.../launch_control/operators/
  f1_track_viz.py
    - DELETE: _v3_reshape_corner
    - DELETE: _styled_line_from_driver_path
    - DELETE: _styled_line_for_driver_legacy
    - DELETE: _extract_offset_profile
    - ADD:    _v4_bake_cross_track_cache
    - ADD:    _v4_compute_delta_d
    - ADD:    _v4_assemble_styled
    - ADD:    F1_OT_ExtractTrackOutline operator
    - REWRITE: F1_OT_GenerateAllStyledRacingLines.execute()

  f1_pipeline.py
    - Auto-chain calls F1_OT_ExtractTrackOutline before generate_all_styled_racing_lines
      if outline JSON missing for the current track.

launch_control_auto_car_rig/.../launch_control/ui/
  f1_track_setup_panel.py
    - ADD: "Extract Track Outline" button under Generate Racing Line

F1_Pipeline_Assets/tracks/
  <gp_slug>_outline.json (one per track, generated)
```

## 12. Tuning Constants (initial values, to be refined on Miami)

```python
K_V = 0.30          # speed-delta scale → d-units
K_B = 0.10          # brake-delta scale → d-units
K_T = 0.10          # throttle-delta scale → d-units
DELTA_D_CAP = 0.20  # max |Δd| per station (= 20% of track width)
SMOOTH_SIGMA = 30   # gaussian sigma in stations for Δd low-pass
D_CLIP_LO = 0.0     # min d_driver (physical inner kerb)
D_CLIP_HI = 1.0     # max d_driver (physical outer kerb)
```

## 13. Open Questions for User Review

1. **Outline auto-extraction vs manual**: should `F1_OT_GenerateAllStyledRacingLines` auto-extract the outline if missing, or should we fail loudly and require the user to click the new "Extract Track Outline" button manually first time? (Current design: auto-extract for one-click smoothness; let me know if you'd rather explicit.)

2. **Output filename convention**: outline JSON at `F1_Pipeline_Assets/tracks/<gp_slug>_outline.json` (proposed) or sibling of the .blend like the standalone script does (`<blend_stem>_outline.json`)? Both work; the former groups outlines with track .blends.

3. **Field median vs other baselines**: with 2-driver queues (NOR + SAI) the field median is the average of the two drivers. That means each driver is shown as ±half the inter-driver delta from the median. Acceptable, or would you prefer one driver to be the "reference" (e.g., the fastest-lap driver = baseline, others = deviations)?
