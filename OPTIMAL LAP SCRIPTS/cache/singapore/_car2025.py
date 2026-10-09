"""2025 car for Singapore (RUS pole 1:29.158), on the era-2017 car model (same V6-hybrid PU architecture,
fitted to real 2018 Q telemetry: cache/era2017/). Only regs/data-fixed changes: mass 800 kg (2025 min 798),
ISA rho, DRS zones from RUS's real DRS channel. cda fitted to his top speed, cl to his lap time (alternating
bisection) on the given line.  python cache/singapore/_car2025.py LINE_RL(mirror frame) OUT_JSON"""
import json, os, sys, contextlib, io
import numpy as np
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "cache", "era2017"))
import sim_2017_car as C
POLE, VTOP = 89.158, 316.0
LAPT = 89.158
def drs_zones():
    # official track (2026-10-08 rebuild): lap fraction = REAL distance / real lap distance on the official clock
    from datetime import datetime
    raw = json.load(open(os.path.join(H, "rus2025_car_data.json"))); lap = raw["lap"]; P_ = datetime.fromisoformat
    cd = sorted([c for c in raw["car_data"] if c.get("speed") is not None], key=lambda c: c["date"])
    t = np.array([(P_(c["date"]) - P_(lap["date_start"])).total_seconds() for c in cd]); v = np.array([c["speed"] for c in cd], float)
    d = np.r_[0, np.cumsum(0.5 * (v[1:] + v[:-1]) / 3.6 * np.diff(t))] + v[0] / 3.6 * t[0]; D = float(np.interp(LAPT, t, d))
    f = d / D; on = np.array([int(c.get("drs") or 0) >= 10 for c in cd]) & (t >= 0) & (t <= LAPT)
    z, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j + 1 < len(on) and on[j + 1]: j += 1
            z.append([round(float(max(f[i], 0)), 4), round(float(min(f[j], 1)), 4)]); i = j + 1
        else: i += 1
    return z
def sim(rl, car, drs, smooth=True):
    with contextlib.redirect_stdout(io.StringIO()): return C.simulate(rl, car, drs, smooth=smooth)
if __name__ == "__main__":
    rl = np.asarray(json.load(open(sys.argv[1]))["raceline"])[:, :2]
    car = dict(json.load(open(os.path.join(ROOT, "cache", "era2017", "sepang_2017_report.json")))["car_untrimmed"])
    car.update(mass=800.0, rho=1.2232); drs = drs_zones(); print("[2025] DRS zones (lap frac):", drs)
    for it in range(4):
        lo, hi = 0.6, 2.4
        for _ in range(30):
            m = 0.5 * (lo + hi); v = sim(rl, dict(car, cda=m), drs)["v"].max() * 3.6
            lo, hi = (m, hi) if v > VTOP else (lo, m)
        car["cda"] = m
        lo, hi = 2.0, 7.0
        for _ in range(30):
            m = 0.5 * (lo + hi); t = sim(rl, dict(car, cl=m), drs)["lap"]
            lo, hi = (m, hi) if t > POLE else (lo, m)
        car["cl"] = m; r = sim(rl, car, drs)
        print(f"[2025] it{it}: cda {car['cda']:.4f} cl {car['cl']:.4f} -> lap {r['lap']:.3f} top {r['v'].max()*3.6:.1f} min {r['v'].min()*3.6:.1f}")
    json.dump(dict(car=car, drs=drs, line=sys.argv[1], lap=r["lap"]), open(sys.argv[2], "w"), indent=1)
