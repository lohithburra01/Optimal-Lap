"""GT3 (Portimao) copy of cache/bahrain/_opt_line_2026.py: cost = sim_gt3_car lap; 4 workers, below-normal priority.
Minimum-LAP-TIME racing line for the 2026 car (sim_2026_lap physics, imported, never edited).
Reuses the knot/corridor machinery of cache/era2017/_opt_line_2017.py (setup/line_of) with the
2026 car's simulate_lap as the cost (bang-bang lap, same as the autofit's raw lap).
  python cache/bahrain/_opt_line_2026.py --base <rl.json> --outline <outline.json> --cda A --cl B --rho C --out X"""
import argparse, contextlib, io, json, os, sys, time
import numpy as np
from concurrent.futures import ProcessPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "cache", "era2017")); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "cache", "bahrain"))
import _opt_line_2017 as O

KN = {}


def init(state, knobs):
    O.init(state); KN.update(knobs)
    try:
        import psutil; psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception: pass


def lap_of(rl):
    import sim_gt3_car as GT
    with contextlib.redirect_stdout(io.StringIO()):
        return float(GT.C.simulate(rl, dict(GT.GT3_CAR, **KN), [], smooth=False)["lap"])


def cost(k):
    rl, viol = O.line_of(np.asarray(k))
    try: lap = lap_of(rl)
    except Exception: return 1e6
    k = np.asarray(k); d2 = np.roll(k, -1) - 2 * k + np.roll(k, 1)
    c = lap + 2.0 * viol + O.G.get("smooth_w", 0.0) * float((d2 ** 2).sum())
    if O.G.get("apex_w", 0.0) > 0:   # inside-apex touch: penalise each corner's min gap to the inside bound
        import _apex_gaps as AG
        off = np.einsum("ij,ij->i", rl - O.G["P"], O.G["N"])
        g = AG.apex_terms(off, O.G["apex_pk"], O.G["apex_kap"], O.G["apex_win"])
        c += O.G["apex_w"] * float((np.maximum(g - O.G["apex_tol"], 0) ** 2).sum())
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--outline", required=True)
    ap.add_argument("--cl", type=float, required=True)
    ap.add_argument("--margin", type=float, default=0.5); ap.add_argument("--every", type=int, default=12)
    ap.add_argument("--steps", default="2,1,0.5,0.25"); ap.add_argument("--max-sweeps", type=int, default=30)
    ap.add_argument("--smooth-w", type=float, default=0.006); ap.add_argument("--init-knots", default=None)
    ap.add_argument("--workers", type=int, default=4); ap.add_argument("--out", required=True)
    ap.add_argument("--time-test", action="store_true")
    ap.add_argument("--apex-w", type=float, default=0.0, help="s/m^2 penalty on each corner's inside-apex gap")
    ap.add_argument("--apex-tol", type=float, default=0.15); ap.add_argument("--apex-win", type=int, default=20)
    a = ap.parse_args()
    O.setup(a.base, a.outline, None, None, a.margin, a.every); O.G["smooth_w"] = a.smooth_w
    K = len(O.G["kidx"]); k = np.load(a.init_knots) if a.init_knots else np.zeros(K)
    if a.apex_w > 0:
        import _apex_gaps as AG
        pk, kap = AG.corners(O.line_of(k)[0], O.G["arc"], O.G["L"])
        O.G.update(apex_w=a.apex_w, apex_tol=a.apex_tol, apex_win=a.apex_win, apex_pk=pk, apex_kap=kap)
        print(f"[opt26] apex penalty on {len(pk)} corners at", [int(O.G["arc"][i]) for i in pk], flush=True)
    knobs = dict(cl=a.cl); state = dict(O.G)
    print(f"[opt26] {len(O.G['P'])} stations, {K} knots, corridor median {np.median(O.G['hi']-O.G['lo']):.1f} m", flush=True)
    if a.time_test:
        init(state, knobs); t = time.time(); print(f"[opt26] lap {cost(k):.3f}s in {time.time()-t:.2f}s"); return
    t0 = time.time()
    with ProcessPoolExecutor(a.workers, initializer=init, initargs=(state, knobs)) as ex:
        best = list(ex.map(cost, [k]))[0]; base = best; print(f"[opt26] base {best:.3f}s", flush=True)
        for step in map(float, a.steps.split(",")):
            for sw in range(a.max_sweeps):
                cands = [(i, s) for i in range(K) for s in (step, -step)]
                cs = []
                for i, s in cands: c = k.copy(); c[i] += s; cs.append(c)
                res = list(ex.map(cost, cs, chunksize=4))
                imp = sorted((r, i, s) for (i, s), r in zip(cands, res) if r < best - 1e-4)
                if not imp: break
                chosen, used = [], set()
                for r, i, s in imp:
                    if all(abs(i - j) >= 3 and abs(i - j) <= K - 3 for j in used): chosen.append((i, s)); used.add(i)
                comb = k.copy()
                for i, s in chosen: comb[i] += s
                rc = list(ex.map(cost, [comb]))[0]
                if rc < imp[0][0]: k, best, nacc = comb, rc, len(chosen)
                else: k = k.copy(); k[imp[0][1]] += imp[0][2]; best = imp[0][0]; nacc = 1
                print(f"[opt26] step {step} sweep {sw}: {best:.3f}s (-{base-best:.3f}) acc {nacc} t {time.time()-t0:.0f}s", flush=True)
                np.save(a.out + "_knots.npy", k)
    rl, viol = O.line_of(k); np.save(a.out + "_knots.npy", k)
    if a.apex_w > 0:
        off = np.einsum("ij,ij->i", rl - O.G["P"], O.G["N"]); g = AG.apex_terms(off, O.G["apex_pk"], O.G["apex_kap"], a.apex_win)
        init(state, knobs); print("[opt26] apex gaps", " ".join(f"{O.G['arc'][i]:.0f}:{x:.2f}" for i, x in zip(O.G["apex_pk"], g)), f"pure lap {lap_of(rl):.3f}s", flush=True)
    json.dump({"raceline": rl.tolist()}, open(a.out + "_rl.json", "w"))
    print(f"[opt26] done: {best:.3f}s (base {base:.3f}), viol {viol:.3f} m", flush=True)


if __name__ == "__main__":
    main()
