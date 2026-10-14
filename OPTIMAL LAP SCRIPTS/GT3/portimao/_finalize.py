"""Finalize the GT3 Portimao lap: roll line + outline to the REAL S/F (2021 FastF1), refit cl to the target on the
final line, write the video CSV (mode BRAKING / blank: no hybrid on a GT3) and the shipped JSONs.
  python GT3/portimao/_finalize.py OPT_RL.json TARGET_S"""
import json, sys, os, io, contextlib, subprocess
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import sim_gt3_car as G
src, target = sys.argv[1], float(sys.argv[2])
TR = os.path.join(HERE, "assets")
rl = np.array(json.load(open(src))["raceline"])[:, :2]
out = subprocess.run([sys.executable, os.path.join(HERE, "_sf_check.py"), src], capture_output=True, text=True, cwd=ROOT).stdout
print(out.strip()); i0 = int(out.split("raceline idx ")[1].split()[0]); assert "SAME" in out
rl = np.roll(rl, -i0, axis=0)
o = json.load(open(os.path.join(TR, "portimao_outline.json")))
oc = (np.array(o["outer"])[:, :2] + np.array(o["inner"])[:, :2]) / 2
j0 = int(np.linalg.norm(oc - rl[0], axis=1).argmin())
o2 = {k: (np.roll(np.array(v), -j0, axis=0).tolist() if k in ("outer", "inner") else v) for k, v in o.items()}
json.dump(o2, open(os.path.join(TR, "portimao_gt3_outline.json"), "w"))
def lap(cl):
    with contextlib.redirect_stdout(io.StringIO()):
        return G.simulate(rl, dict(cl=cl))
lo, hi = 0.5, 6.0
for _ in range(22):
    m = 0.5 * (lo + hi); lo, hi = (m, hi) if lap(m)["lap"] > target else (lo, m)
cl = 0.5 * (lo + hi); r = lap(cl)
car = dict(G.GT3_CAR, cl=round(cl, 4)); json.dump(car, open(os.path.join(HERE, "gt3_car_final.json"), "w"), indent=1)
seg = np.linalg.norm(np.diff(np.vstack([rl, rl[:1]]), axis=0), axis=1)
json.dump({"raceline": rl.tolist(), "arc_length": np.r_[0, np.cumsum(seg)[:-1]].tolist(), "track_length_m": float(seg.sum())},
          open(os.path.join(TR, "portimao_gt3_raceline.json"), "w"))
mode = ["BRAKING" if m == "REGEN" else "" for m in r["mode"]]
csv = os.path.join(HERE, "assets", "portimao_gt3_synthetic.csv")
G.S.write_csv(csv, r["v"], np.ones(len(r["v"])), mode, np.zeros(len(r["v"])), r["t"], r["arc"], r["L"], fps=30)
rho = car["rho"]
print(f"[final] cl {cl:.3f} ({0.5*rho*cl*(200/3.6)**2/9.81:.0f} kg @200)  lap {r['lap']:.3f}s  top {r['v'].max()*3.6:.1f}  "
      f"min {r['v'].min()*3.6:.1f} km/h  outline rolled {j0}, line rolled {i0}")
