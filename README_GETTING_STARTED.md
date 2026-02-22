# F1 Race Replay Studio — Getting Started

## What You Need
- Blender 4.5
- This unzipped `F1_Builder_Context` folder

---

## Setup (One Time Only)

### Step 1 — Install the Addon
1. Open Blender
2. Go to `Edit → Preferences → Add-ons`
3. Click `Install` (top right)
4. Navigate into the `F1_Builder_Context` folder
5. Select `launch_control_auto_car_rig.zip`
6. Click `Install Add-on`
7. Enable it by ticking the checkbox next to **Launch Control Auto Car Rig**
8. Close Preferences

### Step 2 — Open the Blend File
1. In Blender go to `File → Open`
2. Navigate into `F1_Builder_Context`
3. Open `builder addon.blend`

> ⚠️ Always work from this blend file. Never move it outside the `F1_Builder_Context` folder or the addon will not find the assets.

---

## How to Generate a Scene

1. In Blender, open the **N Panel** (press `N` on the keyboard)
2. Find the **Launch Control** tab
3. Find the **F1 Race Replay Studio** section
4. Select your **Season → Race → Session**
5. Select a **Driver** and click **Add Lap**
6. Repeat for up to 4 drivers
7. Click **Generate Scene**

The addon will:
- Download and bake telemetry data for each driver
- Append the track into the scene
- Append each car and put it on its real telemetry-driven path
- Set up all animation ready to render

---

## Important Rules
- Always save the blend file inside `F1_Builder_Context` before generating
- Do not rename or move the `F1_Pipeline_Assets` folder
- Internet connection required for first-time telemetry downloads (FastF1)
