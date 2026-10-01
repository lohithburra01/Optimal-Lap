"""Sepang 2017 on the SVG road (shipped outline): per-corner basin-searched min-time line
(svg_basins_rl.json; T1 inside attack), simulated on the shipped SVG frame (scale 1.0), then ONLY cl trimmed to the
real 1:30.076 pole (as _sepang_2017.py). Writes sepang_2017_svg.csv / _rl.json / _report.json."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sim_2017_car as C
import sim_2026_lap as S
POLE, SCALE = 90.076, 1.0
rep = json.load(open(os.path.join(HERE, "sepang_2017_report.json")))
car0, DRS = dict(rep["car_untrimmed"]), rep["drs"]
rl = np.asarray(json.load(open(os.path.join(HERE, "svg_basins_rl.json")))["raceline"])[:, :2]
untr = C.simulate(rl * SCALE, car0, DRS)["lap"]
lo, hi = car0["cl"] * 0.6, car0["cl"] * 1.4
for _ in range(60):
    mid = 0.5 * (lo + hi); t = C.simulate(rl * SCALE, dict(car0, cl=mid), DRS)["lap"]
    lo, hi = (mid, hi) if t > POLE else (lo, mid)
    if abs(t - POLE) < 0.0004: break
car = dict(car0, cl=mid); r = C.simulate(rl * SCALE, car, DRS)
print(f"untrimmed {untr:.3f}s vs real {POLE}; cl {car0['cl']:.3f} -> {mid:.3f} ({100*(mid/car0['cl']-1):+.1f}%) -> {r['lap']:.3f}s; "
      f"previous (old road, wide T1) trim was {100*(rep['car']['cl']/car0['cl']-1):+.1f}%")
S.write_csv(os.path.join(HERE, "sepang_2017_svg.csv"), r["v"], np.ones(len(r["v"])), r["mode"], r["pkw"], r["t"], r["arc"], r["L"], fps=30)
json.dump({"raceline": rl.tolist(), "arc_length": (r["arc"] / SCALE).tolist(), "track_length_m": r["L"] / SCALE},
          open(os.path.join(HERE, "sepang_2017_svg_rl.json"), "w"))
json.dump(dict(car=car, car_untrimmed=car0, drs=DRS, line="svg_basins_rl.json (SVG road, T1 inside)", scale=SCALE,
               untrimmed_lap=untr, lap=r["lap"], pole_2017=POLE), open(os.path.join(HERE, "sepang_2017_svg_report.json"), "w"), indent=1)
print(f"top {r['v'].max()*3.6:.1f}  min {r['v'].min()*3.6:.1f} km/h")
