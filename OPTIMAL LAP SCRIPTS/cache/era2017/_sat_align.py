"""Fit a similarity transform (scale, rotation, translation) from the project's Sepang metre frame
to the satellite mosaic, by maximising how much of the road (sampled between our outline edges)
lands on asphalt-coloured pixels.  python _sat_align.py sat/sepang_z18.png
Writes sat/align.json: px = A @ [X, Y] + b  (image x right, y down)."""
import json, math, os, sys
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.optimize import minimize
from scipy.spatial import cKDTree
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TR = os.path.join(ROOT, "F1_Pipeline_Assets", "tracks")

img = sys.argv[1]; meta = json.load(open(img[:-4] + ".json"))
rgb = np.asarray(Image.open(img), float) / 255.0
mx, mn = rgb.max(2), rgb.min(2); sat = (mx - mn) / np.maximum(mx, 1e-3)
asph = ((sat < 0.18) & (mx > 0.22) & (mx < 0.62)).astype(float)      # grey tarmac (not white run-off, not grass)
score_map = gaussian_filter(asph, 2.0)
lat0 = 2.761; mpp = 156543.03392 * math.cos(math.radians(lat0)) / 2 ** meta["z"]

o = json.load(open(os.path.join(TR, "malaysian_grand_prix_outline.json")))
outer, inner = np.asarray(o["outer"])[:, :2], np.asarray(o["inner"])[:, :2]
# road samples: points between each outer point and its nearest inner point
j = cKDTree(inner).query(outer)[1]
pts = np.concatenate([outer + f * (inner[j] - outer) for f in (0.2, 0.35, 0.5, 0.65, 0.8)])
edge_out = np.concatenate([outer + f * (outer - inner[j]) for f in (0.25, 0.5)])   # just outside the road


def proj(p, P):
    s, th, tx, ty = p
    c, sn = math.cos(th), math.sin(th)
    X = s * (c * P[:, 0] - sn * P[:, 1]) + tx
    Y = -s * (sn * P[:, 0] + c * P[:, 1]) + ty
    return X, Y


def f(p):
    X, Y = proj(p, pts); Xo, Yo = proj(p, edge_out)
    return -(map_coordinates(score_map, [Y, X], order=1, cval=0).mean()
             - 0.5 * map_coordinates(score_map, [Yo, Xo], order=1, cval=0).mean())

# coarse search: centroid of road samples -> centre of the asphalt mass
H, W = asph.shape; ys, xs = np.nonzero(asph[::4, ::4]); cx0, cy0 = xs.mean() * 4, ys.mean() * 4
c = pts.mean(0); best = None
for sc in (0.97, 1.0, 1.03, 1.06):
    for thd in np.arange(-12, 12.1, 1.5):
        s = sc / mpp; th = math.radians(thd)
        X, Y = proj((s, th, 0, 0), c[None]); 
        for dx in range(-160, 161, 20):
            for dy in range(-160, 161, 20):
                p = (s, th, cx0 - X[0] + dx, cy0 - Y[0] + dy); v = f(p)
                if best is None or v < best[0]: best = (v, p)
print("coarse", best)
r = minimize(f, best[1], method="Nelder-Mead", options=dict(xatol=1e-4, fatol=1e-6, maxiter=4000,
             initial_simplex=None))
s, th, tx, ty = r.x
print("fit score", -r.fun, "scale m-ratio", s * mpp, "rot deg", math.degrees(th), "t", tx, ty)
json.dump({"img": img, "s": s, "th": th, "tx": tx, "ty": ty, "mpp": mpp, "scale_ratio": s * mpp,
           "score": -r.fun}, open(os.path.join(HERE, "sat", "align_" + os.path.basename(img)[:-4] + ".json"), "w"), indent=1)
# overlay
from PIL import ImageDraw
im = Image.open(img).convert("RGB"); d = ImageDraw.Draw(im)
for P, col in ((outer, (255, 0, 255)), (inner, (0, 255, 255))):
    X, Y = proj(r.x, P); d.line(list(zip(X, Y)) + [(X[0], Y[0])], fill=col, width=3)
im.resize((im.width // 2, im.height // 2)).save(os.path.join(HERE, "sat", "align_overlay.png"))
Image.fromarray((asph * 255).astype(np.uint8)).resize((W // 4, H // 4)).save(os.path.join(HERE, "sat", "asphalt_mask.png"))
