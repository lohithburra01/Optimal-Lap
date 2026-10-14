"""Align SVG centreline to the FastF1 2021 map (rotation/scale/mirror) -> mirror? direction? S/F index."""
import json, sys, numpy as np
from scipy.interpolate import interp1d
o = json.load(open(sys.argv[1])); c = (np.array(o['outer'])[:, :2] + np.array(o['inner'])[:, :2]) / 2
f = json.load(open('GT3/portimao/f1_2021_q_pole.json')); r = np.c_[f['x'], f['y']]
def resample(p, n=400):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    return interp1d(s, p, axis=0)(np.linspace(0, s[-1], n, endpoint=False))
R = resample(r); R0 = R - R.mean(0)
best = None
for mirror in (False, True):
    C = c.copy(); C[:, 0] *= (-1 if mirror else 1)
    for rev in (False, True):
        Cr = resample(C[::-1] if rev else C); Cr -= Cr.mean(0)
        for sh in range(0, 400, 2):
            A = np.roll(Cr, -sh, axis=0)
            U, S, Vt = np.linalg.svd(A.T @ R0); Rm = U @ Vt
            if np.linalg.det(Rm) < 0: continue
            sc = S.sum() / (A ** 2).sum(); e = np.sqrt(((sc * A @ Rm - R0) ** 2).sum(1).mean())
            if best is None or e < best[0]: best = (e, mirror, rev, sh, sc)
print('rms %.1f m  mirror=%s reversed=%s shift=%d/400 scale=%.3f' % best)
