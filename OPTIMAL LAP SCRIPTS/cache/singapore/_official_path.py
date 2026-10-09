"""Dense official centreline from the map-matched samples (path_samples.json): order every sample by its
projection onto RUS's lap polyline, sort, light smoothing, uniform 2 m resample, start at S/F (RUS lap start),
metres. Then similarity-align (rotation+scale+translation, Procrustes on arc-fraction correspondence) to our
outline frame. -> cache/singapore/official_path.json {xy (our frame), xy_raw_m, length_m, scale}"""
import os, json, numpy as np
from scipy.ndimage import gaussian_filter1d
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
smp = json.load(open(os.path.join(H, "path_samples.json")))
ref = np.array([[r["x"], r["y"]] for r in smp if r["drv"] == 63], float) / 10.0
allp = np.array([[r["x"], r["y"]] for r in smp], float) / 10.0
seg = np.diff(ref, axis=0); sl = np.linalg.norm(seg, axis=1); cum = np.r_[0, np.cumsum(sl)]
def proj(p):
    a = ref[:-1]; u = np.clip(np.einsum("ij,ij->i", p - a, seg) / np.maximum(sl ** 2, 1e-9), 0, 1)
    q = a + u[:, None] * seg; k = np.argmin(np.linalg.norm(q - p, axis=1)); return cum[k] + u[k] * sl[k], np.linalg.norm(q[k] - p)
pr = np.array([proj(p) for p in allp]); order = np.argsort(pr[:, 0]); P = allp[order]
print(f"[path] {len(P)} pts, max offset from RUS polyline {pr[:,1].max():.1f} m (chord cut), median {np.median(pr[:,1]):.2f}")
# drop duplicates, light smoothing (points lie on one path), resample 2 m
P = P[np.r_[True, np.linalg.norm(np.diff(P, axis=0), axis=1) > 0.05]]
Ps = np.column_stack([gaussian_filter1d(P[:, 0], 1.5, mode="wrap"), gaussian_filter1d(P[:, 1], 1.5, mode="wrap")])
c = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.vstack([Ps, Ps[:1]]), axis=0), axis=1))]; Lp = c[-1]
u = np.arange(0, Lp, 2.0); Q = np.column_stack([np.interp(u, c, np.r_[Ps[:, 0], Ps[0, 0]]), np.interp(u, c, np.r_[Ps[:, 1], Ps[0, 1]])])
print(f"[path] official centreline length {Lp:.1f} m")
# our outline centreline (real frame, S/F at index 0, unrelaxed svg)
o = json.load(open(os.path.join(ROOT, "F1_Pipeline_Assets", "tracks", "singapore_grand_prix_outline_svgraw.json")))
Cc = (np.array(o["outer"]) + np.array(o["inner"])) / 2
cc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.vstack([Cc, Cc[:1]]), axis=0), axis=1))]; Lc = cc[-1]
f = np.linspace(0, 1, 1000, endpoint=False)
A = np.column_stack([np.interp(f * Lp, u, Q[:, 0]), np.interp(f * Lp, u, Q[:, 1])])
B = np.column_stack([np.interp(f * Lc, cc, np.r_[Cc[:, 0], Cc[0, 0]]), np.interp(f * Lc, cc, np.r_[Cc[:, 1], Cc[0, 1]])])
best = None
for sh in range(-30, 31):                      # small S/F offset search (lap-fraction samples)
    Ar = np.roll(A, sh, axis=0); ma, mb = Ar.mean(0), B.mean(0); X, Y = Ar - ma, B - mb
    U, Sg, Vt = np.linalg.svd(X.T @ Y); R = (U @ Vt).T
    if np.linalg.det(R) < 0: continue
    s = Sg.sum() / (X ** 2).sum(); err = np.sqrt(((s * X @ R.T - Y) ** 2).sum(1).mean())
    if best is None or err < best[0]: best = (err, sh, R, s, ma, mb)
err, sh, R, s, ma, mb = best
print(f"[path] Procrustes: S/F shift {sh*Lp/1000:+.1f} m, scale {s:.4f} (unit check: official {Lp:.0f} m vs ours {Lc:.0f} m), rms {err:.1f} m")
Qa = s * (Q - ma) @ R.T + mb
json.dump(dict(xy=Qa.tolist(), length_m=Lp, scale=s, rms=err, sf_shift_m=sh * Lp / 1000), open(os.path.join(H, "official_path.json"), "w"))
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(14, 9)); ax.plot(*Cc.T, "b-", lw=1, label="our SVG centreline"); ax.plot(*Qa.T, "r-", lw=1, label="official path (aligned)")
ax.plot(*Cc[0], "b*", ms=12); ax.plot(*Qa[0], "r*", ms=12); ax.set_aspect("equal"); ax.legend(); plt.savefig(os.path.join(H, "official_vs_svg.png"), dpi=70)
