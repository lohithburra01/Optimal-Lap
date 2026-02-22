bl_info = {
    "name": "F1 Pro Replay (Rubber-Band)",
    "author": "Lohith Burra",
    "version": (5, 1),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > F1 Track Tab",
    "description": "Direct FastF1 to Blender Animation using Rubber-Band Physics",
    "category": "Animation",
}

import bpy
import sys
import site
import subprocess
import importlib.util
import os
import math
import tempfile # <--- ADDED THIS

# ==========================================
# 1. DEPENDENCY MANAGER
# ==========================================
def get_modules_path():
    return bpy.utils.user_resource("SCRIPTS", path="modules", create=True)

def append_modules_to_sys_path(modules_path):
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

def install_package(package, modules_path):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "--target", modules_path, package])
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {package}: {e}")
        return False

# ==========================================
# 2. THE ENGINE (Rubber-Band Delta + Spline)
# ==========================================
def run_physics_engine(year, gp, session_type, driver_names):
    import fastf1
    import numpy as np
    import pandas as pd
    from scipy.interpolate import interp1d, splprep, splev
    from scipy.signal import correlate

    # --- FIX: USE TEMP DIR INSTEAD OF BLENDER CACHE ---
    cache_dir = os.path.join(tempfile.gettempdir(), "fastf1_cache")
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    
    fastf1.Cache.enable_cache(cache_dir)
    # --------------------------------------------------

    session = fastf1.get_session(year, gp, session_type)
    session.load(telemetry=True, laps=True, weather=False, messages=False)
    
    ref_driver = driver_names[0]
    
    def get_raw(d_code):
        try:
            laps = session.laps.pick_driver(d_code)
            lap = laps.pick_fastest()
            tel = lap.get_telemetry().dropna(subset=['Distance', 'Speed', 'X', 'Y']).drop_duplicates(subset=['Time'])
            
            dist = tel['Distance'].values
            dist -= dist[0]
            
            return {
                'dist': dist,
                'speed': tel['Speed'].values / 3.6, # m/s
                'time': tel['Time'].dt.total_seconds().values,
                'x': tel['X'].values, 'y': tel['Y'].values,
                'total_time': lap['LapTime'].total_seconds(),
                'code': d_code
            }
        except: return None

    ref_raw = get_raw(ref_driver)
    if not ref_raw: return None, None

    # Reference Rail (Spline)
    rx, ry = ref_raw['x'], ref_raw['y']
    cx, cy = np.mean(rx), np.mean(ry)
    tck, u = splprep([(rx - cx)*0.1, (ry - cy)*0.1], s=100, per=0)

    # Rubber-Band Physics
    final_data = {}
    
    final_data[ref_driver] = {
        'prog': interp1d(ref_raw['time'], ref_raw['dist'] / ref_raw['dist'].max(), fill_value="extrapolate"),
        'total_time': ref_raw['total_time']
    }
    
    ref_max = ref_raw['dist'].max()

    for d in driver_names:
        if d == ref_driver: continue
        tgt_raw = get_raw(d)
        if not tgt_raw: continue

        scale = ref_max / tgt_raw['dist'].max()
        tgt_scaled = tgt_raw['dist'] * scale
        
        grid = np.linspace(0, ref_max, 2000)
        v_ref = np.interp(grid, ref_raw['dist'], ref_raw['speed'])
        v_tgt = np.interp(grid, tgt_scaled, tgt_raw['speed'])
        
        corr = correlate(v_ref, v_tgt, mode='same')
        shift = (np.argmax(corr) - 1000) * (ref_max / 2000)
        
        warped_dist = tgt_scaled + shift
        
        final_data[d] = {
            'prog': interp1d(tgt_raw['time'], warped_dist / ref_max, fill_value="extrapolate"),
            'total_time': tgt_raw['total_time']
        }

    return final_data, tck

# ==========================================
# 3. THE BUILDER
# ==========================================

class F1_OT_GenerateAnimation(bpy.types.Operator):
    bl_idname = "f1.generate_anim"
    bl_label = "Generate Animation"
    bl_description = "Calculate Delta & Animate Selected Objects"
    
    def execute(self, context):
        props = context.scene.f1_props
        
        modules_path = get_modules_path()
        append_modules_to_sys_path(modules_path)
        if check_dependencies():
            self.report({'ERROR'}, "Dependencies missing. Click Install first.")
            return {'CANCELLED'}

        import numpy as np
        from scipy.interpolate import splev

        driver_inputs = []
        if props.d1_name and props.d1_obj: driver_inputs.append((props.d1_name, props.d1_obj))
        if props.d2_name and props.d2_obj: driver_inputs.append((props.d2_name, props.d2_obj))
        if props.d3_name and props.d3_obj: driver_inputs.append((props.d3_name, props.d3_obj))
        
        if not driver_inputs:
            self.report({'ERROR'}, "Please assign at least one Driver Name and Object.")
            return {'CANCELLED'}

        driver_names = [d[0] for d in driver_inputs]

        self.report({'INFO'}, "Calculating Physics...")
        try:
            data, tck = run_physics_engine(props.year, props.gp, props.session, driver_names)
        except Exception as e:
            self.report({'ERROR'}, f"FastF1 Error: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        if not data: return {'CANCELLED'}

        fps = 30
        bpy.context.scene.render.fps = fps
        max_t = max(d['total_time'] for d in data.values())
        bpy.context.scene.frame_end = int(max_t * fps)
        
        self.report({'INFO'}, "Baking Keyframes...")

        for d_name, d_obj in driver_inputs:
            if d_name not in data: continue
            
            d_data = data[d_name]
            
            # Create Ghost
            ghost_name = f"Ghost_{d_name}"
            if ghost_name in bpy.data.objects:
                bpy.data.objects.remove(bpy.data.objects[ghost_name], do_unlink=True)
                
            bpy.ops.object.empty_add(type='PLAIN_AXES', radius=0.5)
            ghost = bpy.context.active_object
            ghost.name = ghost_name
            ghost.hide_viewport = True
            
            for f in range(1, bpy.context.scene.frame_end, 1):
                t = f / fps
                if t > d_data['total_time']: continue
                
                prog = float(d_data['prog'](t))
                px, py = splev(np.clip(prog, 0, 1), tck)
                
                prog_future = float(d_data['prog'](t + 0.16))
                gx, gy = splev(np.clip(prog_future, 0, 1), tck)
                
                d_obj.location = (px, py, 0)
                d_obj.keyframe_insert(data_path="location", frame=f)
                
                ghost.location = (gx, gy, 0)
                ghost.keyframe_insert(data_path="location", frame=f)

            # Apply Constraint
            for c in d_obj.constraints:
                if c.type == 'DAMPED_TRACK': d_obj.constraints.remove(c)
            
            const = d_obj.constraints.new('DAMPED_TRACK')
            const.target = ghost
            const.track_axis = 'TRACK_NEGATIVE_Y' 
            const.influence = 1.0

        self.report({'INFO'}, "Animation Complete!")
        return {'FINISHED'}

class F1_OT_InstallDeps(bpy.types.Operator):
    bl_idname = "f1.install_deps"
    bl_label = "Install Dependencies"
    
    def execute(self, context):
        path = get_modules_path()
        append_modules_to_sys_path(path)
        missing = check_dependencies()
        for pkg in missing:
            install_package(pkg, path)
        return {'FINISHED'}

# ==========================================
# 4. UI PANEL
# ==========================================

class F1_Properties(bpy.types.PropertyGroup):
    year: bpy.props.IntProperty(name="Year", default=2025)
    gp: bpy.props.StringProperty(name="Grand Prix", default="Monaco")
    session: bpy.props.EnumProperty(name="Session", items=[('Q','Quali',''),('R','Race',''),('SQ','Sprint','')])
    
    d1_name: bpy.props.StringProperty(name="Name", default="VER")
    d1_obj: bpy.props.PointerProperty(name="Model", type=bpy.types.Object)
    
    d2_name: bpy.props.StringProperty(name="Name", default="NOR")
    d2_obj: bpy.props.PointerProperty(name="Model", type=bpy.types.Object)
    
    d3_name: bpy.props.StringProperty(name="Name", default="PIA")
    d3_obj: bpy.props.PointerProperty(name="Model", type=bpy.types.Object)

class VIEW3D_PT_F1Panel(bpy.types.Panel):
    bl_label = "F1 Pro Replay"
    bl_idname = "VIEW3D_PT_f1_replay"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'F1 Track Tab'

    def draw(self, context):
        layout = self.layout
        props = context.scene.f1_props
        
        missing = check_dependencies()
        if missing:
            layout.operator("f1.install_deps", icon='IMPORT', text="Install Requirements")
        else:
            layout.label(text="System Ready", icon='CHECKMARK')

        box = layout.box()
        box.label(text="Query")
        box.prop(props, "year")
        box.prop(props, "gp")
        box.prop(props, "session")
        
        box = layout.box()
        box.label(text="Driver Setup")
        
        def draw_slot(name_prop, obj_prop, label):
            row = box.row()
            row.label(text=label)
            split = row.split(factor=0.3)
            split.prop(props, name_prop, text="")
            split.prop(props, obj_prop, text="")

        draw_slot("d1_name", "d1_obj", "Ref:")
        draw_slot("d2_name", "d2_obj", "Dr 2:")
        draw_slot("d3_name", "d3_obj", "Dr 3:")
        
        layout.separator()
        layout.operator("f1.generate_anim", icon='PLAY', text="Bake Animation")

classes = (
    F1_Properties,
    F1_OT_InstallDeps,
    F1_OT_GenerateAnimation,
    VIEW3D_PT_F1Panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.f1_props = bpy.props.PointerProperty(type=F1_Properties)
    path = get_modules_path()
    append_modules_to_sys_path(path)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.f1_props

if __name__ == "__main__":
    register()