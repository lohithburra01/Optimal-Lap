"""Score the 2017-era car vs real 2018 Q telemetry on 6 tracks (shape + amplitude).
params JSON: shared knobs + per-track {"track": {slug: {cl, cda}}}. Prints a table, returns totals."""
import json, os, sys, time
import numpy as np
from concurrent.futures import ProcessPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.dirname(HERE); ROOT = os.path.dirname(CACHE)
sys.path.insert(0, HERE); sys.path.insert(0, CACHE)
import _track_registry as R
SLUGS = ["canada", "austria", "silverstone", "monza", "bahrain", "spa"]
DRS = json.load(open(os.path.join(HERE, "drs_2018.json")))
_POOL = None
GRID = np.linspace(0, 1, 1000, endpoint=False)

def ref(slug):
    s, v, t = R.load_ref(os.path.join(ROOT, "F1_Pipeline_Assets", "exports", f"reference_2018_{slug}_q.csv"))
    return s / s.max(), v, t

def warp(vs, vr):
    """Corner-matched alignment: pair sim/real speed minima (within 3% of lap), then map the
    sim distance axis piecewise-linearly onto the real one (removes SVG-vs-GPS length drift)."""
    ms = R.corner_minima(GRID * 1000, vs); mr = R.corner_minima(GRID * 1000, vr)
    pairs, _ = R.pair_minima(mr, ms, 1000.0, tol_frac=0.03)
    kr, ks = [0.0], [0.0]
    for r_s, _, s_s, _ in pairs:
        if r_s / 1000 > kr[-1] and s_s / 1000 > ks[-1]:
            kr.append(r_s / 1000); ks.append(s_s / 1000)
    kr.append(1.0); ks.append(1.0)
    f_sim = np.interp(GRID, kr, ks)
    return np.interp(f_sim, GRID, vs, period=1), len(kr) - 2

def one(args):
    slug, car = args
    import sim_2017_car as C
    rl = np.asarray(json.load(open(os.path.join(CACHE, f"autofit_{slug}_rl.json")))["raceline"], float)[:, :2]
    r = C.simulate(rl, car, DRS[slug])
    fs = r["arc"] / r["L"]; vs = np.interp(GRID, fs, r["v"] * 3.6, period=1)
    fr, vr, tr = ref(slug); vr = np.interp(GRID, fr, vr)
    vs_raw = vs; vs, npair = warp(vs, vr)
    return dict(slug=slug, lap=r["lap"], real=tr, top_s=vs.max(), top_r=vr.max(),
                rmse=float(np.sqrt(np.mean((vs - vr) ** 2))), bias=float(np.mean(vs - vr)),
                corr=float(np.corrcoef(vs, vr)[0, 1]), npair=npair,
                rmse_raw=float(np.sqrt(np.mean((vs_raw - vr) ** 2))), vs=vs.tolist(), vr=vr.tolist())

def evaluate(params, slugs=SLUGS, quiet=False):
    import sim_2017_car as C
    jobs = []
    for s in slugs:
        car = dict(C.DEFAULT_CAR); car.update({k: v for k, v in params.items() if k != "track"})
        car.update(params.get("track", {}).get(s, {}))
        car["rho"] = R.rho_isa(R.TRACKS[s].get("altitude_m", 0.0) or 0.0)
        jobs.append((s, car))
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor(6)
    res = list(_POOL.map(one, jobs))
    if not quiet:
        print(f"{'track':12s} {'sim':>8s} {'real':>8s} {'d%':>6s} {'top s/r':>11s} {'rmse':>5s} {'raw':>5s} {'bias':>6s} {'corr':>6s} pairs")
        for r in res:
            print(f"{r['slug']:12s} {r['lap']:8.3f} {r['real']:8.3f} {100*(r['lap']/r['real']-1):6.2f} "
                  f"{r['top_s']:5.0f}/{r['top_r']:<5.0f} {r['rmse']:5.1f} {r['rmse_raw']:5.1f} {r['bias']:6.1f} {r['corr']:6.3f} {r['npair']}")
    return res

if __name__ == "__main__":
    p = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else {}
    t0 = time.time(); res = evaluate(p); print(f"[{time.time()-t0:.0f}s]")
    json.dump(res, open(os.path.join(HERE, "last_eval.json"), "w"))
