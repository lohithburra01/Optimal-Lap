"""Option A (user 2026-10-15): quali-pace v2. Same measured car/line/track; ONLY tyre grip (mu_lat, mu_long, mu_drive)
scaled by one factor k (fresh tyres, low fuel, pro driver in quali) to beat the GT Open 2025 Portimao pole 1:39.966.
Power, drag, downforce, hills, line unchanged.  python GT3/portimao/_quali_grip.py TARGET_S"""
import sys, os, json, io, contextlib, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, HERE)
import sim_gt3_car as G
target = float(sys.argv[1])
base = dict(G.GT3_CAR); base.update(json.load(open(os.path.join(HERE, "gt3_car_measured.json"))))
rl = np.array(json.load(open(os.path.join(HERE, "assets", "portimao_gt3real_raceline.json")))["raceline"])
def run(k):
    c = dict(base); c.update(mu_lat=base["mu_lat"] * k, mu_long=base["mu_long"] * k, mu_drive=base["mu_drive"] * k)
    with contextlib.redirect_stdout(io.StringIO()):
        return G.simulate(rl, c), c
lo, hi = 1.0, 1.4
for _ in range(18):
    m = 0.5 * (lo + hi); lo, hi = (m, hi) if run(m)[0]["lap"] > target else (lo, m)
k = hi; r, c = run(k)
json.dump(c, open(os.path.join(HERE, "gt3_car_quali.json"), "w"), indent=1)
mode = ["BRAKING" if x == "BRAKING" else "" for x in r["mode"]]
G.S.write_csv(os.path.join(HERE, "assets", "portimao_gt3quali_synthetic.csv"),
              r["v"], np.ones(len(r["v"])), mode, np.zeros(len(r["v"])), r["t"], r["arc"], r["L"], fps=30)
print(f"[quali] grip x{k:.4f}: mu_lat {c['mu_lat']:.3f} ({c['mu_lat']:.2f} g static), mu_long {c['mu_long']:.3f}  "
      f"lap {r['lap']:.3f}s  top {r['v'].max()*3.6:.1f}  min {r['v'].min()*3.6:.1f}")
