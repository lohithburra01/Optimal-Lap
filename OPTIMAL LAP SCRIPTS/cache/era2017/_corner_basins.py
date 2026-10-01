"""Per-corner basin search for the 2017 line (the one-knot optimiser gets trapped on the wide-entry
line; at Sepang T1 the inside-attack line is 0.16 s faster with the SAME car). For every corner
(curvature peak, R < 200 m): polish three starts in a window around it - current, entry on the INSIDE,
entry on the OUTSIDE - and keep the fastest. Car unchanged (friction circle, 2018-fitted knobs).
  python _corner_basins.py --init t1in_p2_knots.npy --out basins"""
import argparse, json, os, sys, time
import numpy as np
from concurrent.futures import ProcessPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import _opt_line_2017 as O


def polish(ex, k, active, steps=(2.0, 1.0, 0.5), max_sweeps=25):
    best = list(ex.map(O.cost, [k]))[0]
    for step in steps:
        for _ in range(max_sweeps):
            cands = []
            for i in active:
                for s in (step, -step):
                    c = k.copy(); c[i] += s; cands.append((i, s, c))
            res = list(ex.map(O.cost, [c for *_, c in cands], chunksize=2))
            imp = sorted((r, i, s) for (i, s, _), r in zip(cands, res) if r < best - 1e-4)
            if not imp: break
            chosen, used = [], set()
            for r, i, s in imp:
                if all(abs(i - j) >= 3 for j in used): chosen.append((i, s)); used.add(i)
            comb = k.copy()
            for i, s in chosen: comb[i] += s
            rc = list(ex.map(O.cost, [comb]))[0]
            if rc < imp[0][0]: k, best = comb, rc
            else: k = k.copy(); k[imp[0][1]] += imp[0][2]; best = imp[0][0]
    return k, best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=1.0074)
    ap.add_argument("--base", default="sepang_sat_base_rl.json"); ap.add_argument("--outline", default="sepang_sat_outline.json")
    ap.add_argument("--margin", type=float, default=0.3); ap.add_argument("--every", type=int, default=10)
    a = ap.parse_args(); rep = json.load(open(os.path.join(HERE, "sepang_2017_report.json")))
    O.setup(os.path.join(HERE, a.base), os.path.join(HERE, a.outline), rep["car"], rep["drs"], a.margin, a.every)
    O.G["scale"] = a.scale
    G = O.G; L = G["L"]; ka = G["arc"][G["kidx"]]; klo, khi = G["lo"][G["kidx"]], G["hi"][G["kidx"]]
    k = np.load(a.init)
    rl, _ = O.line_of(k); n = len(rl)
    # corners: curvature peaks of the current line, R < 200 m, >= 150 m apart
    st = 8; kap = np.zeros(n)
    for i in range(n):
        p0, p1, p2 = rl[i - st], rl[i], rl[(i + st) % n]
        u, v = p1 - p0, p2 - p1; kap[i] = 2 * (u[0] * v[1] - u[1] * v[0]) / (np.linalg.norm(u) * np.linalg.norm(v) * np.linalg.norm(p2 - p0))
    order = np.argsort(-np.abs(kap)); peaks = []
    for i in order:
        if abs(kap[i]) < 1 / 200: break
        if all(min(abs(G["arc"][i] - G["arc"][j]), L - abs(G["arc"][i] - G["arc"][j])) > 150 for j in peaks): peaks.append(i)
    peaks.sort(); print(f"[basin] {len(peaks)} corners at", [int(G["arc"][i]) for i in peaks], flush=True)
    def dist(x, c): d = (x - c) % L; return np.where(d > L / 2, d - L, d)   # signed arc offset from apex
    state = dict(G); t0 = time.time()
    with ProcessPoolExecutor(12, initializer=O.init, initargs=(state,)) as ex:
        lap0 = list(ex.map(O.cost, [k]))[0]; print(f"[basin] start lap {lap0:.3f}s", flush=True)
        for pi in peaks:
            ac = G["arc"][pi]; d = dist(ka, ac)
            win = [i for i in range(len(k)) if -260 <= d[i] <= 160]
            entry = (d >= -180) & (d <= -10)
            inside_lo = kap[pi] < 0                       # right-hander -> inside is the lo (-N) side
            starts = {"current": k.copy()}
            ki = k.copy(); ki[entry] = np.where(inside_lo, klo[entry] + 0.2, khi[entry] - 0.2); starts["inside"] = ki
            ko = k.copy(); ko[entry] = np.where(inside_lo, khi[entry] - 0.2, klo[entry] + 0.2); starts["outside"] = ko
            res = {nm: polish(ex, s, win) for nm, s in starts.items()}
            nm = min(res, key=lambda x: res[x][1])
            print(f"[basin] corner @{ac:6.0f} m ({'R' if inside_lo else 'L'}, R={1/abs(kap[pi]):.0f} m): "
                  + "  ".join(f"{x} {res[x][1]:.3f}" for x in res) + f"  -> {nm}  t {time.time()-t0:.0f}s", flush=True)
            k = res[nm][0]; np.save(a.out + "_knots.npy", k)
        lapf = list(ex.map(O.cost, [k]))[0]
    rl, viol = O.line_of(k)
    json.dump({"raceline": rl.tolist()}, open(a.out + "_rl.json", "w"))
    print(f"[basin] done: {lap0:.3f} -> {lapf:.3f}s raw, viol {viol:.3f}", flush=True)


if __name__ == "__main__":
    main()
