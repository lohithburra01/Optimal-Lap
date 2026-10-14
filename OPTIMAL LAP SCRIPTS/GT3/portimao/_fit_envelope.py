"""Car = measured envelope of the real AMG GT3 Evo (from _env.npz). No lap-time fitting.
power/drag : full-throttle kinematic accel (slope removed) per speed bin, p95
lateral     : g_lat at each corner apex (speed minimum) -> mu_lat, cl
braking     : kinematic decel p95 per speed bin -> mu_long + trail release
traction    : low-speed accel cap"""
import json, numpy as np
from scipy.optimize import least_squares
from scipy.signal import find_peaks
E = np.load("_env.npz"); v, a, sl, gl, t = E["v"], E["a"], E["slope"], E["gl"], E["t"]
g = 9.81; m = 1420.0; rho = 1.20
ae = a + g * sl
def binp(x, lo, hi, q):
    c, y = [], []
    for b in range(lo, hi, 20):
        s = (v * 3.6 >= b) & (v * 3.6 < b + 20)
        if s.sum() > 20: c.append((b + 10) / 3.6); y.append(np.percentile(x[s], q))
    return np.array(c), np.array(y)
# ---- power / drag
vc, ac = binp(ae, 120, 260, 95)
r = least_squares(lambda p: p[0] * 1e3 / (m * vc) - 0.5 * rho * p[1] * vc**2 / m - ac, [350, 0.8])
P, CDA = r.x; print(f"power {P:.0f} kW  CdA {CDA:.3f}   resid g", np.round(r.fun / g, 3))
vt = np.linspace(40, 100, 6000); vtop = vt[np.argmin(np.abs(P*1e3/(m*vt) - 0.5*rho*CDA*vt**2/m))]
print(f"  flat-road terminal {vtop*3.6:.0f} km/h")
# ---- traction cap: low speed bins
vl, al = binp(ae, 60, 120, 95); print("traction p95 g", np.round(al / g, 2), "at", np.round(vl * 3.6))
ACC = float(al.max() / g)
# ---- lateral at corner apices
i, _ = find_peaks(-v, prominence=12 / 3.6, distance=40)
apx = []
for k in i:
    w = slice(max(0, k - 15), k + 16); gmax = np.abs(gl[w]).max()
    apx.append((v[k], gmax)); print(f"  apex t {t[k]:6.2f}s  v {v[k]*3.6:5.0f} km/h  g_lat {gmax:.2f}")
apx = np.array(apx)
# (dial/label quantised 0.1 g) fit a = mu (g + 0.5 rho cl v^2 / m) on apex points (upper envelope)
rl = least_squares(lambda p: p[0] * (g + 0.5 * rho * p[1] * apx[:, 0]**2 / m) / g - apx[:, 1], [1.6, 1.5], bounds=([1.0, 0.0], [2.5, 6.0]))
MU, CL = rl.x; print(f"lateral mu {MU:.3f} cl {CL:.2f} -> {MU:.2f} g static, {MU*(1+0.5*rho*CL*(200/3.6)**2/m/g):.2f} g @200   resid", np.round(rl.fun, 2))
# ---- braking (decel p95 per bin) = mu_long (g + DF/m) * trail(v) + drag/m (drag added by engine)
vb, db = binp(-ae, 60, 180, 95)   # >180: samples are mostly brake ramp-in, not the limit
def brk(p, vv):
    mul, tmin, tv, te = p; tr = np.where(vv*3.6 >= tv, 1.0, tmin + (1-tmin) * np.clip(vv*3.6/tv, 0, 1)**te)
    return mul * (g + 0.5*rho*CL*vv**2/m) * tr + 0.5*rho*CDA*vv**2/m
rb = least_squares(lambda p: brk(p, vb) - db, [1.5, 0.5, 160, 1.5], bounds=([1.0, 0.1, 100, 0.5], [2.5, 1.0, 260, 4.0]))
MUL, TMIN, TV, TE = rb.x
print(f"braking mu_long {MUL:.3f} trail_min {TMIN:.2f} trail_v {TV:.0f} trail_exp {TE:.2f}  resid g", np.round(rb.fun / g, 2))
car = dict(mass=m, p_kw=round(P, 1), cda=round(CDA, 4), cl=round(CL, 4), drs_frac=0.0, rho=rho,
           mu_lat=round(MU, 4), mu_long=round(MUL, 4), mu_drive=round(MU, 4), acc_g=round(ACC, 3),
           trail_v=round(TV, 1), trail_min=round(TMIN, 3), trail_exp=round(TE, 3), gg_p=2.0)
json.dump(car, open("gt3_car_measured.json", "w"), indent=1); print(car)
