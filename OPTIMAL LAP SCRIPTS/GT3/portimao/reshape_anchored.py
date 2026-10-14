"""Anchored reshape: move the SVG centreline only SIDEWAYS (offset d(s) along its normal) so the engine line's
curvature follows the REAL car's (g_lat*g/v^2). Each iteration solves
   min  sum ((k(C0 + n0 d) - k_target) / 2e-3)^2  +  sum (d / ANCHOR)^2
with k_target = k_centre + alpha * (k_real - k_line). The anchor keeps corners where the SVG has them
(the drift-free fix of reshape_track.py, whose heading integration bent the straights).
  python GT3/portimao/reshape_anchored.py ITERS ALPHA ANCHOR_M TAG"""
import sys, os, json, numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix
from scipy.ndimage import uniform_filter1d
hdr = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "reshape_track.py")).read().split("START =")[0]
exec(hdr)     # helpers: signed_k, resample_closed, build, evaluate, car, E, N (no track changes)
ANCHOR = float(sys.argv[3]); TAG = sys.argv[4]; ST = 3
o = json.load(open(os.path.join(TR, "portimao_gt3_outline.json")))
A0, B0 = np.array(o["outer"], float), np.array(o["inner"], float)
C0, Lc = resample_closed((A0 + B0) / 2, N); W = float(np.median(np.linalg.norm(A0 - B0, axis=1)))
tg = np.roll(C0, -1, 0) - np.roll(C0, 1, 0); tg /= np.linalg.norm(tg, axis=1)[:, None]; n0 = np.c_[-tg[:, 1], tg[:, 0]]
idxA = np.linspace(0, len(A0) - 1, N).astype(int)
side = np.sign(np.mean(np.sum(n0 * (A0[idxA] - C0), axis=1)))
def outline(X):
    t = np.roll(X, -1, 0) - np.roll(X, 1, 0); t /= np.linalg.norm(t, axis=1)[:, None]; nn = np.c_[-t[:, 1], t[:, 0]]
    return {"outer": (X + side * W / 2 * nn).tolist(), "inner": (X - side * W / 2 * nn).tolist()}
def min_gap(X):
    """closest approach of track sections more than 150 m apart along the lap (overlap guard)"""
    s = np.arange(N) * Lc / N; best = 1e9
    for i in range(0, N, 4):
        dd = np.linalg.norm(X - X[i], axis=1); sep = np.abs(s - s[i]); sep = np.minimum(sep, Lc - sep)
        best = min(best, dd[sep > 150].min())
    return best
J = lil_matrix((4 * N, N))
for i in range(N):
    for k in range(-ST, ST + 1): J[i, (i + k) % N] = 1
    J[N + i, i] = 1
    for k in (-1, 0, 1): J[2 * N + i, (i + k) % N] = 1
    for k in (-1, 0, 1): J[3 * N + i, (i + k) % N] = 1
d = np.zeros(N); X = C0.copy(); best = None; log = []
rl = build(os.path.join(TR, "portimao_gt3_outline.json"), os.path.join(HERE, f"_ra{TAG}_rl_0.json"))
for it in range(ITERS + 1):
    kr, kl, rmse, lap, corr = evaluate(rl, X)
    print(f"[anchored] it {it}: speed RMSE {rmse:.2f} km/h  lap {lap:.3f}  curv err {np.sqrt(np.mean((kr-kl)**2))*1e3:.2f}/km  "
          f"max offset {np.abs(d).max():.1f} m  min section gap {min_gap(X):.1f} m", flush=True)
    log.append(dict(it=it, rmse=rmse, lap=lap))
    if best is None or rmse < best[0]:
        best = (rmse, it)
        json.dump(outline(X) if it else o, open(os.path.join(HERE, f"best_ra{TAG}_outline.json"), "w"))
        json.dump({"raceline": rl.tolist()}, open(os.path.join(HERE, f"best_ra{TAG}_rl.json"), "w"))
    if it == ITERS: break
    kx = signed_k(X, ST)
    e = uniform_filter1d(kr - kl, 9, mode="wrap") * np.sign(np.corrcoef(kx, kl)[0, 1])
    kt = kx + ALPHA * e
    def res(dd):
        Xd = C0 + n0 * dd[:, None]
        k1 = signed_k(Xd, 1)                                             # station-scale curvature: no hidden zigzags
        return np.r_[(signed_k(Xd, ST) - kt) / 2e-3, dd / ANCHOR,
                     (np.roll(dd, -1) - 2 * dd + np.roll(dd, 1)) / 0.05,      # smooth offsets
                     np.maximum(np.abs(k1) - 1 / 12.0, 0) / 1e-3]              # centre radius >= 12 m (edges >= 5.5 m)
    d = least_squares(res, d, jac_sparsity=J, bounds=(-60, 60), max_nfev=60, x_scale=5.0).x
    X = C0 + n0 * d[:, None]
    if min_gap(X) < W + 3: print("[anchored] sections too close - stopping"); break
    path = os.path.join(HERE, f"_ra{TAG}_outline_{it+1}.json"); json.dump(outline(X), open(path, "w"))
    rl = build(path, os.path.join(HERE, f"_ra{TAG}_rl_{it+1}.json"))
json.dump(log, open(os.path.join(HERE, f"reshape_anchored{TAG}_log.json"), "w"), indent=1)
print(f"[anchored] best it {best[1]}  RMSE {best[0]:.2f}")
