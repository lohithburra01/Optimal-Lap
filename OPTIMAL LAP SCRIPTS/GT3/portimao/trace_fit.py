"""Compare / fit the GT3 sim against the REAL AMG GT3 Evo Portimao trace (GT3/portimao/real_amg_gt3_trackday.json).
Alignment: corner speed minima paired in order -> piecewise-linear distance map (no hand offsets)."""
import json, os, sys, io, contextlib
import numpy as np
from scipy.signal import find_peaks
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sim_gt3_car as G
R = json.load(open(os.path.join(HERE, "real_amg_gt3_trackday.json")))
rt = np.array(R["t"]); rv = np.array(R["v_kmh"]); rd = np.array(R["d"])
m = rt >= 0; rd, rv = rd[m], rv[m]

def minima(d, v, prom=12):
    i, _ = find_peaks(-v, prominence=prom, distance=40); return d[i], v[i]

def sim(rl, car):
    with contextlib.redirect_stdout(io.StringIO()):
        r = G.simulate(rl, car)
    return r

REAL_LEN = 4595.0   # video ends ~0.4 s (~30 m) before the timer line at 4565 m integrated

def align_shift(sd, sv, L):
    """Circular shift (m, sim frame) of the real lap start: max correlation of speed shapes (real scaled to L)."""
    x = np.arange(0, L, 2.0); s = np.interp(x, sd, sv, period=L)
    rr = np.interp(x, rd * L / REAL_LEN, rv)
    best = max(range(0, len(x)), key=lambda k: np.dot(np.roll(s, -k) - s.mean(), rr - rr.mean()))
    return x[best]

def compare(rl, car, verbose=False, shift=None):
    r = sim(rl, car); sd = np.asarray(r["arc"]); sv = np.asarray(r["v"]) * 3.6; L = r["L"]
    sh = align_shift(sd, sv, L) if shift is None else shift
    sd = (sd - sh) % L; o = np.argsort(sd); sd, sv = sd[o], sv[o]
    dr, vr = minima(rd, rv); ds, vs = minima(sd, sv)
    # pair minima in order by nearest scaled position
    sc = L / REAL_LEN
    pairs = []
    for x, y in zip(dr, vr):
        j = int(np.argmin(np.abs(ds - x * sc)))
        if abs(ds[j] - x * sc) < 120: pairs.append((x, ds[j], y, vs[j]))
    xr = np.r_[0, [p[0] for p in pairs], rd[-1]]; xs = np.r_[0, [p[1] for p in pairs], rd[-1] * sc]
    mapped = np.interp(rd, xr, xs)
    sv_on_real = np.interp(mapped, sd, sv)
    rmse = float(np.sqrt(np.mean((sv_on_real - rv) ** 2)))
    if verbose:
        print(f"real-lap start = sim arc {sh:.0f} m | lap {r['lap']:.3f}s  top {sv.max():.1f} (real {rv.max():.0f})  speed RMSE {rmse:.1f} km/h  corners paired {len(pairs)}/{len(dr)}")
        for x, s, a, b in pairs: print(f"  real {x:6.0f} m  min {a:5.0f} | sim {s:6.0f} m  min {b:5.0f}  diff {b-a:+5.0f} km/h  pos {s/sc-x:+5.0f} m")
    return rmse, r, pairs, sv_on_real, sh

if __name__ == "__main__":
    rl = json.load(open(sys.argv[1]))["raceline"]; car = dict(G.GT3_CAR)
    if len(sys.argv) > 2: car.update(json.load(open(sys.argv[2])))
    compare(np.asarray(rl), car, True)
