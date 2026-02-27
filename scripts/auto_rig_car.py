"""
Auto-rig a car with Launch Control and set collection name for the F1 pipeline.

- If the .blend already has a rigged car (CarRig_* collection with armature):
  only renames that collection to CarRig_XXX using the driver code from the
  filename (e.g. HAM.blend -> CarRig_HAM).
- If the .blend has an unrigged car (one collection with Body + 4 wheel meshes):
  sets that collection as the Launch Control user vehicle, runs Rig Vehicle,
  then renames the collection to CarRig_XXX and saves.

Run with:
  blender "path/to/HAM.blend" --background --python "path/to/auto_rig_car.py"

Requires: Launch Control addon installed and enabled.
"""

import bpy
import os


def _driver_code_from_filepath(path):
    """e.g. HAM.blend -> HAM, HAM_24176_AUTOSAVE.blend -> HAM"""
    base = os.path.splitext(os.path.basename(path))[0]
    base = base.replace("_AUTOSAVE", "").strip()
    part = base.split("_")[0] if "_" in base else base
    return part[:3].upper() if len(part) >= 3 else part.upper()


def _objects_in_collection(coll):
    objs = list(coll.objects)
    for child in coll.children:
        objs.extend(_objects_in_collection(child))
    return objs


def _is_rig_internal(name):
    n = name.lower()
    return (
        n.startswith("bind_pose_")
        or n.startswith("internal_")
        or n.startswith("gfx_")
        or n.startswith("sim_")
    )


def _collection_has_rig(collection):
    """True if collection (or children) contains an armature (car rig)."""
    for ob in _objects_in_collection(collection):
        if ob.type == "ARMATURE" and ob.name.lower().startswith("car_rig"):
            return True
    return False


def _find_unrigged_car_collection():
    """
    Find a collection that has one body mesh and four wheel meshes (same
    naming rules as Launch Control / check_car_blend), and no armature yet.
    """
    required_wheels = {"RL", "RR", "FR", "FL"}
    for coll in bpy.data.collections:
        if coll.name == "LaunchControl":
            continue
        objs = _objects_in_collection(coll)
        if len(objs) < 5:
            continue
        if _collection_has_rig(coll):
            continue
        body = [
            ob
            for ob in objs
            if ob.type == "MESH"
            and ("body" in ob.name.lower() or "hull" in ob.name.lower())
            and not _is_rig_internal(ob.name)
        ]
        if len(body) != 1:
            continue
        wheels = {}
        for ob in objs:
            if ob.type != "MESH" or _is_rig_internal(ob.name):
                continue
            n = ob.name
            for loc in required_wheels:
                if ("wheel" in n.lower() or "tire" in n.lower()) and loc in n.upper():
                    if "brake" not in n.lower() and "wheelcover" not in n.lower():
                        wheels[loc] = ob.name
                        break
        if set(wheels.keys()) == required_wheels:
            return coll
    return None


def _find_carrig_collection():
    """First collection whose name starts with CarRig_."""
    for c in bpy.data.collections:
        if c.name.startswith("CarRig_"):
            return c
    return None


def main():
    path = bpy.data.filepath
    if not path:
        print("ERROR: No file loaded. Run: blender file.blend --background --python auto_rig_car.py")
        return
    driver_code = _driver_code_from_filepath(path)
    if len(driver_code) != 3 or not driver_code.isalpha():
        print("WARN: Driver code from filename is not 3 letters:", driver_code, "- use e.g. HAM.blend")

    addon = bpy.context.preferences.addons.get("launch_control_auto_car_rig")
    if not addon:
        print("ERROR: Launch Control addon not enabled. Enable it in Blender preferences.")
        return

    target_name = "CarRig_" + driver_code
    scene = bpy.context.scene

    # Already rigged: just rename collection to CarRig_XXX
    car_coll = _find_carrig_collection()
    if car_coll and _collection_has_rig(car_coll):
        if car_coll.name == target_name:
            print("OK: Collection already named", target_name)
        else:
            old = car_coll.name
            car_coll.name = target_name
            print("OK: Renamed collection", old, "->", target_name)
        try:
            bpy.ops.wm.save_mainfile()
            print("Saved:", path)
        except Exception as e:
            print("Save failed:", e)
        return

    # Unrigged: find collection with Body + 4 wheels, run Rig Vehicle, then rename and save
    unrigged = _find_unrigged_car_collection()
    if not unrigged:
        print("ERROR: No unrigged car collection found. Need one collection with:")
        print("  - 1 body MESH (name contains 'body' or 'hull')")
        print("  - 4 wheel MESHes: wheel.RL, wheel.RR, wheel.FR, wheel.FL (or tire.*)")
        print("If the car is already rigged, the script will only rename the collection.")
        return

    scene.car_collection = unrigged
    if getattr(scene, "settings", None) and hasattr(scene.settings, "edit_all_mode"):
        scene.settings.edit_all_mode = False

    print("Rigging collection:", unrigged.name, "with Launch Control...")
    try:
        result = bpy.ops.object.rig_car()
    except Exception as e:
        print("Rig failed:", e)
        return
    if result != {"FINISHED"}:
        print("Rig failed (operator returned", result, "). Check body/wheel names and addon validation.")
        return

    # Rename the collection we just rigged to CarRig_XXX
    if unrigged.name != target_name:
        unrigged.name = target_name
        print("OK: Renamed collection to", target_name)
    try:
        bpy.ops.wm.save_mainfile()
        print("Saved:", path)
    except Exception as e:
        print("Save failed:", e)


if __name__ == "__main__":
    main()
