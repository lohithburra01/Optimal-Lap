"""Hybrid Singapore outline: SVG corner SHAPES placed RIGIDLY at the official path's corner POSITIONS.
- anchors: curvature peaks (R<150 m) matched between the SVG centreline and the official path (FIA 4927 m)
- complexes: anchors closer than GROUP m (svg arc) merge (e.g. T1-T3); region = complex +-PAD m (capped at the
  midpoint to the neighbour complex)
- each complex: rigid Procrustes (rotation+translation, NO scale) of its SVG points onto the corresponding
  official points (arc correspondence piecewise-linear between anchors)
- straights between complexes: the SVG piece mapped by the similarity that sends its two ends onto the moved
  complex ends (only straights stretch/shrink)
- result resampled, min-radius 10 m, constant 12 m width, index 0 at the official S/F.
  python cache/singapore/_hybrid_outline.py OUT_JSON [GROUP] [PAD]"""
import os, sys, json, numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, ROOT)
import svg_to_outline as SO
FIA = 4927.0; out = sys.argv[1]; GROUP = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0; PAD = float(sys.argv[3]) if len(sys.argv) > 3 else 35.0
op = json.load(open(os.path.join(H, "official_path.json"))); Qa = np.array(op["xy"]); mb = Qa.mean(0)
Q = mb + (FIA / op["length_m"] / op["scale"]) * (Qa - mb)
o = json.load(open(os.path.join(ROOT, "F1_Pipeline_Assets", "tracks", "singapore_grand_prix_outline_svgraw.json")))
C = (np.array(o["outer"]) + np.array(o["inner"])) / 2
def arc(P): return np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.vstack([P, P[:1]]), axis=0), axis=1))]
def resample(P, step=1.0):
    s = arc(P); u = np.arange(0, s[-1], step); return np.column_stack([np.interp(u, s, np.r_[P[:, k], P[0, k]]) for k in (0, 1)])
C = resample(C); Q = resample(Q); n, m = len(C), len(Q); sc, sq = arc(C), arc(Q); Lc, Lq = sc[-1], sq[-1]
def kap(P, st=4):
    a, b, c = np.roll(P, st, 0), P, np.roll(P, -st, 0); u, v = b - a, c - b
    return gaussian_filter1d(np.abs(2 * (u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]) / (np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1) * np.linalg.norm(c - a, axis=1) + 1e-12)), 3, mode="wrap")
pc, _ = find_peaks(kap(C), height=1 / 150, distance=40); pq, _ = find_peaks(kap(Q), height=1 / 150, distance=20)
anc = []
for i in pc:
    j = pq[np.argmin(np.abs(sq[pq] / Lq - sc[i] / Lc))]
    if abs(sq[j] / Lq - sc[i] / Lc) < 0.03 and (not anc or (sq[j] > anc[-1][1] and sc[i] > anc[-1][0])): anc.append((sc[i], sq[j]))
xs = np.r_[0.0, [a[0] for a in anc], Lc]; ys = np.r_[0.0, [a[1] for a in anc], Lq]
corr = lambda s: np.interp(s, xs, ys)                          # svg arc -> official arc
Qat = lambda s: np.column_stack([np.interp(corr(s) % Lq, sq, np.r_[Q[:, k], Q[0, k]]) for k in (0, 1)])
# complexes
cx = [[anc[0][0]]]
for a in anc[1:]:
    (cx[-1].append(a[0]) if a[0] - cx[-1][-1] < GROUP else cx.append([a[0]]))
reg = []
for k, g in enumerate(cx):
    lo, hi = g[0] - PAD, g[-1] + PAD
    if k > 0: lo = max(lo, 0.5 * (cx[k - 1][-1] + g[0]))
    if k < len(cx) - 1: hi = min(hi, 0.5 * (g[-1] + cx[k + 1][0]))
    reg.append((lo, hi))
print(f"[hybrid] {len(anc)} anchors -> {len(cx)} corner complexes")
pieces = []
for (lo, hi) in reg:
    s = np.arange(lo, hi, 1.0); P = np.column_stack([np.interp(s, sc, np.r_[C[:, k], C[0, k]]) for k in (0, 1)]); T = Qat(s)
    mp, mt = P.mean(0), T.mean(0); U, _, Vt = np.linalg.svd((P - mp).T @ (T - mt)); R = (U @ Vt).T
    if np.linalg.det(R) < 0: Vt[-1] *= -1; R = (U @ Vt).T
    Pm = (P - mp) @ R.T + mt; pieces.append((lo, hi, Pm)); 
    print(f"  complex {lo:6.0f}-{hi:6.0f} m: rot {np.degrees(np.arctan2(R[1,0],R[0,0])):+5.1f} deg, rms to official {np.sqrt(((Pm-T)**2).sum(1).mean()):.1f} m")
pts = []
for k, (lo, hi, Pm) in enumerate(pieces):
    pts.append(Pm)
    lo2, hi2, Pn = pieces[(k + 1) % len(pieces)]
    a0, a1 = hi, lo2 + (Lc if k == len(pieces) - 1 else 0.0)
    s = np.arange(a0, a1, 1.0)[1:]
    if len(s) < 2: continue
    P = np.column_stack([np.interp(s % Lc, sc, np.r_[C[:, k2], C[0, k2]]) for k2 in (0, 1)])
    e0 = np.interp(a0 % Lc, sc, np.r_[C[:, 0], C[0, 0]]), np.interp(a0 % Lc, sc, np.r_[C[:, 1], C[0, 1]])
    e1 = np.interp(a1 % Lc, sc, np.r_[C[:, 0], C[0, 0]]), np.interp(a1 % Lc, sc, np.r_[C[:, 1], C[0, 1]])
    z0, z1 = complex(*e0), complex(*e1); w0, w1 = complex(*Pm[-1]), complex(*Pn[0])
    A = (w1 - w0) / (z1 - z0); zz = (P[:, 0] + 1j * P[:, 1] - z0) * A + w0
    pts.append(np.column_stack([zz.real, zz.imag]))
    print(f"  straight {a0%Lc:6.0f}-{a1%Lc:6.0f} m: stretch {abs(A):.3f}, rot {np.degrees(np.angle(A)):+5.1f} deg")
N = np.vstack(pts); N = resample(N, 2.0)
N = np.column_stack([gaussian_filter1d(N[:, k], 1.5, mode="wrap") for k in (0, 1)])   # soften junction tangent breaks
j0 = int(np.argmin(np.linalg.norm(N - Q[0], axis=1))); N = np.roll(N, -j0, axis=0)
if SO.signed_area(N) < 0: print("CW?!")
N = SO.limit_min_radius(N, 10.0); O2, I2 = SO.generate_edges_constant_width(N, 12.0)
print(f"[hybrid] length {arc(N)[-1]:.0f} m (official {Lq:.0f})")
json.dump(dict(outer=O2.tolist(), inner=I2.tolist(), hybrid=dict(group_m=GROUP, pad_m=PAD, anchors=len(anc), complexes=len(cx))), open(out, "w"))
