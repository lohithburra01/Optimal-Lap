"""Structured fit of the 2017-era car to real 2018 Q telemetry (6 tracks).
Inner (per track, closed form iterations): cda <- cda*(top_sim/top_real)^3 (v_top ~ CdA^-1/3),
  cl <- secant on lap time. Outer (shared car): Nelder-Mead on mean aligned speed RMSE
  (min of corner-matched and raw) + sorted-speed RMSE. Writes car_2017_fit_v2.json."""
import json, os, sys, time
import numpy as np
from scipy.optimize import minimize
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import _eval_2017 as E
SH = [("p_kw", 480, 800), ("drs_frac", 0.05, 0.25), ("mu_lat", 1.6, 2.6), ("mu_long", 1.1, 2.1),
      ("mu_drive", 0.8, 1.6), ("acc_g", 1.3, 2.6), ("trail_v", 150, 300), ("trail_min", 0.25, 0.8)]
OUT = os.path.join(HERE, "car_2017_fit_v2.json")
state = {"track": {s: {"cl": 4.4, "cda": 1.2} for s in E.SLUGS}}
best = [1e9]; t0 = time.time(); nev = [0]

def inner(shared, iters=6):
    tr = state["track"]
    for it in range(iters):
        res = E.evaluate(dict(shared, track=tr), quiet=True)
        done = True
        for r in res:
            k = tr[r["slug"]]
            k["cda"] = float(np.clip(k["cda"] * (r["top_s"] / r["top_r"]) ** 3, 0.5, 2.5))
            e = r["lap"] / r["real"] - 1
            k["cl"] = float(np.clip(k["cl"] * (1 + 6.0 * e), 1.0, 9.0))   # ~ dlap/dcl elasticity
            if abs(e) > 0.0015 or abs(r["top_s"] - r["top_r"]) > 1.5: done = False
        if done: break
    return E.evaluate(dict(shared, track=tr), quiet=True)

def loss(x):
    shared = {n: float(np.clip(v, lo, hi)) for (n, lo, hi), v in zip(SH, x)}
    res = inner(shared); nev[0] += 1
    L = np.mean([min(r["rmse"], r["rmse_raw"]) + np.sqrt(np.mean((np.sort(r["vs"]) - np.sort(r["vr"])) ** 2))
                 + 15 * abs(100 * (r["lap"] / r["real"] - 1)) for r in res])
    if L < best[0]:
        best[0] = L
        json.dump(dict(loss=float(L), params=dict(shared, track=state["track"]),
                       table=[{k: r[k] for k in ("slug", "lap", "real", "top_s", "top_r", "rmse", "rmse_raw", "corr")} for r in res]),
                  open(OUT, "w"), indent=1)
    print(f"ev {nev[0]} t {time.time()-t0:.0f}s loss {L:.3f} best {best[0]:.3f} " +
          " ".join(f"{n}={v:.3g}" for n, v in shared.items()), flush=True)
    return L

if __name__ == "__main__":
    prev = json.load(open(os.path.join(HERE, "car_2017_fit.json")))["x"]
    x0 = np.array([prev[n] for n, _, _ in SH])
    x0[0] = 660.0
    step = np.array([40, 0.03, 0.15, 0.15, 0.12, 0.2, 25, 0.08])
    sim = np.vstack([x0] + [x0 + np.eye(len(x0))[i] * step[i] for i in range(len(x0))])
    minimize(loss, x0, method="Nelder-Mead", options=dict(initial_simplex=sim, maxfev=int(sys.argv[1]), xatol=1e-3, fatol=0.02))
    print("done", best[0])
