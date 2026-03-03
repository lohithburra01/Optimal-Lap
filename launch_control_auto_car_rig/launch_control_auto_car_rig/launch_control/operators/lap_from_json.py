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
        # F1 Requirement: AUTO handles for smooth bezier curves
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'
            
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

    filepath:   bpy.props.StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE", "HIDDEN"})
    curve_name: bpy.props.StringProperty(default="", options={"SKIP_SAVE", "HIDDEN"})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

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
            
        closed = data.get("closed", False) # Default to false for F1 segments often? Or True for laps.

        # 1. Create Curve (AUTO handles)
        name = self.curve_name if self.curve_name else LAP_CURVE_NAME
        curve_obj = _create_curve_from_points(points, closed, name=name)
        
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

        # 5. Bake Speed Keyframes
        data_path_speed = 'pose.bones["%s"].rotation_euler' % B_SPEED_ROTATE
        
        # Get Action
        if not rig_object.animation_data:
            rig_object.animation_data_create()
        action = rig_object.animation_data.action
        
        # Clear existing
        fc = action.fcurves.find(data_path_speed, index=2)
        if fc: action.fcurves.remove(fc)
        fc = action.fcurves.new(data_path_speed, index=2)
        
        # Insert Keys
        for f, v in zip(kf_frames, kf_values):
            k = fc.keyframe_points.insert(f, v)
            k.interpolation = 'LINEAR'
            
        # 6. REFRESH PHYSICS (Critical Step)
        bpy.ops.object.refresh_physics()

        log_info(f"F1 Lap Applied: {len(points)} points, {total_time:.1f}s", "OBJECT_OT_apply_lap_from_json")
        self.report({'INFO'}, f"F1 Lap Applied: {len(points)} points")
        
        return {"FINISHED"}
