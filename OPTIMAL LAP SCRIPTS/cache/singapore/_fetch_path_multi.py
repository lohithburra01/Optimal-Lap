"""Dense official path: map-matched location samples from the fastest valid Q lap of the top-10 drivers
(Singapore 2025 Q, session 9892). All cars are snapped to ONE path, so the union samples it densely.
-> cache/singapore/path_samples.json  [{drv, t, x, y, z}] (x,y,z in decimetres as OpenF1 gives them)."""
import os, sys, json
from datetime import timedelta
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, ROOT)
import fetch_openf1_lap as F
laps = [l for l in F.get("laps", session_key=9892) if l.get("lap_duration") and not l.get("is_pit_out_lap")]
best = {}
for l in laps:
    if l["driver_number"] not in best or l["lap_duration"] < best[l["driver_number"]]["lap_duration"]: best[l["driver_number"]] = l
top = sorted(best.values(), key=lambda l: l["lap_duration"])[:10]; out = []
for l in top:
    st = F.parse_dt(l["date_start"]); en = st + timedelta(seconds=l["lap_duration"])
    loc = F.get("location", session_key=9892, driver_number=l["driver_number"], **{"date>": st.isoformat(), "date<": en.isoformat()})
    for r in loc: out.append(dict(drv=l["driver_number"], t=(F.parse_dt(r["date"]) - st).total_seconds(), x=r["x"], y=r["y"], z=r["z"]))
    print(l["driver_number"], l["lap_duration"], len(loc), flush=True)
json.dump(out, open(os.path.join(H, "path_samples.json"), "w")); print(len(out), "samples")
