"""PATTERN MODEL: predict a 2026 Q speed trace from a track's 2025 Q trace using only pooled 2025->2026 patterns
learned on OTHER tracks (no track drawing, no car physics):
  corner minima   v26 = v25 * R(v25)                          (pooled ratio curve, median per 20 km/h bin, smoothed)
  speed caps      where 2025 was NOT flat out (partial throttle / braking), v26 <= v25 * R(v25)
  acceleration    dv/dt = A26(v, tau), tau = seconds since the last corner minimum   (pooled 2-D median table)
  braking         dv/dt = -B26(v)                              (pooled)
  v26 = min(forward accel pass, backward braking pass, caps); lap time = integral ds / v."""
import os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); import hlib
from scipy.ndimage import gaussian_filter1d
VB = np.arange(40, 361, 20.0); TB = np.arange(0, 20.1, 2.0)
def accel(L): return np.gradient(gaussian_filter1d(L["v"], 1.0), L["t"]) / 3.6
def tau_since_min(L):
    s, _ = hlib.minima(L["d"], L["v"]); tmin = np.interp(s, L["d"], L["t"]); tau = np.full(len(L["t"]), 30.0)
    for i, t in enumerate(L["t"]):
        k = tmin[tmin <= t]; tau[i] = t - k[-1] if len(k) else t + 5.0
    return tau
def fit(tracks):
    R25, R26, AV, AT, AA, BV, BB = [], [], [], [], [], [], []
    for c in tracks:
        a, b = hlib.lap(c, 2025), hlib.lap(c, 2026)
        s25, m25 = hlib.minima(a["d"], a["v"]); s26, m26 = hlib.minima(b["d"], b["v"])
        for x, y in zip(s25, m25):
            j = np.argmin(abs(s26 / b["D"] - x / a["D"]))
            if abs(s26[j] / b["D"] - x / a["D"]) < 0.02: R25.append(y); R26.append(m26[j])
        acc = accel(b); m = (b["thr"] >= 98) & (b["brk"] == 0); tau = tau_since_min(b)
        AV += b["v"][m].tolist(); AT += tau[m].tolist(); AA += acc[m].tolist()
        mb = (b["brk"] > 0) & (acc < -3); BV += b["v"][mb].tolist(); BB += (-acc[mb]).tolist()
    R25, R26, AV, AT, AA, BV, BB = map(np.array, (R25, R26, AV, AT, AA, BV, BB))
    rc = VB[:-1] + 10; r = np.array([np.median((R26 / R25)[(R25 >= lo) & (R25 < lo + 20)]) if ((R25 >= lo) & (R25 < lo + 20)).sum() >= 3 else np.nan for lo in VB[:-1]])
    ok = ~np.isnan(r); r = np.interp(rc, rc[ok], gaussian_filter1d(r[ok], 1.0))
    A = np.full((len(VB) - 1, len(TB) - 1), np.nan)
    for i, lo in enumerate(VB[:-1]):
        for j, t0 in enumerate(TB[:-1]):
            s = (AV >= lo) & (AV < lo + 20) & (AT >= t0) & (AT < t0 + 2)
            if s.sum() >= 5: A[i, j] = np.median(AA[s])
    for i in range(A.shape[0]):                 # fill along tau: carry last valid value forward, first valid backward
        row = A[i]; ok = ~np.isnan(row)
        if ok.any(): A[i] = np.interp(np.arange(len(row)), np.where(ok)[0], row[ok])
    for j in range(A.shape[1]):                 # fill along v
        col = A[:, j]; ok = ~np.isnan(col)
        if ok.any(): A[:, j] = np.interp(np.arange(len(col)), np.where(ok)[0], col[ok])
    bb = np.array([np.median(BB[(BV >= lo) & (BV < lo + 20)]) if ((BV >= lo) & (BV < lo + 20)).sum() >= 5 else np.nan for lo in VB[:-1]])
    ok = ~np.isnan(bb); bb = np.interp(rc, rc[ok], bb[ok])
    return dict(rc=rc, r=r, A=A, b=bb)
def Afun(M, v, tau):
    i = np.interp(v, M["rc"], np.arange(len(M["rc"]))); j = np.clip(tau / 2.0 - 0.5, 0, M["A"].shape[1] - 1)
    i0, j0 = int(np.floor(i)), int(np.floor(j)); i1, j1 = min(i0 + 1, len(M["rc"]) - 1), min(j0 + 1, M["A"].shape[1] - 1); fi, fj = i - i0, j - j0
    return (M["A"][i0, j0] * (1 - fi) * (1 - fj) + M["A"][i1, j0] * fi * (1 - fj) + M["A"][i0, j1] * (1 - fi) * fj + M["A"][i1, j1] * fi * fj)
def predict(M, L, ds=2.0):
    """2025 lap dict -> (s, v26 km/h, t26 cumulative s)."""
    s = np.arange(0, L["D"], ds); v25 = np.interp(s, L["d"], L["v"]); thr = np.interp(s, L["d"], L["thr"]); brk = np.interp(s, L["d"], L["brk"])
    R = lambda v: np.interp(v, M["rc"], M["r"])
    cap = np.where((thr >= 98) & (brk == 0), 400.0, v25 * R(v25))
    pm, _ = hlib.minima(s, v25); jm = np.searchsorted(s, pm); cap[jm] = np.minimum(cap[jm], v25[jm] * R(v25[jm]))
    n = len(s); v = cap.copy()
    for _ in range(2):                          # forward (accel) pass, two laps for the flying start
        tau = 30.0; vf = np.empty(n); x = v[-1]
        for i in range(n):
            if i in set(jm.tolist()): tau = 0.0
            x = min(x, cap[i]); vf[i] = x
            a = Afun(M, x, tau); vn = np.sqrt(max((x / 3.6) ** 2 + 2 * a * ds, 1.0)) * 3.6
            tau += ds / max(x / 3.6, 1.0); x = vn
        v = vf
    vb = v.copy()
    for _ in range(2):                          # backward (braking) pass
        x = vb[0]
        for i in range(n - 1, -1, -1):
            x = min(x, vb[i]); vb[i] = x; b = np.interp(x, M["rc"], M["b"]); x = np.sqrt((x / 3.6) ** 2 + 2 * b * ds) * 3.6
    v26 = np.minimum(v, vb); t = np.cumsum(ds / (v26 / 3.6))
    return s, v26, t


# ---------------- v2: DIFFERENCE model (measurement bias cancels) ----------------
def _table(V, T, Y, nmin=5):
    A = np.full((len(VB) - 1, len(TB) - 1), np.nan)
    for i, lo in enumerate(VB[:-1]):
        for j, t0 in enumerate(TB[:-1]):
            s = (V >= lo) & (V < lo + 20) & (T >= t0) & (T < t0 + 2)
            if s.sum() >= nmin: A[i, j] = np.median(Y[s])
    for i in range(A.shape[0]):
        row = A[i]; ok = ~np.isnan(row)
        if ok.any(): A[i] = np.interp(np.arange(len(row)), np.where(ok)[0], row[ok])
    for j in range(A.shape[1]):
        col = A[:, j]; ok = ~np.isnan(col)
        if ok.any(): A[:, j] = np.interp(np.arange(len(col)), np.where(ok)[0], col[ok])
    return A
def _vec(V, Y, nmin=5):
    rc = VB[:-1] + 10; y = np.array([np.median(Y[(V >= lo) & (V < lo + 20)]) if ((V >= lo) & (V < lo + 20)).sum() >= nmin else np.nan for lo in VB[:-1]])
    ok = ~np.isnan(y); return np.interp(rc, rc[ok], y[ok])
def fit2(tracks):
    M = fit(tracks); D = {y: dict(AV=[], AT=[], AA=[], BV=[], BB=[]) for y in (2025, 2026)}
    for c in tracks:
        for y in (2025, 2026):
            L = hlib.lap(c, y); acc = accel(L); tau = tau_since_min(L); m = (L["thr"] >= 98) & (L["brk"] == 0)
            D[y]["AV"] += L["v"][m].tolist(); D[y]["AT"] += tau[m].tolist(); D[y]["AA"] += acc[m].tolist()
            mb = (L["brk"] > 0) & (acc < -3); D[y]["BV"] += L["v"][mb].tolist(); D[y]["BB"] += (-acc[mb]).tolist()
    for y in (2025, 2026):
        d = {k: np.array(v) for k, v in D[y].items()}
        M[f"A{y}"] = _table(d["AV"], d["AT"], d["AA"]); M[f"B{y}"] = _vec(d["BV"], d["BB"])
    return M
def _A(M, key, v, tau):
    T = M[key]; i = np.interp(v, M["rc"], np.arange(len(M["rc"]))); j = np.clip(tau / 2.0 - 0.5, 0, T.shape[1] - 1)
    i0, j0 = int(np.floor(i)), int(np.floor(j)); i1, j1 = min(i0 + 1, T.shape[0] - 1), min(j0 + 1, T.shape[1] - 1); fi, fj = i - i0, j - j0
    return T[i0, j0] * (1 - fi) * (1 - fj) + T[i1, j0] * fi * (1 - fj) + T[i0, j1] * (1 - fi) * fj + T[i1, j1] * fi * fj
def predict2(M, L, ds=2.0, zero=False):
    """2026 = 2025 lap's own local accel/decel + pooled (2026 - 2025) shift at the current speeds/time-in-straight.
    Forward pass = accelerating stations only; backward pass = every decelerating station (braking AND lifts),
    anchored at corner minima (detected across the S/F wrap). zero=True: no shift (must reproduce the 2025 lap)."""
    s = np.arange(0, L["D"], ds); n = len(s); v25 = np.interp(s, L["d"], L["v"]); t25 = np.interp(s, L["d"], L["t"])
    brk = np.interp(s, L["d"], L["brk"]) > 0
    vs = gaussian_filter1d(v25, 2.0, mode="wrap"); a25 = np.gradient((vs / 3.6) ** 2 / 2, s)
    from scipy.signal import find_peaks
    p2, _ = find_peaks(-np.r_[vs, vs], prominence=10, distance=30); jm = np.unique(p2 % n)
    tmin = t25[jm]; tau25 = np.array([t - (tmin[tmin <= t][-1] if (tmin <= t).any() else tmin[-1] - L["lap"]) for t in t25])
    R = (lambda v: np.ones_like(v)) if zero else (lambda v: np.interp(v, M["rc"], M["r"]))
    thr = np.interp(s, L["d"], L["thr"]); flat = (thr >= 98) & ~brk
    cap = np.where(flat, 400.0, v25 * R(v25)); cap[jm] = v25[jm] * R(v25[jm]); jms = set(jm.tolist())   # not flat in 2025 -> grip/limited
    v = cap.copy()
    for _ in range(3):                                   # forward: acceleration only (flying lap: 3 passes)
        x = v[-1]; tau = 30.0; vf = np.empty(n)
        for i in range(n):
            if i in jms: tau = 0.0
            x = min(x, cap[i], v[i] if _ else 400.0); vf[i] = x
            if a25[i] > 0:
                a = a25[i] if zero else a25[i] + _A(M, "A2026", x, tau) - _A(M, "A2025", v25[i], tau25[i])
                x = np.sqrt(max((x / 3.6) ** 2 + 2 * a * ds, 1.0)) * 3.6
            tau += ds / max(vf[i] / 3.6, 1.0)
        v = np.minimum(vf, cap)
        vb = v.copy(); x = vb[0]                          # backward: all deceleration, anchored at the minima caps
        for k in range(2 * n - 1, -1, -1):
            i = k % n; x = min(x, vb[i]); vb[i] = x
            if a25[i] < 0:
                b = -a25[i]
                if not zero and brk[i]: b += np.interp(x, M["rc"], M["B2026"]) - np.interp(v25[i], M["rc"], M["B2025"])
                x = np.sqrt((x / 3.6) ** 2 + 2 * max(b, 0.5) * ds) * 3.6
            else: x = 400.0
        v = np.minimum(v, vb)
    return s, v, np.cumsum(ds / (v / 3.6))
