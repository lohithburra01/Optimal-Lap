bl_info = {
    "name": "F1 JSON Baker (Drift Diagnostics)",
    "author": "Lohith Burra",
    "version": (10, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > F1 Data",
    "description": "Exposes GPS Drift and Warp metrics",
    "category": "Animation",
}

import bpy
import sys
import subprocess
import importlib.util
import os
import json
import numpy as np
import tempfile

# --- DEPENDENCIES ---
def setup_deps():
    p = bpy.utils.user_resource("SCRIPTS", path="modules", create=True)
    if p not in sys.path: sys.path.append(p)
    try:
        import fastf1, pandas, scipy
    except:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "fastf1", "pandas", "scipy", "--target", p])

# --- ENGINE ---
def generate_drift_data(year, gp, session_type, drivers, settings):
    setup_deps()
    import fastf1
    from scipy.interpolate import splprep, splev, interp1d
    from scipy.signal import correlate

    # Cache
    cache_dir = os.path.join(tempfile.gettempdir(), "fastf1_cache")
    if not os.path.exists(cache_dir): os.makedirs(cache_dir)
    fastf1.Cache.enable_cache(cache_dir)

    session = fastf1.get_session(year, gp, session_type)
    session.load(telemetry=True, laps=True, weather=False, messages=False)
    
    ref_driver = drivers[0]
    
    def get_clean_telemetry(d):
        try:
            laps = session.laps.pick_driver(d)
            lap = laps.pick_fastest()
            tel = lap.get_telemetry().dropna(subset=['Distance', 'Speed', 'X', 'Y']).drop_duplicates(subset=['Time'])
            return {
                'dist': tel['Distance'].values - tel['Distance'].values[0],
                'speed': tel['Speed'].values / 3.6, # m/s
                'x': tel['X'].values, 
                'y': tel['Y'].values
            }
        except: return None

    ref_data = get_clean_telemetry(ref_driver)
    if not ref_data: return f"Error: No data for {ref_driver}"

    # --- SCALE 1.0 (Real World) ---
    scale = 1.0 
    
    # 1. Master Rail
    tck, u = splprep([ref_data['x']*scale, ref_data['y']*scale], s=100, per=1)
    
    total_len = ref_data['dist'].max() * scale
    num_points = int(total_len / settings['resolution']) 
    u_new = np.linspace(0, 1, num_points)
    x_pts, y_pts = splev(u_new, tck)
    
    base_points = np.column_stack((x_pts, y_pts, np.zeros_like(x_pts)))

    # 2. Process Drivers & Calc Drift
    output_dir = r"C:\Users\91910\Downloads"
    if not os.path.exists(output_dir): 
        output_dir = os.path.join(os.path.expanduser("~"), "Downloads")

    ref_max_dist = ref_data['dist'].max()
    report_msg = []

    for d_idx, d in enumerate(drivers):
        tgt = get_clean_telemetry(d)
        if not tgt: continue

        drift_score = 100.0
        drift_details = "Reference"

        # A. Sync & Drift Calculation
        if d == ref_driver:
            final_dist = tgt['dist']
        else:
            # 1. CALCULATE STRETCH (Scale Drift)
            tgt_max = tgt['dist'].max()
            scale_fac = ref_max_dist / tgt_max
            tgt_scaled = tgt['dist'] * scale_fac
            
            # Metrics:
            dist_diff = abs(ref_max_dist - tgt_max)
            dist_pct = (dist_diff / ref_max_dist) * 100.0
            
            # 2. CALCULATE SLIDE (Phase Shift)
            grid = np.linspace(0, ref_max_dist, 2000)
            v_ref = np.interp(grid, ref_data['dist'], ref_data['speed'])
            v_tgt = np.interp(grid, tgt_scaled, tgt['speed'])
            
            corr = correlate(v_ref, v_tgt, mode='same')
            shift_idx = np.argmax(corr) - 1000
            shift_meters = shift_idx * (ref_max_dist / 2000)
            
            final_dist = tgt_scaled + shift_meters
            
            # 3. SCORING FORMULA
            # Penalty: 1.0 pt per 0.1% length diff, 0.5 pt per 1m shift
            penalty_stretch = dist_pct * 10.0 
            penalty_shift = abs(shift_meters) * 0.5
            
            drift_score = 100.0 - (penalty_stretch + penalty_shift)
            drift_score = max(0.0, drift_score) # Clamp to 0
            
            drift_details = f"Len Δ: {dist_diff:.1f}m ({dist_pct:.2f}%) | Shift: {shift_meters:.1f}m"

        f_speed = interp1d(final_dist, tgt['speed'], kind='linear', fill_value="extrapolate")
        rail_dist_step = ref_max_dist / (num_points - 1)

        # B. Multi-Rail Offset
        offsets_smooth = np.zeros(len(base_points))
        if d_idx > 0: 
            offsets = []
            lookahead = settings['lookahead']
            width = settings['width']         
            for i in range(len(base_points)):
                curr = base_points[i]
                next_i = (i + 1) % len(base_points)
                look_i = (i + lookahead) % len(base_points)
                
                dir_curr = (base_points[next_i] - curr)
                dir_look = (base_points[look_i] - base_points[i])
                
                cross_z = dir_curr[0]*dir_look[1] - dir_curr[1]*dir_look[0]
                turn_dir = np.sign(cross_z)
                curve_mag = abs(cross_z) * 100 
                
                strategy = 1 if ((i // 200) + d_idx) % 2 == 0 else 2
                
                offset = 0.0
                if curve_mag > 0.1:
                    outside = turn_dir * (width * 0.4)
                    apex = -turn_dir * (width * 0.45)
                    t_val = (i % 100) / 100.0
                    
                    if strategy == 1:
                        offset = outside + (apex - outside) * (t_val**3)
                    else:
                        offset = apex + (outside - apex) * (t_val**0.5)
                offsets.append(offset)
            window = 250
            offsets_padded = np.pad(offsets, (window//2, window//2), mode='wrap')
            offsets_smooth = np.convolve(offsets_padded, np.ones(window)/window, mode='valid')

        # C. Build Points
        driver_points = []
        for i in range(len(base_points)):
            next_i = (i + 1) % len(base_points)
            tangent = base_points[next_i] - base_points[i]
            normal = np.array([tangent[1], -tangent[0], 0]) 
            if np.linalg.norm(normal) > 0: normal /= np.linalg.norm(normal)
            
            pos = base_points[i] + (normal * offsets_smooth[i])
            d_loc = i * rail_dist_step
            spd = float(f_speed(d_loc))
            if spd < 1.0: spd = 1.0
            
            driver_points.append({
                "x": round(float(pos[0]), 3),
                "y": round(float(pos[1]), 3),
                "z": 0.0,
                "speed": round(spd, 2)
            })

        print(f"[INFO] {d} Integrity: {drift_score:.1f}% [{drift_details}]")
        report_msg.append(f"{d}: {drift_score:.1f}%")

        # D. Export
        data = {
            "name": f"F1_{d}_{gp}",
            "closed": True,
            "data_confidence": f"{drift_score:.1f}%",
            "drift_diagnostics": drift_details, # <--- Saved for Inspection
            "points": driver_points,
            "launch_control": {
                "speed_unit": "m/s",
                "default_interpolation": "automatic"
            }
        }
        fname = os.path.join(output_dir, f"{d}_lc_path.json")
        with open(fname, 'w') as f: json.dump(data, f, indent=2)
            
    return f"Saved! Drift Scores: {', '.join(report_msg)}"

# --- UI ---
class F1_OT_Gen(bpy.types.Operator):
    bl_idname = "f1.gen_json"
    bl_label = "Generate with Drift Metrics"
    
    def execute(self, context):
        p = context.scene.f1_props
        drivers = [d for d in [p.d1, p.d2, p.d3] if d]
        if not drivers: return {'CANCELLED'}
        
        settings = {'resolution': p.res, 'lookahead': p.lookahead, 'width': p.width}
        msg = generate_drift_data(p.year, p.gp, p.session, drivers, settings)
        self.report({'INFO'}, msg)
        return {'FINISHED'}

class F1_Panel(bpy.types.Panel):
    bl_label = "F1 JSON Baker"
    bl_idname = "PT_F1_Gen"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'F1 Data'
    def draw(self, context):
        p = context.scene.f1_props
        layout = self.layout
        layout.prop(p, "year"); layout.prop(p, "gp"); layout.prop(p, "session")
        layout.label(text="Drivers:")
        layout.prop(p, "d1"); layout.prop(p, "d2"); layout.prop(p, "d3")
        layout.separator()
        layout.label(text="Multi-Rail Settings:")
        layout.prop(p, "res"); layout.prop(p, "width"); layout.prop(p, "lookahead")
        layout.separator()
        layout.operator("f1.gen_json", icon='EXPORT')

class F1_Props(bpy.types.PropertyGroup):
    year: bpy.props.IntProperty(default=2025)
    gp: bpy.props.StringProperty(default="Monaco")
    session: bpy.props.EnumProperty(items=[('Q','Q',''),('R','R','')])
    d1: bpy.props.StringProperty(default="VER")
    d2: bpy.props.StringProperty(default="NOR")
    d3: bpy.props.StringProperty(default="PIA")
    res: bpy.props.FloatProperty(name="Res", default=0.5)
    width: bpy.props.FloatProperty(name="Width", default=6.0)
    lookahead: bpy.props.IntProperty(name="Lookahead", default=70)

def register():
    bpy.utils.register_class(F1_OT_Gen); bpy.utils.register_class(F1_Panel); bpy.utils.register_class(F1_Props)
    bpy.types.Scene.f1_props = bpy.props.PointerProperty(type=F1_Props)
def unregister():
    del bpy.types.Scene.f1_props
    bpy.utils.unregister_class(F1_Props); bpy.utils.unregister_class(F1_Panel); bpy.utils.unregister_class(F1_OT_Gen)

if __name__ == "__main__": register()