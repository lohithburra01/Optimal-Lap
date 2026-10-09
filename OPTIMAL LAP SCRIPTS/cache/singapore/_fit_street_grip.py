"""Measure the Singapore street-grip factor on the PHYSICAL 2025 car (2018-fit fleet cl 4.277, mass 800, DRS from
RUS, cda -> 316 km/h): bisect k so the lap = RUS's 89.158 on the given 2025 line; compare corner minima with the
real lap and with the cl-trimmed car. -> cache/singapore/street_grip.json"""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "cache", "era2017")); sys.path.insert(0, H)
import sim_2026_lap as S, _sg_grip as G, _car2025 as K
from scipy.signal import find_peaks
line = sys.argv[1]; rl = np.asarray(json.load(open(line))["raceline"])[:, :2]
phys = json.load(open(os.path.join(H, "car2025_phys.json"))); car, drs = phys["car"], phys["drs"]
def lap(k, c=car):
    G.apply(S, k); return K.sim(rl, c, drs)
lo, hi = 0.3, 1.0
for _ in range(25):
    m = 0.5 * (lo + hi); t = lap(m)["lap"]; lo, hi = (lo, m) if t < 89.158 else (m, hi)
k = m; r = lap(k)
real = np.genfromtxt(os.path.join(ROOT, "F1_Pipeline_Assets", "exports", "reference_2025_singapore_q.csv"), delimiter=",", names=True)
pr, _ = find_peaks(-real["speed"], prominence=12); fr = real["distance"] / real["distance"][-1]
def mins(r):
    v = r["v"] * 3.6; f = r["arc"] / r["L"]; return np.array([v[np.abs(f - x) < 0.015].min() for x in fr[pr]])
mk = mins(r); trim = json.load(open(os.path.join(H, "car2025_off2.json"))); G.apply(S, 1.0) if False else None
S.a_lat_max_banked, S.v_grip_static = S._sg_orig; S._sg_mech = 1.0
mt = mins(K.sim(rl, trim["car"], trim["drs"]))
print(f"street-grip k = {k:.4f} (lap {r['lap']:.3f}, top {r['v'].max()*3.6:.1f})")
print(" corner  real  k-car  cl-trim");
for x, a, b, c in zip(real["distance"][pr], real["speed"][pr], mk, mt): print(f" {x:5.0f}  {a:4.0f}  {b:4.0f} {b-a:+4.0f}  {c:4.0f} {c-a:+4.0f}")
print(f" median |err|: k-car {np.median(np.abs(mk-real['speed'][pr])):.1f}, cl-trim {np.median(np.abs(mt-real['speed'][pr])):.1f}; "
      f"max: {np.abs(mk-real['speed'][pr]).max():.0f} / {np.abs(mt-real['speed'][pr]).max():.0f}")
json.dump(dict(k=k, car=car, drs=drs, line=line, lap=r["lap"]), open(os.path.join(H, "street_grip.json"), "w"), indent=1)
