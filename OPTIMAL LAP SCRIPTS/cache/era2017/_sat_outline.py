"""Clean the satellite edge detections and write a real-world Sepang outline (same metre frame as the
shipped outline, so it overlays the 2026 assets; true scale = x align scale_ratio).
Cleaning per side: shift = sat - old; reject |shift| > MAXS (detector leaked into service roads /
shadows) -> interpolate from neighbours; median(9) then gaussian(3 stations ~ 6 m).
  python _sat_outline.py  -> sepang_sat_outline.json, sat/edges_clean.npz"""
import json, os, sys
import numpy as np
from scipy.ndimage import median_filter, gaussian_filter1d
from shapely.geometry import Polygon
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import _sat_zoom as ZZ
MAXS = float(os.environ.get("MAXS", "6.0"))
E = dict(np.load(os.path.join(HERE, "sat", "edges_raw.npz"))); P, N = E["P"], E["N"]; n = len(P)
idx = np.arange(n); out = {}
ab = ZZ.arcs(P)
# Reviewed by eye on every 500 m crop (sat/clean_*.png). Where the imagery cannot show the edge,
# keep the old outline: lo 1030-1330 two-tone resurfacing mid-road; lo 4060-4260 / 4580-4720 pit-entry
# lines; lo 5150-5470 pit-wall line; hi 4280-5060 grandstand roof overhangs the back straight and T15.
OVERRIDE = {"lo": [(1030, 1330), (4060, 4260), (4580, 4720), (5150, 5470)], "hi": [(4280, 5060)]}
for side in ("lo", "hi"):
    s = E[side + "_sat"] - E[side + "_old"]
    bad = ~np.isfinite(s) | (np.abs(s) > MAXS)
    s[bad] = np.interp(idx[bad], idx[~bad], s[~bad], period=n)
    for a0, a1 in OVERRIDE[side]:
        s[(ab >= a0) & (ab <= a1)] = 0.0
    s = gaussian_filter1d(median_filter(s, size=9, mode="wrap"), 3, mode="wrap")
    out[side] = E[side + "_old"] + s
    print(side, "rejected", int(bad.sum()), "stations")
lo, hi = out["lo"], out["hi"]
w = hi - lo; print("width pct 5/50/95", np.percentile(w, [5, 50, 95]).round(1))
L, R = P + hi[:, None] * N, P + lo[:, None] * N
A, B = Polygon(L), Polygon(R)
outer, inner = (L, R) if A.area > B.area else (R, L)
al = json.load(open(os.path.join(HERE, "sat", "align_sepang_z18.json")))
C = 0.5 * (L + R); cl = np.linalg.norm(np.diff(C, axis=0, append=C[:1]), axis=1).sum()
print(f"centreline {cl:.1f} m (frame), x{al['scale_ratio']:.4f} = {cl * al['scale_ratio']:.1f} m true; official 5543 m")
json.dump({"outer": outer.tolist(), "inner": inner.tolist(), "source": "Esri World Imagery z19 edge detection (_sat_edges.py/_sat_outline.py)",
           "frame": "same as malaysian_grand_prix_outline.json", "true_scale": al["scale_ratio"]},
          open(os.path.join(HERE, "sepang_sat_outline.json"), "w"))
np.savez(os.path.join(HERE, "sat", "edges_clean.npz"), P=P, N=N, lo_old=E["lo_old"], hi_old=E["hi_old"], lo_sat=lo, hi_sat=hi)
