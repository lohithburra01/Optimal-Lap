"""Map the real 2021 S/F (FastF1 lap start) onto the outline frame: Procrustes (no mirror) then report arc offset of raceline[0]."""
import json, sys, numpy as np
from scipy.interpolate import interp1d
rl = np.array(json.load(open(sys.argv[1]))['raceline'])[:, :2]
f = json.load(open('GT3/portimao/f1_2021_q_pole.json')); r = np.c_[f['x'], f['y']]
def res(p, n=400):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    return interp1d(s, p, axis=0)(np.linspace(0, s[-1], n, endpoint=False)), s[-1]
R, Lr = res(r); mR = R.mean(0)
best = None
for rev in (False, True):
    C, _ = res(rl[::-1] if rev else rl); mC = C.mean(0)
    for sh in range(400):
        A = np.roll(C, -sh, 0) - mC; U, S, Vt = np.linalg.svd(A.T @ (R - mR)); M = U @ Vt
        if np.linalg.det(M) < 0: continue
        sc = S.sum() / (A ** 2).sum(); e = np.sqrt(((sc * A @ M - (R - mR)) ** 2).sum(1).mean())
        if best is None or e < best[0]: best = (e, rev, sh, sc, M, mC)
e, rev, sh, sc, M, mC = best
p0 = (r[0] - mR) @ np.linalg.inv(M) / sc + mC        # real S/F in raceline frame
d = np.linalg.norm(rl - p0, axis=1); i = int(d.argmin())
seg = np.linalg.norm(np.diff(np.vstack([rl, rl[:1]]), axis=0), axis=1); arc = np.r_[0, np.cumsum(seg)]
print(f'rms {e:.1f} m, raceline drives {"OPPOSITE to" if rev else "SAME as"} real; real S/F = raceline idx {i} '
      f'(arc {arc[i]:.0f} m of {arc[-1]:.0f}), dist {d[i]:.1f} m')
