# How to Rig a Car for Launch Control (F1 Hot Lap)

Follow these steps in order. Everything must be done in the **same Blender file** and in the **same collection** that you will later rename to `CarRig_DRIVERCODE`.

---

## What You Need Before You Start

- Blender **4.2+** (4.5 recommended)
- Your car model with at least:
  - **1 body** (chassis)
  - **4 wheels** (tyres, meshes)
  - **4 brakes** (calipers) — optional in addon preferences, but recommended
- Launch Control addon **installed and enabled**

---

## Step 1 — Prepare Your Model in One Collection

1. Open a **new blank** Blender file.
2. Import or place your car model (body + 4 wheels + 4 brakes).
3. Put **all** of these objects in **one collection** (e.g. create a collection and parent or move everything into it).
4. Leave that collection **selected** in the Outliner (click it so it’s the active collection).  
   This collection is the one you will later **select in Launch Control** and rename to `CarRig_DRIVERCODE`.

---

## Step 2 — Name Objects Exactly as Launch Control Expects

Launch Control finds parts **by name**. Use these **exact** names (case can vary for body/wheel/brake keywords, but locations RL/RR/FR/FL must be clear).

### Required

| Part        | Object name in Blender | Notes                                      |
|------------|-------------------------|--------------------------------------------|
| **Body**   | `Body`                  | One object. Name must contain "body" or "hull". |
| **Wheels** | `wheel.RL`              | Rear Left tyre mesh                        |
|            | `wheel.RR`              | Rear Right                                 |
|            | `wheel.FR`              | Front Right                                |
|            | `wheel.FL`              | Front Left                                 |

### Optional but recommended

| Part     | Object name in Blender | Notes                                      |
|----------|-------------------------|--------------------------------------------|
| **Brakes** | `brake.RL`            | Rear Left brake caliper                    |
|          | `brake.RR`              | Rear Right                                 |
|          | `brake.FR`              | Front Right                                |
|          | `brake.FL`              | Front Left                                 |

**Important:**

- **RL = Rear Left, RR = Rear Right, FR = Front Right, FL = Front Left** — as seen from **behind** the car. If the car moves in +Y in Blender, “rear” is the back of the car.
- Names must contain the **location** (RL, RR, FR, FL). Alternatives like `wheel_RL`, `wheel_RearLeft`, or `tire.RL` usually work, but **`wheel.RL`** (and the same for RR/FR/FL and for brakes) is the safest.
- **Body:** exactly **one** object named so it contains **"Body"** (e.g. `Body` or `Car Body`). If more than one object matches, the addon will error.
- All of these objects must be **inside the same collection** you will give to Launch Control.

---

## Step 3 — Run the Launch Control Rigging Workflow

1. Open the **N Panel** (press **N**).
2. Go to the **Launch Control** tab.
3. In the **User Vehicle** dropdown, select the **collection** that contains your Body + 4 wheels + 4 brakes (the one with the names above).
4. Click **Rig Vehicle** (or **Rig Car**).
5. When prompted, assign:
   - **Body** → the object named `Body` (or equivalent).
   - **Wheels** → the four wheel meshes (wheel.RL, wheel.RR, wheel.FR, wheel.FL).
   - **Brakes** → the four brake calipers (if you have them and the addon asks).
6. Complete any other steps the addon shows (e.g. ground, options).
7. When rigging finishes, click **Animate Vehicle** (or equivalent) and move the timeline to confirm the car moves and the rig works.
8. **Save the .blend file.**

---

## Step 4 — Rename the Collection to CarRig_DRIVERCODE

1. In the **Outliner**, find the **main car collection** that Launch Control created (it may be named like `CarRig_lc ...` or similar).
2. **Rename** that **top-level** collection to:

   ```text
   CarRig_DRIVERCODE
   ```

   Examples:

   - `CarRig_VER`
   - `CarRig_NOR`
   - `CarRig_HAM`
   - `CarRig_LEC`

3. **Do not rename** objects inside it (e.g. leave the armature name as LC created it, often `car_rig_...`). Only the **collection** name must follow `CarRig_DRIVERCODE`.

**Rule:** The collection name **must** start with **`CarRig_`** exactly. The F1 pipeline and path assignment use this prefix to find the car.

---

## Step 5 — Check the Structure (Reference)

After rigging, the Outliner often looks like this:

```text
CarRig_HAM                    ← your car collection (rename to CarRig_DRIVERCODE)
  └── [your Body, wheel.*, brake.* meshes]

LaunchControl                 ← addon collection (do not rename)
  └── CarRig_Ferrari_Hamilton ← rig collection (armature, path, etc.)
        ├── car_rig_Ferrari_Hamilton   ← armature (do not rename)
        ├── driving_path_...
        └── ...
```

**This is correct.** Launch Control keeps your **meshes** in the car collection (`CarRig_HAM`) and puts the **rig** (armature, path curve, internals) inside **LaunchControl**. The pipeline finds the car by the collection name `CarRig_HAM`; the armature can live in LaunchControl. Only the **car collection** is renamed to `CarRig_DRIVERCODE` (e.g. `CarRig_HAM`).

---

## Step 6 — Save and Place the File for the F1 Pipeline

1. **Save** the .blend as the driver’s **3-letter code**:
   - `VER.blend`
   - `NOR.blend`
   - `HAM.blend`
   - etc.
2. Put it in the correct folder:

   ```text
   F1_Pipeline_Assets/
   └── cars/
       └── 2024/
           ├── McLaren/
           │     NOR.blend
           │     PIA.blend
           ├── Red Bull Racing/
           │     VER.blend
           └── Mercedes/
                 HAM.blend
   ```

3. **Team folder** name must match what the database uses (e.g. from `F1_Pipeline_Assets/database/drivers_by_race.json`).  
   Path rule: **`F1_Pipeline_Assets/cars/{year}/{team}/{driver}.blend`**.

---

## Quick Checklist

- [ ] One collection with Body + 4 wheels + 4 brakes (brakes optional in prefs).
- [ ] Body: one object, name contains "Body" (e.g. `Body`).
- [ ] Wheels: four meshes named with wheel + RL/RR/FR/FL (e.g. `wheel.RL`, `wheel.RR`, `wheel.FR`, `wheel.FL`).
- [ ] Brakes: four meshes named with brake + RL/RR/FR/FL (e.g. `brake.RL`, …).
- [ ] Launch Control → User Vehicle = that collection → Rig Vehicle → assign body, wheels, brakes.
- [ ] Test with Animate Vehicle, then save.
- [ ] Rename **only** the top-level LC collection to `CarRig_DRIVERCODE`.
- [ ] Save .blend as `DRIVERCODE.blend` in `cars/{year}/{team}/`.

---

## If Something Goes Wrong

- **“Please rename the main car body part to 'Body'”**  
  → One object in the collection must have a name containing **Body** (e.g. `Body`).

- **“Please rename the … Tire Mesh to 'wheel.RL'”**  
  → That wheel’s object name must contain both a wheel word (e.g. wheel, tire) and the location (RL, RR, FR, or FL). Use `wheel.RL`, `wheel.RR`, `wheel.FR`, `wheel.FL`.

- **“Name labels seem flipped”**  
  → RL/RR/FR/FL are from the **rear** of the car. Swap names so RL is rear left, RR rear right, FR front right, FL front left.

- **Car not selected / path not assigned**  
  → Collection must be named exactly `CarRig_DRIVERCODE` (e.g. `CarRig_VER`). The rig object name should start with `car_rig_` (LC creates this). After **Generate Scene**, the pipeline selects the car by this collection name and applies the path.

- **No armature found**  
  → Rig the car with Launch Control first (Step 3). The armature is usually inside **LaunchControl**, not inside `CarRig_*`; that’s normal.

For adding the car to the pipeline and file naming, see **README_ADDING_MODELS.md**.  
For generating a scene end-to-end, see **README_GETTING_STARTED.md**.
