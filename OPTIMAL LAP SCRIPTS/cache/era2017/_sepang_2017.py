"""Sepang 2017 recreation with the 2018-calibrated 2017-era car.

1. Car = shared knobs fitted on real 2018 Q telemetry (car_2017_fit.json) + a Sepang wing
   level = median (cl, cda) of the high-downforce calibration tracks (not Monza/Spa).
2. Line = the fastest of the candidate Sepang lines FOR THIS CAR (optimiser line, the shipped
   2026 T1 edit, and the earlier-inside / onboard-style T1 variants) - physics chooses.
3. Untrimmed prediction is reported (the honest test vs the real 1:30.076), then ONLY the
   wing level (cl) is trimmed by bisection to land on the real pole time.
Outputs: cache/era2017/sepang_2017.csv, sepang_2017_rl.json, sepang_2017_report.json
"""
import glob, json, os, sys, statistics as st
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.dirname(HERE); ROOT = os.path.dirname(CACHE)
sys.path.insert(0, HERE); sys.path.insert(0, CACHE)
import sim_2017_car as C
import sim_2026_lap as S

POLE_2017 = 90.076                      # HAM, 2017 Malaysian GP Q3 (Jolpica)
RHO = 1.2202                            # ISA @ ~40 m, same as the shipped 2026 Sepang sim
HIGH_DF = ["canada", "austria", "silverstone", "bahrain"]
# 2017 Sepang DRS: main straight (T15 exit -> T1) and back straight (T14 exit -> T15),
# as arc fractions of the S/F-aligned Sepang line (from the shipped lap's brake points).
DRS = [[0.915, 0.067], [0.750, 0.878]]

fit = json.load(open(os.path.join(HERE, "car_2017_fit_v2.json")))["params"]
car = dict(C.DEFAULT_CAR); car.update({k: v for k, v in fit.items() if k != "track"})
car["cl"] = st.median(fit["track"][t]["cl"] for t in HIGH_DF)
car["cda"] = st.median(fit["track"][t]["cda"] for t in HIGH_DF)
car["rho"] = RHO

SEP = os.path.join(CACHE, "sepang")
cands = {"optimiser (inset 0.5)": os.path.join(SEP, "rl_in05.json"),
         "shipped 2026 line (T1 H60)": os.path.join(ROOT, "F1_Pipeline_Assets", "tracks",
                                                    "malaysian_grand_prix_raceline.json")}
for p in sorted(glob.glob(os.path.join(SEP, "t1_*.json"))):
    if not p.endswith("_rl.json"):
        cands[os.path.basename(p)[:-5]] = p


def load(p):
    return np.asarray(json.load(open(p))["raceline"], float)[:, :2]


def lap(rl, c):
    return C.simulate(rl, c, DRS)


rows = []
for name, p in cands.items():
    r = lap(load(p), car)
    rows.append((r["lap"], name, p, r["v"].max() * 3.6, r["v"].min() * 3.6))
    print(f"  {name:28s} {r['lap']:7.3f}s  top {r['v'].max()*3.6:5.1f}  min {r['v'].min()*3.6:5.1f}", flush=True)
rows.sort()
best_lap, best_name, best_p = rows[0][:3]
print(f"[line] fastest for the 2017 car: {best_name} ({best_lap:.3f}s); "
      f"shipped 2026 line {[r for r in rows if r[1].startswith('shipped')][0][0]:.3f}s")

untrimmed = best_lap
rl = load(best_p)
lo, hi = car["cl"] * 0.7, car["cl"] * 1.4
for _ in range(60):
    mid = 0.5 * (lo + hi); c2 = dict(car, cl=mid)
    t = lap(rl, c2)["lap"]
    if t > POLE_2017: lo = mid
    else: hi = mid
    if abs(t - POLE_2017) < 0.0004: break
car_final = dict(car, cl=mid)
r = lap(rl, car_final)
print(f"[trim] untrimmed {untrimmed:.3f}s vs real {POLE_2017}; cl {car['cl']:.3f} -> {mid:.3f} "
      f"({100*(mid/car['cl']-1):+.1f}%) -> {r['lap']:.3f}s")

# the chosen line re-run with the trimmed car (does the line choice survive the trim?)
rows2 = sorted((lap(load(p), car_final)["lap"], n) for n, p in cands.items())
print("[line@trim] " + ", ".join(f"{n} {t:.3f}" for t, n in rows2[:4]))

S.write_csv(os.path.join(HERE, "sepang_2017.csv"), r["v"], np.ones(len(r["v"])), r["mode"],
            r["pkw"], r["t"], r["arc"], r["L"], fps=30)
src = json.load(open(best_p))
json.dump({"raceline": rl.tolist(), "arc_length": r["arc"].tolist(), "track_length_m": r["L"]},
          open(os.path.join(HERE, "sepang_2017_rl.json"), "w"))
json.dump(dict(car=car_final, car_untrimmed=car, drs=DRS, line=best_name, line_src=best_p,
               untrimmed_lap=untrimmed, lap=r["lap"], pole_2017=POLE_2017,
               candidates=[dict(lap=a, name=b) for a, b, *_ in rows],
               candidates_trimmed=[dict(lap=a, name=b) for a, b in rows2]),
          open(os.path.join(HERE, "sepang_2017_report.json"), "w"), indent=1)
print(f"[out] top {r['v'].max()*3.6:.1f}  min {r['v'].min()*3.6:.1f} km/h, lap {r['lap']:.3f}s")
