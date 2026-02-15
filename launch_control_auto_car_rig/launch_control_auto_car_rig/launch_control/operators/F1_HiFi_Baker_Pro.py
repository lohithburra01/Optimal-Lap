
import bpy
import sys
import subprocess
import os
import json
import numpy as np
import tempfile
import warnings
import importlib.util

# ==============================================================================
# 1. DEPENDENCY HANDLING (SAFE MODE)
# ==============================================================================
def check_dependencies():
    required = {"fastf1": "fastf1", "pandas": "pandas", "scipy": "scipy", "numpy": "numpy"}
    missing = []
    for import_name, package_name in required.items():
        if importlib.util.find_spec(import_name) is None:
            missing.append(package_name)
    return missing

MISSING_DEPS = check_dependencies()

try:
    if not MISSING_DEPS:
        import fastf1
        import pandas as pd
        from scipy.interpolate import interp1d, splprep, splev
        from scipy.signal import correlate, medfilt
        warnings.simplefilter(action='ignore')
except Exception as e:
    print(f"F1 Baker: Dependencies present but import failed: {e}")
    MISSING_DEPS = ["Import Error - Check Console"]

# ==============================================================================
# 2. INSTALLATION OPERATOR
# ==============================================================================
class F1_OT_InstallDeps(bpy.types.Operator):
    bl_idname = "f1.install_deps"
    bl_label = "Install Required Libraries"
    bl_description = "Installs fastf1, pandas, and scipy. Blender may freeze for 30s."

    def execute(self, context):
        p = os.path.join(bpy.utils.user_resource("SCRIPTS"), "modules")
        if not os.path.exists(p): os.makedirs(p)
        
        import ensurepip
        ensurepip.bootstrap()
        
        deps = ["fastf1", "pandas", "scipy", "numpy", "requests", "timple", "requests-cache"]
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *deps, "--target", p])
            global MISSING_DEPS
            importlib.invalidate_caches()
            MISSING_DEPS = check_dependencies()
            
            if not MISSING_DEPS:
                global fastf1, pd, interp1d, splprep, splev, correlate, medfilt
                import fastf1
                import pandas as pd
                from scipy.interpolate import interp1d, splprep, splev
                from scipy.signal import correlate, medfilt
                self.report({'INFO'}, "Installation Complete! Restart advised.")
            else:
                self.report({'WARNING'}, "Installation finished but modules missing.")
        except Exception as e:
            self.report({'ERROR'}, f"Installation Failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

# ==============================================================================
# 3. CORE MATH ENGINE
# ==============================================================================
INTEGRITY_TAU = 5
INTEGRITY_P = 1.5
INTEGRITY_LAMBDA = 700

def calculate_integrity_score(length_offset_m, shift_offset_m):
    total_offset = length_offset_m + shift_offset_m
    effective = max(0, total_offset - INTEGRITY_TAU)
    score = 100.0 * np.exp(-(effective ** INTEGRITY_P) / INTEGRITY_LAMBDA)
    
    if score >= 95:    grade = "Excellent"
    elif score >= 85:  grade = "Good"
    elif score >= 70:  grade = "Acceptable"
    elif score >= 50:  grade = "Warning"
    else:              grade = "Critical"
    
    return {'score': round(score, 1), 'grade': grade}

def calculate_fidelity(scale, local_shifts, track_len, raw_d, smooth_d, lap_time, drift):
    step1 = abs(scale - 1.0) * 100
    step2 = (np.sqrt(np.mean(np.array(local_shifts)**2)) / track_len) * 100 if len(local_shifts) > 0 else 0.0
    diff = smooth_d - raw_d
    step3 = (np.sqrt(np.mean(diff**2)) / lap_time) * 100
    step4 = (abs(drift) / lap_time) * 100
    total = step1 + step2 + step3 + step4
    return {'fidelity': round(100.0 - total, 3)}

def get_clean_trace(session, driver):
    try:
        laps = session.laps.pick_drivers(driver)
        if laps.empty: return None
        lap = laps.pick_fastest()
        tel = lap.get_telemetry().dropna(subset=['Distance', 'Speed', 'X', 'Y']).drop_duplicates(subset=['Time'])
        tel = tel.drop_duplicates(subset=['Distance'])
        return {
            'dist': tel['Distance'].values, 'speed': tel['Speed'].values, 
            'time': tel['Time'].dt.total_seconds().values, 'driver': driver,
            'lap_time': lap['LapTime'].total_seconds(), 'x': tel['X'].values, 'y': tel['Y'].values
        }
    except: return None

def calculate_hifi_delta(ref, tgt):
    master_len = ref['dist'].max()
    tgt_max_dist = tgt['dist'].max()
    if master_len == 0 or tgt_max_dist == 0: return None, None, {}

    scale = master_len / tgt_max_dist
    tgt_dist_scaled = tgt['dist'] * scale
    length_offset_m = abs(master_len - tgt_max_dist)

    window_size = 300; step_size = 50 
    grid_len = 10000; common_grid = np.linspace(0, master_len, grid_len)
    
    v_ref = np.interp(common_grid, ref['dist'], ref['speed'])
    v_tgt = np.interp(common_grid, tgt_dist_scaled, tgt['speed'])
    
    shifts = []; positions = []
    for start_pos in range(0, int(master_len), step_size):
        end_pos = start_pos + window_size
        if end_pos > master_len: break
        idx_start = int((start_pos / master_len) * grid_len)
        idx_end = int((end_pos / master_len) * grid_len)
        c_ref = v_ref[idx_start:idx_end]
        c_tgt = v_tgt[idx_start:idx_end]
        if len(c_ref) == 0: continue
        
        corr = correlate(c_ref - np.mean(c_ref), c_tgt - np.mean(c_tgt), mode='same')
        if len(corr) == 0: continue
        lag_idx = np.argmax(corr) - (len(corr) // 2)
        shift_m = lag_idx * (master_len / grid_len)
        if abs(shift_m) < 40:
            shifts.append(shift_m); positions.append(start_pos + window_size/2)

    # Global shift
    v_ref_f = (v_ref - np.mean(v_ref)) / (np.std(v_ref) + 1e-6)
    v_tgt_f = (v_tgt - np.mean(v_tgt)) / (np.std(v_tgt) + 1e-6)
    corr_f = correlate(v_ref_f, v_tgt_f, mode='same')
    global_lag = np.argmax(corr_f) - (len(corr_f) // 2)
    shift_offset_m = abs(global_lag * (master_len / grid_len))

    local_shifts_applied = []
    if positions:
        if positions[0] > 0: positions.insert(0, 0); shifts.insert(0, shifts[0])
        if positions[-1] < master_len: positions.append(master_len); shifts.append(shifts[-1])
        sorted_pairs = sorted(zip(positions, shifts))
        positions, shifts = zip(*sorted_pairs)
        shift_interp = interp1d(positions, shifts, kind='linear', fill_value="extrapolate")
        local_shifts_applied = shift_interp(tgt_dist_scaled).tolist()
        tgt_dist_warped = tgt_dist_scaled + shift_interp(tgt_dist_scaled)
    else:
        tgt_dist_warped = tgt_dist_scaled

    f_tgt_time = interp1d(tgt_dist_warped, tgt['time'], fill_value="extrapolate")
    tgt_time_mapped = f_tgt_time(ref['dist'])
    raw_delta = tgt_time_mapped - ref['time']
    delta_smooth = medfilt(raw_delta, kernel_size=15)
    delta_zeroed = delta_smooth - delta_smooth[0]
    raw_delta_zeroed = raw_delta - raw_delta[0]

    drift = delta_zeroed[-1] - (tgt['lap_time'] - ref['lap_time'])
    ramp = np.linspace(0, 1, len(delta_zeroed))
    final_delta = delta_zeroed - (ramp * drift)

    integrity = calculate_integrity_score(length_offset_m, shift_offset_m)
    fidelity = calculate_fidelity(scale, local_shifts_applied, master_len, raw_delta_zeroed, delta_zeroed, ref['lap_time'], drift)
    
    metrics = {'integrity': integrity, 'fidelity': fidelity}
    return ref['dist'], final_delta, metrics

# ==============================================================================
# 4. MULTI-RAIL GENERATOR (ANALYTICAL DERIVATIVES)
# ==============================================================================
def generate_multirail_data(year, gp, session_type, drivers, settings):
    if MISSING_DEPS: return "Error: Missing Deps", {}

    # Define temp data path
    # Using the local project folder's temp_data if accessible, or system temp
    # The requirement says "Stores the generated telemetry JSONs... local temp_data folder"
    # Project root is c:/Users/91910/Downloads/F1_Builder_Context/F1_Pipeline_Assets/temp_data
    # But this script is inside the addon. We need to pass the output path or infer it.
    # For now, I will use the passed 'output_dir' if I add it to settings, or default to temp.
    # I'll stick to the original logic but update the output path.
    
    # We will use the system temp for cache, but we need to target the F1_Pipeline_Assets/temp_data for output
    cache_dir = os.path.join(tempfile.gettempdir(), "fastf1_cache")
    if not os.path.exists(cache_dir): os.makedirs(cache_dir)
    fastf1.Cache.enable_cache(cache_dir)

    print(f"Loading {year} {gp}...")
    try:
        session = fastf1.get_session(year, gp, session_type)
        session.load(telemetry=True, laps=True, weather=False, messages=False)
    except Exception as e:
        return f"FastF1 Error: {e}", {}
    
    ref_driver = drivers[0]
    ref_data = get_clean_trace(session, ref_driver)
    if not ref_data: return "Error: No Ref Data", {}

    ref_data['time'] -= ref_data['time'][0]
    
    # --- SMOOTH SPLINE GEOMETRY ---
    scale_geo = 0.1 
    path_x = ref_data['x'] * scale_geo
    path_y = ref_data['y'] * scale_geo
    cx, cy = np.mean(path_x), np.mean(path_y)
    path_x -= cx
    path_y -= cy

    # Lock Physics to Distance
    u_vals = ref_data['dist'] / ref_data['dist'].max()
    smooth_factor = len(path_x) * 10 # Strong smoothing for GPS jitter
    
    is_closed = np.linalg.norm(np.array([path_x[0], path_y[0]]) - np.array([path_x[-1], path_y[-1]])) < 50
    
    try:
        tck, u = splprep([path_x, path_y], u=u_vals, k=3, s=smooth_factor, per=1 if is_closed else 0)
    except:
        tck, u = splprep([path_x, path_y], s=len(path_x), per=0)

    # --- KEY FIX: ANALYTICAL DERIVATIVES ---
    total_len_geo = ref_data['dist'].max() * scale_geo
    num_points = int(total_len_geo / settings['resolution'])
    u_new = np.linspace(0, 1, num_points)
    
    # 0th Derivative (Position)
    x_pts, y_pts = splev(u_new, tck)
    # 1st Derivative (Velocity/Tangent) - GUARANTEES SMOOTHNESS
    dx_pts, dy_pts = splev(u_new, tck, der=1)
    
    base_points = np.column_stack((x_pts, y_pts, np.zeros_like(x_pts)))
    
    # Recalculate physical distance
    segment_lengths = np.sqrt(np.sum(np.diff(base_points, axis=0)**2, axis=1))
    actual_total_len = np.sum(segment_lengths)
    rail_dist_step = actual_total_len / (num_points - 1) 

    # --- CURVATURE OFFSETS ---
    lookahead = settings['lookahead']
    width = settings['width']
    offsets_list_L = []
    offsets_list_R = []
    
    for i in range(len(base_points)):
        # Calculate curvature using smooth derivatives
        look_i = (i + lookahead) % len(base_points)
        
        # Tangent at current and lookahead
        tan_curr = np.array([dx_pts[i], dy_pts[i]])
        tan_look = np.array([dx_pts[look_i], dy_pts[look_i]])
        
        # Normalize for cross product check
        if np.linalg.norm(tan_curr) > 0: tan_curr /= np.linalg.norm(tan_curr)
        if np.linalg.norm(tan_look) > 0: tan_look /= np.linalg.norm(tan_look)
        
        cross_z = tan_curr[0]*tan_look[1] - tan_curr[1]*tan_look[0]
        turn_dir = np.sign(cross_z)
        curve_mag = abs(cross_z) * 10 
        
        offset_L = 0.0; offset_R = 0.0
        if curve_mag > 0.1:
            outside = turn_dir * (width * 0.4)
            apex = -turn_dir * (width * 0.45)
            t_val = (i % 100) / 100.0
            offset_L = outside + (apex - outside) * (t_val**3)
            offset_R = apex + (outside - apex) * (t_val**0.5)
            
        offsets_list_L.append(offset_L)
        offsets_list_R.append(offset_R)

    # Smooth offsets (Window adjusted for high res)
    window = 400 
    def smooth_arr(arr):
        padded = np.pad(arr, (window//2, window//2), mode='wrap')
        return np.convolve(padded, np.ones(window)/window, mode='valid')
    
    smooth_L = smooth_arr(offsets_list_L)
    smooth_R = smooth_arr(offsets_list_R)

    # --- EXPORT ---
    # output_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    # UPDATED: Use the path passed in settings or fallback
    output_dir = settings.get('output_dir', os.path.join(os.path.expanduser("~"), "Downloads"))
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    results_map = {}

    for d_idx, d in enumerate(drivers):
        metrics_display = "Ref (Baseline)"
        if d == ref_driver:
            f_time_at_dist = interp1d(ref_data['dist'], ref_data['time'], kind='linear', fill_value="extrapolate")
            my_offset_arr = np.zeros(len(base_points)) 
        else:
            tgt_data = get_clean_trace(session, d)
            if not tgt_data: continue
            d_axis, final_delta, metrics = calculate_hifi_delta(ref_data, tgt_data)
            
            if d_axis is not None:
                fid = metrics['fidelity']['fidelity']
                int_sc = metrics['integrity']['score']
                metrics_display = f"Fid:{fid:.0f}% Int:{int_sc:.0f}%"
                
                ref_time_interp = interp1d(ref_data['dist'], ref_data['time'], fill_value="extrapolate")
                delta_interp = interp1d(d_axis, final_delta, fill_value="extrapolate")
                f_time_at_dist = lambda dist_m: float(ref_time_interp(dist_m) + delta_interp(dist_m))
            else:
                f_time_at_dist = lambda x: 0
            
            my_offset_arr = smooth_L if (d_idx % 2 != 0) else smooth_R

        results_map[d] = metrics_display
        driver_points = []
        
        for i in range(len(base_points)):
            # --- NORMAL VECTOR FIX ---
            # Use analytical derivative [dx, dy] rotated 90 deg
            dx, dy = dx_pts[i], dy_pts[i]
            
            # Normal is (-dy, dx)
            normal = np.array([-dy, dx, 0.0])
            norm_mag = np.linalg.norm(normal)
            if norm_mag > 0: normal /= norm_mag
            
            # Apply offset
            pos = base_points[i] + (normal * my_offset_arr[i])
            
            # Physics
            original_dist_ref = u_new[i] * ref_data['dist'].max()
            original_dist_next = u_new[min(i+1, len(u_new)-1)] * ref_data['dist'].max()
            
            t_curr = float(f_time_at_dist(original_dist_ref))
            t_next = float(f_time_at_dist(original_dist_next))
            
            dt = t_next - t_curr
            if dt <= 0: dt = 0.001 
            req_speed = rail_dist_step / dt 
            
            driver_points.append({
                "x": round(float(pos[0]), 3), "y": round(float(pos[1]), 3), "z": 0.0,
                "speed": round(req_speed, 2)
            })

        json_data = {
            "name": f"F1_{d}_{gp}", "closed": True, "points": driver_points,
            "launch_control": {"speed_unit": "m/s", "source": "Hi-Fi Baker"}
        }
        
        fname = os.path.join(output_dir, f"{d}_hifi_path.json")
        with open(fname, 'w') as f: json.dump(json_data, f, indent=2)

    return f"Saved to {output_dir}", results_map, ref_data['lap_time']

