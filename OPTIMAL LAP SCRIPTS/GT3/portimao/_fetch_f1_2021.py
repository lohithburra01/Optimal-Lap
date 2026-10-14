"""Fetch 2021 Portuguese GP Q pole lap (FastF1): true X/Y/Z, direction, S/F, speed. Reference geometry for the GT3 build."""
import fastf1, json, numpy as np, os
os.makedirs('GT3/portimao/ff1', exist_ok=True); fastf1.Cache.enable_cache('GT3/portimao/ff1')
s = fastf1.get_session(2021, 'Portugal', 'Q'); s.load(weather=False, messages=False)
lap = s.laps.pick_fastest(); tel = lap.get_telemetry()
print(lap['Driver'], lap['LapTime'])
out = dict(driver=lap['Driver'], lap_s=lap['LapTime'].total_seconds(),
           x=(tel['X']/10).tolist(), y=(tel['Y']/10).tolist(), z=(tel['Z']/10).tolist(),
           d=tel['Distance'].tolist(), v=tel['Speed'].tolist())
json.dump(out, open('GT3/portimao/f1_2021_q_pole.json', 'w'))
print('pts', len(out['x']), 'dist', out['d'][-1], 'z span', max(out['z'])-min(out['z']), 'vmax', max(out['v']))
