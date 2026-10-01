"""2017-era F1 car on the SAME physics engine as sim_2026_lap.py (imported, never edited).

What changes vs the 2026 car (regs 2017-2018):
  * passive aero: ONE drag/downforce level all lap (no X/Z active aero), plus DRS:
    drag cut by DRS_FRAC only inside the DRS zones (arc-fraction windows).
  * 1.6 V6 hybrid: ICE + 120 kW MGU-K, MGU-H keeps the store topped up in quali,
    so full power is available everywhere: no deploy taper, no superclip, no SOC.
  * 728 kg min incl. driver (+ a few kg quali fuel), wider 2017 tyres -> own mu.
Knobs come from a JSON (--car): calibrated on 2018 Q telemetry by _calibrate_2017.py.
The racing line is supplied (--raceline-in, S/F-aligned), as sim_2026_lap --raceline-in.
"""
import argparse, json, math, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
import sim_2026_lap as S

DEFAULT_CAR = dict(mass=733.0, p_kw=700.0, cda=1.10, cl=4.6, drs_frac=0.12, rho=1.225,
                   mu_lat=2.05, mu_long=1.45, mu_drive=1.10, acc_g=1.9,
                   trail_v=235.0, trail_min=0.40, trail_exp=1.6, gg_p=2.0)


def combined(r, p):
    """Fraction of longitudinal grip left at lateral-use ratio r: g-g superellipse (1 - r^p)^(1/p).
    p = 2 is the engine's friction circle (the default; unchanged results). p > 2 lets the car brake
    and turn together closer to the limit (fuller g-g, as measured on high-downforce cars)."""
    r = min(1.0, abs(r))
    return math.sqrt(1.0 - r * r) if p == 2.0 else (1.0 - r ** p) ** (1.0 / p)


def v_brake_backward(v_grip, kappa, arc, L, p, n_iters=3):
    """S.compute_v_brake_backward with the g-g exponent p (identical when p == 2; banking 0 at Sepang)."""
    n = len(v_grip); ds = np.diff(np.concatenate([arc, [L]])); v = v_grip.copy()
    for _ in range(n_iters):
        for i in range(n - 1, -1, -1):
            ip = (i + 1) % n
            a_lat_max = S.a_lat_max_banked(v[ip], "CORNER", S._bank_at(ip))
            if a_lat_max <= 0.0: continue
            r = abs(kappa[ip]) * v[ip] * v[ip] / a_lat_max
            a_long = S.MU_LONG * (S.G + S.downforce(v[ip], "CORNER") / S.MASS_KG) * combined(r, p)
            a_long *= S._trail_brake_frac(v[ip])
            a_dec = a_long + S.drag_force(v[ip], "CORNER") / S.MASS_KG
            vp = math.sqrt(max(0.0, v[ip] * v[ip] + 2.0 * a_dec * ds[i]))
            if vp < v[i]: v[i] = vp
    return v


def apply_car(car):
    g = S.__dict__
    g["MASS_KG"] = car["mass"]; g["RHO"] = car["rho"]; g["WARM_RHO"] = car["rho"]
    g["CDA_STRAIGHT_M2"] = g["CDA_CORNER_M2"] = car["cda"]
    g["CL_STRAIGHT_M2"] = g["CL_CORNER_M2"] = car["cl"]
    g["MU_LAT"] = car["mu_lat"]; g["MU_LONG"] = car["mu_long"]; g["MU_DRIVE"] = car["mu_drive"]
    g["A_ACC_LONG_MAX"] = car["acc_g"] * 9.81
    g["P_ICE_MAX_W"] = car["p_kw"] * 1000.0; g["P_MGU_DEPLOY_MAX_W"] = 0.0   # used by _ideal_speed_profile
    g["TRAIL_V_FULL_KMH"] = car["trail_v"]; g["TRAIL_FRAC_MIN"] = car["trail_min"]; g["TRAIL_EXP"] = car["trail_exp"]


def drs_mask_for(arc, total_len, zones):
    f = np.asarray(arc) / total_len
    m = np.zeros(len(f), dtype=bool)
    for a, b in zones:
        m |= (f >= a) & (f <= b) if a <= b else ((f >= a) | (f <= b))
    return m


def v_grip_array(raceline):
    """Same wide-stencil + median curvature as S.simulate_lap uses for grip."""
    from scipy.ndimage import median_filter
    st = int(os.environ.get("KGRIP_STENCIL", "4")); rl = np.asarray(raceline, float); n = len(rl)
    k = np.zeros(n)
    for i in range(n):
        a = rl[(i - st) % n]; b = rl[i]; c = rl[(i + st) % n]
        ab = b - a; bc = c - b; ac = c - a
        cr = ab[0] * bc[1] - ab[1] * bc[0]
        d = np.linalg.norm(ab) * np.linalg.norm(bc) * np.linalg.norm(ac)
        k[i] = 0.0 if d < 1e-9 else 2.0 * cr / d
    ks = median_filter(k, size=5, mode="wrap")
    return np.array([S.v_grip_static(x) for x in ks])


def forward(v_grip, v_brake, kappa, ds, drs, braking, car, v0):
    n = len(v_grip); m = car["mass"]; P = car["p_kw"] * 1000.0
    v = np.full(n, v0); t = np.zeros(n); mode = ["FULL"] * n; pkw = np.zeros(n); tt = 0.0
    for i in range(n):
        v[i] = min(v[i], v_grip[i], v_brake[i]); ip = (i + 1) % n
        if braking[i]:
            vn = min(v[i], v_grip[ip], v_brake[ip]); mode[i] = "REGEN"
        else:
            cda = car["cda"] * (1.0 - car["drs_frac"]) if drs[i] else car["cda"]
            mode[i] = "DRS" if drs[i] else "FULL"; pkw[i] = P / 1000.0
            a_lat = abs(kappa[i]) * v[i] ** 2
            a_max = S.a_lat_max_banked(v[i], "CORNER")
            grip = car["mu_drive"] * (S.G + S.downforce(v[i], "CORNER") / m) * combined(a_lat / max(a_max, 1e-6), car.get("gg_p", 2.0))
            a = min(grip, P / (m * max(v[i], S.V_FLOOR_MS)), car["acc_g"] * 9.81) \
                - 0.5 * car["rho"] * cda * v[i] ** 2 / m
            vn = min(math.sqrt(max(S.V_FLOOR_MS ** 2, v[i] ** 2 + 2 * a * ds[i])), v_grip[ip], v_brake[ip])
        v[ip] = vn
        tt += 2.0 * ds[i] / max(v[i] + vn, 1e-3); t[i] = tt
    return v, mode, pkw, t


def simulate(raceline, car, drs_zones, smooth=True):
    apply_car(car)
    arc, kappa, L = S._arc_kappa_closed(np.asarray(raceline, float))
    ds = np.diff(np.concatenate([arc, [L]]))
    drs = drs_mask_for(arc, L, drs_zones)
    v_grip = v_grip_array(raceline)
    v0 = 60.0
    for it in range(8):
        p = car.get("gg_p", 2.0)
        v_brake = S.compute_v_brake_backward(v_grip, kappa, arc, L) if p == 2.0 else v_brake_backward(v_grip, kappa, arc, L, p)
        braking = S._braking_zones(v_grip, v_brake, kappa, ds, v0)
        v, mode, pkw, t = forward(v_grip, v_brake, kappa, ds, drs, braking, car, v0)
        if abs(v[-1] - v[0]) < 1.0 and it >= 1: break
        v0 = 0.5 * (v[0] + v[-1])
    raw = float(t[-1])
    if smooth:
        v, t = S.smooth_longitudinal(v, arc, L, win_s=0.45)
        v, t = S.suppress_microhumps(v, arc, L, t)
    return dict(v=v, t=t, arc=arc, L=L, mode=mode, pkw=pkw, lap_raw=raw, lap=float(t[-1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raceline-in", required=True); ap.add_argument("--csv-out", required=True)
    ap.add_argument("--car", required=True, help="car JSON (knobs; may hold drs_zones)")
    ap.add_argument("--drs", default=None, help="JSON list of [a,b] arc-fraction DRS windows")
    a = ap.parse_args()
    car = dict(DEFAULT_CAR); car.update(json.load(open(a.car)))
    zones = json.loads(a.drs) if a.drs else car.get("drs_zones", [])
    rl = json.load(open(a.raceline_in))["raceline"]
    r = simulate(np.asarray(rl, float)[:, :2], car, zones)
    soc = np.ones(len(r["v"]))
    S.write_csv(a.csv_out, r["v"], soc, r["mode"], r["pkw"], r["t"], r["arc"], r["L"], fps=30)
    print(f"[sim2017] lap {r['lap_raw']:.3f}s raw -> {r['lap']:.3f}s  top {r['v'].max()*3.6:.1f}  min {r['v'].min()*3.6:.1f} km/h")


if __name__ == "__main__":
    main()
