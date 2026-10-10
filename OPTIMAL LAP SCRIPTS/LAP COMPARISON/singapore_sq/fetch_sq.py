"""Fetch VER + RUS fastest Singapore 2026 Sprint Qualifying laps exactly as LAPCOMP.IPYNB get_clean_trace does,
and save them to sq_traces.npz so the renderer never re-downloads."""
import sys, numpy as np, fastf1, warnings
warnings.simplefilter("ignore")
try: fastf1.Cache.enable_cache("cache")
except Exception: import os; os.makedirs("cache", exist_ok=True); fastf1.Cache.enable_cache("cache")
backend = sys.argv[1] if len(sys.argv) > 1 else None
s = fastf1.get_session(2026, "Singapore", "SQ", backend=backend) if backend else fastf1.get_session(2026, "Singapore", "SQ")
s.load(telemetry=True, laps=True, weather=False, messages=False)
out = {}
for drv in ["VER", "RUS"]:
    lap = s.laps.pick_driver(drv).pick_fastest()
    tel = lap.get_telemetry().dropna(subset=["Distance", "Speed", "X", "Y"]).drop_duplicates(subset=["Time"])
    d = tel["Distance"].values.astype(float); d -= d[0]
    out[drv + "_dist"] = d; out[drv + "_speed"] = tel["Speed"].values / 3.6
    out[drv + "_time"] = tel["Time"].dt.total_seconds().values
    out[drv + "_x"] = tel["X"].values / 10.0; out[drv + "_y"] = tel["Y"].values / 10.0
    out[drv + "_lap_time"] = lap["LapTime"].total_seconds()
    print(drv, lap["LapTime"], "seg", lap["Compound"], "n", len(d), "len %.1f" % d[-1])
q = s.laps.pick_quicklaps().sort_values("LapTime").drop_duplicates("Driver")[["Driver", "LapTime"]].head(5)
print(q.to_string())
np.savez("sq_traces.npz", **out)
