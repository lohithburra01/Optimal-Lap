"""Where the line sits in the road: lateral position (0 = inner/right edge ... 1 = outer) and centreline radius, by real distance."""
import sys, json, io, contextlib, numpy as np
import trace_fit as T, sim_gt3_car as G
rl = np.array(json.load(open(sys.argv[1]))["raceline"])[:, :2]
car = dict(G.GT3_CAR); car.update(json.load(open(sys.argv[2])))
o = json.load(open("assets/" + (sys.argv[6] if len(sys.argv) > 6 else "portimao_outline.json")))
A = np.array(o["outer"]); B = np.array(o["inner"]); Cn = (A + B) / 2
with contextlib.redirect_stdout(io.StringIO()):
    rmse, r, pairs, svr, sh = T.compare(rl, car)
arc = r["arc"]; L = r["L"]; sc = L / T.REAL_LEN
xr = np.r_[0, [p[0] for p in pairs], T.rd[-1]]; xs = np.r_[0, [p[1] for p in pairs], T.rd[-1] * sc]
def kap(P, st):
    n = len(P); k = np.zeros(n)
    for i in range(n):
        a, b, c = P[(i - st) % n], P[i], P[(i + st) % n]; ab, bc, ac = b - a, c - b, c - a
        k[i] = 2 * (ab[0] * bc[1] - ab[1] * bc[0]) / max(np.linalg.norm(ab) * np.linalg.norm(bc) * np.linalg.norm(ac), 1e-9)
    return k
kc = kap(Cn, 6)
lo, hi, step = map(int, sys.argv[3:6])
for x in range(lo, hi, step):
    s = (np.interp(x, xr, xs) + sh) % L; i = int(np.argmin(np.abs(arc - s)))
    p = rl[i]; j = int(np.argmin(np.linalg.norm(Cn - p, axis=1)))
    w = np.linalg.norm(A[j] - B[j]); lat = np.dot(p - B[j], A[j] - B[j]) / w ** 2
    print(f"{x:5d} lat {lat:4.2f} (0=inner-file edge)  width {w:4.1f}  R_centre {1/max(abs(kc[j]),1e-4):6.0f} sign {np.sign(kc[j]):+.0f}")
