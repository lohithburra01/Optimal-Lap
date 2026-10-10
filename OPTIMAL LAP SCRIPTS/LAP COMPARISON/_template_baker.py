# ==========================================
# 1-2. OPTIMAL x QUALI ENGINE
#   Delta engine + animation timing = the LAPCOMP.IPYNB code, copied VERBATIM into lap_compare_optimal.py.
#   Road + racing line = the optimal lap built for this track (F1_Pipeline_Assets/tracks/<track>_lapcomp.json).
#   P1 drives the shipped optimal line; every other car gets its own optimiser line (~1% setup variation, cached).
# ==========================================
import sys, importlib
LAPCOMP_DIR = r"D:\f1_hot_lap\OPTIMAL LAP SCRIPTS\LAP COMPARISON"
if LAPCOMP_DIR not in sys.path: sys.path.insert(0, LAPCOMP_DIR)
import lap_compare_optimal as LCO, optimal_lines as OL
importlib.reload(LCO); importlib.reload(OL)

class F1VideoBaker:
    def __init__(self, track, configs, is_same_race=True, zoom_factor=1.0, trail_frames=60, fps=30):
        self.track = track
        self.configs = configs
        self.is_same_race = is_same_race
        self.fps = fps
        self.zoom_factor = zoom_factor
        self.trail_frames = trail_frames
        self.ref_config = configs[0]
        self.loaded_sessions = {}

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
        try:
            recipe = OL.load_recipe(self.track)
        except FileNotFoundError as e:
            print(f"❌ {e}"); return

        traces = []
        for cfg in self.configs:
            tr = self.get_clean_trace(cfg)
            if not tr:
                if cfg is self.ref_config:
                    print("❌ Reference driver trace missing.")
                    ok, msg = check_f1_api_access()
                    print(f"🚫 LIKELY CAUSE: {msg}" if not ok else "   (F1 API is reachable — verify the driver code / year / session are valid for this race.)")
                    return
                continue
            tr['label'] = self.format_display_name(cfg)
            traces.append(tr)
            print(f"   {tr['label']}: {tr['lap_time']:.3f}s")

        print(f"🛤️ Road + line from the optimal lap: {os.path.basename(recipe['raceline'])}")
        if len(traces) > 1:
            print(f"   making {len(traces) - 1} driver line(s) (first time per track: a few minutes each, then cached)")
        variants = OL.variant_lines(recipe, len(traces) - 1)
        line_paths = {traces[0]['label']: recipe['raceline']}
        for tr, p in zip(traces[1:], variants): line_paths[tr['label']] = p

        title1 = f"{self.track.upper()}" + (f" - {self.ref_config['year']}" if self.is_same_race else "")
        title2 = (f"TOP {len(traces)} - {self.ref_config['session'].upper()} LAP COMPARISON" if self.is_same_race
                  else "CROSS-SESSION LAP COMPARISON")
        out_filename = f"f1_{self.track.replace(' ', '_').lower()}_{self.ref_config['year']}_{self.ref_config['session'].lower()}_optimal_comparison.mp4"
        out_path = os.path.join(LAPCOMP_DIR, out_filename)
        print("📼 Rendering High-Speed MP4...")
        LCO.render(traces, recipe['outline'], line_paths, self.track, self.ref_config['year'],
                   self.ref_config['session'], out_path, zoom=float(recipe.get('zoom', 28)) * self.zoom_factor,
                   trail_frames=self.trail_frames, fps=self.fps, title1=title1, title2=title2,
                   log=lambda m: None if m.startswith("  frame") else print(m))
        print(f"✅ SUCCESS: Video saved as '{out_path}'")
        try: subprocess.run(f'explorer /select,"{out_path}"', shell=True)
        except: pass
