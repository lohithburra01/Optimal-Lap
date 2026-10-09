"""Car A for the Singapore 2025-vs-2026 dual video: George Russell's REAL 2025 pole lap (1:29.158).
OpenF1 car_data (speed/throttle/brake/DRS, ~3.7 Hz) for session 9892 drv 63 lap 17, same window and
distance integration as fetch_openf1_lap.py, plus the DRS channel -> mode DRS/REGEN/FULL/NORMAL.
The official position feed is map-matched (one path for all cars), so his real LINE is unknown: he
rides our 2026 line. His distance is warped onto our lap corner-by-corner (speed minima paired) so he
brakes at the right place on our line; time is scaled so the integrated lap = official 89.158 s.
  python cache/singapore/_rus2025_car.py"""
import csv, json, os, sys
import numpy as np
from datetime import timedelta
from scipy.signal import find_peaks
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, ROOT)
import fetch_openf1_lap as F
RAW = os.path.join(H, "rus2025_car_data.json")
# argv: [SIM_CSV OUT_CSV] - warp onto the lap of SIM_CSV (default: the 2026 lap, as the first dual video)
SIM = sys.argv[1] if len(sys.argv) > 2 else os.path.join(ROOT, "F1_Pipeline_Assets", "exports", "singapore_2026_synthetic.csv")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(H, "rus2025_on_2026_line.csv")
OFFICIAL = 89.158
if not os.path.exists(RAW):
    lap = [l for l in F.get("laps", session_key=9892, driver_number=63) if l["lap_number"] == 17][0]
    start = F.parse_dt(lap["date_start"]); end = start + timedelta(seconds=lap["lap_duration"] + 0.5)
    cd = F.get("car_data", session_key=9892, driver_number=63, **{"date>": start.isoformat(), "date<": end.isoformat()})
    json.dump(dict(lap=lap, car_data=cd), open(RAW, "w"))
raw = json.load(open(RAW)); cd = sorted([c for c in raw["car_data"] if c.get("speed") is not None], key=lambda c: c["date"])
seen, rows = set(), []
for c in cd:
    if c["date"] not in seen: seen.add(c["date"]); rows.append(c)
t0 = F.parse_dt(rows[0]["date"]); t = np.array([(F.parse_dt(c["date"]) - t0).total_seconds() for c in rows])
v = np.array([float(c["speed"]) for c in rows]); d = np.r_[0, np.cumsum(0.5 * (v[1:] + v[:-1]) / 3.6 * np.diff(t))]
print(f"[rus] {len(rows)} samples, lap {t[-1]:.3f} s integrated, {d[-1]:.0f} m (official {raw['lap']['lap_duration']})")
# corner pairing: real speed minima <-> our 2026 sim minima (same order, nearest lap fraction)
s = np.genfromtxt(SIM, delimiter=",", names=True); ds, vs = s["distance"], s["speed"]
Ds = ds[-1] + (ds[-1] - ds[-2]); Dr = d[-1] + (d[-1] - d[-2])
pr, _ = find_peaks(-v, prominence=12); ps, _ = find_peaks(-vs, prominence=12, distance=20)
kr, ks = [0.0], [0.0]
for i in pr:
    j = ps[np.argmin(abs(ds[ps] / Ds - d[i] / Dr))]
    if abs(ds[j] / Ds - d[i] / Dr) < 0.02 and ds[j] > ks[-1]:
        kr.append(d[i]); ks.append(ds[j]); print(f"[rus] corner {d[i]:6.0f} m ({v[i]:.0f}) -> ours {ds[j]:6.0f} m ({vs[j]:.0f})")
kr.append(Dr); ks.append(Ds)
dw = np.interp(d, kr, ks)
t = t * OFFICIAL / t[-1]
drs = np.array([int(c.get("drs") or 0) for c in rows]); br = np.array([float(c.get("brake") or 0) for c in rows])
thr = np.array([float(c.get("throttle") or 0) for c in rows])
mode = np.where(drs >= 10, "DRS", np.where(br > 0, "REGEN", np.where(thr >= 98, "FULL", "NORMAL")))
print(f"[rus] DRS open {np.mean(drs >= 10):.0%} of samples; paired {len(kr) - 2}/{len(pr)} corners")
with open(OUT, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["frame", "time_s", "distance", "speed", "throttle", "brake", "gear", "rpm", "mode"])
    for i, c in enumerate(rows):
        w.writerow([i, round(t[i], 4), round(dw[i], 3), v[i], thr[i], br[i], int(c.get("n_gear") or 0), int(c.get("rpm") or 0), mode[i]])
print(f"[rus] wrote {OUT}")
