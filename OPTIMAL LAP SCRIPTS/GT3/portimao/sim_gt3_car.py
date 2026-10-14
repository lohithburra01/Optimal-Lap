"""Mercedes-AMG GT3 EVO on the SAME physics engine (sim_2026_lap via cache/era2017/sim_2017_car; neither edited).

GT3 vs the F1 engine: passive aero (one drag/downforce level, no active aero, no DRS), no hybrid
(NA 6.2 V8, BoP-restricted, constant tractive power, no deploy/SOC), ~1.4 t, ABS braking.
Priors (sources in cache/rwanda_portimao_spec_2026-10-14.md / GT3/portimao/gt3_car_notes.md);
cl (downforce area) is fitted to the real GT3 Portimao lap.
  python GT3/portimao/sim_gt3_car.py --raceline-in RL.json --csv-out OUT.csv [--car car.json]
"""
import argparse, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "cache", "era2017"))
import sim_2017_car as C
S = C.S

GT3_CAR = dict(
    mass=1420.0,      # BoP ~1320 kg + driver 75 + quali fuel ~25
    p_kw=365.0,       # ~550 hp (BoP-restricted) x ~0.89 driveline -> tractive power
    cda=0.85,         # Cd ~0.42 x frontal ~2.0 m^2
    cl=2.6,           # downforce area: FITTED (fit_gt3.py)
    drs_frac=0.0, rho=1.20,
    mu_lat=1.60, mu_long=1.60, mu_drive=1.20,   # Pirelli GT3 slick; ABS braking; RWD traction
    acc_g=0.95,       # 0-100 km/h ~3 s
    trail_v=200.0, trail_min=0.60, trail_exp=1.2,  # ABS: flatter brake release than F1
    gg_p=2.0)


def elevation_for(arc, L):
    """Road height z(s) [m] from the real 2021 FastF1 Portimao pole lap, by lap fraction.
    The raceline must already be rolled to the real S/F (arc 0 = start line)."""
    from scipy.ndimage import uniform_filter1d
    F = json.load(open(os.path.join(HERE, "f1_2021_q_pole.json")))
    fd = np.asarray(F["d"], float); fz = uniform_filter1d(np.asarray(F["z"], float), 25)
    return np.interp(np.asarray(arc) / L * fd[-1], fd, fz, period=fd[-1])


def _simulate_elev(rl, car, z):
    """C.simulate with gravity along the slope (GT3 file only; the shared engines are untouched).
    forward:  a = traction - drag/m - g sin(theta);  backward: a_dec = brake + drag/m + g sin(theta)."""
    import math
    C.apply_car(car)
    arc, kappa, L = S._arc_kappa_closed(rl)
    ds = np.diff(np.concatenate([arc, [L]])); n = len(arc)
    sin_t = np.diff(np.concatenate([z, [z[0]]])) / np.maximum(ds, 1e-3)
    sin_t = np.clip(sin_t, -0.2, 0.2)
    v_grip = C.v_grip_array(rl); p = car.get("gg_p", 2.0); g = S.G; m = car["mass"]; P = car["p_kw"] * 1e3
    v_b = v_grip.copy()
    for _ in range(3):
        for i in range(n - 1, -1, -1):
            ip = (i + 1) % n
            a_lat_max = S.a_lat_max_banked(v_b[ip], "CORNER")
            r = abs(kappa[ip]) * v_b[ip] ** 2 / a_lat_max
            a_long = S.MU_LONG * (g + S.downforce(v_b[ip], "CORNER") / m) * C.combined(r, p) * S._trail_brake_frac(v_b[ip])
            a_dec = a_long + S.drag_force(v_b[ip], "CORNER") / m + g * sin_t[i]
            vp = math.sqrt(max(0.0, v_b[ip] ** 2 + 2.0 * a_dec * ds[i]))
            if vp < v_b[i]: v_b[i] = vp
    v0 = 60.0
    for it in range(8):
        v = np.full(n, v0); t = np.zeros(n); mode = ["FULL"] * n; pkw = np.zeros(n); tt = 0.0
        for i in range(n):
            v[i] = min(v[i], v_grip[i], v_b[i]); ip = (i + 1) % n
            a_lat = abs(kappa[i]) * v[i] ** 2; a_max = S.a_lat_max_banked(v[i], "CORNER")
            grip = car["mu_drive"] * (g + S.downforce(v[i], "CORNER") / m) * C.combined(a_lat / max(a_max, 1e-6), p)
            a = min(grip, P / (m * max(v[i], S.V_FLOOR_MS)), car["acc_g"] * g) - 0.5 * car["rho"] * car["cda"] * v[i] ** 2 / m - g * sin_t[i]
            va = math.sqrt(max(S.V_FLOOR_MS ** 2, v[i] ** 2 + 2 * a * ds[i]))
            vn = min(va, v_grip[ip], v_b[ip])
            if v_b[ip] < va and vn < v[i] - 1e-3: mode[i] = "BRAKING"
            else: pkw[i] = P / 1e3
            v[ip] = vn; tt += 2.0 * ds[i] / max(v[i] + vn, 1e-3); t[i] = tt
        if abs(v[-1] - v[0]) < 1.0 and it >= 1: break
        v0 = 0.5 * (v[0] + v[-1])
    raw = float(t[-1])
    v, t = S.smooth_longitudinal(v, arc, L, win_s=0.45)
    v, t = S.suppress_microhumps(v, arc, L, t)
    return dict(v=v, t=t, arc=arc, L=L, mode=mode, pkw=pkw, lap_raw=raw, lap=float(t[-1]), z=z)


def simulate(raceline, car=None, elev=True):
    c = dict(GT3_CAR); c.update(car or {})
    rl = np.asarray(raceline, float)[:, :2]
    if not elev:
        return C.simulate(rl, c, [])
    arc, _, L = S._arc_kappa_closed(rl)
    return _simulate_elev(rl, c, elevation_for(arc, L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raceline-in", required=True); ap.add_argument("--csv-out", required=True)
    ap.add_argument("--car", default=None); ap.add_argument("--flat", action="store_true", help="ignore elevation")
    a = ap.parse_args()
    car = dict(GT3_CAR)
    if a.car: car.update(json.load(open(a.car)))
    rl = json.load(open(a.raceline_in))["raceline"]
    r = simulate(rl, car, elev=not a.flat)
    S.write_csv(a.csv_out, r["v"], np.ones(len(r["v"])), r["mode"], r["pkw"], r["t"], r["arc"], r["L"], fps=30)
    print(f"[gt3] lap {r['lap_raw']:.3f}s raw -> {r['lap']:.3f}s  top {r['v'].max()*3.6:.1f}  min {r['v'].min()*3.6:.1f} km/h")


if __name__ == "__main__":
    main()
