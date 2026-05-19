# Ideal Racing Line Video — Standalone Pipeline

Goal: produce a formulytics-style vertical MP4 of an animated dot traveling the *ideal* racing line on a real F1 track outline, with no Blender dependency at runtime and no telemetry needed for the animation.

## Pipeline

Two scripts. Run the Blender script once per track to capture geometry; run the standalone script anytime to render videos.

```
extract_track_outline.py   (Blender Scripting tab, one-shot per track)
        │
        ▼
<track>_outline.json   { "outer": [[x,y], ...], "inner": [[x,y], ...] }
        │
        ▼
raceline_video.py          (standalone Python, no Blender)
        │
        ▼
<track>_ideal_lap.mp4
```

## extract_track_outline.py

- Operate on the mesh object literally named `Track`.
- Apply world matrix so output is world-space.
- Use `bmesh` to iterate edges; boundary edges have exactly 1 linked face.
- Walk boundary edges via shared vertices into closed loops.
- Sort loops by perimeter; the **two longest** are outer + inner edge of the road ribbon.
  - Decide outer vs inner by perimeter (longer = outer).
- Drop Z (top-down render).
- Write `<blendfile>_outline.json` next to the .blend.
- Print summary: loop count, outer length, inner length, point counts.

The script must be self-contained, runnable with one click in Blender's text editor. No reliance on the `launch_control` addon or `TRACK_CENTER_FIXED`.

## raceline_video.py

Single-file standalone script. Dependencies: `numpy`, `scipy`, `opencv-python`, `Pillow`, `trajectory-planning-helpers`, `quadprog`.

### Stage 1 — Track corridor
1. Load JSON.
2. Smooth each loop with periodic spline (`scipy.interpolate.splprep(..., per=True, s=large)`) to absorb the boundary-edge jaggedness from the user's hand-separated mesh.
3. Resample each loop at uniform arc length, e.g. 800 pts.
4. Pair inner ↔ outer points. Strategy: arc-length parameterize both loops in the same rotational direction starting from a common reference angle, then match by parameter. Closest-point KD-tree fallback if direction inference is ambiguous.
5. Centerline = midpoint of each pair. Half-widths = distance from midpoint to each side.
6. Inset half-widths by `INSET_M = 1.5` to absorb residual edge noise and mirror the addon's `racing_line_inset`.

### Stage 2 — IQP min-curvature racing line
- Direct port of `_opt_min_curv_sparse` from `f1_track_visualizer_addonLastLastLasttry5.py` (sparse `spsolve` instead of dense `inv`, `quadprog.solve_qp` for the QP).
- IQP loop with up to 5 iterations, alpha tolerance 0.10, safety margin 0.15, mirroring the addon (`pip install trajectory-planning-helpers quadprog scipy`).
- Output: closed racing line polyline at user-specified stepsize (default 3m) with curvature κ(s).

### Stage 3 — Speed profile (telemetry-free)
- `v_max(s) = sqrt(a_lat_max / max(|κ(s)|, eps))`, capped at `v_top`.
- Forward pass with `a_long_max` (acceleration limit) iterating over arc-length segments.
- Backward pass with `a_brake_max` (braking limit).
- Final v(s) = elementwise minimum of the three constraints.
- Defaults (configurable at top of file):
  - `a_lat_max = 30.0` m/s² (~3g cornering)
  - `a_long_max = 12.0` m/s² (acceleration)
  - `a_brake_max = 45.0` m/s² (braking)
  - `v_top = 95.0` m/s (~342 km/h)
- Convert to time: `t(s) = cumulative ds / v(s)`, used for animation timing.

### Stage 4 — Render
- Output: 1080×1920 vertical MP4 via `cv2.VideoWriter`, 30 fps default.
- Camera: world-space → screen with zoom factor (default 3.0); recentered on dot every frame.
- Per frame:
  1. Black background.
  2. Outer-edge polyline (white, thick).
  3. Inner-edge polyline (white, thick).
  4. Filled dark gray ribbon between them — this is the **real track surface visible in the video**.
  5. Racing line drawn on top (cyan, thin).
  6. Dot trail (last `trail_frames` positions, colored polyline).
  7. Dot itself (colored disc + white outline, identical to formulytics).
  8. PIL overlay: title block (`<TRACK NAME>` / `IDEAL RACING LINE`), minimap (whole track + dot dot), live speed readout in km/h, watermark.
- Total frames = `int(lap_time * fps)`.

### CLI
```
python raceline_video.py \
    --outline miami_grand_prix_outline.json \
    --track-name "MIAMI GRAND PRIX" \
    --zoom 3.0 \
    --trail-frames 60 \
    --fps 30 \
    --out miami_ideal_lap.mp4
```

## Code reuse
| From | What |
|---|---|
| `formulyticsScript.py` | Font setup, `draw_centered`, world↔screen + minimap transforms, frame loop layout, trail/dot styling, title/minimap/watermark, MP4 writer |
| `f1_track_visualizer_addonLastLastLasttry5.py` | `_opt_min_curv_sparse` (verbatim), IQP loop, centerline smoothing, inset+safety margin |
| New | Blender boundary extractor, edge-pair matcher, curvature-physics velocity solver, two-edge "real track" render |

## Out of scope
- Multi-driver lap comparison (single dot only).
- Telemetry input.
- Real-time interactive UI (CLI only; no widgets).
- Z-axis rendering (strict top-down).
- Audio.

## Risks & mitigations
- **Boundary mesh has gaps / not two clean loops** → script reports loop count and longest perimeters; user can re-separate. Smoothing + insetting absorbs minor noise but not topological breaks.
- **IQP infeasible on tight tracks** → small `H` regularization + minimum-corridor clamp already in the addon's port; failure prints diagnostic and exits non-zero.
- **`trajectory_planning_helpers` install on Windows** → the user already has it working in Blender; the package is pure Python except for `quadprog` which has Windows wheels.
