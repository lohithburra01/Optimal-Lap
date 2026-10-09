"""Warp the SVG outline onto the official path: true corner POSITIONS and distances, SVG corner SHAPES kept.
Official path (official_path.json) rescaled to the FIA length 4927 m. Anchors = curvature peaks (R<150 m) of both
centrelines matched in order (lap fraction within 3%) + S/F. Arc correspondence piecewise-linear between anchors;
displacement field D(s) = official(s') - svg(s), Gaussian-smoothed along s (sigma SIG m), applied to the svg
centreline and to both edges; index 0 rolled to the official S/F.
  python cache/singapore/_warp_to_official.py SRC_OUTLINE OUT_OUTLINE [SIG]"""
import os, sys, json, numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
FIA = 4927.0
src, dst = sys.argv[1], sys.argv[2]; SIG = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
op = json.load(open(os.path.join(H, "official_path.json"))); Qa = np.array(op["xy"]); mb = Qa.mean(0)
Q = mb + (FIA / op["length_m"] / op["scale"]) * (Qa - mb)
o = json.load(open(src)); O = np.array(o["outer"]); I = np.array(o["inner"]); C = (O + I) / 2; n = len(C)
def arc(P): return np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.vstack([P, P[:1]]), axis=0), axis=1))]
def curv(P, st):
    m = len(P); k = np.zeros(m)
    for i in range(m):
        a, b, c = P[i - st], P[i], P[(i + st) % m]; u, v = b - a, c - b
        k[i] = 2 * (u[0] * v[1] - u[1] * v[0]) / (np.linalg.norm(u) * np.linalg.norm(v) * np.linalg.norm(c - a) + 1e-12)
    return k
sc, sq = arc(C), arc(Q); Lc, Lq = sc[-1], sq[-1]
kc = gaussian_filter1d(np.abs(curv(C, 3)), 2, mode="wrap"); kq = gaussian_filter1d(np.abs(curv(Q, 3)), 2, mode="wrap")
pc, _ = find_peaks(kc, height=1 / 150, distance=int(40 / (Lc / n))); pq, _ = find_peaks(kq, height=1 / 150, distance=20)
anc = []
for i in pc:
    fc = sc[i] / Lc; j = pq[np.argmin(np.abs(sq[pq] / Lq - fc))]
    if abs(sq[j] / Lq - fc) < 0.03 and (not anc or (sq[j] > anc[-1][1] and sc[i] > anc[-1][0])): anc.append((sc[i], sq[j]))
print(f"[warp] svg {Lc:.0f} m -> official {Lq:.0f} m; {len(anc)} corner anchors")
# correspondence: svg arc -> official arc (S/F: svg 0 <-> official 0, closing at the lap ends)
xs = np.r_[0.0, [a[0] for a in anc], Lc]; ys = np.r_[0.0, [a[1] for a in anc], Lq]
sq_of = np.interp(sc[:-1], xs, ys)
Qm = np.column_stack([np.interp(sq_of, sq, np.r_[Q[:, 0], Q[0, 0]]), np.interp(sq_of, sq, np.r_[Q[:, 1], Q[0, 1]])])
D = Qm - C; ds = Lc / n
if SIG > 0:
    Ds = np.column_stack([gaussian_filter1d(D[:, k], SIG / ds, mode="wrap") for k in (0, 1)])
else:
    # SIG=0: RIGID corners - displacement = the anchor's mean offset (+-15 m window) at each corner, linear in
    # arc between anchors, so each corner keeps its drawn shape and only the straights stretch/shrink
    ai = [int(np.argmin(np.abs(sc[:-1] - a[0]))) for a in anc]; w = int(15 / ds)
    Dk = [D[(np.arange(i - w, i + w + 1)) % n].mean(0) for i in ai]
    xa = np.r_[[sc[i] for i in ai], sc[ai[0]] + Lc]; Da = np.vstack(Dk + [Dk[0]])
    sx = np.where(sc[:-1] < xa[0], sc[:-1] + Lc, sc[:-1])
    Ds = np.column_stack([np.interp(sx, xa, Da[:, k]) for k in (0, 1)])
O2, I2, C2 = O + Ds, I + Ds, C + Ds
j0 = int(np.argmin(np.linalg.norm(C2 - Q[0], axis=1))); O2, I2, C2 = (np.roll(X, -j0, axis=0) for X in (O2, I2, C2))
s2 = arc(C2); print(f"[warp] new centreline {s2[-1]:.0f} m; S/F roll {j0}; max shift {np.linalg.norm(Ds, axis=1).max():.1f} m, median {np.median(np.linalg.norm(Ds, axis=1)):.1f} m")
# rebuild the edges from the warped centreline (shifting the edges separately pinched T1 to 9.7 m):
# same constant width + min-radius limiter as svg_to_outline (12 m, R>=10 m)
sys.path.insert(0, ROOT); import svg_to_outline as SO
C2 = SO.limit_min_radius(C2, 10.0); O2, I2 = SO.generate_edges_constant_width(C2, 12.0)
w = np.linalg.norm(O2 - I2, axis=1); print(f"[warp] width {w.min():.2f}..{w.max():.2f} m")
o2 = dict(outer=O2.tolist(), inner=I2.tolist(), warp=dict(src=src, sigma_m=SIG, fia_m=FIA, anchors=len(anc)))
json.dump(o2, open(dst, "w")); print("[warp] wrote", dst)
