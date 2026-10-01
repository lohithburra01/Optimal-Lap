"""Locally smooth ONE drawn corner of an outline (FITTED geometry correction).

Some SVGs draw a hairpin as a sharp V: the centreline turns ~150 deg over a few
metres at R~10 m, so offsetting a 15 m road folds the inside edge into a cusp
(R~2.5 m) - a road that cannot exist, which the racing line then 'leaves'.
This rebuilds the road around that corner only: centreline = (outer+inner)/2,
Gaussian-smooth it with a raised-cosine blend of half-length HALF m around the
corner, keep each station's original half-width, re-offset both edges along the
smoothed normal. Everything outside the blend is bit-identical.

  python cache/_outline_local_smooth.py IN.json OUT.json --near X,Y --half 60 --sigma 8
(--near: a point at the corner in outline coordinates, e.g. the sim raceline apex)
"""
import argparse, json
import numpy as np
from scipy.ndimage import gaussian_filter1d

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("out")
ap.add_argument("--near", required=True); ap.add_argument("--half", type=float, default=60.0)
ap.add_argument("--sigma", type=float, required=True, help="smoothing sigma [m]")
a = ap.parse_args()
o = json.load(open(a.src))
O = np.asarray(o["outer"], float); I = np.asarray(o["inner"], float)
C = (O + I) / 2; hw = np.linalg.norm(O - I, axis=1) / 2
seg = np.linalg.norm(np.diff(np.vstack([C, C[0]]), axis=0), axis=1); ds = seg.mean()
n = len(C); j0 = int(np.argmin(np.linalg.norm(C - np.array([float(v) for v in a.near.split(",")]), axis=1)))
sig = a.sigma / ds
Cs = np.column_stack([gaussian_filter1d(C[:, 0], sig, mode="wrap"), gaussian_filter1d(C[:, 1], sig, mode="wrap")])
d = (np.arange(n) - j0 + n // 2) % n - n // 2
h = a.half / ds
w = np.where(np.abs(d) < h, 0.5 * (1 + np.cos(np.pi * d / h)), 0.0)
Cn = C + w[:, None] * (Cs - C)
t = np.roll(Cn, -1, 0) - np.roll(Cn, 1, 0); t /= np.linalg.norm(t, axis=1)[:, None]
nl = np.column_stack([-t[:, 1], t[:, 0]])
side = np.sign(np.einsum("ij,ij->i", O - C, np.column_stack([-(np.roll(C, -1, 0) - np.roll(C, 1, 0))[:, 1], (np.roll(C, -1, 0) - np.roll(C, 1, 0))[:, 0]])))
On = np.where(w[:, None] > 0, Cn + (side * hw)[:, None] * nl, O)
In = np.where(w[:, None] > 0, Cn - (side * hw)[:, None] * nl, I)
def rmin(P, idx):
    a_, b_, c_ = np.roll(P, 2, 0), P, np.roll(P, -2, 0); ab, bc, ac = b_ - a_, c_ - b_, c_ - a_
    k = 2 * np.abs(ab[:, 0] * bc[:, 1] - ab[:, 1] * bc[:, 0]) / (np.linalg.norm(ab, axis=1) * np.linalg.norm(bc, axis=1) * np.linalg.norm(ac, axis=1) + 1e-12)
    return 1 / k[idx].max()
blend = np.where(w > 0)[0]
print(f"corner at outline idx {j0}; blend {len(blend)} stations; centre Rmin {rmin(C, blend):.1f} -> {rmin(Cn, blend):.1f} m; "
      f"edge Rmin outer {rmin(O, blend):.1f}->{rmin(On, blend):.1f}, inner {rmin(I, blend):.1f}->{rmin(In, blend):.1f} m; "
      f"max centre move {np.linalg.norm(Cn - C, axis=1).max():.2f} m")
o2 = dict(o); o2["outer"] = On.tolist(); o2["inner"] = In.tolist()
o2["local_smooth"] = dict(src=a.src, near=a.near, half_m=a.half, sigma_m=a.sigma, idx=j0)
json.dump(o2, open(a.out, "w"))
