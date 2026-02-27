"""
Lap from JSON: load a JSON file with path coordinates and speed per point,
create the path, assign it as User Path, and bake speed keyframes.
"""
import bpy
import json
import math
import os
from mathutils import Vector

from ..utils.errors.exceptions import RigCollectionNotFound, DrivingPathnNotFound
from ..ui.utils import show_message_box
from ..logger import log_error, log_info
from ..utils.functions import get_active_curve_length, get_speed_rotate_fcurve
from ..utils.validations import validate_lc_object
from ..globals import B_SPEED_ROTATE

SPEED_ROTATE_SCALE = 9.99
LAP_CURVE_NAME = "LC_LapPath"

def _distance(a, b):
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2)

def _create_curve_from_points(points, closed, name=LAP_CURVE_NAME):
    """Create a Bezier curve with AUTO handles for smooth F1 path."""
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    if name in bpy.data.curves:
        bpy.data.curves.remove(bpy.data.curves[name], do_unlink=True)
        
    curve = bpy.data.curves.new(name=name, type="CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("BEZIER")
    n = len(points)
    spline.bezier_points.add(n - 1)
    
    for i, pt in enumerate(points):
        bp = spline.bezier_points[i]
        bp.co = (pt["x"], pt["y"], pt["z"])
        # F1 Requirement: VECTOR handles for exact point-to-point lines (no smoothing/overshoot)
        bp.handle_left_type = 'VECTOR'
        bp.handle_right_type = 'VECTOR'
            
    spline.use_cyclic_u = closed
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    return obj


def _compute_baking_data(points, closed, fps):
    """Compute frames and rotation values based on precise distance/speed calculation."""
    n = len(points)
    
    # We accumulate time and distance to ensure exact sync
    total_dist = 0.0
    total_time = 0.0
    
    kf_frames = [1.0] # Start at frame 1
    kf_values = [0.0]
    
    # Iterate segments
    for i in range(1, n):
        p1 = points[i-1]
        p2 = points[i]
        
        dist = _distance(p1, p2)
        total_dist += dist
        
        # Average speed for segment
        v_avg = (p1.get("speed", 20) + p2.get("speed", 20)) / 2.0
        if v_avg < 0.1: v_avg = 0.1
        
        dt = dist / v_avg
        total_time += dt
        
        frame = 1.0 + (total_time * fps)
        val = total_dist / SPEED_ROTATE_SCALE
        
        kf_frames.append(frame)
        kf_values.append(val)
        
    # Closure
    if closed and n > 1:
        p1 = points[-1]
        p2 = points[0]
        dist = _distance(p1, p2)
        total_dist += dist
        
        v_avg = (p1.get("speed", 20) + p2.get("speed", 20)) / 2.0
        if v_avg < 0.1: v_avg = 0.1
        dt = dist / v_avg
        total_time += dt
        
        frame = 1.0 + (total_time * fps)
        val = total_dist / SPEED_ROTATE_SCALE
        
        kf_frames.append(frame)
        kf_values.append(val)
        
    return kf_frames, kf_values, total_time

class OBJECT_OT_apply_lap_from_json(bpy.types.Operator):
    bl_label = "Lap from JSON"
    bl_idname = "object.apply_lap_from_json"
    bl_description = "Load path + speed from a JSON file, create path, assign as User Path, and bake F1 speed"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE", "HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def _verify_driving_setup(self, active_car, rig_object, driving_path):
        """Verify and fix the driving setup after prepare_animation.
        Ensures eval_time drivers, Follow Path constraints, and path_duration
        all reference the correct objects for THIS car.
        """
        print(f"  [F1 Lap] 🔍 Verifying driving setup for: {active_car.name}")
        print(f"    driving_path: {driving_path.name}")
        print(f"    path_duration: {driving_path.data.path_duration}")
        print(f"    use_path: {driving_path.data.use_path}")

        # --- Check eval_time drivers on Object level ---
        if driving_path.animation_data:
            for drv in driving_path.animation_data.drivers:
                if 'eval_time' in drv.data_path:
                    for var in drv.driver.variables:
                        for target in var.targets:
                            tid = target.id
                            if tid and tid != rig_object:
                                print(f"    ⚠️ eval_time driver target MISMATCH: "
                                      f"{tid.name} -> fixing to {rig_object.name}")
                                target.id = rig_object
                            elif tid:
                                print(f"    ✅ eval_time driver target OK: {tid.name}")

        # --- Check eval_time drivers on Data level ---
        if driving_path.data.animation_data:
            for drv in driving_path.data.animation_data.drivers:
                if 'eval_time' in drv.data_path:
                    for var in drv.driver.variables:
                        for target in var.targets:
                            tid = target.id
                            if tid and tid != rig_object:
                                print(f"    ⚠️ eval_time DATA driver target MISMATCH: "
                                      f"{tid.name} -> fixing to {rig_object.name}")
                                target.id = rig_object
                            elif tid:
                                print(f"    ✅ eval_time DATA driver target OK: {tid.name}")

        # --- Check ALL Follow Path constraints on ALL bones ---
        fixed_count = 0
        checked_count = 0
        try:
            for bone in rig_object.pose.bones:
                for con in bone.constraints:
                    if con.type == 'FOLLOW_PATH':
                        checked_count += 1
                        if con.target != driving_path:
                            old_name = con.target.name if con.target else "NONE"
                            print(f"    ⚠️ {bone.name} -> '{con.name}' target MISMATCH: "
                                  f"{old_name} -> fixing to {driving_path.name}")
                            con.target = driving_path
                            fixed_count += 1
            if fixed_count > 0:
                print(f"    🔧 Fixed {fixed_count}/{checked_count} Follow Path constraints")
            else:
                print(f"    ✅ All {checked_count} Follow Path constraints target OK")
        except Exception as e:
            print(f"    ⚠️ Follow Path check error: {e}")

        # --- Check action ---
        if rig_object.animation_data and rig_object.animation_data.action:
            act = rig_object.animation_data.action
            print(f"    Action: {act.name} ({len(act.fcurves)} fcurves)")
        else:
            print(f"    ⚠️ No action on rig!")

    def _dump_drivers_and_constraints(self, driving_path, rig_object):
        """Dump ALL drivers and constraint details for debugging multi-car issues."""
        print(f"  [F1 Lap] 📊 === DRIVER & CONSTRAINT DUMP for {driving_path.name} ===")

        # Object-level drivers
        if driving_path.animation_data:
            drivers = driving_path.animation_data.drivers
            print(f"    Object drivers: {len(drivers)}")
            for drv in drivers:
                targets_info = []
                for var in drv.driver.variables:
                    for t in var.targets:
                        targets_info.append(f"{t.id.name if t.id else 'None'}:{t.data_path}")
                print(f"      {drv.data_path} -> {targets_info}")
        else:
            print(f"    Object animation_data: None")

        # Data-level drivers
        if driving_path.data.animation_data:
            drivers = driving_path.data.animation_data.drivers
            print(f"    Data drivers: {len(drivers)}")
            for drv in drivers:
                targets_info = []
                for var in drv.driver.variables:
                    for t in var.targets:
                        targets_info.append(f"{t.id.name if t.id else 'None'}:{t.data_path}")
                print(f"      {drv.data_path} -> {targets_info}")
        else:
            print(f"    Data animation_data: None")

        # Follow Path constraint details
        try:
            fp = rig_object.pose.bones["bone_find_up_dir"].constraints.get("Follow Path")
            if fp:
                print(f"    Follow Path: target={fp.target.name if fp.target else 'None'}")
                print(f"      use_fixed_location={fp.use_fixed_location}")
                print(f"      use_curve_follow={fp.use_curve_follow}")
                print(f"      offset_factor={fp.offset_factor}")
                print(f"      offset={fp.offset}")
                print(f"      forward_axis={fp.forward_axis}")
                print(f"      up_axis={fp.up_axis}")
        except Exception as e:
            print(f"    Follow Path dump error: {e}")

        # Check ALL drivers on rig armature
        if rig_object.animation_data:
            rig_drivers = rig_object.animation_data.drivers
            if len(rig_drivers) > 0:
                print(f"    Rig drivers: {len(rig_drivers)}")
                for drv in rig_drivers:
                    targets_info = []
                    for var in drv.driver.variables:
                        for t in var.targets:
                            targets_info.append(f"{t.id.name if t.id else 'None'}:{t.data_path}")
                    print(f"      {drv.data_path} -> {targets_info}")

        print(f"  [F1 Lap] 📊 === END DUMP ===")

    def execute(self, context):
        scene = context.scene
        active_car = scene.lc.find_selected()

        # Validation
        if active_car is None:
            show_message_box("No Launch Control vehicle selected.", "Lap from JSON", "ERROR")
            return {"CANCELLED"}

        try:
            driving_path = active_car.driving_path
            rig_object = active_car.rig_object
        except Exception:
            show_message_box("Active vehicle has no rig using LC logic.", "Lap from JSON", "ERROR")
            return {"CANCELLED"}

        path = self.filepath
        if not path or not os.path.isfile(path):
            show_message_box("Invalid File.", "Lap from JSON", "ERROR")
            return {"CANCELLED"}

        # Log which file we're loading for this car
        print(f"  [F1 Lap] 📂 Loading JSON for car '{active_car.name}': {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            show_message_box(f"JSON Error: {e}", "Lap from JSON", "ERROR")
            return {"CANCELLED"}

        points = data.get("points", [])
        if not points:
            show_message_box("JSON has no 'points'.", "Lap from JSON", "ERROR")
            return {"CANCELLED"}

        # Log speed values from JSON to verify they're unique per driver
        speeds = [p.get("speed", 0) for p in points[:5]]
        speeds_end = [p.get("speed", 0) for p in points[-3:]]
        print(f"  [F1 Lap] 📊 JSON speeds (first 5): {speeds}")
        print(f"  [F1 Lap] 📊 JSON speeds (last 3): {speeds_end}")
        print(f"  [F1 Lap] 📊 JSON points[0] xyz: ({points[0]['x']}, {points[0]['y']}, {points[0]['z']})")

        closed = data.get("closed", False) # Default to false for F1 segments often? Or True for laps.

        # 1. Create Curve (unique name per car to avoid collisions)
        car_name = active_car.name if active_car.name else "unknown"
        curve_name = f"LC_LapPath_{car_name}"
        curve_obj = _create_curve_from_points(points, closed, name=curve_name)
        
        # 2. Assign to Car
        props = active_car.properties
        props.custom_path = curve_obj
        
        # 3. Compute Baking Data
        fps = scene.render.fps
        kf_frames, kf_values, total_time = _compute_baking_data(points, closed, fps)
        
        frame_end = round(kf_frames[-1])
        props.frame_custom_path_start = 1
        props.frame_custom_path_end = max(1, frame_end)

        # 4. Prepare Animation (LC standard setup)
        # Select car for context
        bpy.ops.object.select_all(action='DESELECT')
        active_car.rig_object.select_set(True)
        context.view_layer.objects.active = active_car.rig_object

        result = bpy.ops.object.prepare_animation()
        if result != {"FINISHED"}:
            return result

        # 4b. Post-animation diagnostics & fixes
        # Re-read driving_path in case prepare_animation changed references
        driving_path = active_car.driving_path
        self._verify_driving_setup(active_car, rig_object, driving_path)

        # 4c. Comprehensive driver/constraint dump (debug multi-car)
        self._dump_drivers_and_constraints(driving_path, rig_object)

        # 5. Bake Speed Keyframes
        data_path_speed = 'pose.bones["%s"].rotation_euler' % B_SPEED_ROTATE

        # Get Action
        if not rig_object.animation_data:
            rig_object.animation_data_create()
        action = rig_object.animation_data.action

        print(f"  [F1 Lap] 🎬 Baking speed to action: {action.name} on rig: {rig_object.name}")

        # Clear existing
        fc = action.fcurves.find(data_path_speed, index=2)
        if fc: action.fcurves.remove(fc)
        fc = action.fcurves.new(data_path_speed, index=2)

        # Insert Keys
        for f, v in zip(kf_frames, kf_values):
            k = fc.keyframe_points.insert(f, v)
            k.interpolation = 'LINEAR'

        # Log baked keyframe summary
        n_keys = len(fc.keyframe_points)
        if n_keys > 0:
            first_kf = fc.keyframe_points[0]
            last_kf = fc.keyframe_points[n_keys - 1]
            print(f"  [F1 Lap] 📊 Baked {n_keys} keyframes: "
                  f"frame {first_kf.co[0]:.1f}→{last_kf.co[0]:.1f}, "
                  f"value {first_kf.co[1]:.3f}→{last_kf.co[1]:.3f}")
            print(f"  [F1 Lap] 📊 path_duration={driving_path.data.path_duration}, "
                  f"expected_end_value≈{driving_path.data.path_duration / SPEED_ROTATE_SCALE:.3f}")

        # 6. REFRESH PHYSICS (Critical Step — may fail if sim objects are missing)
        try:
            bpy.ops.object.refresh_physics()
        except Exception as e:
            print(f"[F1 Lap] Physics refresh skipped: {e}")

        log_info(f"F1 Lap Applied: {len(points)} points, {total_time:.1f}s", "OBJECT_OT_apply_lap_from_json")
        self.report({'INFO'}, f"F1 Lap Applied: {len(points)} points")
        
        return {"FINISHED"}
