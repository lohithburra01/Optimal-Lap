"""RATIO-FIELD pattern model (v3): v26(s) = v25(s) * q(s). The 2025 lap is cut into phases: ACCEL (corner minimum ->
next speed peak) and BRAKE (peak -> next minimum). q is learned, pooled over other tracks, as a function of the
position fraction u within the phase, separately per phase-length class (ACCEL: <250, 250-600, >600 m; BRAKE one
class), plus the corner-minimum ratio R(v25). This captures the 2026 straight SHAPE (harder early push, earlier
peak, energy fade before braking) and the 2026 braking-zone change, without measuring absolute accelerations."""
import os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); import hlib
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
UB = np.linspace(0, 1, 11); CL = [0, 250, 600, 1e9]
def phases(s, v):
    vs = gaussian_filter1d(v, 2.0, mode="wrap"); n = len(v)
    mn, _ = find_peaks(-np.r_[vs, vs], prominence=10, distance=30); mn = np.unique(mn % n)
    ph = []                                     # (kind, i0, i1) with i1 possibly > n (wrap)
    for k, i0 in enumerate(mn):
        i2 = mn[k + 1] if k + 1 < len(mn) else mn[0] + n
        seg = np.r_[vs, vs][i0:i2 + 1]; ip = i0 + int(np.argmax(seg))
        ph.append(("A", i0, ip)); ph.append(("B", ip, i2))
    return ph, mn
def _cls(kind, length):
    return "B" if kind == "B" else "A%d" % next(i for i in range(3) if CL[i] <= length < CL[i + 1])
def fit(tracks, ds=2.0):
    pool = {}; R25, R26 = [], []
    for c in tracks:
        a, b = hlib.lap(c, 2025), hlib.lap(c, 2026); A = hlib.align(a, b, n=int(a["D"] / ds))
        s, v5, v6 = A["s"], A["v25"], A["v26"]; n = len(s); q = v6 / v5
        ph, mn = phases(s, v5)
        for kind, i0, i1 in ph:
            L = (i1 - i0) * (s[1] - s[0]); idx = np.arange(i0, i1 + 1); u = (idx - i0) / max(i1 - i0, 1)
            key = _cls(kind, L); pool.setdefault(key, []).append((u, q[idx % n]))
        for i in mn: R25.append(v5[i]); R26.append(min(v6[max(i - 10, 0):i + 10]))
    M = {}
    for key, lst in pool.items():
        u = np.concatenate([x[0] for x in lst]); qq = np.concatenate([x[1] for x in lst])
        M[key] = np.array([np.median(qq[(u >= lo) & (u <= lo + 0.1)]) for lo in UB[:-1]])
    R25, R26 = np.array(R25), np.array(R26); rc = np.arange(50, 351, 20.0)
    r = np.array([np.median((R26 / R25)[(R25 >= x - 10) & (R25 < x + 10)]) if ((R25 >= x - 10) & (R25 < x + 10)).sum() >= 3 else np.nan for x in rc])
    ok = ~np.isnan(r); M["rc"], M["r"] = rc, np.interp(rc, rc[ok], gaussian_filter1d(r[ok], 1.0)); M["uc"] = UB[:-1] + 0.05
    return M
def predict(M, L, ds=2.0):
    """2025 lap dict -> (s, v26, t26). Lap time = integral, reported relative: real 2025 lap x (t26/t25 model)."""
    s = np.arange(0, L["D"], ds); n = len(s); v5 = np.interp(s, L["d"], L["v"]); q = np.ones(n); w = np.zeros(n)
    ph, mn = phases(s, v5)
    for kind, i0, i1 in ph:
        Lp = (i1 - i0) * ds; idx = np.arange(i0, i1 + 1); u = (idx - i0) / max(i1 - i0, 1)
        qq = np.interp(u, M["uc"], M[_cls(kind, Lp)]); q[idx % n] += qq - 1; w[idx % n] += 1
    q = 1 + (q - 1) / np.maximum(w, 1)
    for i in mn:                                   # corner minima from the speed-dependent ratio, blended +-20 m
        k = np.arange(i - 10, i + 11) % n; wt = 1 - abs(np.arange(-10, 11)) / 11
        q[k] = q[k] * (1 - wt) + np.interp(v5[i], M["rc"], M["r"]) * wt
    v6 = v5 * gaussian_filter1d(q, 3, mode="wrap")
    t6 = np.cumsum(ds / (v6 / 3.6)); t5 = np.cumsum(ds / (v5 / 3.6))
    return s, v6, t6 * L["lap"] / t5[-1]
