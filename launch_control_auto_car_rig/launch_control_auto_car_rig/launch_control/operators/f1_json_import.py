import bpy
import json
import math
import os
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator
from bpy.props import StringProperty

class F1_OT_ImportPath(Operator, ImportHelper):
    bl_idname = "f1.import_path"
    bl_label = "Import F1 Path"
    bl_description = "Import F1 Telemetry JSON and apply to selected car"
    
    filter_glob: StringProperty(
        default="*.json",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        filepath = self.filepath
        if not os.path.exists(filepath):
            self.report({'ERROR'}, "File not found!")
            return {'CANCELLED'}

        # 1. Load JSON
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read JSON: {e}")
            return {'CANCELLED'}

        points = data.get('points', [])
        if not points:
            self.report({'ERROR'}, "JSON contains no 'points' data")
            return {'CANCELLED'}

        # 2. Get Selected Car
        # We assume the user has selected the Car Root Object (collection instance or empty)
        car_obj = context.active_object
        if not car_obj:
            self.report({'ERROR'}, "No object selected! Select a Launch Control car.")
            return {'CANCELLED'}

        # Check if it's a valid LC car (has properties)
        if not hasattr(car_obj, "properties") or not hasattr(car_obj, "lc_car_id"):
             # Try to find parent if user selected a part
             if car_obj.parent and hasattr(car_obj.parent, "properties"):
                 car_obj = car_obj.parent
             else:
                 self.report({'WARNING'}, "Selected object may not be a valid Launch Control Car Root. Tread carefully.")

        # 3. Generate Bezier Curve
        curve_name = f"F1_Path_{data.get('name', 'Imported')}"
        
        # Cleanup existing
        if curve_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[curve_name], do_unlink=True)
            
        curve_data = bpy.data.curves.new(curve_name, type='CURVE')
        curve_data.dimensions = '3D'
        curve_data.resolution_u = 4 # Standard resolution
        
        spline = curve_data.splines.new('BEZIER')
        spline.bezier_points.add(len(points) - 1)
        
        for i, p in enumerate(points):
            bp = spline.bezier_points[i]
            bp.co = (p['x'], p['y'], p['z'])
            bp.handle_left_type = 'AUTO'
            bp.handle_right_type = 'AUTO'
            
        path_obj = bpy.data.objects.new(curve_name, curve_data)
        context.collection.objects.link(path_obj)
        
        # 4. Assign Path
        car_obj.properties.custom_path = path_obj
        
        # 5. Bake Speed Keyframes
        self.bake_speed_profile(context, car_obj, points)
        
        # 6. Refresh Physics
        bpy.ops.object.refresh_physics()
        
        self.report({'INFO'}, f"imported {len(points)} points & baked speed.")
        return {'FINISHED'}

    def bake_speed_profile(self, context, car_obj, points):
        # find rig
        rig_obj = None
        if hasattr(car_obj, "rig_object") and car_obj.rig_object:
            rig_obj = car_obj.rig_object
        else:
            # Fallback search
            for child in car_obj.children:
                if child.type == 'ARMATURE':
                    rig_obj = child
                    break
        
        if not rig_obj:
            self.report({'ERROR'}, "Could not find Rig Object!")
            return

        # Prepare Animation (Standard LC setup)
        # Select car to ensure operator works
        bpy.ops.object.select_all(action='DESELECT')
        car_obj.select_set(True)
        context.view_layer.objects.active = car_obj
        
        bpy.ops.object.prepare_animation()

        # Get Action
        if not rig_obj.animation_data:
            rig_obj.animation_data_create()
            
        action = rig_obj.animation_data.action
        if not action:
            action = bpy.data.actions.new(name=f"F1_Bake_{car_obj.name}")
            rig_obj.animation_data.action = action

        # Target Bone: bone_Speed_Rotate (Z Axis)
        data_path = 'pose.bones["bone_Speed_Rotate"].rotation_euler'
        
        # Clear existing curves
        fcurve = action.fcurves.find(data_path, index=2)
        if fcurve:
            action.fcurves.remove(fcurve)
        
        fcurve = action.fcurves.new(data_path, index=2)
        
        # Calculate Baking Data
        fps = context.scene.render.fps
        SPEED_ROTATE_SCALE = 9.99
        
        total_dist = 0.0
        total_time = 0.0
        
        kf_frames = [1.0] # Start at frame 1
        kf_values = [0.0]
        
        for i in range(1, len(points)):
            p1 = points[i-1]
            p2 = points[i]
            
            # Distance
            dist = math.sqrt((p2['x']-p1['x'])**2 + (p2['y']-p1['y'])**2 + (p2['z']-p1['z'])**2)
            total_dist += dist
            
            # Speed (Average)
            v_avg = (p1.get('speed', 10.0) + p2.get('speed', 10.0)) / 2.0
            if v_avg < 0.1: v_avg = 0.1
            
            # Time
            dt = dist / v_avg
            total_time += dt
            
            # Result
            frame = 1.0 + (total_time * fps)
            val = total_dist / SPEED_ROTATE_SCALE
            
            kf_frames.append(frame)
            kf_values.append(val)
            
        # Batch insert
        # We can perform simple loop insertion
        for f, v in zip(kf_frames, kf_values):
            k = fcurve.keyframe_points.insert(f, v)
            k.interpolation = 'LINEAR'
            
        # Update Car Range
        car_obj.properties.frame_custom_path_start = 1
        car_obj.properties.frame_custom_path_end = int(kf_frames[-1])
