"""Fit the 2017-era car to real 2018 Q speed traces (6 tracks).
Shared: p_kw, drs_frac, mu_lat, mu_long, mu_drive, acc_g, trail_v, trail_min.  Per track: cl, cda.
Loss per track = rmse(aligned speed) + rmse(sorted speed = amplitude, alignment-free) + 15*|lap err %|.
Writes car_2017_fit.json. Bounded Powell."""
import json, os, sys, time
import numpy as np
from scipy.optimize import minimize
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import _eval_2017 as E
SH = [("p_kw", 480, 780, 700), ("drs_frac", 0.05, 0.25, 0.12), ("mu_lat", 1.6, 2.6, 2.05),
      ("mu_long", 1.1, 2.0, 1.45), ("mu_drive", 0.8, 1.6, 1.1), ("acc_g", 1.3, 2.5, 1.9),
      ("trail_v", 150, 300, 235), ("trail_min", 0.25, 0.8, 0.40)]
PT = [("cl", 2.0, 8.0, 4.6), ("cda", 0.7, 2.2, 1.4)]
names = [s[0] for s in SH] + [f"{t}.{p[0]}" for t in E.SLUGS for p in PT]
lo = np.array([s[1] for s in SH] + [p[1] for t in E.SLUGS for p in PT], float)
hi = np.array([s[2] for s in SH] + [p[2] for t in E.SLUGS for p in PT], float)
x0 = np.array([s[3] for s in SH] + [p[3] for t in E.SLUGS for p in PT], float)
start = os.path.join(HERE, "car_2017_fit.json")
if os.path.exists(start) and "--fresh" not in sys.argv:
    j = json.load(open(start)); x0 = np.array([j["x"][n] for n in names])

def to_params(x):
    p = {n: float(v) for n, v in zip(names, x) if "." not in n}; p["track"] = {}
    for n, v in zip(names, x):
        if "." in n:
            t, k = n.split("."); p["track"].setdefault(t, {})[k] = float(v)
    return p

best = [1e9]; n_ev = [0]; t0 = time.time()
def loss(z):
    x = lo + (hi - lo) * np.clip(z, 0, 1)
    res = E.evaluate(to_params(x), quiet=True); L = 0.0
    for r in res:
        vs, vr = np.array(r["vs"]), np.array(r["vr"])
        L += min(r["rmse"], r["rmse_raw"]) + float(np.sqrt(np.mean((np.sort(vs) - np.sort(vr)) ** 2))) \
             + 15 * abs(100 * (r["lap"] / r["real"] - 1))
    L /= len(res); n_ev[0] += 1
    if L < best[0]:
        best[0] = L
        json.dump(dict(loss=L, x=dict(zip(names, map(float, x))), params=to_params(x)),
                  open(start, "w"), indent=1)
        print(f"ev {n_ev[0]} t {time.time()-t0:.0f}s loss {L:.3f}", flush=True)
    return L

if __name__ == "__main__":
  z0 = (x0 - lo) / (hi - lo)
  r = minimize(loss, z0, method="Powell", bounds=[(0, 1)] * len(z0),
               options=dict(maxfev=int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1500, xtol=1e-3, ftol=1e-4))
  print("done", r.fun, n_ev[0])
