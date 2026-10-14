"""Variant: power 368 kW and CdA 0.73 FIXED at the values measured from the real full-throttle acceleration curve.
Fit GT3 car parameters to the REAL AMG GT3 Evo Portimao speed trace (Nelder-Mead on aligned speed RMSE).
  python GT3/portimao/fit_to_trace.py LINE_SF.json OUT_CAR.json"""
import json, sys, os
import numpy as np
from scipy.optimize import minimize
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import trace_fit as T
rl = np.asarray(json.load(open(sys.argv[1]))["raceline"])
base = dict(T.G.GT3_CAR); base.update(p_kw=368.0, cda=0.73)
_, _, _, _, SH = T.compare(rl, base)
KEYS = ["cl", "mu_lat", "mu_long", "mu_drive", "trail_min"]
x0 = np.array([2.7, 1.60, 1.60, 1.20, 0.60])
def car_of(x):
    c = dict(base); c.update(zip(KEYS, x)); c["mu_lat"] = max(c["mu_lat"], 0.8); return c
def f(x):
    if x[0] < 0 or not (0.2 <= x[4] <= 1.0): return 1e3
    try: return T.compare(rl, car_of(x), shift=SH)[0]
    except Exception: return 1e3
res = minimize(f, x0, method="Nelder-Mead", options=dict(maxfev=500, xatol=1e-3, fatol=0.02, initial_simplex=None))
car = car_of(res.x); json.dump(car, open(sys.argv[2], "w"), indent=1)
print("RMSE %.2f km/h" % res.fun, {k: round(car[k], 3) for k in KEYS})
T.compare(rl, car, verbose=True, shift=SH)
