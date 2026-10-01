"""Gradient polish of an _opt_line_2017 result: L-BFGS-B on all knots at once (parallel central
differences, h = 0.25 m), bounded to the corridor. Moves knots TOGETHER, which the one-knot pattern
search cannot, so it tests whether a pattern-search result is a real optimum or a local trap.
  python _polish_line.py --knots sat_optA_knots.npy --out sat_optA_pol  (same corridor args as the optimiser)"""
import argparse, json, os, sys, time
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from scipy.optimize import minimize
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import _opt_line_2017 as O

H = 0.25


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="sepang_sat_base_rl.json"); ap.add_argument("--outline", default="sepang_sat_outline.json")
    ap.add_argument("--report", default="sepang_2017_report.json"); ap.add_argument("--margin", type=float, default=0.3)
    ap.add_argument("--every", type=int, default=10); ap.add_argument("--scale", type=float, default=1.0074)
    ap.add_argument("--knots", required=True); ap.add_argument("--iters", type=int, default=60); ap.add_argument("--out", required=True)
    a = ap.parse_args(); rep = json.load(open(a.report))
    O.setup(a.base, a.outline, rep["car"], rep["drs"], a.margin, a.every); O.G["scale"] = a.scale
    k0 = np.load(a.knots); K = len(k0); ki = O.G["kidx"]
    bounds = list(zip(O.G["lo"][ki], O.G["hi"][ki])); state = dict(O.G); t0 = time.time()
    with ProcessPoolExecutor(12, initializer=O.init, initargs=(state,)) as ex:
        def fg(k):
            cands = [k] + [k + H * e for e in np.eye(K)] + [k - H * e for e in np.eye(K)]
            r = np.array(list(ex.map(O.cost, cands, chunksize=8)))
            g = (r[1:K + 1] - r[K + 1:]) / (2 * H)
            print(f"[pol] f {r[0]:.3f}s |g| {np.linalg.norm(g):.3f} t {time.time()-t0:.0f}s", flush=True)
            return r[0], g
        f0 = fg(k0)[0]
        res = minimize(fg, k0, jac=True, method="L-BFGS-B", bounds=bounds, options=dict(maxiter=a.iters, maxls=10))
    k = res.x; np.save(a.out + "_knots.npy", k)
    rl, viol = O.line_of(k)
    import sim_2017_car as C
    r = C.simulate(rl * a.scale, O.G["car"], O.G["drs"])
    json.dump({"raceline": rl.tolist()}, open(a.out + "_rl.json", "w"))
    print(f"[pol] done: raw {res.fun:.3f}s (start {f0:.3f}), smoothed {r['lap']:.3f}s, viol {viol:.3f}, {res.message}", flush=True)


if __name__ == "__main__":
    main()
