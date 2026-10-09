"""Car A for the 2025-vs-2026 dual video on the official-geometry track: George Russell's REAL 2025 pole lap on
the OFFICIAL CLOCK (t = car_data date - lap date_start; t=0 at the line, 89.158 at the flag; endpoint samples
interpolated), mapped onto his 2025 line by REAL distance (uniform scale; the track is distance-correct).
Reports timing at the official sector lines and per-segment length ratio (on-screen dot speed vs shown speed).
  python cache/singapore/_rus2025_exact.py SIM2025_CSV OUT_CSV"""
import os, sys, json, csv, numpy as np
from datetime import datetime
from scipy.signal import find_peaks
H = os.path.dirname(os.path.abspath(__file__)); LAP = 89.158
raw = json.load(open(os.path.join(H, "rus2025_car_data.json"))); lap = raw["lap"]; P_ = datetime.fromisoformat
cd = sorted([c for c in raw["car_data"] if c.get("speed") is not None], key=lambda c: c["date"]); seen, rows = set(), []
for c in cd:
    if c["date"] not in seen: seen.add(c["date"]); rows.append(c)
t = np.array([(P_(c["date"]) - P_(lap["date_start"])).total_seconds() for c in rows]); v = np.array([float(c["speed"]) for c in rows])
d = np.r_[0, np.cumsum(0.5 * (v[1:] + v[:-1]) / 3.6 * np.diff(t))] + v[0] / 3.6 * t[0]
k = (t > 0) & (t < LAP); vE = float(np.interp(LAP, t, v)); dE = float(np.interp(LAP, t, d))
tt = np.r_[0.0, t[k], LAP]; vv = np.r_[v[0], v[k], vE]; dd = np.r_[0.0, d[k], dE]
thr = np.r_[rows[0].get("throttle") or 0, [float(c.get("throttle") or 0) for c, m in zip(rows, k) if m], 100.0]
br = np.r_[0.0, [float(c.get("brake") or 0) for c, m in zip(rows, k) if m], 0.0]
drs = np.r_[int(rows[0].get("drs") or 0), [int(c.get("drs") or 0) for c, m in zip(rows, k) if m], 0]
gear = np.r_[int(rows[0].get("n_gear") or 0), [int(c.get("n_gear") or 0) for c, m in zip(rows, k) if m], 7]
s = np.genfromtxt(sys.argv[1], delimiter=",", names=True); ds_, vs = s["distance"], s["speed"]; Ds = ds_[-1] + (ds_[-1] - ds_[-2])
pr, _ = find_peaks(-vv, prominence=12); ps, _ = find_peaks(-vs, prominence=10, distance=20)
kr, ks = [0.0], [0.0]
for i in pr:
    j = ps[np.argmin(abs(ds_[ps] / Ds - dd[i] / dE))]
    if abs(ds_[j] / Ds - dd[i] / dE) < 0.02 and ds_[j] > ks[-1]: kr.append(dd[i]); ks.append(ds_[j])
kr.append(dE); ks.append(Ds); kr, ks = np.array(kr), np.array(ks)
ratio = np.diff(ks) / np.diff(kr)
# On the distance-correct (official) track, map by REAL distance only (no corner anchors): dot position = his real
# distance travelled, dot speed == shown speed everywhere. The anchors are kept only as a report.
dw = dd * Ds / dE
print(f"[rus] official clock: {tt[0]:.3f} -> {tt[-1]:.3f} s, real {dE:.0f} m -> line {Ds:.0f} m; {len(kr)-2}/{len(pr)} corners anchored")
print(f"[rus] per-segment length ratio (line/real): " + " ".join(f"{x:.3f}" for x in ratio) + f"  (anchor warp, NOT used); used: uniform {Ds/dE:.4f}")
S1, S2 = lap["duration_sector_1"], lap["duration_sector_1"] + lap["duration_sector_2"]
for nm, x in (("S1", S1), ("S2", S2), ("LAP", LAP)): print(f"[rus] {nm}: clock {float(np.interp(np.interp(x, tt, dd), dd, tt)):.3f} s = official {x:.3f}")
mode = np.where(drs >= 10, "DRS", np.where(br > 0, "REGEN", np.where(thr >= 98, "FULL", "NORMAL")))
with open(sys.argv[2], "w", newline="") as f:
    w = csv.writer(f); w.writerow(["frame", "time_s", "distance", "speed", "throttle", "brake", "gear", "rpm", "mode"])
    for i in range(len(tt)): w.writerow([i, round(tt[i], 4), round(dw[i], 3), vv[i], thr[i], br[i], gear[i], 0, mode[i]])
print("[rus] wrote", sys.argv[2])
