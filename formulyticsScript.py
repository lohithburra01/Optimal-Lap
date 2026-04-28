import fastf1
import fastf1.plotting
import pandas as pd
import numpy as np
import cv2
import os
import json
import subprocess
import ipywidgets as widgets
from IPython.display import display
from PIL import Image, ImageDraw, ImageFont
from scipy.interpolate import interp1d, splprep, splev
from scipy.signal import correlate, medfilt
import warnings

warnings.simplefilter(action='ignore')

# ==========================================
# 0. DATABASE CONNECTION
# ==========================================
DB_DIR = r"C:\Users\91910\Downloads\openclaw-pipeline\database"
CALENDAR_DB = {}
DRIVERS_DB = {}
SEASON_DB = {}

try:
    with open(os.path.join(DB_DIR, "calendar_cache.json"), 'r', encoding='utf-8') as f:
        CALENDAR_DB = json.load(f)
    with open(os.path.join(DB_DIR, "drivers_by_race.json"), 'r', encoding='utf-8') as f:
        DRIVERS_DB = json.load(f)
    with open(os.path.join(DB_DIR, "drivers_by_season.json"), 'r', encoding='utf-8') as f:
        SEASON_DB = json.load(f)
    print(f"✅ Successfully linked local F1 database.")
except Exception as e:
    print(f"⚠️ Warning: Could not load local databases. Error: {e}")

# ==========================================
# 1. HIGH-FIDELITY DELTA ENGINE (PURE MATH)
# ==========================================
def calculate_hifi_delta(ref_trace, tgt_trace):
    master_len = ref_trace['dist'].max()
    scale = master_len / tgt_trace['dist'].max()
    tgt_dist_scaled = tgt_trace['dist'] * scale

    grid_len = 10000; window_size = 300; step_size = 50
    common_grid = np.linspace(0, master_len, grid_len)
    v_ref = np.interp(common_grid, ref_trace['dist'], ref_trace['speed'])
    v_tgt = np.interp(common_grid, tgt_dist_scaled, tgt_trace['speed'])

    shifts, positions = [], []
    for start_pos in range(0, int(master_len), step_size):
        end_pos = start_pos + window_size
        if end_pos > master_len: break
        i0 = int((start_pos / master_len) * grid_len)
        i1 = int((end_pos / master_len) * grid_len)
        corr = correlate(v_ref[i0:i1], v_tgt[i0:i1], mode='same')
        if len(corr) == 0: continue
        lag_idx = np.argmax(corr) - (len(corr) // 2)
        shift_m = lag_idx * (master_len / grid_len)
        if abs(shift_m) < 40:
            shifts.append(shift_m); positions.append(start_pos + window_size/2)

    if positions:
        if positions[0] > 0: positions.insert(0, 0); shifts.insert(0, shifts[0])
        if positions[-1] < master_len: positions.append(master_len); shifts.append(shifts[-1])
        positions, shifts = zip(*sorted(zip(positions, shifts)))
        shift_interp = interp1d(positions, shifts, kind='linear', fill_value="extrapolate")
        tgt_dist_warped = tgt_dist_scaled + shift_interp(tgt_dist_scaled)
    else:
        tgt_dist_warped = tgt_dist_scaled

    f_tgt_time = interp1d(tgt_dist_warped, tgt_trace['time'], fill_value="extrapolate")
    raw_delta = f_tgt_time(ref_trace['dist']) - ref_trace['time']
    delta_smooth = medfilt(raw_delta, kernel_size=15)
    delta_zeroed = delta_smooth - delta_smooth[0]

    actual_lap_diff = tgt_trace['lap_time'] - ref_trace['lap_time']
    residual_error = delta_zeroed[-1] - actual_lap_diff
    
    if abs(residual_error) > 1e-6:
        ramp = np.linspace(0, 1, len(delta_zeroed))
        final_delta = delta_zeroed - (ramp * residual_error)
    else:
        final_delta = delta_zeroed

    return ref_trace['dist'], final_delta

# ==========================================
# 2. THE VIDEO ENGINE (CV2 EXPORTER)
# ==========================================

def draw_centered(draw, x, y, text, font, fill):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]; h = bbox[3] - bbox[1]
    except:
        w, h = draw.textsize(text, font=font)
    draw.text((x - w/2, y - h/2 - 4), text, font=font, fill=fill)

class F1VideoBaker:
    def __init__(self, track, configs, is_same_race=True, zoom_factor=3.0, trail_frames=60, fps=30):
        self.track = track
        self.configs = configs
        self.is_same_race = is_same_race
        self.fps = fps
        self.zoom_factor = zoom_factor
        self.trail_frames = trail_frames
        self.ref_config = configs[0]
        self.loaded_sessions = {}
        
        font_dir = r"C:\Users\91910\Downloads\Formula1"
        try:
            self.font_title = ImageFont.truetype(os.path.join(font_dir, "Formula1-Bold_web_0.ttf.ttf"), 42)
            self.font_sub = ImageFont.truetype(os.path.join(font_dir, "Formula1-Regular_web_0.ttf.ttf"), 26)
            self.font_lb_pos = ImageFont.truetype(os.path.join(font_dir, "Formula1-Bold_web_0.ttf.ttf"), 20)
            self.font_lb_name = ImageFont.truetype(os.path.join(font_dir, "Formula1-Bold_web_0.ttf.ttf"), 30)
            self.font_lb_gap = ImageFont.truetype(os.path.join(font_dir, "Formula1-Regular_web_0.ttf.ttf"), 26)
            self.font_car = ImageFont.truetype(os.path.join(font_dir, "Formula1-Bold_web_0.ttf.ttf"), 20)
            self.font_wm = ImageFont.truetype(os.path.join(font_dir, "Formula1-Bold_web_0.ttf.ttf"), 24)
        except:
            print("⚠️ Font load error. Using defaults.")
            def_font = ImageFont.load_default()
            self.font_title = self.font_sub = self.font_lb_pos = self.font_lb_name = self.font_lb_gap = self.font_car = self.font_wm = def_font

    def _hex_to_bgr(self, hex_str):
        hex_str = hex_str.lstrip('#')
        if len(hex_str) != 6: return (255, 255, 255)
        r, g, b = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
        return (b, g, r)

    def get_team_colors(self, driver_code, year):
        DRIVER_COLOR_MAP = {
            # Red Bull Racing
            'VER': '#3671C6', 'HAD': '#3671C6',
            # Ferrari
            'LEC': '#E8002D', 'HAM': '#E8002D',
            # McLaren
            'NOR': '#FF8000', 'PIA': '#FF8000',
            # Mercedes
            'RUS': '#27F4D2', 'ANT': '#27F4D2',
            # Aston Martin
            'ALO': '#229971', 'STR': '#229971',
            # Alpine
            'GAS': '#0090FF', 'COL': '#0090FF',
            # Williams
            'ALB': '#005AFF', 'SAI': '#005AFF',
            # Racing Bulls
            'LAW': '#C8D2F0', 'LIN': '#C8D2F0',
            # Haas
            'OCO': '#B6BABD', 'BEA': '#B6BABD',
            # Audi
            'HUL': '#C0003C', 'BOR': '#C0003C',
            # Cadillac
            'BOT': '#A0A0A0', 'PER': '#A0A0A0',
            # Legacy pre-2026
            'SAR': '#64C4FF', 'MAG': '#B6BABD',
            'ZHO': '#52E252', 'TSU': '#6692FF',
            'RIC': '#6692FF', 'DEV': '#6692FF',
        }

        if driver_code in DRIVER_COLOR_MAP:
            return self._hex_to_bgr(DRIVER_COLOR_MAP[driver_code])

        try:
            TEAM_COLOR_MAP = {
                'red bull':     '#3671C6',
                'ferrari':      '#E8002D',
                'mclaren':      '#FF8000',
                'mercedes':     '#27F4D2',
                'aston martin': '#229971',
                'alpine':       '#0090FF',
                'williams':     '#005AFF',
                'racing bulls': '#C8D2F0',
                'haas':         '#B6BABD',
                'audi':         '#C0003C',
                'cadillac':     '#A0A0A0',
                'kick sauber':  '#52E252',
                'sauber':       '#52E252',
                'alphatauri':   '#6692FF',
            }
            session = next(iter(self.loaded_sessions.values()))
            driver_laps = session.laps[session.laps['Driver'] == driver_code]
            if not driver_laps.empty:
                team_name = driver_laps.iloc[0]['TeamName'].lower().strip()
                for key, color in TEAM_COLOR_MAP.items():
                    if key in team_name:
                        return self._hex_to_bgr(color)
        except:
            pass

        return (255, 255, 255)

    def get_session(self, year, session_type):
        key = (year, self.track, session_type)
        if key not in self.loaded_sessions:
            print(f"⏳ Loading Session: {year} {self.track} ({session_type})...")
            try: fastf1.Cache.enable_cache('cache')
            except: pass
            s = fastf1.get_session(year, self.track, session_type)
            s.load(telemetry=True, laps=True, weather=False, messages=False)
            self.loaded_sessions[key] = s
        return self.loaded_sessions[key]

    def get_clean_trace(self, config):
        try:
            session = self.get_session(config['year'], config['session'])
            laps = session.laps.pick_driver(config['driver'])
            if laps.empty: return None
            lap = laps.pick_fastest()
            tel = lap.get_telemetry().dropna(subset=['Distance', 'Speed', 'X', 'Y'])
            tel = tel.drop_duplicates(subset=['Time'])
            
            dist = tel['Distance'].values
            dist -= dist[0]
            
            return {
                'dist': dist,
                'speed': tel['Speed'].values / 3.6,
                'time': tel['Time'].dt.total_seconds().values,
                'x': tel['X'].values / 10.0,
                'y': tel['Y'].values / 10.0,
                'lap_time': lap['LapTime'].total_seconds(),
                'driver': config['driver'],
                'config': config
            }
        except Exception as e:
            print(f"⚠️ Error with {config['driver']} ({config['year']}): {e}")
            return None

    def format_display_name(self, config):
        if self.is_same_race: return config['driver']
        yr = str(config['year'])[-2:]
        return f"{config['driver']} '{yr} ({config['session']})"

    def bake(self):
        ref_trace = self.get_clean_trace(self.ref_config)
        if not ref_trace:
            print("❌ Reference driver trace missing. Cannot build track spline.")
            return

        title_line1 = f"{self.track.upper()}"
        if self.is_same_race: title_line1 += f" - {self.ref_config['year']}"
        title_line2 = f"TOP {len(self.configs)} - {self.ref_config['session'].upper()} LAP COMPARISON" if self.is_same_race else f"CROSS-SESSION LAP COMPARISON"
        
        master_len = ref_trace['dist'][-1]
        time_mappings = {}
        delta_functions = {}

        print("⚙️ Applying HiFi Delta Engine (Cross-Year Aligned)...")
        valid_traces = []
        for cfg in self.configs:
            tgt_trace = self.get_clean_trace(cfg)
            if not tgt_trace: continue
            
            uid = f"{cfg['driver']}_{cfg['year']}_{cfg['session']}"
            tgt_trace['uid'] = uid
            valid_traces.append(tgt_trace)
            
            if cfg == self.ref_config:
                mapped_time = ref_trace['time']
                delta_functions[uid] = lambda d: 0.0
            else:
                _, final_delta = calculate_hifi_delta(ref_trace, tgt_trace)
                mapped_time = ref_trace['time'] + final_delta
                delta_functions[uid] = interp1d(ref_trace['dist'], final_delta, fill_value="extrapolate")
                
            time_mappings[uid] = np.maximum.accumulate(mapped_time)

        print("🛤️ Generating Base Rail from Reference...")
        ref_x = ref_trace['x']
        ref_y = ref_trace['y']
        cx, cy = np.mean(ref_x), np.mean(ref_y)
        ref_x -= cx
        ref_y -= cy
        
        coords = np.stack([ref_x, ref_y], axis=1)
        diffs = np.linalg.norm(np.diff(coords, axis=0), axis=1)
        print(f"zero-distance steps: {np.sum(diffs == 0)}")
        print(f"near-zero steps (<0.1): {np.sum(diffs < 0.1)}")
        print(f"min step distance: {diffs.min():.6f}")
# Remove consecutive duplicate points
        mask = np.concatenate([[True], diffs > 0])
        ref_x = ref_x[mask]
        ref_y = ref_y[mask]

        tck, _ = splprep([ref_x, ref_y], s=100, per=0)
        def get_pos(prog):
            p = np.clip(prog, 0, 1)
            x, y = splev(p, tck)
            return float(x), float(y)

        track_pts_normalized = [get_pos(p) for p in np.linspace(0, 1, 2000)]
        max_time = max(t[-1] for t in time_mappings.values())
        total_frames = int(max_time * self.fps)

        vec_arrays = {tr['uid']: (time_mappings[tr['uid']], ref_trace['dist']) for tr in valid_traces}

        print("📼 Rendering High-Speed MP4...")
        WIDTH, HEIGHT = 1080, 1920
        out_filename = f"f1_{self.track.replace(' ', '_').lower()}_comparison.mp4"
        out = cv2.VideoWriter(out_filename, cv2.VideoWriter_fourcc(*'mp4v'), self.fps, (WIDTH, HEIGHT))

        track_w = max(p[0] for p in track_pts_normalized) - min(p[0] for p in track_pts_normalized)
        track_h = max(p[1] for p in track_pts_normalized) - min(p[1] for p in track_pts_normalized)
        scale = (min(WIDTH, HEIGHT * 0.5) / max(track_w, track_h)) * self.zoom_factor

        def world_to_screen(x, y, cam_x, cam_y):
            sx = int(WIDTH/2 + (x - cam_x) * scale)
            sy = int(HEIGHT*0.4 - (y - cam_y) * scale)
            return sx, sy

        track_screen_base = np.array(track_pts_normalized)
        trails = {tr['uid']: [] for tr in valid_traces}
        car_radius = 30 

        MAP_SIZE = 280
        MAP_X = WIDTH - MAP_SIZE - 60
        lb_y_start = 1350 - (len(valid_traces) * 70) 
        MAP_Y = 1350 - MAP_SIZE 
        map_scale = MAP_SIZE / max(track_w, track_h) * 0.95

        def world_to_minimap(x, y):
            return int(MAP_X + MAP_SIZE/2 + x * map_scale), int(MAP_Y + MAP_SIZE/2 - y * map_scale)

        map_track_screen = np.array([world_to_minimap(p[0], p[1]) for p in track_pts_normalized], np.int32)
        ref_uid = f"{self.ref_config['driver']}_{self.ref_config['year']}_{self.ref_config['session']}"

        for f in range(total_frames):
            frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            t = f / self.fps

            current_distances = {}
            for tr in valid_traces:
                t_arr, d_arr = vec_arrays[tr['uid']]
                current_distances[tr['uid']] = np.interp(t, t_arr, d_arr)

            ref_dist = current_distances[ref_uid]
            cam_x, cam_y = get_pos(ref_dist / master_len)

            pts = np.array([world_to_screen(p[0], p[1], cam_x, cam_y) for p in track_screen_base], np.int32)
            cv2.polylines(frame, [pts.reshape((-1, 1, 2))], False, (255, 255, 255), thickness=40, lineType=cv2.LINE_AA)
            cv2.polylines(frame, [pts.reshape((-1, 1, 2))], False, (40, 40, 40), thickness=32, lineType=cv2.LINE_AA)

            draw_order = sorted(valid_traces, key=lambda tr: current_distances[tr['uid']])
            
            for tr in draw_order:
                uid = tr['uid']
                dist = current_distances[uid]
                px, py = get_pos(dist / master_len)
                color_bgr = self.get_team_colors(tr['config']['driver'], tr['config']['year'])
                
                trails[uid].append((px, py))
                if len(trails[uid]) > self.trail_frames: trails[uid].pop(0)
                    
                if len(trails[uid]) > 1:
                    screen_trail = np.array([world_to_screen(tx, ty, cam_x, cam_y) for tx, ty in trails[uid]], np.int32)
                    cv2.polylines(frame, [screen_trail.reshape((-1, 1, 2))], False, color_bgr, thickness=18, lineType=cv2.LINE_AA)

            cv2.polylines(frame, [map_track_screen.reshape((-1, 1, 2))], False, (80, 80, 80), thickness=6, lineType=cv2.LINE_AA)
            for tr in draw_order:
                dist = current_distances[tr['uid']]
                px, py = get_pos(dist / master_len)
                sx, sy = world_to_screen(px, py, cam_x, cam_y)
                mx, my = world_to_minimap(px, py)
                color_bgr = self.get_team_colors(tr['config']['driver'], tr['config']['year'])

                cv2.circle(frame, (sx, sy), car_radius, color_bgr, -1, cv2.LINE_AA)
                cv2.circle(frame, (sx, sy), car_radius, (255, 255, 255), 4, cv2.LINE_AA)
                cv2.circle(frame, (mx, my), 8, color_bgr, -1, cv2.LINE_AA)
                cv2.circle(frame, (mx, my), 8, (255, 255, 255), 2, cv2.LINE_AA)

            img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img_pil)

            draw_centered(draw, WIDTH//2, 250, title_line1, self.font_title, (255, 255, 255))
            draw_centered(draw, WIDTH//2, 300, title_line2, self.font_sub, (200, 200, 200))

            for tr in draw_order:
                uid = tr['uid']
                sx, sy = world_to_screen(*get_pos(current_distances[uid] / master_len), cam_x, cam_y)
                display_name = self.format_display_name(tr['config'])
                
                try: bbox = draw.textbbox((0, 0), display_name, font=self.font_car); tw = bbox[2]-bbox[0]; th = bbox[3]-bbox[1]
                except: tw, th = draw.textsize(display_name, font=self.font_car)
                    
                ly = sy - 55
                draw.rectangle([sx - tw/2 - 8, ly - th/2 - 6, sx + tw/2 + 8, ly + th/2 + 6], fill=(0,0,0))
                draw_centered(draw, sx, ly, display_name, self.font_car, (255, 255, 255))

            sorted_by_pos = sorted(valid_traces, key=lambda tr: current_distances[tr['uid']], reverse=True)
            
            for i, tr in enumerate(sorted_by_pos):
                uid = tr['uid']
                dist = current_distances[uid]
                c_bgr = self.get_team_colors(tr['config']['driver'], tr['config']['year'])
                color_rgb = (c_bgr[2], c_bgr[1], c_bgr[0]) 
                
                cy = lb_y_start + i * 70 + 15
                dist_to_ref = abs(dist - ref_dist)
                
                if uid == ref_uid:
                    gap_text = "LEADER"
                    color_text_rgb = (150, 150, 150)
                else:
                    sign = "+" if dist < ref_dist else "-"
                    time_gap = delta_functions[uid](dist)
                    gap_text = f"{sign}{dist_to_ref:.0f}m ({sign}{abs(time_gap):.3f}s)"
                    color_text_rgb = (230, 50, 50) if dist < ref_dist else (50, 230, 50)

                draw.ellipse([80-18, cy-18, 80+18, cy+18], fill=color_rgb)
                draw_centered(draw, 80, cy, f"P{i+1}", self.font_lb_pos, (255, 255, 255))
                
                display_name = self.format_display_name(tr['config'])
                draw.text((120, cy - 18), display_name, font=self.font_lb_name, fill=color_rgb)
                
                try: name_w = draw.textbbox((0, 0), display_name, font=self.font_lb_name)[2]
                except: name_w = draw.textsize(display_name, font=self.font_lb_name)[0]
                    
                draw.text((120 + name_w + 35, cy - 14), gap_text, font=self.font_lb_gap, fill=color_text_rgb)

            draw_centered(draw, WIDTH//2, 1450, "@formulytics", self.font_wm, (150, 150, 150))
            out.write(cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR))

        out.release()
        print(f"✅ SUCCESS: Video saved as '{out_filename}'")
        try: subprocess.run(f'explorer /select,"{os.path.abspath(out_filename)}"', shell=True)
        except: pass


# ==========================================
# 3. INTERACTIVE WIDGET UI PIPELINE
# ==========================================
years = sorted(list(CALENDAR_DB.keys()), reverse=True) if CALENDAR_DB else ['2024', '2023', '2022']
all_tracks = set()
for y, races in CALENDAR_DB.items():
    for r in races: all_tracks.add(r['event_name'])
all_tracks = sorted(list(all_tracks)) if all_tracks else ['Bahrain Grand Prix']

w_track = widgets.Dropdown(options=all_tracks, value=all_tracks[0], description='Track:')
w_same_race = widgets.Checkbox(value=True, description='Same Race (Lock Targets to Ref Year/Session)')

driver_rows = []
for i in range(5):
    y_drop = widgets.Dropdown(options=years, value=years[0], layout=widgets.Layout(width='80px'))
    s_drop = widgets.Dropdown(options=['Q', 'R', 'S', 'SQ', 'FP1', 'FP2', 'FP3'], value='Q', layout=widgets.Layout(width='60px'))
    d_drop = widgets.Dropdown(options=[], layout=widgets.Layout(width='120px'))
    driver_rows.append({'year': y_drop, 'session': s_drop, 'driver': d_drop})

def _extract_drivers_flat(node):
    if isinstance(node, list):
        for item in node:
            if isinstance(item, dict) and 'code' in item:
                yield item
    elif isinstance(node, dict):
        for v in node.values():
            yield from _extract_drivers_flat(v)

def update_driver_options(row_idx):
    row = driver_rows[row_idx]
    yr = row['year'].value
    trk = w_track.value
    d_list = []

    if str(yr) in DRIVERS_DB and trk in DRIVERS_DB[str(yr)]:
        seen = {}
        for d in _extract_drivers_flat(DRIVERS_DB[str(yr)][trk]):
            if d['code'] not in seen:
                seen[d['code']] = True
        d_list = list(seen.keys())

    if not d_list and str(yr) in SEASON_DB:
        season = SEASON_DB[str(yr)]
        d_list = [d['code'] for d in _extract_drivers_flat(season)]
        
    if not d_list:
        d_list = ['VER', 'PER', 'LEC', 'SAI', 'NOR', 'PIA', 'HAM', 'RUS', 'ALO', 'STR']
        
    if row_idx > 0:
        d_list = [""] + d_list
        
    old_val = row['driver'].value
    row['driver'].options = d_list
    if old_val in d_list:
        row['driver'].value = old_val

def on_global_change(*args):
    for i in range(len(driver_rows)): update_driver_options(i)

w_track.observe(on_global_change, 'value')
for i, r in enumerate(driver_rows):
    r['year'].observe(lambda change, idx=i: update_driver_options(idx), 'value')

def sync_same_race(*args):
    is_locked = w_same_race.value
    ref_y = driver_rows[0]['year'].value
    ref_s = driver_rows[0]['session'].value
    for i in range(1, 5):
        driver_rows[i]['year'].disabled = is_locked
        driver_rows[i]['session'].disabled = is_locked
        if is_locked:
            driver_rows[i]['year'].value = ref_y
            driver_rows[i]['session'].value = ref_s

w_same_race.observe(sync_same_race, 'value')
driver_rows[0]['year'].observe(sync_same_race, 'value')
driver_rows[0]['session'].observe(sync_same_race, 'value')

on_global_change()
sync_same_race()

w_zoom = widgets.FloatSlider(value=3.0, min=0.5, max=20.0, step=0.5, description='Zoom Level:')
w_trail = widgets.IntSlider(value=60, min=0, max=300, step=10, description='Trail Frames:')

btn_gen = widgets.Button(description="GENERATE MANUAL", button_style='success')
btn_top3 = widgets.Button(description="AUTO TOP 3", button_style='info')
btn_top5 = widgets.Button(description="AUTO TOP 5", button_style='primary')
out = widgets.Output()

def get_auto_top_drivers(n):
    year = int(driver_rows[0]['year'].value)
    track = w_track.value
    session_type = driver_rows[0]['session'].value
    
    print(f"🔍 Auto-detecting Top {n} drivers for {year} {track} ({session_type})...")
    try: fastf1.Cache.enable_cache('cache')
    except: pass
    
    s = fastf1.get_session(year, track, session_type)
    s.load(telemetry=False, weather=False, messages=False)
    
    if s.laps.empty:
        print("❌ Could not find valid laps for this session.")
        return []
        
    fastest_laps = s.laps.pick_quicklaps().sort_values(by='LapTime')
    seen = []
    for _, lap in fastest_laps.iterrows():
        drv = lap['Driver']
        if drv not in seen: seen.append(drv)
        if len(seen) == n: break
        
    return seen

def on_auto_generate(n):
    with out:
        out.clear_output()
        seen_drivers = get_auto_top_drivers(n)
        if not seen_drivers: return
            
        print(f"🏁 Found Top {n}: {', '.join(seen_drivers)}")
        
        w_same_race.value = True
        for i, r in enumerate(driver_rows):
            if i < len(seen_drivers):
                d = seen_drivers[i]
                if d not in r['driver'].options:
                    r['driver'].options = list(r['driver'].options) + [d]
                r['driver'].value = d
            else:
                if "" not in r['driver'].options:
                    r['driver'].options = [""] + list(r['driver'].options)
                r['driver'].value = ""
        
        configs = [{'driver': d, 'year': int(driver_rows[0]['year'].value), 'session': driver_rows[0]['session'].value} for d in seen_drivers]
        
        baker = F1VideoBaker(
            track=w_track.value,
            configs=configs,
            is_same_race=True,
            zoom_factor=w_zoom.value,
            trail_frames=w_trail.value
        )
        baker.bake()

def on_manual_generate(b):
    with out:
        out.clear_output()
        configs = []
        for i, r in enumerate(driver_rows):
            d_val = r['driver'].value
            if d_val and str(d_val).strip() != '':
                configs.append({
                    'driver': d_val,
                    'year': int(r['year'].value),
                    'session': r['session'].value
                })
                
        if not configs:
            print("❌ Select at least a reference driver.")
            return
            
        baker = F1VideoBaker(
            track=w_track.value,
            configs=configs,
            is_same_race=w_same_race.value,
            zoom_factor=w_zoom.value,
            trail_frames=w_trail.value
        )
        baker.bake()

btn_gen.on_click(on_manual_generate)
btn_top3.on_click(lambda b: on_auto_generate(3))
btn_top5.on_click(lambda b: on_auto_generate(5))

ui_rows = [widgets.HBox([widgets.Label(f"{'Ref' if i==0 else f'Tgt {i}'}:", layout=widgets.Layout(width='40px')), r['year'], r['session'], r['driver']]) for i, r in enumerate(driver_rows)]
buttons_box = widgets.HBox([btn_gen, btn_top3, btn_top5])

ui = widgets.VBox([
    widgets.HTML("<h2>🏎️ F1 Global Cross-Year Automation</h2>"),
    w_track, w_same_race,
    widgets.HTML("<hr><b>Driver Roster:</b>"),
    *ui_rows,
    widgets.HTML("<hr><b>Visual Settings:</b>"),
    widgets.HBox([w_zoom, w_trail]),
    widgets.HTML("<hr>"),
    buttons_box,
    out
])

display(ui)