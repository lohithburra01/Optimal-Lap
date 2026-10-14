"""Reshape the Portimao track so the TUM line engine's line drives the REAL car's curvature profile.
Real driven curvature  k_real(d) = g_lat * g / v^2  (real AMG GT3 Evo trace, _env.npz).
Loop:  k_centre += alpha * smooth(k_real - k_line)   ->  rebuild centreline by heading integration (closed)
       -> outline = centre +/- half width  -> build_gt3_line.py (engine line, no add-ons)  -> repeat.
Track ACCURACY is not the goal (user 2026-10-14): the car must drive like the real car.
  python GT3/portimao/reshape_track.py ITERS [ALPHA]"""
import sys, os, json, io, contextlib, subprocess, numpy as np
from scipy.ndimage import uniform_filter1d, median_filter
from scipy.interpolate import interp1d
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TR = os.path.join(HERE, "assets")
sys.path.insert(0, HERE)
import trace_fit as T, sim_gt3_car as G
import psutil; psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
ITERS = int(sys.argv[1]); ALPHA = float(sys.argv[2]) if len(sys.argv) > 2 else 0.6
CARF = os.path.join(HERE, "gt3_car_measured.json"); car = dict(G.GT3_CAR); car.update(json.load(open(CARF)))
E = np.load(os.path.join(HERE, "_env.npz"))
k_real_raw = uniform_filter1d(E["gl"] * 9.81 / np.maximum(E["v"], 8.0) ** 2, 15)
N = 2000

def signed_k(P, st):
    n = len(P); k = np.zeros(n)
    for i in range(n):
        a, b, c = P[(i - st) % n], P[i], P[(i + st) % n]; ab, bc, ac = b - a, c - b, c - a
        k[i] = 2 * (ab[0] * bc[1] - ab[1] * bc[0]) / max(np.linalg.norm(ab) * np.linalg.norm(bc) * np.linalg.norm(ac), 1e-9)
    return k

def resample_closed(P, n):
    Q = np.vstack([P, P[:1]]); s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    return interp1d(s, Q, axis=0)(np.linspace(0, s[-1], n, endpoint=False)), s[-1]

def build(outline_path, rl_path):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    out = subprocess.run([sys.executable, os.path.join(HERE, "build_gt3_line.py"), rl_path, "--car", CARF,
                          "--outline", outline_path, "--roll-to-outline0"], capture_output=True, text=True, env=env)
    if out.returncode: print(out.stderr[-2000:]); raise SystemExit("build failed")
    return np.array(json.load(open(rl_path))["raceline"])[:, :2]

def evaluate(rl, C, verbose=False):
    """Return k_real and k_line on the centreline stations, speed RMSE, lap."""
    with contextlib.redirect_stdout(io.StringIO()):
        rmse, r, pairs, svr, sh = T.compare(rl, car, verbose)
    L = r["L"]; sc = L / T.REAL_LEN
    xr = np.r_[0, [p[0] for p in pairs], T.rd[-1]]; xs = np.r_[0, [p[1] for p in pairs], T.rd[-1] * sc]
    kl = median_filter(signed_k(rl, 4), 5, mode="wrap")
    # line station -> centreline station (nearest), line arc -> real distance
    j = np.array([int(np.argmin(np.linalg.norm(C - p, axis=1))) for p in rl])
    d_real = np.interp((r["arc"] - sh) % L, xs, xr)
    kr = np.interp(d_real, E["d"], k_real_raw)
    # sign convention: g_lat sign vs geometric curvature
    sgn = np.sign(np.corrcoef(kr, kl)[0, 1]); kr = sgn * kr
    kc_line = np.zeros(len(C)); kc_real = np.zeros(len(C)); cnt = np.zeros(len(C))
    np.add.at(kc_line, j, kl); np.add.at(kc_real, j, kr); np.add.at(cnt, j, 1)
    idx = np.where(cnt > 0)[0]; allx = np.arange(len(C))
    kc_line = np.interp(allx, idx, kc_line[idx] / cnt[idx], period=len(C))
    kc_real = np.interp(allx, idx, kc_real[idx] / cnt[idx], period=len(C))
    return kc_real, kc_line, rmse, r["lap"], np.corrcoef(kr, kl)[0, 1] * sgn

START = sys.argv[3] if len(sys.argv) > 3 else os.path.join(TR, "portimao_gt3_outline.json")
TAG = sys.argv[4] if len(sys.argv) > 4 else ""
o = json.load(open(START))       # rolled: station 0 = real S/F
A0, B0 = np.array(o["outer"], float), np.array(o["inner"], float)
C, Lc = resample_closed((A0 + B0) / 2, N); W = float(np.median(np.linalg.norm(A0 - B0, axis=1)))
ds = Lc / N
side = np.sign(np.mean(np.cross(np.diff(np.vstack([C, C[:1]]), axis=0), A0[np.linspace(0, len(A0) - 1, N).astype(int)] - C)))
log = []; best = None
rl = build(START, os.path.join(HERE, f"_rs{TAG}_rl_0.json"))
for it in range(ITERS + 1):
    kr, kl, rmse, lap, corr = evaluate(rl, C)
    ek = np.sqrt(np.mean((kr - kl) ** 2))
    print(f"[reshape] it {it}: speed RMSE {rmse:.2f} km/h  lap {lap:.3f}  curvature rms err {ek*1000:.2f} 1/km  corr {corr:.3f}", flush=True)
    log.append(dict(it=it, rmse=rmse, lap=lap, kerr=ek))
    if best is None or rmse < best[0]:
        best = (rmse, it)
        json.dump({"outer": (C + side * W / 2 * nrm).tolist() if it else A0.tolist(),
                   "inner": (C - side * W / 2 * nrm).tolist() if it else B0.tolist()} if it else o,
                  open(os.path.join(TR, "portimao_gt3real_outline.json"), "w"))
        json.dump({"raceline": rl.tolist()}, open(os.path.join(HERE, "reshaped_rl.json"), "w"))
    if it == ITERS: break
    # ---- update centreline curvature
    th = np.unwrap(np.arctan2(*np.diff(np.vstack([C, C[:1]]), axis=0)[:, ::-1].T))
    dth = np.diff(np.r_[th, th[0]]); dth = (dth + np.pi) % (2 * np.pi) - np.pi; kc = dth / ds   # heading change per metre
    tot = kc.sum() * ds
    e = uniform_filter1d(kr - kl, 9, mode="wrap")                                # ~20 m smoothing
    e *= np.sign(np.corrcoef(kc, kl)[0, 1])          # line runs opposite to outline index order -> match centreline sign
    kn = kc + ALPHA * e
    kn += (tot - kn.sum() * ds) / (N * ds)                                       # keep total turning (closed loop)
    thn = th[0] + np.r_[0, np.cumsum(kn[:-1] * ds)]
    P = np.c_[np.cos(thn), np.sin(thn)] * ds; X = np.cumsum(np.vstack([[0, 0], P[:-1]]), axis=0) + C[0]
    gap = (X[-1] + P[-1]) - C[0]
    X -= np.outer(np.arange(N) / N, gap)                                         # close the position loop
    C = X
    tg = np.diff(np.vstack([C, C[:1]]), axis=0); tg /= np.linalg.norm(tg, axis=1)[:, None]
    nrm = np.c_[-tg[:, 1], tg[:, 0]]
    path = os.path.join(HERE, f"_rs{TAG}_outline_{it+1}.json")
    json.dump({"outer": (C + side * W / 2 * nrm).tolist(), "inner": (C - side * W / 2 * nrm).tolist()}, open(path, "w"))
    rl = build(path, os.path.join(HERE, f"_rs{TAG}_rl_{it+1}.json"))
json.dump(log, open(os.path.join(HERE, f"reshape{TAG}_log.json"), "w"), indent=1)
print(f"[reshape] best it {best[1]}  RMSE {best[0]:.2f} -> portimao_gt3real_outline.json + reshaped_rl.json")
