import bpy
import sys
import site
import subprocess
import importlib
import math
import numpy as np
import os

# ==========================================
# 1. DEPENDENCY MANAGER
# ==========================================
def get_modules_path():
    return bpy.utils.user_resource("SCRIPTS", path="modules", create=True)

def append_modules_to_sys_path():
    modules_path = get_modules_path()
    if modules_path not in sys.path:
        sys.path.append(modules_path)
        site.addsitedir(modules_path)

def check_dependencies():
    required = ["fastf1", "pandas", "scipy"]
    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    return missing

def install_package(package):
    modules_path = get_modules_path()
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "--target", modules_path, package])
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {package}: {e}")
        return False

# ==========================================
# 2. PATH LOGIC (The Brain)
# ==========================================
def generate_variable_paths(year, gp, session_type, drivers, settings):
    import fastf1
    import pandas as pd
    from scipy.interpolate import splprep, splev, interp1d
    
    # Cache setup
    import tempfile
    cache_dir = os.path.join(tempfile.gettempdir(), "fastf1_cache")
    if not os.path.exists(cache_dir): os.makedirs(cache_dir)
    fastf1.Cache.enable_cache(cache_dir)

    is_testing = settings.get('is_testing', False)
    if is_testing:
        # API: get_testing_session(year, test_number, day) e.g. (2026, 1, 2) = Test 1 Day 2
        test_number = int(settings.get('test_number', 1))
        test_session = int(settings.get('test_session', 1))
        print(f"Fetching Testing for {year} – Test {test_number}, Day {test_session}...")
        try:
            session = fastf1.get_testing_session(year, test_number, test_session)
            session.load(telemetry=True, laps=True, weather=False, messages=False)
        except Exception as e:
            print(f"FastF1 Testing Load Error: {e}")
            return None
    else:
        print(f"Fetching {session_type} for {year} {gp}...")
        try:
            session = fastf1.get_session(year, gp, session_type)
            session.load(telemetry=True, laps=True, weather=False, messages=False)
        except Exception as e:
            print(f"FastF1 Load Error: {e}")
            return None

    ref_driver_name = drivers[0] # First driver is reference
    
    # 2. Get Reference Data
    def get_raw(d):
        try:
            laps = session.laps.pick_driver(d)
            lap = laps.pick_fastest()
            # Drop data with NaN values in critical columns
            tel = lap.get_telemetry().dropna(subset=['Distance', 'Speed', 'X', 'Y']).drop_duplicates(subset=['Time'])
            return {
                'dist': tel['Distance'].values - tel['Distance'].values[0],
                'speed': tel['Speed'].values / 3.6, # Convert km/h to m/s
                'x': tel['X'].values, 
                'y': tel['Y'].values
            }
        except Exception as e: 
            print(f"Error getting data for {d}: {e}")
            return None

    print(f"Getting reference data for {ref_driver_name}...")
    ref_data = get_raw(ref_driver_name)
    if not ref_data: return None

    # 3. Create Base Spline
    # FastF1 coordinates are in METERS. 
    # Blender default scale: 1 unit = 1 meter.
    # However, F1 tracks are huge (5km+). We scale down by 0.1 to keep viewport manageable.
    scale = 0.1 
    rx, ry = ref_data['x'], ref_data['y']
    
    tck, u = splprep([rx * scale, ry * scale], s=100, per=0)
    
    total_len = ref_data['dist'].max() * scale
    num_points = int(total_len / settings['resolution']) # e.g. every 0.5m
    u_new = np.linspace(0, 1, num_points)
    
    base_x, base_y = splev(u_new, tck)
    base_points = np.column_stack((base_x, base_y, np.zeros_like(base_x)))
    
    # Speed Interpolator (Distance -> Speed)
    # We map normalized distance (0-1) to speed
    ref_speed_interp = interp1d(np.linspace(0, 1, len(ref_data['speed'])), ref_data['speed'], kind='linear', fill_value="extrapolate")
    
    results = {}

    # 4. Generate Paths for ALL Drivers
    for d_idx, d_name in enumerate(drivers):
        print(f"Processing path for {d_name} (Index {d_idx})...")
        
        final_path_points = []
        offsets_smooth = np.zeros(len(base_points))

        # Strategic Offset Logic
        if d_idx > 0:
            offsets = []
            lookahead = settings['lookahead']
            width = settings['width'] * scale # Scale width too!
            
            for i in range(len(base_points)):
                # Curvature Calc
                curr = base_points[i]
                next_i = (i + 1) % len(base_points)
                look_i = (i + lookahead) % len(base_points)
                
                dir_curr = (base_points[next_i] - curr)
                dir_look = (base_points[look_i] - base_points[i])
                
                if np.linalg.norm(dir_curr) > 0: dir_curr /= np.linalg.norm(dir_curr)
                if np.linalg.norm(dir_look) > 0: dir_look /= np.linalg.norm(dir_look)
                
                cross_z = dir_curr[0]*dir_look[1] - dir_curr[1]*dir_look[0]
                turn_dir = np.sign(cross_z)
                curve_mag = abs(cross_z) * 100 
                
                # Strategy Switching
                # Driver 1 gets strategy 1, Driver 2 gets strategy 2...
                strategy = 1 if ((i // 200) + d_idx) % 2 == 0 else 2
                
                offset = 0.0
                if curve_mag > 0.1:
                    # Logic from Unity script
                    outside = turn_dir * (width * 0.4)
                    apex = -turn_dir * (width * 0.45)
                    t_val = (i % 100) / 100.0
                    
                    if strategy == 1: # Late Apex
                        offset = outside + (apex - outside) * (t_val**3)
                    else: # Early Apex
                        offset = apex + (outside - apex) * (t_val**0.5)
                
                offsets.append(offset)
            
            # Smooth offsets
            window = 250
            offsets_padded = np.pad(offsets, (window//2, window//2), mode='wrap')
            offsets_smooth = np.convolve(offsets_padded, np.ones(window)/window, mode='valid')

        # Build Points
        for i in range(len(base_points)):
            # Calc Normal
            next_i = (i + 1) % len(base_points)
            tangent = base_points[next_i] - base_points[i]
            normal = np.array([tangent[1], -tangent[0], 0]) # Rotate 90 deg Z
            n_norm = np.linalg.norm(normal)
            if n_norm > 0: normal /= n_norm
            
            # Apply Offset
            pos = base_points[i] + (normal * offsets_smooth[i])
            
            # Get Speed (Rubber banding: Use reference speed for everyone for now to keep them close)
            # In a real race they separate, but for comparison we want them relatively synced
            # or we can try to fetch individual speeds. 
            # For "Rubber Banding to Ref", we use Reference Speed.
            u_val = i / len(base_points)
            spd = float(ref_speed_interp(u_val))
            
            final_path_points.append({
                "x": pos[0], "y": pos[1], "z": 0.0,
                "speed": spd
            })
            
        results[d_name] = final_path_points
        
    return results

# ==========================================
# 3. OPERATORS
# ==========================================

class F1_OT_AddDriver(bpy.types.Operator):
    bl_idname = "f1.add_driver"
    bl_label = "Add Driver"
    
    def execute(self, context):
        props = context.scene.f1_lc_props
        item = props.drivers_list.add()
        item.name = "NEW"
        return {'FINISHED'}

class F1_OT_RemoveDriver(bpy.types.Operator):
    bl_idname = "f1.remove_driver"
    bl_label = "Remove Driver"
    
    def execute(self, context):
        props = context.scene.f1_lc_props
        if props.driver_index >= 0 and len(props.drivers_list) > props.driver_index:
            props.drivers_list.remove(props.driver_index)
            props.driver_index = max(0, props.driver_index - 1)
        return {'FINISHED'}

class F1_OT_InstallDeps(bpy.types.Operator):
    bl_idname = "f1.install_deps_lc"
    bl_label = "Install Dependencies"
    
    def execute(self, context):
        append_modules_to_sys_path()
        missing = check_dependencies()
        if not missing:
            self.report({'INFO'}, "All dependencies already installed.")
            return {'FINISHED'}
        
        for pkg in missing:
            self.report({'INFO'}, f"Installing {pkg}...")
            if not install_package(pkg):
                self.report({'ERROR'}, f"Failed to install {pkg}. Check console.")
                return {'CANCELLED'}
        
        self.report({'INFO'}, "Dependencies installed! You may need to restart Blender.")
        return {'FINISHED'}

class F1_OT_CompareLaps(bpy.types.Operator):
    bl_idname = "f1.compare_laps"
    bl_label = "Compare Laps"
    
    def execute(self, context):
        props = context.scene.f1_lc_props
        
        # 1. Validation
        if len(props.drivers_list) == 0:
            self.report({'ERROR'}, "Add at least 1 driver to compare!")
            return {'CANCELLED'}
            
        drivers_data = [] # List of (name, target_car_obj)
        drivers_names = []
        
        for item in props.drivers_list:
            if not item.target_car:
                 self.report({'ERROR'}, f"Assign a Target Car for driver {item.name}")
                 return {'CANCELLED'}
            drivers_data.append((item.name, item.target_car))
            drivers_names.append(item.name)

        # 2. Check Deps
        append_modules_to_sys_path()
        if check_dependencies():
            self.report({'ERROR'}, "Install Dependencies first!")
            return {'CANCELLED'}
            
        # 3. Calculate Paths
        settings = {
            'resolution': props.resolution, 
            'width': props.track_width,   
            'lookahead': props.lookahead 
        }
        
        self.report({'INFO'}, f"Fetching data for {drivers_names}...")
        
        try:
            # Returns dict: {'VER': [{'x':..., 'speed':...}, ...], 'NOR': ...}
            paths = generate_variable_paths(props.year, props.gp, props.session, drivers_names, settings)
        except Exception as e:
            self.report({'ERROR'}, f"Calculation Failed: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}
            
        if not paths: return {'CANCELLED'}
        
        # 4. Blender Automation (The Heartbeat)
        fps = context.scene.render.fps
        
        for d_name, car_obj in drivers_data:
            if d_name not in paths: continue
            
            points = paths[d_name]
            
            # A. Create Curve Object
            curve_name = f"F1_Path_{d_name}"
            if curve_name in bpy.data.objects:
                bpy.data.objects.remove(bpy.data.objects[curve_name], do_unlink=True)
            
            curve_data = bpy.data.curves.new(curve_name, type='CURVE')
            curve_data.dimensions = '3D'
            spline = curve_data.splines.new('POLY')
            spline.points.add(len(points)-1)
            
            for i, p in enumerate(points):
                spline.points[i].co = (p['x'], p['y'], p['z'], 1)
                
            path_obj = bpy.data.objects.new(curve_name, curve_data)
            context.collection.objects.link(path_obj)
            
            # B. Assign to Car
            # Assuming 'car_obj' is the Empty/Parent. Launch Control properties are on this object.
            # We need to find the 'rig_object' which is usually a child or defined in properties.
            # But wait, looking at Launch Control code, 'active_car' usually refers to the collection wrapper.
            # The user selected an Object in the pointer property. 
            # We assume they selected the Car ROOT object (the one with 'launch_control' props).
            
            if not hasattr(car_obj, "properties"):
                self.report({'WARNING'}, f"{car_obj.name} is not a valid Launch Control car root!")
                continue
                
            car_obj.properties.custom_path = path_obj
            
            # C. Bake Animation (Speed Profile)
            # Find Rig
            rig_obj = None
            if hasattr(car_obj, "rig_object"): # LC 1.9+ often has this pointer
                rig_obj = car_obj.rig_object
            
            if not rig_obj:
                # Fallback: look for children
                for child in car_obj.children:
                    if child.type == 'ARMATURE':
                        rig_obj = child
                        break
            
            if not rig_obj:
                self.report({'WARNING'}, f"Could not find Rig for {car_obj.name}")
                continue
                
            # Prepare Animation (Basic setup)
            # We need to select the car to run the operator? 
            # Or just duplicate logic? Calling operator is safer for dependencies.
            bpy.ops.object.select_all(action='DESELECT')
            car_obj.select_set(True)
            context.view_layer.objects.active = car_obj
            
            # This LC operator sets up constraints and drivers
            bpy.ops.object.prepare_animation()
            
            # Override Keyframes
            action = rig_obj.animation_data.action
            if not action:
                action = bpy.data.actions.new(name=f"F1_Action_{d_name}")
                rig_obj.animation_data.action = action
                
            data_path = 'pose.bones["bone_Speed_Rotate"].rotation_euler'
            
            # Clear old
            fcurve = action.fcurves.find(data_path, index=2)
            if fcurve: action.fcurves.remove(fcurve)
            fcurve = action.fcurves.new(data_path, index=2)
            
            # Calculate Timings
            total_dist = 0.0
            total_time = 0.0
            SPEED_ROTATE_SCALE = 9.99
            
            # Frames and Values
            kf_frames = []
            kf_values = []
            
            # Start at 0
            kf_frames.append(1.0)
            kf_values.append(0.0)
            
            for i in range(1, len(points)):
                p1 = points[i-1]
                p2 = points[i]
                dist = math.sqrt((p2['x']-p1['x'])**2 + (p2['y']-p1['y'])**2)
                
                total_dist += dist
                
                v_avg = (p1['speed'] + p2['speed']) / 2.0
                if v_avg < 0.1: v_avg = 0.1
                
                dt = dist / v_avg
                total_time += dt
                
                frame = 1.0 + (total_time * fps)
                val = total_dist / SPEED_ROTATE_SCALE
                
                kf_frames.append(frame)
                kf_values.append(val)
                
            # Batch Insert
            # fcurve.keyframe_points.add(len(kf_frames)) # Optimization if needed
            for f, v in zip(kf_frames, kf_values):
                k = fcurve.keyframe_points.insert(f, v)
                k.interpolation = 'LINEAR'
                
            # Update Frame Range on Car
            car_obj.properties.frame_custom_path_start = 1
            car_obj.properties.frame_custom_path_end = int(kf_frames[-1])
            
            self.report({'INFO'}, f"Baked {d_name}: {int(kf_frames[-1])} frames")
            
        # 5. Global Physics Update
        bpy.ops.object.refresh_physics()
        
        return {'FINISHED'}
