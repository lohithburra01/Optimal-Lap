"""Kerb-level satellite crop of a stretch of Sepang with our lines drawn on it.
  python _sat_zoom.py <arc_from_m> <arc_to_m> <out.png> [line.json ...]
Lines: base 2026 line (cyan) + any extra raceline json (orange, magenta, ...). Arc ticks every 50 m."""
import json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import _sat_sepang as T
TR = os.path.join(ROOT, "F1_Pipeline_Assets", "tracks")
Z = 19
al = json.load(open(os.path.join(HERE, "sat", "align_sepang_z18.json")))
m18 = json.load(open(os.path.join(HERE, "sat", "sepang_z18.json")))


def to_g19(P):
    """metre frame -> global z19 pixel coords."""
    s, th = al["s"], al["th"]; c, sn = math.cos(th), math.sin(th)
    X = s * (c * P[:, 0] - sn * P[:, 1]) + al["tx"]; Y = -s * (sn * P[:, 0] + c * P[:, 1]) + al["ty"]
    return np.column_stack([(m18["tx0"] * 256 + X) * 2, (m18["ty0"] * 256 + Y) * 2])


def arcs(P):
    seg = np.linalg.norm(np.diff(P, axis=0, append=P[:1]), axis=1); return np.cumsum(seg) - seg


def main():
    a0, a1, out = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
    base = np.asarray(json.load(open(os.path.join(TR, "malaysian_grand_prix_raceline.json")))["raceline"])[:, :2]
    lines = [("2026 shipped", base)] + [(os.path.basename(p)[:-5], np.asarray(json.load(open(p))["raceline"])[:, :2]) for p in sys.argv[4:]]
    ab = arcs(base); sel = (ab >= a0) & (ab <= a1)
    g = to_g19(base[sel]); pad = 120
    x0, y0 = g.min(0) - pad; x1, y1 = g.max(0) + pad
    X0, Y0, X1, Y1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    im = Image.new("RGB", ((X1 - X0 + 1) * 256, (Y1 - Y0 + 1) * 256))
    for x in range(X0, X1 + 1):
        for y in range(Y0, Y1 + 1):
            im.paste(T.get(Z, x, y), ((x - X0) * 256, (y - Y0) * 256))
    off = np.array([X0 * 256, Y0 * 256]); d = ImageDraw.Draw(im)
    o = json.load(open(os.environ.get("SAT_OUTLINE") or os.path.join(TR, "malaysian_grand_prix_outline.json")))
    for k in ("outer", "inner"):
        q = to_g19(np.asarray(o[k])[:, :2]) - off; d.line([tuple(p) for p in q], fill=(255, 255, 255), width=1)
    cols = [(0, 230, 255), (255, 150, 0), (255, 0, 200), (120, 255, 0)]
    for (name, P), col in zip(lines, cols):
        q = to_g19(P) - off; d.line([tuple(p) for p in q] + [tuple(q[0])], fill=col, width=3)
    for a in np.arange(math.ceil(a0 / 50) * 50, a1, 50):
        i = int(np.argmin(np.abs(ab - a))); p = to_g19(base[i:i + 1])[0] - off
        d.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], fill=(255, 255, 0)); d.text((p[0] + 6, p[1] - 6), f"{int(a)}", fill=(255, 255, 0))
    for k, ((name, _), col) in enumerate(zip(lines, cols)):
        d.text((10, 10 + 14 * k), name, fill=col)
    lo, hi = (x0 - X0 * 256, y0 - Y0 * 256), (x1 - X0 * 256, y1 - Y0 * 256)
    im = im.crop((int(lo[0]), int(lo[1]), int(hi[0]), int(hi[1])))
    im.save(out); print(out, im.size, "m/px", al["mpp"] / 2)


if __name__ == "__main__":
    main()
