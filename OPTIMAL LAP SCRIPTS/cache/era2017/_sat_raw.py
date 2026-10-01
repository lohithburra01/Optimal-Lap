"""Raw (no overlay) contrast-stretched satellite crop of an arc stretch, to read tarmac edges, kerbs and rubber.
  python _sat_raw.py <arc_from> <arc_to> <out.png>"""
import sys, os, json, numpy as np
from PIL import Image, ImageOps
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import _sat_zoom as ZZ, _sat_sepang as T
a0, a1, out = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
base = np.asarray(json.load(open(os.path.join(ZZ.TR, "malaysian_grand_prix_raceline.json")))["raceline"])[:, :2]
ab = ZZ.arcs(base); g = ZZ.to_g19(base[(ab >= a0) & (ab <= a1)]); pad = 80
x0, y0 = g.min(0) - pad; x1, y1 = g.max(0) + pad
X0, Y0, X1, Y1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
im = Image.new("RGB", ((X1 - X0 + 1) * 256, (Y1 - Y0 + 1) * 256))
for x in range(X0, X1 + 1):
    for y in range(Y0, Y1 + 1):
        im.paste(T.get(19, x, y), ((x - X0) * 256, (y - Y0) * 256))
im = im.crop((int(x0 - X0 * 256), int(y0 - Y0 * 256), int(x1 - X0 * 256), int(y1 - Y0 * 256)))
gray = np.asarray(im.convert("L"), float)
lo, hi = np.percentile(gray[(gray > 40) & (gray < 150)], [3, 97])          # stretch the tarmac range
st = np.clip((gray - lo) / (hi - lo), 0, 1) ** 1.2
Image.fromarray((st * 255).astype(np.uint8)).resize((im.width * 2 // 2, im.height * 2 // 2)).save(out); print(out, im.size)
