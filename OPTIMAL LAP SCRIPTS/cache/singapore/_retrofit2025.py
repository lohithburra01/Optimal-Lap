"""RETROFIT the 2025 car sim to George Russell's REAL 2025 pole lap timing (user: 'perfect timing').
Real clock = OpenF1 car_data timestamps minus the official lap date_start (lap = 89.158 s exactly; the earlier
dual video scaled the whole sample window and was ~0.12-0.16 s off at the sector lines).
Mini-sectors = the 12 corners (speed minima, paired with the 2025 sim's minima on its own line opt2025c).
Per corner j: grip factor gf_j (Voronoi cell around the corner) -> real v_min_j; per corner-to-corner segment j:
acceleration factor pf_j (power+traction) -> real segment time. Checked at the official sector lines (26.475 /
63.804) and the straight peaks. Writes sim CSV + report.
  python cache/singapore/_retrofit2025.py [CAR_JSON LINE_JSON [TAG]]"""
import os, sys, json, math, contextlib, io
import numpy as np
from datetime import datetime
from scipy.signal import find_peaks
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "cache", "era2017")); sys.path.insert(0, H)
import sim_2017_car as C, sim_2026_lap as S
LAP = 89.158
# ---------------- real lap on the official clock ----------------
raw = json.load(open(os.path.join(H, "rus2025_car_data.json"))); lap = raw["lap"]; P_ = datetime.fromisoformat
cd = sorted([c for c in raw["car_data"] if c.get("speed") is not None], key=lambda c: c["date"])
seen, rows = set(), []
for c in cd:
    if c["date"] not in seen: seen.add(c["date"]); rows.append(c)
t0 = P_(lap["date_start"]); tr = np.array([(P_(c["date"]) - t0).total_seconds() for c in rows]); vr = np.array([float(c["speed"]) for c in rows])
dr = np.r_[0, np.cumsum(0.5 * (vr[1:] + vr[:-1]) / 3.6 * np.diff(tr))] + vr[0] / 3.6 * tr[0]   # metres from the line
Dr = float(np.interp(LAP, tr, dr))                                                               # distance at lap end
S1, S2 = lap["duration_sector_1"], lap["duration_sector_1"] + lap["duration_sector_2"]
pr, _ = find_peaks(-vr, prominence=12)
# sub-sample minimum: parabola through the 3 samples
def para(i, x, y):
    a, b, c = y[i - 1], y[i], y[i + 1]; den = a - 2 * b + c
    u = 0.0 if abs(den) < 1e-9 else 0.5 * (a - c) / den
    return x[i] + u * (x[i + 1] - x[i - 1]) / 2, b - 0.25 * (a - c) * u
real_min = [(np.interp(para(i, dr, vr)[0], dr, tr), para(i, dr, vr)[0], para(i, tr, vr)[1]) for i in pr]   # (t, d, v)
# ---------------- 2025 car + line ----------------
CARJ = sys.argv[1] if len(sys.argv) > 2 else os.path.join(H, "car2025c.json"); LINEJ = sys.argv[2] if len(sys.argv) > 2 else os.path.join(H, "opt2025c_rl.json")
TAG = sys.argv[3] if len(sys.argv) > 3 else ""
cj = json.load(open(CARJ)); car, drs = cj["car"], cj["drs"]
rl = np.asarray(json.load(open(LINEJ))["raceline"])[:, :2]
C.apply_car(car)
arc, kappa, L = S._arc_kappa_closed(rl); ds = np.diff(np.concatenate([arc, [L]])); n = len(rl)
drsm = C.drs_mask_for(arc, L, drs); vg0 = C.v_grip_array(rl)
def forward(v_grip, v_brake, braking, pf, v0):
    m = car["mass"]; P = car["p_kw"] * 1000.0
    v = np.full(n, v0); t = np.zeros(n); mode = ["FULL"] * n; pkw = np.zeros(n); tt = 0.0
    for i in range(n):
        v[i] = min(v[i], v_grip[i], v_brake[i]); ip = (i + 1) % n
        if braking[i]:
            vn = min(v[i], v_grip[ip], v_brake[ip]); mode[i] = "REGEN"
        else:
            cda = car["cda"] * (1.0 - car["drs_frac"]) if drsm[i] else car["cda"]
            mode[i] = "DRS" if drsm[i] else "FULL"; pkw[i] = P / 1000.0
            a_lat = abs(kappa[i]) * v[i] ** 2; a_max = S.a_lat_max_banked(v[i], "CORNER")
            grip = car["mu_drive"] * (S.G + S.downforce(v[i], "CORNER") / m) * C.combined(a_lat / max(a_max, 1e-6), car.get("gg_p", 2.0))
            a = pf[i] * min(grip, P / (m * max(v[i], S.V_FLOOR_MS)), car["acc_g"] * 9.81) - 0.5 * car["rho"] * cda * v[i] ** 2 / m
            vn = min(math.sqrt(max(S.V_FLOOR_MS ** 2, v[i] ** 2 + 2 * a * ds[i])), v_grip[ip], v_brake[ip])
        v[ip] = vn; tt += 2.0 * ds[i] / max(v[i] + vn, 1e-3); t[i] = tt
    return v, mode, pkw, t
def simulate(gfs, pfs):
    vg = vg0 * gfs
    v0 = 60.0
    with contextlib.redirect_stdout(io.StringIO()):
        for it in range(8):
            vb = S.compute_v_brake_backward(vg, kappa, arc, L); br = S._braking_zones(vg, vb, kappa, ds, v0)
            v, mode, pkw, t = forward(vg, vb, br, pfs, v0)
            if abs(v[-1] - v[0]) < 1.0 and it >= 1: break
            v0 = 0.5 * (v[0] + v[-1])
        v, t = S.smooth_longitudinal(v, arc, L, win_s=0.45); v, t = S.suppress_microhumps(v, arc, L, t)
    tl = np.r_[0.0, t[:-1]]                       # time at station i (t[i] is the time at i+1)
    return v, tl, float(t[-1]), mode, pkw, t
# pair corners on our line (base run)
v, tl, lt, *_ = simulate(np.ones(n), np.ones(n))
ps, _ = find_peaks(-v * 3.6, prominence=12, distance=20)
pairs = []
for (tm, dm, vm) in real_min:
    j = ps[np.argmin(abs(arc[ps] / L - dm / Dr))]
    if abs(arc[j] / L - dm / Dr) >= 0.02:          # no sim minimum near: slowest station within +-40 m of the real one
        j0 = int(np.argmin(abs(arc / L - dm / Dr))); w = (np.arange(-20, 21) + j0) % n; j = int(w[np.argmin(v[w])])
        print(f"[retro] corner at {dm:.0f} m: no sim minimum within 2% -> station {j} ({v[j]*3.6:.0f} km/h)")
    pairs.append((tm, dm, vm, j))
assert len(pairs) == len(real_min), f"paired {len(pairs)}/{len(real_min)}"
J = np.array([p[3] for p in pairs]); K = len(J)
# zones: grip cell = Voronoi (midpoints between consecutive minima), accel segment = [min_j, min_j+1)
mid = [((J[k] + ((J[(k + 1) % K] - J[k]) % n) // 2)) % n for k in range(K)]
cell = np.zeros(n, int); seg = np.zeros(n, int)
for k in range(K):
    a, b = mid[k - 1], mid[k]; idx = np.arange(a, b if b > a else b + n) % n; cell[idx] = k
    a, b = J[k], J[(k + 1) % K]; idx = np.arange(a, b if b > a else b + n) % n; seg[idx] = k
gf, pf = np.ones(K), np.ones(K)
treal = np.array([p[0] for p in pairs]); vreal = np.array([p[2] for p in pairs])
dtr = np.array([(treal[(k + 1) % K] - treal[k]) % LAP for k in range(K)])
for it in range(40):
    v, tl, lt, mode, pkw, traw = simulate(gf[cell], pf[seg])
    # local min near each paired station
    jm = [int((J[k] + np.argmin([v[(J[k] + o) % n] for o in range(-15, 16)]) - 15) % n) for k in range(K)]
    vs = np.array([v[j] * 3.6 for j in jm]); ts = np.array([tl[j] for j in jm])
    dts = np.array([(ts[(k + 1) % K] - ts[k]) % lt for k in range(K)])
    ev, et = vs - vreal, ts - treal
    print(f"[retro] it{it:2d}: lap {lt:.3f}  vmin err max {np.abs(ev).max():.2f} km/h  corner-time err max {np.abs(et).max()*1000:.0f} ms  "
          f"seg err max {np.abs(dts-dtr).max()*1000:.0f} ms", flush=True)
    if np.abs(ev).max() < 0.3 and np.abs(et).max() < 0.010 and abs(lt - LAP) < 0.005: break
    gf *= (vreal / vs)
    pf *= np.clip((dts / dtr) ** 3, 0.85, 1.15)
gfs, pfs = gf[cell], pf[seg]
# ---------------- checks ----------------
def ours_at(d_real):                               # real distance -> our arc via the corner anchors
    kr = [0.0] + [p[1] for p in pairs] + [Dr]; ks = [0.0] + [arc[j] for j in J] + [L]
    return np.interp(d_real, kr, ks)
print("\n[retro] official sector lines (real distance from the real clock):")
for name, tt in (("S1", S1), ("S2", S2)):
    d_line = float(np.interp(tt, tr, dr)); ts = float(np.interp(ours_at(d_line), arc, tl))
    print(f"  {name}: real {tt:.3f}s  sim {ts:.3f}s  err {1000*(ts-tt):+.0f} ms")
print(f"  LAP: real {LAP:.3f}s  sim {lt:.3f}s  err {1000*(lt-LAP):+.0f} ms")
pk, _ = find_peaks(vr, prominence=30); print("[retro] straight peaks (real vs sim, km/h):")
for i in pk:
    a = ours_at(dr[i]); w = np.abs(arc - a) < 60; print(f"  {dr[i]:5.0f} m: real {vr[i]:.0f}  sim {v[w].max()*3.6:.0f}")
print("[retro] gf", np.round(gf, 3).tolist()); print("[retro] pf", np.round(pf, 3).tolist())
S.write_csv(os.path.join(H, f"sim2025_retrofit{TAG}.csv"), v, np.ones(n), mode, pkw, traw, arc, L, fps=30)
json.dump(dict(gf=gf.tolist(), pf=pf.tolist(), corners_station=J.tolist(), corners_frac=(arc[J] / L).tolist(), mid_frac=(arc[np.array(mid)] / L).tolist(), lap=lt, car=CARJ, line=LINEJ), open(os.path.join(H, f"retrofit2025{TAG}.json"), "w"), indent=1)
print("[retro] wrote sim2025_retrofit.csv")
