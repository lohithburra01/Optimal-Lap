"""Data-driven racing line for the second car.

P1 drives the shipped optimal line. P2's line = P1's line changed ONLY in corners where the two real speed
traces say the drivers did something different, and only in the direction the physics implies:
  * apex timing   - P2's slow-speed zone sits later/earlier along the lap -> the corner's lateral profile
                    (entry, apex, exit offsets vs the centreline) is slid along the track by that much.
  * apex speed    - same grip => R ~ v^2. A higher minimum speed needs a larger-radius arc through the same
                    entry/exit points: flatter arc = apex moves OUTWARD by the sagitta difference (and inward
                    for a lower minimum speed, never closer to a wall than P1 itself ever gets).
Everywhere else P2 == P1 exactly. Check: lateral g (v_min^2 * curvature of its own line) per corner.

  python driver_lines.py --track "Singapore Grand Prix" --year 2026 --session SQ --drivers TOP2   (mockup PNG)
"""
import argparse, json, os, sys
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lap_compare_optimal as LCO
import optimal_lines as OL
RV = LCO.RV

MIN_DV_KMH = 1.5        # apex-speed differences smaller than this are noise -> no radius change
MIN_DS_M = 3.0          # apex-timing differences smaller than this are noise -> no slide
MAX_DS_M = 10.0
MAX_BUMP_M = 2.0        # a driver's line never strays more than this from P1's (per bump)
BROADEN_M = 18.0        # how far a faster apex spreads the turning (gaussian sigma, m)
CORNER_PROM_KMH = 12.0  # a corner = a speed minimum this deep
SLOW_ZONE_KMH = 8.0     # "slow zone" = within this of the corner's minimum speed (its centroid = apex timing)


def _resample(P, n):
    P = np.asarray(P, float); C = np.vstack([P, P[:1]])
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))])
    s = np.linspace(0, arc[-1], n, endpoint=False)
    return np.column_stack([np.interp(s, arc, C[:, 0]), np.interp(s, arc, C[:, 1])]), arc[-1]


def _frame(P):
    """unit tangent, left normal, signed curvature of a closed polyline."""
    d1 = (np.roll(P, -1, 0) - np.roll(P, 1, 0)) / 2; d2 = np.roll(P, -1, 0) - 2 * P + np.roll(P, 1, 0)
    sp = np.linalg.norm(d1, axis=1); T = d1 / sp[:, None]
    k = (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / sp ** 3
    return T, np.column_stack([-T[:, 1], T[:, 0]]), k


def _speed_on_grid(tr, master_len, grid):
    d = tr['dist'] * master_len / tr['dist'].max()
    return gaussian_filter1d(np.interp(grid, d, tr['speed'] * 3.6), 3, mode='wrap')


def build(recipe, ref_tr, tgt_tr, log=print):
    n = 4000
    P1, L = _resample(json.load(open(recipe['raceline'], encoding='utf-8'))['raceline'], n)
    ds = L / n
    o = json.load(open(recipe['outline'], encoding='utf-8'))
    outer, _ = _resample(o['outer'], n); inner, _ = _resample(o['inner'], n)
    T, N, k1 = _frame(P1)
    k1s = gaussian_filter1d(k1, 4, mode='wrap')
    # room to each side of P1 along its normal (distance to the road edges)
    edges = np.vstack([outer, inner]); tree = cKDTree(edges)

    def room(P, Nv, sign):
        r = np.full(len(P), 30.0)
        for step in np.arange(0.1, 30.0, 0.1):
            hit = tree.query(P + sign * step * Nv)[0] < 0.12
            r = np.where(hit & (r == 30.0), step, r)
        return r
    room_l, room_r = room(P1, N, +1), room(P1, N, -1)
    # P1's own closest approach to an edge = the wall margin P2 must respect too
    min_clear = float(min(room_l.min(), room_r.min()))

    master_len = ref_tr['dist'].max()
    grid = np.arange(n) * master_len / n                      # telemetry distance at each line station
    v1 = _speed_on_grid(ref_tr, master_len, grid); v2 = _speed_on_grid(tgt_tr, master_len, grid)
    mins, _ = find_peaks(-np.tile(v1, 3), prominence=CORNER_PROM_KMH, distance=int(60 / ds))
    mins = sorted({m - n for m in mins if n <= m < 2 * n})

    idx = np.arange(n); report = []; n_off = np.zeros(n)
    ksm_signed = gaussian_filter1d(k1, 4, mode='wrap'); ksm = np.abs(ksm_signed)
    from scipy.optimize import minimize
    for c, m in enumerate(mins):
        win = (idx - m + n // 2) % n - n // 2
        near = np.abs(win) * ds < 80
        j1 = np.where(near)[0][np.argmin(v1[near])]; j2 = np.where(near)[0][np.argmin(v2[near])]
        vm1, vm2 = v1[j1], v2[j2]

        def apex_after_brake(v, vm):
            # slow-zone centroid measured from this driver's OWN braking point (telemetry distance drift cancels)
            back = (win > -300 / ds) & (win <= 0)
            seg = np.where(back)[0][np.argsort(win[back])]
            vmax_i = seg[np.argmax(v[seg])]
            after = seg[win[seg] > win[vmax_i]]
            brake = after[np.argmax(v[after] < v[vmax_i] - 3)] if np.any(v[after] < v[vmax_i] - 3) else vmax_i
            z = near & (v < vm + SLOW_ZONE_KMH)
            return float(np.average(win[z], weights=(vm + SLOW_ZONE_KMH - v[z])) - win[brake]) * ds
        dS = apex_after_brake(v2, vm2) - apex_after_brake(v1, vm1)
        dV = vm2 - vm1
        dS = float(np.clip(dS, -MAX_DS_M, MAX_DS_M)) if abs(dS) >= MIN_DS_M else 0.0
        if abs(dV) < MIN_DV_KMH: dV = 0.0
        pk = int(np.where(near)[0][np.argmax(ksm[near])]); kp = ksm[pk]
        a = pk; b = pk
        while ksm[(a - 1) % n] > 0.3 * kp and (pk - a) * ds < 150: a -= 1
        while ksm[(b + 1) % n] > 0.3 * kp and (b - pk) * ds < 150: b += 1
        rec = dict(corner=c + 1, at_m=round(m * ds), v1=round(vm1, 1), v2=round(vm2, 1), dV=round(dV, 1),
                   dS=round(dS, 1), shape='same', pk=pk)
        if not dV and not dS:
            report.append(rec); continue
        # window: 50 m before turn-in .. 50 m after exit; 3 lateral bumps (entry / apex / exit)
        i0, i1 = a - int(50 / ds), b + int(50 / ds)
        st = np.arange(i0, i1) % n; loc = np.arange(len(st)) * ds; L_w = loc[-1]
        sgn = np.sign(ksm_signed[pk])                    # +1 left-hander: inside = +normal
        cA, cE, cX = (pk - i0) * ds, (a - i0) * ds, (b - i0) * ds
        hw = max((b - a) * ds / 2, 15.0)
        B = np.array([np.where(np.abs(loc - c0) < hw * 1.2, np.cos(0.5 * np.pi * (loc - c0) / (hw * 1.2)) ** 2, 0)
                      for c0 in (cE, cA, cX)])
        B *= np.clip(np.minimum(loc, L_w - loc) / 25.0, 0, 1)        # exactly zero at the window ends
        Pw, Nw = P1[st], N[st]
        lo = -(room_r[st] - min_clear); hi = room_l[st] - min_clear
        target_k = kp * (vm1 / vm2) ** 2
        cen1 = np.sum(loc * ksm[st]) / np.sum(ksm[st])

        def curv(wts):
            Q = Pw + np.clip(wts @ B, lo, hi)[:, None] * Nw
            d1 = np.gradient(Q, ds, axis=0); d2 = np.gradient(d1, ds, axis=0)
            k = (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / np.maximum(np.linalg.norm(d1, axis=1) ** 3, 1e-9)
            return np.abs(gaussian_filter1d(k, 4))

        def cost(wts):
            k = curv(wts)
            e_k = (k[(loc > cA - hw) & (loc < cA + hw)].max() / target_k - 1) ** 2   # same grip at P2's apex speed
            e_s = ((np.sum(loc * k) / np.sum(k) - cen1 - dS) / 5.0) ** 2 if dS else 0.0
            return 50 * e_k + 4 * e_s + 0.02 * np.sum(wts ** 2) + 20 * max(0, k.max() / target_k - 1.03) ** 2
        w_opt = minimize(cost, np.zeros(3), method='Nelder-Mead', bounds=[(-MAX_BUMP_M, MAX_BUMP_M)] * 3,
                         options=dict(xatol=0.01, fatol=1e-5, maxiter=600)).x
        nn = np.clip(w_opt @ B, lo, hi)
        n_off[st] += nn
        k_new = curv(w_opt)
        rec['shape'] = 'rounder' if k_new[(loc > cA - hw) & (loc < cA + hw)].max() < kp * 0.99 else                        'sharper' if k_new[(loc > cA - hw) & (loc < cA + hw)].max() > kp * 1.01 else 'same'
        rec['w'] = [round(float(x), 2) for x in w_opt]
        rec['dS_line'] = round(float(np.sum(loc * k_new) / np.sum(k_new) - cen1), 1)
        report.append(rec)
    # wall check: never closer to an edge than P1 itself ever gets
    clipped = np.clip(n_off, -(room_r - min_clear), room_l - min_clear)
    n_clip = float(np.abs(clipped - n_off).max()); n_off = clipped
    P2 = P1 + n_off[:, None] * N
    _, _, k2 = _frame(P2); k2s = gaussian_filter1d(k2, 4, mode='wrap')
    for r in report:
        pk = r['pk']; w = slice(max(0, pk - int(25 / ds)), pk + int(25 / ds))
        r['latg1'] = round((r['v1'] / 3.6) ** 2 * np.abs(k1s[w]).max() / 9.81, 2)
        r['latg2'] = round((r['v2'] / 3.6) ** 2 * np.abs(k2s[w]).max() / 9.81, 2)
    gap = np.linalg.norm(P2 - P1, axis=1)
    log(f"[lines] wall clip max {n_clip:.2f} m")
    log(f"[lines] {len(report)} corners; changed at {sum(1 for r in report if r['shape'] != 'same' or r['dS'])}; "
        f"gap mean {gap.mean():.2f} m, max {gap.max():.2f} m; wall margin kept >= {min_clear:.2f} m")
    return P1, P2, outer, inner, report, (v1, v2, grid)


def mockup(P1, P2, outer, inner, report, labels, out_png):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    ch = sorted([r for r in report if r['shape'] != 'same' or r['dS']], key=lambda r: -np.linalg.norm(P2[r['pk']] - P1[r['pk']]))[:6]
    fig = plt.figure(figsize=(16, 11), facecolor='black')
    ax0 = fig.add_axes([0.0, 0.0, 0.42, 1.0])
    for ax in [ax0]:
        ax.fill(outer[:, 0], outer[:, 1], color='#282828'); ax.fill(inner[:, 0], inner[:, 1], color='black')
        ax.plot(*np.vstack([P1, P1[:1]]).T, color='#00e0ff', lw=1.2); ax.plot(*np.vstack([P2, P2[:1]]).T, color='#ff9a3c', lw=1.2)
    for r in ch:
        ax0.text(*P1[r['pk']], f" C{r['corner']}", color='white', fontsize=10)
    ax0.set_aspect('equal'); ax0.axis('off')
    ax0.set_title(f"{labels[0]} (cyan, shipped optimal line)  vs  {labels[1]} (orange, data-driven)", color='white', fontsize=11)
    for i, r in enumerate(ch):
        ax = fig.add_axes([0.44 + (i % 3) * 0.188, 0.52 - (i // 3) * 0.48, 0.18, 0.44])
        c = P1[r['pk']]; R = 45
        ax.fill(outer[:, 0], outer[:, 1], color='#282828'); ax.fill(inner[:, 0], inner[:, 1], color='black')
        ax.plot(*outer.T, color='white', lw=1); ax.plot(*inner.T, color='white', lw=1)
        ax.plot(*P1.T, color='#00e0ff', lw=2); ax.plot(*P2.T, color='#ff9a3c', lw=2)
        ax.set_xlim(c[0] - R, c[0] + R); ax.set_ylim(c[1] - R, c[1] + R); ax.set_aspect('equal'); ax.axis('off')
        ax.set_title(f"C{r['corner']}  min {r['v1']:.0f} vs {r['v2']:.0f} km/h ({r['dV']:+.1f})\n"
                     f"apex {'later' if r['dS'] > 0 else 'earlier' if r['dS'] < 0 else 'same'} {abs(r['dS']):.0f} m (line {abs(r.get('dS_line', 0)):.0f} m), "
                     f"{r['shape']} arc\nlat g {r['latg1']} vs {r['latg2']}",
                     color='white', fontsize=9)
    fig.savefig(out_png, dpi=110, facecolor='black'); plt.close(fig)


def main():
    import optimal_x_quali as Q
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default=Q.TRACK); ap.add_argument("--year", type=int, default=Q.YEAR)
    ap.add_argument("--session", default=Q.SESSION); ap.add_argument("--drivers", default=Q.DRIVERS)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    traces, event, _ = Q.load_traces(a.track, a.year, a.session.upper(), a.drivers)
    recipe = OL.load_recipe(event)
    P1, P2, outer, inner, rep, _ = build(recipe, traces[0], traces[1])
    for r in rep:
        print({k: v for k, v in r.items() if k != 'pk'})
    out = a.out or os.path.join(HERE, "mockups", f"lines_{traces[0]['label']}_vs_{traces[1]['label']}.png")
    mockup(P1, P2, outer, inner, rep, (traces[0]['label'], traces[1]['label']), out)
    print("mockup ->", out)


if __name__ == "__main__":
    main()
