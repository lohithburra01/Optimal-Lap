"""Sepang 2017 on the SVG road with the 2017 car UNCHANGED (sepang_2017_report.json 'car', cl 4.037 =
the 2018-fit car trimmed on the builder line) on the min-time line (svg_basins_rl.json, T1 inside).
User choice 2026-10-01: keep the car, accept the faster lap (no re-trim).
Writes sepang_2017_svg_keepcar.csv / _rl.json / _report.json."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sim_2017_car as C
import sim_2026_lap as S
rep = json.load(open(os.path.join(HERE, "sepang_2017_report.json"))); car, DRS = rep["car"], rep["drs"]
rl = np.asarray(json.load(open(os.path.join(HERE, "svg_sm0.006_rl.json")))["raceline"])[:, :2]
r = C.simulate(rl, car, DRS)
S.write_csv(os.path.join(HERE, "sepang_2017_svg_keepcar.csv"), r["v"], np.ones(len(r["v"])), r["mode"], r["pkw"], r["t"], r["arc"], r["L"], fps=30)
json.dump({"raceline": rl.tolist(), "arc_length": r["arc"].tolist(), "track_length_m": r["L"]},
          open(os.path.join(HERE, "sepang_2017_svg_keepcar_rl.json"), "w"))
json.dump(dict(car=car, drs=DRS, line="svg_sm0.006_rl.json (SVG road, min-time + anti-zigzag 0.006, T1 inside)", lap=r["lap"], pole_2017=90.076),
          open(os.path.join(HERE, "sepang_2017_svg_keepcar_report.json"), "w"), indent=1)
print(f"lap {r['lap']:.3f}s  top {r['v'].max()*3.6:.1f}  min {r['v'].min()*3.6:.1f} km/h")
