# F1 Race Replay Studio — Adding New Models

---

## Adding a New Car Model

### Step 1 — Rig the Car with Launch Control
Every car model must be rigged using Launch Control before it can be used in the pipeline.

1. Open a **new blank blend file** in Blender
2. Import or build your car model (body, 4 wheels, brakes)
3. Open the **Launch Control** panel (N Panel → Launch Control tab)
4. Follow the standard Launch Control rigging workflow:
   - Select your car collection
   - Click **Rig Car**
   - Assign body, wheels, and brakes as prompted
   - Click **Animate Vehicle** to confirm the rig works
5. Once rigged and working, save the file

### Step 2 — Name the Collection Correctly
Inside the blend file, in the **Outliner**, find the main car collection that Launch Control created. It will be named something like `CarRig_lc porsche 944 turbo`.

**Rename it to match this exact pattern:**
```
CarRig_DRIVERCODE
```

Examples:
```
CarRig_VER
CarRig_NOR
CarRig_HAM
CarRig_LEC
```

> ⚠️ The collection name must start with `CarRig_` exactly. The addon searches for this prefix.

### Reference — How Collections Should Be Named
For reference, open one of the already-added test cars in `F1_Pipeline_Assets\cars\2024\`:
- `McLaren\NOR.blend`
- `McLaren\PIA.blend`
- `Red Bull Racing\VER.blend`

Open any of these in Blender and check the **Outliner**. You will see the collection structure LC creates when a car is rigged. Your new car must follow the same structure — the main rig collection renamed to `CarRig_{CODE}`.

The structure looks like this:
```
CarRig_NOR                        ← rename this to match your driver code
  ├── car_rig_LC ...              ← armature, do not rename
  ├── driving_path_LC ...         ← path curve, do not rename
  ├── Lights_...                  ← do not rename
  ├── InternalCar_...             ← do not rename
  │     ├── Gfx
  │     └── SkidmarkEngine_...
  └── [your car mesh objects]
```

Only the top-level collection needs to be renamed to `CarRig_{CODE}`. Everything inside stays as LC named it.

### Step 3 — Save the Blend File with the Correct Name
Save the blend file as the **driver's 3-letter code**:
```
VER.blend
NOR.blend
HAM.blend
LEC.blend
```

### Step 4 — Place the File in the Correct Folder
Put the blend file inside `F1_Pipeline_Assets\cars\` under the correct year and team folder:

```
F1_Pipeline_Assets\
└───cars\
    └───2024\
        ├───McLaren\
        │       NOR.blend
        │       PIA.blend
        │       NOR_Round5.blend    ← special livery for Round 5 only
        ├───Red Bull Racing\
        │       VER.blend
        └───Mercedes\
                HAM.blend
```

> ⚠️ The team folder name must match exactly what FastF1 returns for that team. Check `F1_Pipeline_Assets\database\drivers_by_race.json` to confirm the correct team name spelling for each year.

### How the pipeline finds your car (path rule)
When you click **Add Lap** in F1 Race Replay Studio, the addon stores **year**, **event**, **session**, **driver**, and **team** from the database. When you click **Generate Scene**, it builds the path to your blend file like this:

```
F1_Pipeline_Assets/cars/{year}/{team}/{driver}.blend
```

Example: if you add **Lando Norris** for a **2024** race, the database sets `team` to **McLaren**, so the addon looks for:

- **`F1_Pipeline_Assets/cars/2024/McLaren/NOR.blend`**

So you must have a **team folder** (e.g. `McLaren`) under the year folder. Putting only `NOR.blend` inside `cars/2024/` (with no team subfolder) will not work — the pipeline expects `cars/2024/McLaren/NOR.blend`.

If the path is wrong, check:
1. The **year** folder: `2024`, `2025`, etc.
2. The **team** folder: name must match `team_raw` in `F1_Pipeline_Assets/database/drivers_by_race.json` for that year and race (e.g. `McLaren`, `Red Bull Racing`, `Mercedes`).
3. The **filename**: `NOR.blend` (driver 3-letter code + `.blend`).

### “The path is not getting created” (driving path curve)
If the **car file is found** but the **driving path** (the curve the car follows) does not appear or has no telemetry:

1. Your car blend must have been **rigged with Launch Control** so it contains a **curve** object (the “driving path” LC creates). The pipeline finds any object of type CURVE inside the `CarRig_*` collection and uses it; then it writes the lap telemetry from the JSON onto that path.
2. Make sure **Generate Scene** runs without “Car file not found” or “No LC collection found” warnings. If you see those, fix the file path and collection name as above.
3. The telemetry path is generated only when **Generate Scene** runs (it creates `{driver}_hifi_path.json` and applies it). If the JSON is missing or the operator fails, the path curve may stay empty — check the Blender System Console for errors.

### Special Liveries (Round-Specific)
Some races have special one-off liveries — Monaco, home races, anniversary liveries etc. The pipeline supports round-specific overrides automatically.

**Naming pattern:** `{CODE}_Round{round_number}.blend`

Examples:
```
VER_Round5.blend     ← VER's special livery for Round 5 only
NOR_Round8.blend     ← NOR's special livery for Round 8 only
HAM_Round12.blend    ← HAM's special livery for Round 12 only
```

**How it works:** When generating a scene, the addon first checks if a round-specific file exists for that driver. If it does, it uses that instead of the standard `VER.blend`. If not, it falls back to the standard file automatically. You don't need to do anything extra — just name the file correctly and place it in the same team folder.

To find the round number for a race, check `F1_Pipeline_Assets\database\calendar_cache.json`.

---

## Adding a New Track Model

### Step 1 — Prepare the Track Collection
Inside your track blend file, make sure the track collection is named either:
- `track`
- or any name containing the word `track` or `circuit` (case insensitive)

Examples that work:
```
track
Track
circuit
Albert_Park_Circuit
```

### Step 2 — Name and Place the File
Save the blend file using the **race name in lowercase with underscores** and place it in `F1_Pipeline_Assets\tracks\`:

```
F1_Pipeline_Assets\
└───tracks\
        australian_grand_prix.blend
        bahrain_grand_prix.blend
        monaco_grand_prix.blend
```

The naming pattern is exactly: `event_name.lower().replace(" ", "_") + ".blend"`

So **Australian Grand Prix** → `australian_grand_prix.blend`

> ⚠️ The filename must match exactly. The addon converts the race name from the dropdown directly into this filename to find the track.

---

## Adding Driver Photos

Driver photos are used by the After Effects UI overlay to display driver headshots.

### Setup — Create the Folder (one time only)
Run this command in PowerShell to create the drivers photo folder:

```powershell
mkdir "C:\Users\91910\Downloads\F1_Builder_Context\F1_Pipeline_Assets\database\drivers"
```

> If you're on a different machine, replace `C:\Users\91910\Downloads\F1_Builder_Context` with your own `F1_Builder_Context` folder path.

### Step 1 — Name the Photo Correctly
Name each photo using the driver's **3-letter code**:
```
VER.jpg
NOR.jpg
PIA.jpg
HAM.jpg
LEC.jpg
```

Supported formats: `.jpg`, `.jpeg`, `.png`

### Step 2 — Place the Photo in the Correct Folder
```
F1_Pipeline_Assets\
└───database\
    └───drivers\
            VER.jpg
            NOR.jpg
            PIA.jpg
            HAM.jpg
            LEC.jpg
            RUS.jpg
```

### Notes
- One photo per driver, named by 3-letter code
- Photo is the same across all seasons — if a driver changes teams just keep the same file
- If a driver photo is missing the AE script will use a placeholder
- Recommended resolution: 512x512px or higher, square crop preferred

---

## Quick Reference

| Asset | Collection Name | File Name | Folder |
|---|---|---|---|
| Car (standard) | `CarRig_VER` | `VER.blend` | `cars/2024/Red Bull Racing/` |
| Car (special livery) | `CarRig_VER` | `VER_Round5.blend` | `cars/2024/Red Bull Racing/` |
| Track | contains `track` or `circuit` | `australian_grand_prix.blend` | `tracks/` |
| Driver Photo | — | `VER.jpg` | `database/drivers/` |