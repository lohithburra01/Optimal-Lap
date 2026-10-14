"""v2 (2026-10-14): ship the reshaped-track lap. Car = MEASURED real AMG GT3 Evo envelope (gt3_car_measured.json,
no lap-time fit); track = SVG reshaped so the engine line drives the real curvature (reshape_track.py, it 4);
line = TUM engine, no add-ons; hills from 2021 FastF1 z. Line + outline already start at the real S/F.
  python GT3/portimao/_finalize_real.py OUTLINE.json RL.json"""
import json, sys, os, io, contextlib, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, HERE)
import sim_gt3_car as G
TR = os.path.join(HERE, "assets")
o = json.load(open(sys.argv[1])); rl = np.array(json.load(open(sys.argv[2]))["raceline"])[:, :2]
car = dict(G.GT3_CAR); car.update(json.load(open(os.path.join(HERE, "gt3_car_measured.json"))))
with contextlib.redirect_stdout(io.StringIO()):
    r = G.simulate(rl, car)
json.dump(o, open(os.path.join(TR, "portimao_gt3real_outline.json"), "w"))
seg = np.linalg.norm(np.diff(np.vstack([rl, rl[:1]]), axis=0), axis=1)
json.dump({"raceline": rl.tolist(), "arc_length": np.r_[0, np.cumsum(seg)[:-1]].tolist(), "track_length_m": float(seg.sum())},
          open(os.path.join(TR, "portimao_gt3real_raceline.json"), "w"))
mode = ["BRAKING" if m == "BRAKING" else "" for m in r["mode"]]
G.S.write_csv(os.path.join(HERE, "assets", "portimao_gt3real_synthetic.csv"),
              r["v"], np.ones(len(r["v"])), mode, np.zeros(len(r["v"])), r["t"], r["arc"], r["L"], fps=30)
print(f"[final v2] lap {r['lap']:.3f}s  top {r['v'].max()*3.6:.1f}  min {r['v'].min()*3.6:.1f} km/h  L {r['L']:.0f} m")
