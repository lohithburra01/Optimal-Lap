"""Rebuild Sepang's road edges from z19 satellite imagery (real-world geometry, not the SVG).
For every station of the shipped line, cast the road normal, classify pixels as tarmac / not-tarmac,
and walk out from the old-outline road centre to the first >= RUN m of not-tarmac on each side
(the white edge line / kerb / run-off / grass). Outputs offsets in the OLD metre frame:
  sat/edges_raw.npz  (P, N, lo_old, hi_old, lo_sat, hi_sat, ok)
  python _sat_edges.py"""
import json, math, os, sys
import numpy as np
import shapely
from shapely.geometry import Polygon
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import _sat_zoom as ZZ, _sat_sepang as T
RUN = float(os.environ.get("EDGE_RUN", "0.6"))
TILES = {}


def px(gx, gy):
    """bilinear-free nearest RGB at global z19 pixel coords (arrays)."""
    tx, ty = (gx // 256).astype(int), (gy // 256).astype(int)
    out = np.zeros((len(gx), 3))
    for key in set(zip(tx.tolist(), ty.tolist())):
        if key not in TILES:
            TILES[key] = np.asarray(T.get(19, key[0], key[1]), float) / 255.0
        m = (tx == key[0]) & (ty == key[1])
        out[m] = TILES[key][(gy[m] % 256).astype(int), (gx[m] % 256).astype(int)]
    return out


def tarmac(rgb):
    mx, mn = rgb.max(1), rgb.min(1); sat = (mx - mn) / np.maximum(mx, 1e-3)
    blue = (rgb[:, 2] - rgb[:, 0]) > 0.035                      # painted run-off beyond the white line
    return (sat < 0.20) & (mx > 0.16) & (mx < 0.60) & ~blue


def main():
    P = np.asarray(json.load(open(os.path.join(ZZ.TR, "malaysian_grand_prix_raceline.json")))["raceline"])[:, :2]
    n = len(P); t = np.roll(P, -1, 0) - np.roll(P, 1, 0); t /= np.linalg.norm(t, axis=1, keepdims=True)
    N = np.column_stack([-t[:, 1], t[:, 0]])
    o = json.load(open(os.path.join(ZZ.TR, "malaysian_grand_prix_outline.json")))
    A, B = Polygon(o["outer"]), Polygon(o["inner"]); big, small = (A, B) if A.area > B.area else (B, A)
    road = big.difference(small); shapely.prepare(road)
    d = np.arange(-40, 40.001, 0.15); i0 = len(d) // 2
    lo_o = np.zeros(n); hi_o = np.zeros(n); lo_s = np.full(n, np.nan); hi_s = np.full(n, np.nan)
    run = max(1, int(round(RUN / 0.15)))
    for i in range(n):
        pts = P[i] + d[:, None] * N[i]
        ins = shapely.contains_xy(road, pts[:, 0], pts[:, 1])
        j = i0 if ins[i0] else int(np.argmin(np.where(ins, np.abs(d), 1e9)))
        a = j
        while a > 0 and ins[a - 1]: a -= 1
        b = j
        while b < len(d) - 1 and ins[b + 1]: b += 1
        lo_o[i], hi_o[i] = d[a], d[b]
        g = ZZ.to_g19(pts); tm = tarmac(px(g[:, 0], g[:, 1]))
        c = int(round((a + b) / 2))
        if not tm[c]:                                   # seed on tarmac nearest the old centre
            cand = np.nonzero(tm[max(0, c - 27):c + 28])[0]
            if not len(cand): continue
            c = max(0, c - 27) + cand[np.argmin(np.abs(cand - 27))]
        def walk(k, step):
            while 0 <= k + step < len(d):
                seg = tm[k + step: k + step * (run + 1): step] if step > 0 else tm[max(0, k + step * run): k][::-1]
                if len(seg) and not seg.any(): return k
                k += step
            return None
        ea, eb = walk(c, -1), walk(c, +1)
        if ea is not None and eb is not None:
            lo_s[i], hi_s[i] = d[ea], d[eb]
    ok = np.isfinite(lo_s) & np.isfinite(hi_s)
    np.savez(os.path.join(HERE, "sat", "edges_raw.npz"), P=P, N=N, lo_old=lo_o, hi_old=hi_o, lo_sat=lo_s, hi_sat=hi_s, ok=ok)
    w_o, w_s = hi_o - lo_o, hi_s - lo_s
    print(f"stations {n}, detected {ok.sum()}, old width median {np.median(w_o):.1f} m, sat width median {np.nanmedian(w_s):.1f} m")
    print("sat width pct 5/25/50/75/95:", np.nanpercentile(w_s, [5, 25, 50, 75, 95]).round(1))
    print("edge shift |sat-old| median lo %.2f hi %.2f m" % (np.nanmedian(np.abs(lo_s - lo_o)), np.nanmedian(np.abs(hi_s - hi_o))))


if __name__ == "__main__":
    main()
