
import bpy
import sys
import subprocess
import os
import json
import warnings
import importlib.util

# Add Blender's F1 Studio modules path first so we don't overwrite/lock files in scripts/modules
def _get_f1_modules_path():
    scripts = bpy.utils.user_resource("SCRIPTS")
    if scripts:
        p = os.path.join(scripts, "f1_studio_modules")
        return p
    return None

_f1_mod_path = _get_f1_modules_path()
if _f1_mod_path and os.path.isdir(_f1_mod_path) and _f1_mod_path not in sys.path:
    sys.path.insert(0, _f1_mod_path)

import math
import numpy as np
import tempfile

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
        from scipy.signal import correlate, medfilt, savgol_filter
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
        # Install to a dedicated folder to avoid PermissionError when overwriting locked .pyd in scripts/modules
        p = _get_f1_modules_path()
        if not p:
            self.report({'ERROR'}, "Could not resolve Blender scripts path.")
            return {'CANCELLED'}
        os.makedirs(p, exist_ok=True)

        import ensurepip
        ensurepip.bootstrap()

        deps = ["fastf1>=3.8.1", "pandas", "scipy", "numpy", "requests", "timple", "requests-cache"]
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", *deps, "--target", p])
            if p not in sys.path:
                sys.path.insert(0, p)
            global MISSING_DEPS
            importlib.invalidate_caches()
            MISSING_DEPS = check_dependencies()

            if not MISSING_DEPS:
                global fastf1, pd, interp1d, splprep, splev, correlate, medfilt
                import fastf1
                import pandas as pd
                from scipy.interpolate import interp1d, splprep, splev
                from scipy.signal import correlate, medfilt
                self.report({'INFO'}, "Installation Complete! Restart Blender to use FastF1 3.8.1.")
            else:
                self.report({'WARNING'}, "Installation finished but modules missing. Restart Blender.")
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
# 5. TELEMETRY EXPORT (CSV)
# ==============================================================================
def generate_telemetry_csv(year, gp, session_type, drivers, settings):
    print(f"Generating Telemetry CSVs for {drivers}...")
    fps = settings.get('fps', 24)
    exports_dir = settings.get('exports_dir', settings.get('output_dir', os.path.join(os.path.expanduser("~"), "Downloads")))
    if not os.path.exists(exports_dir):
        os.makedirs(exports_dir)

    is_testing = settings.get('is_testing', False)
    try:
        if is_testing:
            # API: get_testing_session(year, test_number, day) e.g. (2026, 1, 2) = Test 1 Day 2
            test_number = int(settings.get('test_number', 1))
            test_session = int(settings.get('test_session', 1))
            session = fastf1.get_testing_session(year, test_number, test_session)
        else:
            session = fastf1.get_session(year, gp, session_type)
        session.load(telemetry=True, laps=True, weather=False, messages=False)
    except Exception as e:
        print(f"CSV Export Error: {e}")
        return

    ref_driver = drivers[0]

    def get_rich_telemetry(drv):
        laps = session.laps.pick_drivers(drv)
        if laps.empty: return None
        lap = laps.pick_fastest()
        try:
            tel = lap.get_telemetry()
            # Drop NaN rows only for critical path channels to ensure valid interpolation
            tel = tel.dropna(subset=['Distance', 'Speed', 'Time'])
            tel = tel.drop_duplicates(subset=['Distance'])
            return {
                'dist': tel['Distance'].values,
                'time': tel['Time'].dt.total_seconds().values,
                'speed': tel['Speed'].values,
                'throttle': tel['Throttle'].values,
                'brake': tel['Brake'].values,
                'gear': tel['nGear'].values,
                'rpm': tel['RPM'].values,
                'drs': tel['DRS'].values,
                'lap_time': lap['LapTime'].total_seconds(),
                'driver': drv
            }
        except: return None

    ref_data = get_rich_telemetry(ref_driver)
    if not ref_data: return

    # Normalize Ref Time
    ref_data['time'] -= ref_data['time'][0]
    
    # --- PREPARE DELTA CSV MASTER GRID ---
    # We use Reference Driver's Lap Time to define the comparison frame grid
    total_frames = int(np.ceil(ref_data['lap_time'] * fps))
    frame_indices = np.arange(total_frames)
    frame_times = frame_indices / fps
    
    f_ref_dist_at_time = interp1d(ref_data['time'], ref_data['dist'], fill_value="extrapolate")
    ref_dists_at_frames = f_ref_dist_at_time(frame_times)
    
    delta_data = {
        'frame': frame_indices,
        'distance': np.round(ref_dists_at_frames, 3),
        f'{ref_driver}_delta': np.zeros(total_frames)
    }
    
    for drv in drivers:
        drv_data = get_rich_telemetry(drv)
        if not drv_data: continue
        
        # 1. Calculate Alignment (Delta)
        if drv == ref_driver:
            dist_vals = ref_data['dist']
            final_delta_vals = np.zeros_like(dist_vals)
            f_time_at_dist = interp1d(ref_data['dist'], ref_data['time'], fill_value="extrapolate")
        else:
            # Must reuse the same HiFi alignment logic
            dist_vals, final_delta_vals, _ = calculate_hifi_delta(ref_data, drv_data)
            
            if dist_vals is None: continue
            
            ref_time_interp = interp1d(ref_data['dist'], ref_data['time'], fill_value="extrapolate")
            delta_interp = interp1d(dist_vals, final_delta_vals, fill_value="extrapolate")
            f_time_at_dist = lambda d: ref_time_interp(d) + delta_interp(d)
            
            # Populate Delta CSV Column
            # Align delta to Ref Frames
            delta_at_frames = delta_interp(ref_dists_at_frames)
            delta_data[f'{drv}_delta'] = np.round(delta_at_frames, 4)

        # 2. Generate Individual Telemetry CSV
        # We need frames for THIS driver's simulated run (warped)
        # Create dense distance grid to invert time mapping
        sample_dists = np.linspace(0, ref_data['dist'].max(), 5000)
        sample_times = f_time_at_dist(sample_dists)
        
        # Invert to get Dist(Time) for the driver's warp
        # Handle non-strict monotonicity if small glitches occur (sort)
        if np.any(np.diff(sample_times) < 0):
             sorted_indices = np.argsort(sample_times)
             sample_times = sample_times[sorted_indices]
             sample_dists = sample_dists[sorted_indices]
             
        f_dist_at_time = interp1d(sample_times, sample_dists, fill_value="extrapolate", bounds_error=False)
        
        # Driver Frame Grid
        drv_duration = sample_times[-1]
        drv_total_frames = int(np.ceil(drv_duration * fps))
        drv_frames = np.arange(drv_total_frames)
        drv_frame_times = drv_frames / fps
        
        # Corresponding Distances on Track
        drv_dists = f_dist_at_time(drv_frame_times)
        
        # Sample Raw Telemetry at these distances
        f_time_s = interp1d(drv_data['dist'], drv_data['time'], fill_value="extrapolate")
        f_spd = interp1d(drv_data['dist'], drv_data['speed'], fill_value="extrapolate")
        f_thr = interp1d(drv_data['dist'], drv_data['throttle'], fill_value="extrapolate")
        f_brk = interp1d(drv_data['dist'], drv_data['brake'], fill_value="extrapolate")
        f_rpm = interp1d(drv_data['dist'], drv_data['rpm'], fill_value="extrapolate")
        f_gear = interp1d(drv_data['dist'], drv_data['gear'], kind='nearest', fill_value="extrapolate")
        f_drs = interp1d(drv_data['dist'], drv_data['drs'], kind='nearest', fill_value="extrapolate")
        
        raw_drs = f_drs(drv_dists)
        # Map DRS: 0-7->0, 8-9->1 (Detected), 10+->2 (Active)
        ers_deploy = np.zeros_like(raw_drs, dtype=int)
        ers_deploy[raw_drs >= 8] = 1
        ers_deploy[raw_drs >= 10] = 2

        # time_s: seconds from lap start, normalised so first sample = 0
        raw_time_s = f_time_s(drv_dists)
        time_s = np.round(raw_time_s - raw_time_s[0], 4)

        df_out = pd.DataFrame({
            'frame': drv_frames,
            'time_s': time_s,
            'distance': np.round(drv_dists, 2),
            'speed': np.round(f_spd(drv_dists), 1),
            'throttle': np.round(f_thr(drv_dists), 1),
            'brake': np.round(f_brk(drv_dists), 1),
            'gear': np.round(f_gear(drv_dists)).astype(int),
            'rpm': np.round(f_rpm(drv_dists)).astype(int),
            'ers_deploy': ers_deploy
        })
        
        fname = os.path.join(exports_dir, f"{drv}_telemetry.csv")
        df_out.to_csv(fname, index=False)
        
    # Save Delta CSV
    pd.DataFrame(delta_data).to_csv(os.path.join(exports_dir, "delta_comparison.csv"), index=False)
    print("CSV Export Complete.")


# ==============================================================================
# 6. MINIMAP RENDERER
# ==============================================================================
# ==============================================================================
# 6. MINIMAP RENDERER
# ==============================================================================
def generate_minimap_frames(session, drivers, exports_dir, ref_driver, year, event, session_type=None):
    
    TEAM_COLORS = {
        'Red Bull Racing': '#3671C6',
        'McLaren': '#FF8000',
        'Ferrari': '#F91536',
        'Mercedes': '#6CD3BF',
        'Aston Martin': '#358C75',
        'Alpine': '#2293D1',
        'Williams': '#64C4FF',
        'RB': '#6692FF',
        'Racing Bulls': '#6692FF',
        'Haas F1 Team': '#B6BABD',
        'Kick Sauber': '#C92D4B',
        'Alfa Romeo': '#C92D4B',
        'AlphaTauri': '#6692FF',
        'Toro Rosso': '#6692FF',
        'Renault': '#FFF500',
        'Racing Point': '#F596C8',
        'Force India': '#F596C8',
        'Sauber': '#C92D4B',
        'Audi': '#C0003C',
        'Cadillac': '#D5CECD',
    }

    print(f"Generating Minimap Frames...")
    
    # Load Driver Database
    db_path = os.path.join(os.path.dirname(exports_dir), 'database', 'drivers_by_race.json')
    race_drivers_db = []
    
    if os.path.exists(db_path):
        try:
            with open(db_path, 'r') as f:
                full_db = json.load(f)
                year_str = str(year)
                # Try to find the event (handling case sensitivity or partial match could be added, but strict for now)
                # The user prompt implies structure: { "YEAR": { "Race Name": [...] } }
                if year_str in full_db:
                    # We need to match 'event' to the key in json. FastF1 event name might differ slightly.
                    # Best effort: Look for exact match first, then caseless.
                    # Using the passed 'event' (gp) string.
                    
                    # Assuming strict match logic for now based on instruction "Find the entry matching year and event name"
                    if event in full_db[year_str]:
                        event_node = full_db[year_str][event]
                        # JSON structure: { YEAR: { EVENT: { SESSION: [drivers] } } }
                        # Pick the requested session; fall back to merging all sessions.
                        if isinstance(event_node, dict):
                            if session_type and session_type in event_node:
                                race_drivers_db = event_node[session_type]
                            else:
                                seen = set()
                                merged = []
                                for sess_list in event_node.values():
                                    if not isinstance(sess_list, list):
                                        continue
                                    for entry in sess_list:
                                        if isinstance(entry, dict):
                                            code = entry.get('code')
                                            if code and code not in seen:
                                                seen.add(code)
                                                merged.append(entry)
                                race_drivers_db = merged
                        elif isinstance(event_node, list):
                            race_drivers_db = event_node
                    else:
                        print(f"Event '{event}' not found in database for {year_str}.")
        except Exception as e:
            print(f"Database Load Error: {e}")
    else:
        print(f"Database not found at {db_path}")

    def get_team_color(drv_code):
        # Find driver in the loaded race list
        for entry in race_drivers_db:
            if entry.get('code') == drv_code:
                team = entry.get('team_raw')
                return TEAM_COLORS.get(team, '#FFFFFF')
        return '#FFFFFF'

    # 1. Setup Output Directory
    frames_dir = os.path.join(exports_dir, "minimap_frames")
    if not os.path.exists(frames_dir):
        os.makedirs(frames_dir)
        
    # 2. Build Track Spline (from Ref Driver's Fastest Lap)
    try:
        lap = session.laps.pick_driver(ref_driver).pick_fastest()
        tel = lap.get_telemetry().dropna(subset=['X', 'Y', 'Distance'])
        tel = tel.drop_duplicates(subset=['Distance'])
        
        x = tel['X'].values
        y = tel['Y'].values
        dist = tel['Distance'].values
        
        # Normalize to 0-1 for splprep
        dist_norm = dist / dist.max()
        
        # Create Spline (smooth factor s=0 forces through points if needed, but small s is better)
        # We use a small amount of smoothing to handle GPS jitter
        tck, u = splprep([x, y], u=dist_norm, s=10000, per=0) 
        
        # Function to get (x,y) from distance
        def get_pos_from_dist(d):
            # Clamp d to max distance
            d_clamped = np.clip(d, 0, dist.max())
            u_val = d_clamped / dist.max()
            return splev(u_val, tck)

        # Pre-calculate track line for plotting
        u_track = np.linspace(0, 1, 1000)
        track_x, track_y = splev(u_track, tck)
        
    except Exception as e:
        print(f"Minimap Spline Error: {e}")
        return

    # 3. Load Baked CSV Data
    driver_data = {}
    max_frames = 0
    
    for drv in drivers:
        csv_path = os.path.join(exports_dir, f"{drv}_telemetry.csv")
        if not os.path.exists(csv_path):
            print(f"Missing CSV for {drv}")
            continue
            
        df = pd.read_csv(csv_path)
        driver_data[drv] = {
            'dist': df['distance'].values,
            'color': get_team_color(drv),
            'label': drv
        }
        # Ref driver defines the frame count usually, but take max to be safe
        if drv == ref_driver:
            max_frames = len(df)
    
    if max_frames == 0:
        print("No valid telemetry data found.")
        return

    # 4. Render Frames
    # Use Agg backend for headless rendering
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    # Setup Figure (500x300, Transparent)
    dpi = 100
    fig = plt.figure(figsize=(500/dpi, 300/dpi), dpi=dpi)
    # Make background transparent
    fig.patch.set_alpha(0.0)
    
    ax = fig.add_axes([0, 0, 1, 1]) # Full figure
    ax.axis('off')
    ax.set_aspect('equal')
    
    # Plot Track Outline
    ax.plot(track_x, track_y, color='white', linewidth=2, alpha=0.6)
    
    avg_dot = ax.scatter([], [], color='#FFFFFF', s=140, zorder=10,
                         edgecolors='none', linewidth=0)

    print(f"Rendering {max_frames} frames...")

    # Frame Loop
    for i in range(max_frames):
        xs, ys = [], []
        for drv in driver_data:
            dists = driver_data[drv]['dist']
            if i < len(dists):
                x_pos, y_pos = get_pos_from_dist(dists[i])
                xs.append(x_pos)
                ys.append(y_pos)

        if xs:
            avg_x = sum(xs) / len(xs)
            avg_y = sum(ys) / len(ys)
            avg_dot.set_offsets([[avg_x, avg_y]])
            avg_dot.set_visible(True)
        else:
            avg_dot.set_visible(False)

        frame_name = os.path.join(frames_dir, f"frame_{i:05d}.png")
        plt.savefig(frame_name, transparent=True, dpi=dpi)

        if i % 100 == 0:
            print(f"  Frame {i}/{max_frames}", end='\r')
            
    print(f"\nMinimap Generation Complete. Saved to {frames_dir}")
    plt.close(fig)


# ==============================================================================
# 4a. TRACK GEOMETRY HELPERS
# ==============================================================================

def _segment_track(speed_array, distance_array):
    """Classify each point as STRAIGHT or CORNER based on speed threshold.

    Returns list of {'type': 'STRAIGHT'|'CORNER', 'start': int, 'end': int}.

    - Threshold = 80% of max speed.
    - Morphological close (dilate + erode, iterations=10) fills momentary dips.
    - Short segments merged into neighbors:
        STRAIGHT < 30 pts -> absorbed into adjacent corner
        CORNER   < 10 pts -> absorbed into adjacent straight
    """
    from scipy.ndimage import binary_dilation, binary_erosion

    n = len(speed_array)
    if n == 0:
        return []

    max_speed = float(np.max(speed_array))
    if max_speed < 1e-6:
        return [{'type': 'CORNER', 'start': 0, 'end': n - 1}]

    is_straight = speed_array > max_speed * 0.80

    # Morphological close: fill small gaps inside straights
    is_straight = binary_dilation(is_straight, iterations=10)
    is_straight = binary_erosion(is_straight,  iterations=10)

    # Build contiguous runs
    raw_segs  = []
    cur_type  = 'STRAIGHT' if is_straight[0] else 'CORNER'
    seg_start = 0
    for i in range(1, n):
        t = 'STRAIGHT' if is_straight[i] else 'CORNER'
        if t != cur_type:
            raw_segs.append({'type': cur_type, 'start': seg_start, 'end': i - 1})
            cur_type  = t
            seg_start = i
    raw_segs.append({'type': cur_type, 'start': seg_start, 'end': n - 1})

    # Merge short segments
    MIN_STRAIGHT = 30
    MIN_CORNER   = 10
    changed = True
    while changed:
        changed = False
        merged = []
        i = 0
        while i < len(raw_segs):
            seg    = raw_segs[i]
            length = seg['end'] - seg['start'] + 1
            too_short = ((seg['type'] == 'STRAIGHT' and length < MIN_STRAIGHT) or
                         (seg['type'] == 'CORNER'   and length < MIN_CORNER))
            if too_short:
                changed = True
                if merged:
                    merged[-1]['end'] = seg['end']
                elif i + 1 < len(raw_segs):
                    raw_segs[i + 1]['start'] = seg['start']
                    i += 1
                    continue
                else:
                    merged.append(seg)
            else:
                merged.append(seg)
            i += 1
        raw_segs = merged

    return raw_segs


def _correct_straights(points_x, points_y, segments, blend_points=12):
    """Linearize STRAIGHT segments in-place with cosine blend at each end.

    For every STRAIGHT segment:
      1. Linear interpolation from entry to exit point.
      2. Cosine blend over blend_points at each end.
    Arrays are modified in-place.
    """
    n      = len(points_x)
    orig_x = points_x.copy()
    orig_y = points_y.copy()

    for seg in segments:
        if seg['type'] != 'STRAIGHT':
            continue
        s       = seg['start']
        e       = min(seg['end'], n - 1)
        seg_len = e - s
        if seg_len < 2:
            continue

        bp       = min(blend_points, seg_len // 2)
        linear_x = np.linspace(orig_x[s], orig_x[e], seg_len + 1)
        linear_y = np.linspace(orig_y[s], orig_y[e], seg_len + 1)

        for j in range(seg_len + 1):
            gi = s + j
            if gi >= n:
                break
            if j < bp:
                t = 0.5 * (1.0 - math.cos(math.pi * j / bp))
            elif j > seg_len - bp:
                t = 0.5 * (1.0 - math.cos(math.pi * (seg_len - j) / bp))
            else:
                t = 1.0
            points_x[gi] = orig_x[gi] * (1.0 - t) + linear_x[j] * t
            points_y[gi] = orig_y[gi] * (1.0 - t) + linear_y[j] * t


# ==============================================================================
# 4b. MULTI-RAIL GENERATOR
# ==============================================================================
def generate_multirail_data(year, gp, session_type, drivers, settings):
    if MISSING_DEPS:
        return "Error: Missing Deps", {}, None

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

    is_testing = settings.get('is_testing', False)
    if is_testing:
        # API: get_testing_session(year, test_number, day) — e.g. (2026, 1, 2) = Test 1 Day 2, (2026, 2, 1) = Test 2 Day 1
        test_number = int(settings.get('test_number', 1))
        test_session = int(settings.get('test_session', 1))
        print(f"Loading {year} Testing – Test {test_number}, Day {test_session}...")
        try:
            session = fastf1.get_testing_session(year, test_number, test_session)
            session.load(telemetry=True, laps=True, weather=False, messages=False)
        except Exception as e:
            hint = " Data is only available after the session has finished (often 30-120 min). Future/unrun sessions have no data yet."
            return f"FastF1 Testing Error: {e}.{hint}", {}, None
    else:
        print(f"Loading {year} {gp}...")
        try:
            session = fastf1.get_session(year, gp, session_type)
            session.load(telemetry=True, laps=True, weather=False, messages=False)
        except Exception as e:
            hint = " Data is only available after the session has finished (often 30-120 min). Check event/session name."
            return f"FastF1 Error: {e}.{hint}", {}, None

    ref_driver = drivers[0]
    ref_data = get_clean_trace(session, ref_driver)
    if not ref_data:
        return "Error: No Ref Data (no telemetry for selected driver/session).", {}, None

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
    smooth_factor = len(path_x) * 0.1 # Tight smoothing — close to raw GPS

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
    dx_pts, dy_pts = splev(u_new, tck, der=1)

    base_points = np.column_stack((x_pts, y_pts, np.zeros_like(x_pts)))

    # Recalculate physical distance
    segment_lengths = np.sqrt(np.sum(np.diff(base_points, axis=0)**2, axis=1))
    actual_total_len = np.sum(segment_lengths)
    rail_dist_step = actual_total_len / (num_points - 1)

    # --- PER-DRIVER GPS SPLINES (built once per driver, inside the loop below) ---
    # Lateral offset system removed. Each driver's XY now comes from their own
    # GPS trace resampled at u_new. Timing engine (rail_dist_step, f_time_at_dist)
    # is unchanged and still driven by the reference spline above.

    # --- EXPORT ---
    output_dir = settings.get('output_dir', os.path.join(os.path.expanduser("~"), "Downloads"))
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    results_map = {}

    for d_idx, d in enumerate(drivers):
        # ── TIMING ENGINE (unchanged) ────────────────────────────────────────
        if d == ref_driver:
            f_time_at_dist = interp1d(ref_data['dist'], ref_data['time'],
                                      kind='linear', fill_value="extrapolate")
        else:
            tgt_data = get_clean_trace(session, d)
            if not tgt_data: continue
            d_axis, final_delta, metrics = calculate_hifi_delta(ref_data, tgt_data)
            if d_axis is not None:
                ref_time_interp = interp1d(ref_data['dist'], ref_data['time'],
                                           fill_value="extrapolate")
                delta_interp = interp1d(d_axis, final_delta, fill_value="extrapolate")
                f_time_at_dist = lambda dist_m, _ri=ref_time_interp, _di=delta_interp: float(_ri(dist_m) + _di(dist_m))
            else:
                f_time_at_dist = lambda x: 0.0

        # ── SPATIAL PATH: driver's own GPS spline ───────────────────────────
        drv_data = ref_data if d == ref_driver else tgt_data
        drv_x = drv_data['x'] * scale_geo - cx   # centered on reference driver
        drv_y = drv_data['y'] * scale_geo - cy
        drv_u = drv_data['dist'] / drv_data['dist'].max()
        drv_closed = np.linalg.norm([drv_x[0] - drv_x[-1], drv_y[0] - drv_y[-1]]) < 50
        try:
            drv_tck, _ = splprep([drv_x, drv_y], u=drv_u, k=3, s=len(drv_x) * 10,
                                  per=1 if drv_closed else 0)
        except Exception:
            drv_tck, _ = splprep([drv_x, drv_y], s=len(drv_x) * 0.1, per=0)

        # Resample at SAME u_new as reference → same num_points, same index alignment
        drv_xpts, drv_ypts = splev(u_new, drv_tck)

        # Straight correction (disabled — functions kept for later use)
        # drv_speed_at_pts = np.interp(
        #     u_new * drv_data['dist'].max(),
        #     drv_data['dist'],
        #     drv_data['speed']
        # )
        # segments = _segment_track(drv_speed_at_pts, u_new * drv_data['dist'].max())
        # _correct_straights(drv_xpts, drv_ypts, segments, blend_points=12)

        # ── COMBINE: driver XY + reference timing ────────────────────────────
        driver_points = []
        for i in range(num_points):
            # position: this driver's corrected GPS spline
            drv_pos_x = drv_xpts[i]
            drv_pos_y = drv_ypts[i]

            dist_curr = u_new[i] * ref_data['dist'].max()
            dist_next = u_new[min(i + 1, num_points - 1)] * ref_data['dist'].max()
            t_curr = float(f_time_at_dist(dist_curr))
            t_next = float(f_time_at_dist(dist_next))
            dt = t_next - t_curr
            if dt <= 0: dt = 0.001
            req_speed = rail_dist_step / dt

            driver_points.append({
                "x": round(float(drv_pos_x), 3),
                "y": round(float(drv_pos_y), 3),
                "z": 0.0,
                "speed": round(req_speed, 2)
            })

        json_data = {
            "name": f"F1_{d}_{gp}", "closed": True, "points": driver_points,
            "launch_control": {"speed_unit": "m/s", "source": "Hi-Fi Baker"}
        }

        slot_ids = settings.get("slot_ids")
        if slot_ids is not None and d_idx < len(slot_ids) and slot_ids[d_idx] is not None:
            fname = os.path.join(output_dir, f"{d}_{slot_ids[d_idx]}_hifi_path.json")
        else:
            fname = os.path.join(output_dir, f"{d}_hifi_path.json")
        with open(fname, 'w') as f: json.dump(json_data, f, indent=2)

    
    # CALL NEW CSV GENERATOR
    exports_dir = settings.get('exports_dir', output_dir)
    if not os.path.exists(exports_dir):
        os.makedirs(exports_dir)
    generate_telemetry_csv(year, gp, session_type, drivers, settings)

    # CALL MINIMAP GENERATOR (if enabled)
    if settings.get('render_minimap', True):
        generate_minimap_frames(session, drivers, exports_dir, ref_driver, year, gp, session_type)
    else:
        print("[F1 Baker] Minimap rendering skipped (disabled in settings)")

    return f"Saved to {output_dir}", results_map, ref_data['lap_time']

