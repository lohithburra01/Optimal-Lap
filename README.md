# Hot Lap – F1 Race Replay Studio

Generate cinematic F1 race replays from real telemetry data. Import cars, tracks, and lap paths from FastF1; animate cars along paths; add helicopter cameras, trails, and minimap exports for After Effects or video editing.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Initial Setup](#initial-setup)
- [How to Use](#how-to-use)
- [Track Map (Minimap) Export](#track-map-minimap-export)
- [Helicopter Camera](#helicopter-camera)
- [Car Trails](#car-trails)
- [Path Correction](#path-correction)
- [Project Structure](#project-structure)
- [Data & Assets](#data--assets)
- [Troubleshooting](#troubleshooting)

---

## Features

- **Multi-car scene generation** — Add up to 4 laps to the queue; generate a full scene with track, cars, and paths
- **FastF1 integration** — Uses official F1 timing data via FastF1 (races, qualifying, practice, pre-season testing)
- **Path & speed animation** — Paths follow real GPS telemetry; speed keyframes drive car motion
- **Helicopter camera** — Dynamic chase cam that follows cars, with marker-based overrides and smoothing
- **Car trails** — Ribbons behind each car, animated via `bevel_factor_end`; bakeable for reliable renders
- **Path correction** — Diagnose, auto-correct off-track points, flatten Z, snap to track, sculpt brush
- **Minimap export** — Transparent PNG frames for After Effects, with average driver position and track outline
- **Telemetry CSVs** — Exported for each driver (frame, time_s, distance, speed, throttle, brake, gear, rpm, etc.)

---

## Requirements

| Requirement | Details |
|-------------|---------|
| **Blender** | 4.2.0 or newer |
| **Python (addon)** | fastf1, pandas, scipy, numpy, requests, timple, requests-cache |
| **Project layout** | Blender `.blend` file must live in the same folder as `F1_Pipeline_Assets` |

---

## Installation

### 1. Install the Addon

1. Download or clone this repository.
2. In Blender: **Edit → Preferences → Extensions** (or Add-ons).
3. Use **Install from Disk** and select the folder `launch_control_auto_car_rig`.
4. Enable **"Hot Lap – F1 Race Replay Studio"**.

### 2. Install Python Dependencies

1. Open Blender and go to the **3D Viewport**.
2. Press `N` to open the sidebar → **Hot Lap** tab.
3. If dependencies are missing, the panel shows an error.
4. Click **"Install Dependencies"** or **"Upgrade / Reinstall FastF1 (3.8.1+)"**.
5. Wait for the install to finish (installs into `scripts/f1_studio_modules/`).

Alternatively, install manually:

```bash
pip install -r launch_control_auto_car_rig/launch_control_auto_car_rig/requirements-f1.txt --target <Blender scripts path>
```

**Dependencies:**

- `fastf1>=3.8.1` (testing sessions, latest data)
- `pandas`, `scipy`, `numpy`, `requests`, `timple`, `requests-cache`

---

## Initial Setup

### 1. Refresh the Database

Run the refresh script to update calendars and driver data:

```bash
py scripts/refresh_database.py 2026
```

(Replace `2026` with your target year.)

This updates:

- `F1_Pipeline_Assets/database/calendar_cache.json`
- `F1_Pipeline_Assets/database/drivers_by_race.json`
- `F1_Pipeline_Assets/database/drivers_by_season.json`
- `F1_Pipeline_Assets/database/testing_events.json`
- `F1_Pipeline_Assets/database/event_session_map.json`

### 2. Prepare Assets

**Car assets:**

Place car `.blend` files at:

```
F1_Pipeline_Assets/cars/{year}/{team}/{code}.blend
```

Example: `F1_Pipeline_Assets/cars/2026/Red Bull Racing/VER.blend`

Each file should contain a `CarRig` collection with armature, driving path, and sim objects.

**Track assets:**

Place track `.blend` files at:

```
F1_Pipeline_Assets/tracks/{event_slug}.blend
```

Event names are normalized: `"Bahrain Grand Prix"` → `bahrain_grand_prix.blend`, `"Chinese Grand Prix"` → `chinese_grand_prix.blend`.

The main track surface mesh should be named **"Track"**. Optional: a `track_cosmetic` collection for kerbs/runoff used in ground detection.

**Track metadata:**

`F1_Pipeline_Assets/database/tracks.json` stores track versions and alignment. Alignment (offset X/Y, rotation, scale) is saved/loaded via the UI.

### 3. Project Layout

Your project folder should look like:

```
your_project/
├── my_scene.blend                    ← Your Blender file (open this)
├── F1_Pipeline_Assets/
│   ├── database/
│   │   ├── calendar_cache.json
│   │   ├── drivers_by_race.json
│   │   ├── tracks.json
│   │   └── ...
│   ├── cars/
│   │   └── 2026/
│   │       └── Red Bull Racing/
│   │           └── VER.blend
│   ├── tracks/
│   │   └── bahrain_grand_prix.blend
│   ├── temp_data/                   (auto-created)
│   └── exports/                     (auto-created)
└── launch_control_auto_car_rig/     (addon folder)
```

---

## How to Use

### Basic Workflow

1. **Open Blender** with your `.blend` file in the project folder.
2. Go to **3D Viewport → N → Hot Lap**.
3. **Query Engine:**
   - Select **Year** (e.g. 2026).
   - Select **Race/Event** (e.g. Bahrain Grand Prix).
   - Select **Session** (FP1, FP2, FP3, Q, R, or Day 1/2/3 for testing).
   - Optionally enable **Fastest Lap (auto)**.
   - Select **Driver**.
   - Click **Add Lap to Queue**.
4. Repeat step 3 for up to 4 drivers (different laps or same driver from different sessions).
5. Enable **Render Track Map** if you want minimap frames exported.
6. Click **GENERATE SCENE**.

### What Happens During Generation

1. **Track** — Loaded first if not already in the scene.
2. **Telemetry** — FastF1 session is loaded; path splines and speed data are generated.
3. **Per car:**
   - Car is appended from `cars/{year}/{team}/{code}.blend`.
   - Path JSON is applied to the driving path curve.
   - Speed keyframes drive the car along the path.
   - Trail is created and linked to the car.
4. **Exports** — CSVs and (optionally) minimap frames are written to `exports/`.

### Track Alignment

If paths don’t line up with the track model:

1. In **Track Alignment**, adjust **Offset X**, **Offset Y**, **Rotation**, **Scale**.
2. Click **Save** to store alignment in `tracks.json`.
3. Click **Load** to restore it for this track next time.

---

## Track Map (Minimap) Export

Transparent PNG frames for use in After Effects or similar tools.

- **Location:** `F1_Pipeline_Assets/exports/minimap_frames/frame_XXXXX.png`
- **Content:** Track outline (white line) and a single white dot at the **average position of all drivers** each frame.
- **Format:** 500×300 px, transparent background.

### Render Minimap Only

To re-render the minimap without re-importing cars or tracks:

1. Ensure telemetry CSVs exist in `F1_Pipeline_Assets/exports/` (e.g. `VER_telemetry.csv`).
2. In the Hot Lap panel, click **Render Minimap Only**.
3. The addon discovers drivers from existing CSVs, loads the FastF1 session for the track spline, and renders frames.

---

## Helicopter Camera

A dynamic camera that follows cars and keeps them framed.

### Create / Remove

- **Create Heli-Cam** — Adds the helicopter camera and target.
- **Remove** — Deletes the heli-cam objects.

### Live Adjustments

While playing back or scrubbing:

- **Height** — Camera height above the centroid.
- **Angle** — Viewing angle around the cars.
- **Distance** — Distance from the centroid.
- **Focal** — Focal length (zoom).

Sliders update the camera in real time.

### Markers (Keyframe-style)

1. Move to a frame where the camera looks good.
2. Adjust sliders as desired.
3. Click **Set Marker**.
4. The camera will smoothly interpolate between markers during playback.
5. Use **Prev / Next** to jump between markers; **Delete** to remove one; **Clear All** to remove all.

### Smoothing

A **Smoothing** slider controls how much temporal smoothing is applied. Higher values reduce jitter but add lag.

---

## Car Trails

Ribbon trails behind each car, animated by car position along the path.

### Refresh Trails

If trails stop animating (e.g. after reloading the file):

- Click **Refresh Trails** in the Path Diagnostic section.
- This re-registers the animation handler and re-syncs trail geometry from paths.

### Bake Trails

**Recommended before rendering.**

Handler-based trails can lag or miss frames during render. Baking writes keyframes for `bevel_factor_end` on each trail curve.

1. Click **Bake Trails**.
2. Keyframes are created for the full frame range (frame start–end).
3. Trails will render correctly and survive save/reload without the handler.

### Trail Height

**Trail Z Offset** in Path Diagnostic controls how high the trail sits above the track. Increase if trails clip into the surface.

---

## Path Correction

If paths drift off the track surface, use these tools in **Path Diagnostic**.

### Track Surface

Assign the **Track Surface** mesh (usually `Track`). The addon auto-assigns it when a track is loaded.

### Diagnose

- Click **Diagnose**.
- Path vertices turn **green** (on-track) or **red** (off-track).
- Use **Clear Diagnostic** to remove the overlay.

### Correct (Single Pass)

- Adjust **Correction Falloff**, **Correction Strength**, **Edge Inset**.
- Click **Correct** to run one correction pass on all paths and trails.
- **Edge Inset** — Positive: push points slightly inward from the track edge. Negative: push outward. The direction is derived from the correction vector (left/right of track).

### Auto-Correct

- Click **Auto-Correct (until on-track)**.
- Iterates until all vertices are on-track or a max iteration count is reached.

### Height Tools

- **Flatten Z** — Set path Z to a fixed value.
- **Snap Z to Track** — Ray-cast vertices onto the track surface for height.

### Path Sculpt

- Select a path in **Path**.
- Adjust **Radius** and **Strength**.
- Use **Sculpt Path** and paint in the viewport (M to toggle push/pull, scroll for radius, Shift+scroll for strength).

---

## Project Structure

```
f1_hot_lap/
├── launch_control_auto_car_rig/
│   └── launch_control_auto_car_rig/
│       ├── blender_manifest.toml
│       ├── requirements-f1.txt
│       └── launch_control/
│           ├── data/
│           │   └── f1_properties.py      # F1_Lap_Item, F1_Pipeline_Props, DB loading
│           ├── operators/
│           │   ├── f1_pipeline.py        # Scene gen, queue, path correction, alignment
│           │   ├── F1_HiFi_Baker_Pro.py  # FastF1, path gen, CSV, minimap
│           │   ├── heli_cam.py           # Helicopter camera
│           │   ├── f1_trail.py           # Trails, bake, refresh
│           │   ├── path_brush.py         # Path sculpt
│           │   └── lap_from_json.py      # Apply path JSON to Launch Control
│           └── ui/
│               └── f1_studio_panel.py    # Hot Lap panel
│
├── F1_Pipeline_Assets/
│   ├── database/
│   ├── cars/
│   ├── tracks/
│   ├── temp_data/    # Telemetry JSONs
│   └── exports/      # CSVs, minimap_frames/
│
└── scripts/
    ├── refresh_database.py
    ├── fetch_one_lap.py
    └── ...
```

---

## Data & Assets

### Database Files

| File | Purpose |
|------|---------|
| `calendar_cache.json` | Race calendar (year → events) |
| `drivers_by_race.json` | Drivers per event (code, team, etc.) |
| `drivers_by_season.json` | Season-wide driver list |
| `tracks.json` | Track versions, alignment |
| `testing_events.json` | Pre-season test events |
| `event_session_map.json` | Session display names |

### Generated Outputs

| Location | Contents |
|----------|----------|
| `temp_data/` | `{DRIVER}_hifi_path.json`, `{DRIVER}_{slot}_hifi_path.json` |
| `exports/` | `{DRIVER}_telemetry.csv`, `delta_comparison.csv`, `minimap_frames/*.png` |

### Telemetry CSV Columns

- `frame`, `time_s`, `distance`, `speed`, `throttle`, `brake`, `gear`, `rpm`, `ers_deploy`, etc.

---

## Troubleshooting

### "Missing Dependencies"

- Use **Install Dependencies** in the Hot Lap panel, or install manually (see [Installation](#installation)).

### Paths Don’t Match Track

- Use **Track Alignment** (Offset X/Y, Rotation, Scale) and **Save**.
- Use **Path Correction** (Diagnose, Auto-Correct) if points are off-track.

### Trails Not Animating in Render

- Click **Bake Trails** before rendering. Baked keyframes are reliable in all render engines.

### Trails Lost After Reload

- Click **Refresh Trails** to re-register the handler.
- Or **Bake Trails** for a permanent solution.

### Minimap Frames Missing

- Ensure **Render Track Map** is enabled before **GENERATE SCENE**.
- Or run **Render Minimap Only** after CSVs are in `exports/`.

### FastF1 "No data"

- Data is only available after sessions finish (often 30–120 minutes).
- Check event and session names (e.g. exact spelling).

### Cars / Tracks Not Found

- Verify paths: `F1_Pipeline_Assets/cars/{year}/{team}/{code}.blend` and `F1_Pipeline_Assets/tracks/{event_slug}.blend`.
- Ensure the `.blend` file is in the project root next to `F1_Pipeline_Assets`.

---

## License

SPDX:GPL-3.0-or-later

---

## Credits

- **Maintainers:** Daniel Vesterbaek, Gabriela Rodriguez, Blastframe  
- **Website:** [launch-control.org](https://launch-control.org)  
- **Addon:** Launch Control Auto Car Rig (Hot Lap – F1 Race Replay Studio)
