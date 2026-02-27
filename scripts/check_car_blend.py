"""
Check a car .blend for Launch Control / F1 pipeline compliance.
Run with: blender "path/to/car.blend" --background --python check_car_blend.py

Note: Does not use sys.exit() so Blender can shut down cleanly in background
mode (avoids GPU teardown crash). Check printed "RESULT:" line for pass/fail.
"""
import bpy
import os

def main():
    path = bpy.data.filepath
    if not path:
        print("ERROR: No file loaded (run with: blender file.blend --background --python check_car_blend.py)")
        return

    print("=" * 60)
    print("Checking:", path)
    print("=" * 60)

    # Find CarRig_* collection
    car_coll = None
    for c in bpy.data.collections:
        if c.name.startswith("CarRig_"):
            car_coll = c
            break

    if not car_coll:
        print("FAIL: No collection named CarRig_* found.")
        print("  Expected: CarRig_DRIVERCODE (e.g. CarRig_HAM)")
        print("RESULT: INCOMPLETE (no CarRig_* collection)")
        return

    print("OK: Found collection:", car_coll.name)

    # Driver code from collection name (pipeline expects 3-letter code, e.g. HAM)
    driver_code = car_coll.name.replace("CarRig_", "").strip()
    if not driver_code:
        print("WARN: Collection is 'CarRig_' with no driver code.")
    else:
        print("  Driver code:", driver_code)
    if len(driver_code) != 3 or driver_code.upper() != driver_code or not driver_code.isalpha():
        print("WARN: Pipeline expects CarRig_DRIVERCODE with 3-letter code (e.g. CarRig_HAM). Current: CarRig_" + driver_code)

    # Gather all objects in this collection (including nested)
    def objects_in_collection(coll):
        objs = list(coll.objects)
        for child in coll.children:
            objs.extend(objects_in_collection(child))
        return objs

    objs = objects_in_collection(car_coll)

    # Ignore rig internals (bind poses, internal props, gfx, sim)
    def is_rig_internal(name):
        n = name.lower()
        return n.startswith("bind_pose_") or n.startswith("internal_") or n.startswith("gfx_") or n.startswith("sim_")

    # Body: single MESH with "body" or "hull", exclude rig internals
    body_candidates = [
        ob for ob in objs
        if ob.type == "MESH" and (("body" in ob.name.lower() or "hull" in ob.name.lower()) and not is_rig_internal(ob.name))
    ]
    if not body_candidates:
        print("FAIL: No main body MESH found (expect one MESH named e.g. 'Body', excluding bind_pose_*, sim_*, gfx_*)")
    elif len(body_candidates) > 1:
        print("WARN: Multiple body mesh candidates:", [o.name for o in body_candidates])
    else:
        print("OK: Body:", body_candidates[0].name)

    # Wheels: MESH only, wheel/tire + RL/RR/FR/FL, exclude rig internals
    required_wheels = {"RL", "RR", "FR", "FL"}
    found_wheels = {}
    for ob in objs:
        if ob.type != "MESH" or is_rig_internal(ob.name):
            continue
        n = ob.name
        for loc in required_wheels:
            if ("wheel" in n.lower() or "tire" in n.lower()) and loc in n.upper():
                if "brake" not in n.lower() and "wheelcover" not in n.lower():
                    found_wheels[loc] = n
                    break

    for loc in required_wheels:
        if loc in found_wheels:
            print("OK: Wheel", loc + ":", found_wheels[loc])
        else:
            print("FAIL: Missing wheel MESH for", loc, "(expect e.g. wheel." + loc + ", not bind_pose_ or internal_)")

    # Brakes: MESH only, exclude rig internals (bind_pose_brake.* are rig empties, not caliper meshes)
    found_brakes = {}
    for ob in objs:
        if ob.type != "MESH" or is_rig_internal(ob.name):
            continue
        n = ob.name
        for loc in required_wheels:
            if "brake" in n.lower() and loc in n.upper():
                found_brakes[loc] = n
                break
    if len(found_brakes) == 4:
        print("OK: All 4 brake meshes found:", list(found_brakes.values()))
    elif found_brakes:
        print("WARN: Only some brake meshes:", found_brakes)
    else:
        print("INFO: No brake caliper meshes (brake.RL etc) - optional.")

    # Armature (car_rig_*) - Launch Control puts it in the LaunchControl collection, not in CarRig_*
    armatures = [ob for ob in objs if ob.type == "ARMATURE" and ob.name.lower().startswith("car_rig")]
    if not armatures:
        # Look in whole file: rig often lives in LaunchControl collection
        armatures = [
            ob for ob in bpy.data.objects
            if ob.type == "ARMATURE" and ob.name.lower().startswith("car_rig")
        ]
    if not armatures:
        armatures = [ob for ob in objs if ob.type == "ARMATURE"]
        if armatures:
            print("WARN: Armature found but name does not start with 'car_rig_':", armatures[0].name)
        else:
            print("FAIL: No armature found. Rig the car with Launch Control.")
    else:
        where = " (in LaunchControl)" if armatures[0].name not in [o.name for o in objs] else ""
        print("OK: Armature:", armatures[0].name + where)

    # Filename vs driver code
    base = os.path.splitext(os.path.basename(path))[0].upper()
    if base != driver_code.upper():
        print("WARN: Filename driver code '{}' does not match collection 'CarRig_{}'".format(base, driver_code))
    else:
        print("OK: Filename matches driver code:", base)

    print("=" * 60)
    if not body_candidates or len(found_wheels) != 4:
        print("RESULT: INCOMPLETE (need 1 body MESH and 4 wheel MESHes; exclude bind_pose_/internal_/gfx_/sim_)")
        return
    if not armatures or not armatures[0].name.lower().startswith("car_rig"):
        print("RESULT: INCOMPLETE (rig with Launch Control or fix armature name)")
        return
    if len(driver_code) != 3 or driver_code.upper() != driver_code or not driver_code.isalpha():
        print("RESULT: INCOMPLETE (rename collection to CarRig_XXX with 3-letter code, e.g. CarRig_HAM)")
        return
    print("RESULT: Looks good for F1 pipeline.")

if __name__ == "__main__":
    main()
