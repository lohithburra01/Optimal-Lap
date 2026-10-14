"""Measure the real AMG GT3 Evo envelope from real_amg_gt3_trackday.json (speed OCR + g-dial).
Kinematic accel = dv/dt of the speed trace (immune to accelerometer slope bias); slope from FastF1 2021 z."""
import json, numpy as np
from scipy.ndimage import uniform_filter1d
R = json.load(open("real_amg_gt3_trackday.json")); F = json.load(open("f1_2021_q_pole.json"))
t = np.array(R["t"]); d = np.array(R["d"]); v = np.array(R["v_kmh"]) / 3.6
gl = np.array(R["g_lat"], float); gx = np.array(R["g_lon"], float)
m = t >= 0; t, d, v, gl, gx = t[m], d[m], v[m], gl[m], gx[m]
fd = np.array(F["d"]); fz = np.array(F["z"]); Lf = fd[-1]
print("F1 lap len", Lf, "real len 4595  samples", len(t), "dt", np.median(np.diff(t)))
SH = 266.0; LS = 4653.0   # real lap start = sim arc 266 m on the S/F-rolled line (sim L ~ outline len)
fz_s = uniform_filter1d(fz, 25)
dz = lambda dd: np.interp(((dd * Lf / 4595.0) + SH * Lf / LS) % Lf, fd, fz_s, period=Lf)
z = dz(d); vs = uniform_filter1d(v, 9)
a = np.gradient(vs, t); a = uniform_filter1d(a, 9)
slope = np.gradient(uniform_filter1d(z, 31), d + np.arange(len(d)) * 1e-6)
print("z span on trace", z.max() - z.min(), "max slope %", 100 * np.abs(slope).max())
print("sign check: corr(a, g_lon) =", np.corrcoef(a, gx)[0, 1])
k = 9.81
print("\nspeed bin | g_lat p95 max | brake kin p95 (incl slope) | accel kin p95 | a+g*slope p95")
for lo in range(60, 280, 20):
    s = (v * 3.6 >= lo) & (v * 3.6 < lo + 20)
    if s.sum() < 10: continue
    ae = a + k * slope   # tractive minus drag (slope removed): what power/grip delivers
    print(f"{lo:3d}-{lo+20:3d} n{s.sum():4d} | {np.percentile(np.abs(gl[s]),95):.2f} {np.abs(gl[s]).max():.2f} | "
          f"{np.percentile(-a[s],95)/k:.2f} {np.percentile(-ae[s],95)/k:.2f} | {np.percentile(a[s],95)/k:.2f} | {np.percentile(ae[s],95)/k:.2f}")
np.savez("_env.npz", t=t, d=d, v=v, a=a, slope=slope, gl=gl, gx=gx, z=z)
