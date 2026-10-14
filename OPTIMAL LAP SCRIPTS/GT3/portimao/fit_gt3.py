"""Fit the GT3 downforce area cl so the sim lap on a given line = target (real best Mercedes-AMG GT3 Evo Q lap).
  python GT3/portimao/fit_gt3.py RACELINE.json TARGET_S [out.json]"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contextlib, io
import sim_gt3_car as G
rl = json.load(open(sys.argv[1]))["raceline"]; target = float(sys.argv[2])
def lap(cl):
    with contextlib.redirect_stdout(io.StringIO()):
        r = G.simulate(rl, dict(cl=cl))
    return r["lap"], r
lo, hi = 0.5, 8.0
for _ in range(22):
    m = 0.5 * (lo + hi); t, _ = lap(m)
    lo, hi = (m, hi) if t > target else (lo, m)
cl = 0.5 * (lo + hi); t, r = lap(cl)
rho = G.GT3_CAR["rho"]; v = 200 / 3.6
print(f"cl {cl:.3f}  lap {t:.3f}  top {r['v'].max()*3.6:.1f}  min {r['v'].min()*3.6:.1f} km/h  "
      f"downforce@200 {0.5*rho*cl*v*v/9.81:.0f} kg  @250 {0.5*rho*cl*(250/3.6)**2/9.81:.0f} kg")
if len(sys.argv) > 3: json.dump(dict(G.GT3_CAR, cl=round(cl, 4), target_s=target), open(sys.argv[3], "w"), indent=1)
