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
        ├───Red Bull Racing\
        │       VER.blend
        └───Mercedes\
                HAM.blend
```

> ⚠️ The team folder name must match exactly what FastF1 returns for that team. Check `F1_Pipeline_Assets\database\drivers_by_race.json` to confirm the correct team name spelling for each year.

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

## Quick Reference

| Asset | Collection Name | File Name | Folder |
|---|---|---|---|
| Car | `CarRig_VER` | `VER.blend` | `cars/2024/Red Bull Racing/` |
| Track | contains `track` or `circuit` | `australian_grand_prix.blend` | `tracks/` |
