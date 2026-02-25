# F1 Race Replay Studio — Asset Pipeline Guide

This documentation outlines the mandatory workflow for adding car models, track models, and driver assets to the **F1 Race Replay Studio** database. 

---

## 🏎️ Adding a New Car Model

To make a car compatible with the pipeline, we use a **"Bait-and-Switch"** hierarchy. This allows the addon to find the meshes while keeping the Launch Control (LC) engine active in the background.

### Step 1 — Rigging
1. Open a new Blend file and import your car model.
2. Use **Launch Control** to rig the car (Assign Body, 4 Wheels, and Brakes).
3. Click "Animate Vehicle" to ensure the rig is functional before proceeding.

### Step 2 — The "Bait-and-Switch" Hierarchy
You must separate the "Render Meshes" from the "Rig Logic."
1. Create a collection at the top level named `CarRig_DRIVERCODE` (e.g., `CarRig_HAM`).
2. Move your **Body Mesh** and **4 Wheel Meshes** into this new collection.
3. **DO NOT** delete or rename the `LaunchControl` folder. It must stay in the scene.
4. Delete any empty sub-folders like "Tyres" or "Mercedes" created during the initial rig.

**Required Outliner Structure:**
- Scene Collection
    - 📂 `LaunchControl` (Keep this untouched)
        - 📂 `CarRig_lc [car_name]` (The internal rig)
    - 📂 `CarRig_HAM` (The addon targets this)
        - 📄 `body`
        - 📄 `wheel.FL`
        - 📄 `wheel.FR`
        - 📄 `wheel.RL`
        - 📄 `wheel.RR`

### Step 3 — Aligning Physics Suffixes
The `refresh_physics()` function in the addon will crash if names don't match.
1. Check your Armature name (e.g., `car_rig_LC Mercedes`). The suffix is `_LC Mercedes`.
2. Ensure all objects inside the `InternalCar` folder (e.g., `sim_Wheels`, `sim_Body`, `dummy`) end with that **exact same suffix**.

---

## 🏗️ Library Prep Script (Automation)
Run this script inside your car's `.blend` source file after rigging to automate the hierarchy and naming fixes.
```python
import bpy

# --- SETTINGS ---
DRIVER_CODE = "HAM"  
CAR_NAME = "Mercedes" 

# 1. Setup Collections
target_col = bpy.data.collections.get(f"CarRig_{DRIVER_CODE}")
if not target_col:
    target_col = bpy.data.collections.new(f"CarRig_{DRIVER_CODE}")
    bpy.context.scene.collection.children.link(target_col)

# 2. Move Meshes to Target
mesh_names = ["body", "wheel.FL", "wheel.FR", "wheel.RL", "wheel.RR"]
for name in mesh_names:
    obj = bpy.data.objects.get(name)
    if obj:
        for col in obj.users_collection:
            col.objects.unlink(obj)
        target_col.objects.link(obj)

# 3. Rename Physics Objects
old_suf = f"_{CAR_NAME}"
new_suf = f"_LC {CAR_NAME}"
for obj in bpy.data.objects:
    if obj.name.endswith(old_suf):
        obj.name = obj.name.replace(old_suf, new_suf)
```

---

## 🏁 Track & Driver Assets

### Track Models
- **File Name:** `event_name.lower().replace(" ", "_") + ".blend"`
- **Example:** `australian_grand_prix.blend`
- **Collection:** Must contain the word `track` or `circuit` (case insensitive).
- **Required Object Name:** The road surface mesh must be named exactly `Track`.

### ⚠️ One-Time Track Alignment (Required Before Use)

Each track must be manually aligned to the GPS coordinate space once before use.
Once saved, it never needs to be done again for that circuit.

1. Open the track `.blend` file directly in Blender.
2. Run the F1 path generation script for that circuit — a `GPS_PATH` curve will appear at the origin.
3. Switch to **top-down orthographic view** (Numpad 7).
4. Select the **track model** and use **G / R / S** to move, rotate, and scale it until the road sits under the `GPS_PATH` curve. Aim for ~99% coverage.
5. Delete `GPS_PATH` from the scene.
6. **Save the `.blend` file.** The alignment is now permanent.

> The pipeline imports tracks with `link=False` so the saved transform is always preserved.  
> Any remaining misalignment on specific corners can be fixed after scene generation using the **Path Sculpt Brush** in the addon panel.

### Driver Photos
- **Path:** `F1_Pipeline_Assets\database\drivers\`
- **Naming:** `{DRIVER_CODE}.jpg` (e.g., `HAM.jpg`)
- **Spec:** 512x512px Square.

---

## 📊 Quick Reference Table

| Asset Type | Target Folder | Target Collection |
| :--- | :--- | :--- |
| **Standard Car** | `cars/2024/TeamName/` | `CarRig_HAM` |
| **Special Livery** | `cars/2024/TeamName/` | `CarRig_HAM` |
| **Track Model** | `tracks/` | `track` or `circuit` |
| **Driver Photo** | `database/drivers/` | N/A |