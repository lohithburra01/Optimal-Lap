"""Minimum-LAP-TIME racing line for the 2017-era car at Sepang (physics, car-specific).

The project's line builder is min-curvature (car-independent), so it gives every car the same
line. Here the line is a lateral offset from a base line, defined at knots every ~24 m and
interpolated with a periodic cubic spline, and the knots are moved by a parallel pattern
search to minimise the 2017 car's simulated lap (sim_2017_car, same physics engine).
Corridor: the painted road eroded by --margin (car centre to edge; 0.95 m = wheels on the line).

  python cache/era2017/_opt_line_2017.py --out cache/era2017/opt2017
"""
import argparse, json, os, sys, time
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from scipy.interpolate import CubicSpline
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

G = {}


def setup(base_path, outline_path, car, drs, margin, every):
    import shapely
    from shapely.geometry import Polygon
    P = np.asarray(json.load(open(base_path))["raceline"], float)[:, :2]
    n = len(P)
    t = np.roll(P, -1, 0) - np.roll(P, 1, 0); t /= np.linalg.norm(t, axis=1, keepdims=True)
    N = np.column_stack([-t[:, 1], t[:, 0]])
    o = json.load(open(outline_path))
    A, B = Polygon(o["outer"]), Polygon(o["inner"])
    big, small = (A, B) if A.area > B.area else (B, A)
    road = big.difference(small).buffer(-margin); shapely.prepare(road)
    d = np.arange(-20, 20.001, 0.05)
    lo = np.zeros(n); hi = np.zeros(n)
    for i in range(n):
        pts = P[i] + d[:, None] * N[i]
        ins = shapely.contains_xy(road, pts[:, 0], pts[:, 1])
        if not ins.any():
            lo[i] = hi[i] = 0.0; continue
        j0 = int(np.argmin(np.abs(d))) if ins[np.argmin(np.abs(d))] else int(np.argmin(np.where(ins, np.abs(d), 1e9)))
        a = j0
        while a > 0 and ins[a - 1]: a -= 1
        b = j0
        while b < len(d) - 1 and ins[b + 1]: b += 1
        lo[i], hi[i] = d[a], d[b]
    lo = np.minimum(lo, 0.0); hi = np.maximum(hi, 0.0)   # the shipped (on-track-checked) base is always feasible
    seg = np.linalg.norm(np.roll(P, -1, 0) - P, axis=1); arc = np.concatenate([[0], np.cumsum(seg)])
    knots = np.arange(0, n, every)
    G.update(P=P, N=N, lo=lo, hi=hi, arc=arc, L=arc[-1], kidx=knots, car=car, drs=drs)


def init(state):
    G.update(state)


def line_of(k):
    ka = G["arc"][G["kidx"]]
    cs = CubicSpline(np.append(ka, G["L"]), np.append(k, k[0]), bc_type="periodic")
    off = cs(G["arc"][:-1])
    viol = np.maximum(off - G["hi"], 0) + np.maximum(G["lo"] - off, 0)
    off = np.clip(off, G["lo"], G["hi"])
    return G["P"] + off[:, None] * G["N"], float(viol.sum())


def cost(k):
    import sim_2017_car as C
    rl, viol = line_of(np.asarray(k))
    try:
        lap = C.simulate(rl * G["scale"], G["car"], G["drs"], smooth=False)["lap"]
    except Exception:
        return 1e6
    k = np.asarray(k); d2 = np.roll(k, -1) - 2 * k + np.roll(k, 1)       # knot-scale zigzag (periodic)
    return lap + 2.0 * viol + G.get("smooth_w", 0.0) * float((d2 ** 2).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.join(ROOT, "F1_Pipeline_Assets", "tracks", "malaysian_grand_prix_raceline.json"))
    ap.add_argument("--outline", default=os.path.join(ROOT, "F1_Pipeline_Assets", "tracks", "malaysian_grand_prix_outline.json"))
    ap.add_argument("--report", default=os.path.join(HERE, "sepang_2017_report.json"), help="car + drs")
    ap.add_argument("--margin", type=float, default=0.5)
    ap.add_argument("--every", type=int, default=12, help="stations per knot (~2 m each)")
    ap.add_argument("--steps", default="2,1,0.5,0.25")
    ap.add_argument("--max-sweeps", type=int, default=30)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=1.0, help="frame -> true metres for the physics (sat align scale_ratio)")
    ap.add_argument("--car-cl", type=float, default=None, help="override the report car's cl")
    ap.add_argument("--smooth-w", type=float, default=0.0, help="penalty s/m^2 on knot 2nd differences (anti-zigzag)")
    ap.add_argument("--gg-p", type=float, default=2.0, help="g-g superellipse exponent (2 = friction circle)")
    ap.add_argument("--arc-range", default=None, help="a0,a1: only move knots in this arc range (m, frame)")
    ap.add_argument("--init-knots", default=None, help="resume from a saved *_knots.npy checkpoint")
    a = ap.parse_args()
    rep = json.load(open(a.report))
    car = dict(rep["car"]); car["cl"] = a.car_cl or car["cl"]; car["gg_p"] = a.gg_p
    setup(a.base, a.outline, car, rep["drs"], a.margin, a.every); G["scale"] = a.scale; G["smooth_w"] = a.smooth_w
    state = dict(G)
    K = len(G["kidx"]); k = np.zeros(K)
    if a.init_knots:
        k = np.load(a.init_knots); assert len(k) == K, (len(k), K)
        print(f"[opt] resumed from {a.init_knots}", flush=True)
    print(f"[opt] {len(G['P'])} stations, {K} knots, corridor width median {np.median(G['hi']-G['lo']):.1f} m", flush=True)
    active = range(K)
    if a.arc_range:
        r0, r1 = map(float, a.arc_range.split(",")); ka = G["arc"][G["kidx"]]
        active = [i for i in range(K) if r0 <= ka[i] <= r1]
        print(f"[opt] moving {len(active)} knots in {r0:.0f}-{r1:.0f} m", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(12, initializer=init, initargs=(state,)) as ex:
        best = list(ex.map(cost, [k]))[0]; base_lap = best
        print(f"[opt] base raw lap {best:.3f}s", flush=True)
        for step in map(float, a.steps.split(",")):
            for sw in range(a.max_sweeps):
                cands = []
                for i in active:
                    for s in (+step, -step):
                        c = k.copy(); c[i] += s; cands.append((i, s, c))
                res = list(ex.map(cost, [c for _, _, c in cands], chunksize=4))
                imp = sorted((r, i, s) for (i, s, _), r in zip(cands, res) if r < best - 1e-4)
                if not imp:
                    break
                chosen, used = [], set()
                for r, i, s in imp:
                    if all(abs(i - j) >= 3 and abs(i - j) <= K - 3 for j in used):
                        chosen.append((i, s)); used.add(i)
                comb = k.copy()
                for i, s in chosen: comb[i] += s
                rc = list(ex.map(cost, [comb]))[0]
                if rc < imp[0][0]:
                    k, best = comb, rc; nacc = len(chosen)
                else:
                    k = k.copy(); k[imp[0][1]] += imp[0][2]; best = imp[0][0]; nacc = 1
                print(f"[opt] step {step} sweep {sw}: {best:.3f}s (-{base_lap-best:.3f}) accepted {nacc} "
                      f"t {time.time()-t0:.0f}s", flush=True)
                np.save(a.out + "_knots.npy", k)
    rl, viol = line_of(k)
    import sim_2017_car as C
    r = C.simulate(rl * G["scale"], G["car"], G["drs"])
    json.dump({"raceline": rl.tolist(), "arc_length": r["arc"].tolist(), "track_length_m": r["L"],
               "offset_m": (np.einsum("ij,ij->i", rl - G["P"], G["N"])).round(3).tolist()},
              open(a.out + "_rl.json", "w"))
    print(f"[opt] done: raw {best:.3f}s (base {base_lap:.3f}), smoothed lap {r['lap']:.3f}s, viol {viol:.3f} m", flush=True)


if __name__ == "__main__":
    main()
