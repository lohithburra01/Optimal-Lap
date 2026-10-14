"""Real driven curvature (g_lat*g/v^2) vs sim line curvature (engine grip stencil), on the real distance axis."""
import sys, json, io, contextlib, numpy as np
from scipy.ndimage import uniform_filter1d
import trace_fit as T, sim_gt3_car as G
rl = np.array(json.load(open(sys.argv[1]))["raceline"]); car = dict(G.GT3_CAR); car.update(json.load(open(sys.argv[2])))
with contextlib.redirect_stdout(io.StringIO()):
    rmse, r, pairs, svr, sh = T.compare(rl, car)
E = np.load("_env.npz")
kr = uniform_filter1d(np.abs(E["gl"]) * 9.81 / np.maximum(E["v"], 5) ** 2, 15)
G.C.apply_car(car); ks = np.array([0.0])
from scipy.ndimage import median_filter
n = len(rl); st = 4; k = np.zeros(n)
for i in range(n):
    a, b, c = rl[(i - st) % n], rl[i], rl[(i + st) % n]; ab, bc, ac = b - a, c - b, c - a
    k[i] = abs(2 * (ab[0] * bc[1] - ab[1] * bc[0]) / max(np.linalg.norm(ab) * np.linalg.norm(bc) * np.linalg.norm(ac), 1e-9))
k = median_filter(k, 5, mode="wrap"); sd = (r["arc"] - sh) % r["L"]; o = np.argsort(sd)
# use the same piecewise map as compare
sc = r["L"] / T.REAL_LEN
xr = np.r_[0, [p[0] for p in pairs], T.rd[-1]]; xs = np.r_[0, [p[1] for p in pairs], T.rd[-1] * sc]
ksr = np.interp(np.interp(E["d"], xr, xs), sd[o], k[o])
lo = int(sys.argv[3]) if len(sys.argv) > 3 else 0; hi = int(sys.argv[4]) if len(sys.argv) > 4 else 4600; step = int(sys.argv[5]) if len(sys.argv) > 5 else 25
for x in range(lo, hi, step):
    m = (E["d"] >= x) & (E["d"] < x + step)
    if m.any():
        print(f"{x:5d} R_real {1/max(kr[m].max(),1e-4):6.0f}  R_sim {1/max(ksr[m].max(),1e-4):6.0f}   v {E['v'][m].mean()*3.6:4.0f}")
