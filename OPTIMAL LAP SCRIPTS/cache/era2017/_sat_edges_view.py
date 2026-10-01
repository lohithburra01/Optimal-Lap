"""Draw detected satellite edges (lime/magenta dots) vs old outline (white) on a z19 crop.
  python _sat_edges_view.py <arc_from> <arc_to> <out.png> [edges.npz]"""
import sys, os, json, numpy as np
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import _sat_zoom as ZZ, _sat_sepang as T
a0, a1, out = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
E = np.load(sys.argv[4] if len(sys.argv) > 4 else os.path.join(HERE, "sat", "edges_raw.npz"))
P, N = E["P"], E["N"]; ab = ZZ.arcs(P); sel = (ab >= a0) & (ab <= a1)
g = ZZ.to_g19(P[sel]); pad = 110
x0, y0 = g.min(0) - pad; x1, y1 = g.max(0) + pad
X0, Y0, X1, Y1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
im = Image.new("RGB", ((X1 - X0 + 1) * 256, (Y1 - Y0 + 1) * 256))
for x in range(X0, X1 + 1):
    for y in range(Y0, Y1 + 1):
        im.paste(T.get(19, x, y), ((x - X0) * 256, (y - Y0) * 256))
off = np.array([X0 * 256, Y0 * 256]); d = ImageDraw.Draw(im)
for key, col in (("lo_old", (255, 255, 255)), ("hi_old", (255, 255, 255))):
    q = ZZ.to_g19(P + E[key][:, None] * N)[sel] - off; d.line([tuple(p) for p in q], fill=col, width=1)
for key, col in (("lo_sat", (0, 255, 0)), ("hi_sat", (255, 0, 255))):
    v = E[key]; m = sel & np.isfinite(v)
    q = ZZ.to_g19(P[m] + v[m][:, None] * N[m]) - off
    for p in q: d.ellipse([p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2], fill=col)
for a in np.arange(np.ceil(a0 / 50) * 50, a1, 50):
    i = int(np.argmin(np.abs(ab - a))); p = ZZ.to_g19(P[i:i + 1])[0] - off
    d.text((p[0] + 4, p[1] - 4), f"{int(a)}", fill=(255, 255, 0))
im.crop((int(x0 - X0 * 256), int(y0 - Y0 * 256), int(x1 - X0 * 256), int(y1 - Y0 * 256))).save(out); print(out)
