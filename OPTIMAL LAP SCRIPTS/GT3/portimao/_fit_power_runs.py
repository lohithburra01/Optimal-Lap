"""Power/drag from sustained full-throttle runs (speed rising >=2.5 s, |g_lat|<0.6, v>110 km/h), slope removed,
least squares on ALL run samples (not a percentile: dv/dt noise inflates percentiles)."""
import json, numpy as np
from scipy.optimize import least_squares
from scipy.ndimage import uniform_filter1d
E = np.load("_env.npz"); t, v, a, sl, gl = E["t"], E["v"], E["a"], E["slope"], E["gl"]
g = 9.81; m = 1420.0; rho = 1.2
vs = uniform_filter1d(v, 31); up = np.gradient(vs, t) > 0.3
ok = up & (np.abs(gl) < 0.6) & (v * 3.6 > 110)
# keep runs >= 2.5 s, drop first/last 0.3 s (throttle transitions)
idx = np.where(ok)[0]; runs = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1); sel = []
for r in runs:
    if len(r) >= 75: sel.extend(r[9:-9]); print(f"run t {t[r[0]]:6.1f}-{t[r[-1]]:6.1f}s  v {v[r[0]]*3.6:4.0f}->{v[r[-1]]*3.6:4.0f}")
sel = np.array(sel); va, aa = v[sel], a[sel] + g * sl[sel]
r = least_squares(lambda p: p[0]*1e3/(m*va) - 0.5*rho*p[1]*va**2/m - aa, [300, 0.8])
P, CDA = r.x; print(f"P {P:.0f} kW  CdA {CDA:.3f}  rms resid {np.sqrt(np.mean(r.fun**2))/g:.3f} g  n {len(sel)}")
c = json.load(open("gt3_car_measured.json")); c["p_kw"] = round(float(P), 1); c["cda"] = round(float(CDA), 4)
json.dump(c, open("gt3_car_measured.json", "w"), indent=1)
