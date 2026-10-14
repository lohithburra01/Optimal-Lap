"""GT3 racing line from the project's TUM-based line engine (sim_2026_lap.build_raceline: IQP min-curv seed +
jerk-constrained QP), with the engine's car parameters (WARM_*) set to the GT3 instead of the 2026 F1 car.
No pattern search, no apex penalty.  python GT3/portimao/build_gt3_line.py OUT_RL.json [--inset M] [--jerk J] [--unwind U]"""
import argparse, json, os, sys, io, contextlib
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import sim_gt3_car as G
S = G.S
ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--inset", type=float, default=0.5)
ap.add_argument("--jerk", type=float, default=None); ap.add_argument("--unwind", type=float, default=None)
ap.add_argument("--outline", default=os.path.join(HERE, "assets", "portimao_outline.json"))
ap.add_argument("--car", default=os.path.join(HERE, "gt3_car_final.json"))
ap.add_argument("--roll-to-outline0", action="store_true", help="start the line at the point nearest outline station 0 (S/F)")
a = ap.parse_args()
car = dict(G.GT3_CAR); car.update(json.load(open(a.car)))
a_lat = car["mu_lat"] * (9.81 + 0.5 * car["rho"] * car["cl"] * 45.0 ** 2 / car["mass"])   # grip at a typical 160 km/h corner
S.WARM_MASS_KG = car["mass"]; S.WARM_A_LAT_MAX = a_lat; S.WARM_A_ACC_MAX = car["acc_g"] * 9.81
S.WARM_A_BRK_MAX = car["mu_long"] * 9.81 * 1.15; S.WARM_P_MAX_W = car["p_kw"] * 1e3; S.WARM_CDA = car["cda"]
S.WARM_V_CAP = 85.0; S.WARM_RHO = car["rho"]
if a.jerk: S.J_MAX_LAT_JERK = a.jerk
if a.unwind: S.UNWIND_RATIO = a.unwind
print(f"[gt3line] warm a_lat {a_lat/9.81:.2f} g, jerk {S.J_MAX_LAT_JERK}, unwind {S.UNWIND_RATIO}, inset {a.inset}")
o = json.load(open(a.outline))
rl, arc, kap, L = S.build_raceline(np.array(o["outer"], float), np.array(o["inner"], float), inset_m=a.inset)
if a.roll_to_outline0:
    c0 = (np.array(o["outer"][0]) + np.array(o["inner"][0])) / 2
    rl = np.roll(rl, -int(np.argmin(np.linalg.norm(rl[:, :2] - c0, axis=1))), axis=0)
json.dump({"raceline": rl.tolist()}, open(a.out, "w"))
with contextlib.redirect_stdout(io.StringIO()):
    r = G.simulate(rl, car)
print(f"[gt3line] lap {r['lap']:.3f}s  top {r['v'].max()*3.6:.1f}  min {r['v'].min()*3.6:.1f}")
