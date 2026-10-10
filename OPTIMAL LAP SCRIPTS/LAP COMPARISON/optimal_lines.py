"""Road + racing lines for OPTIMAL x QUALI comparisons.

Every optimal-lap build leaves a recipe:  F1_Pipeline_Assets/tracks/<slug>_lapcomp.json
  {"track_name", "outline", "raceline", "zoom",
   "optimiser": {"script", "env", "mirror", "cda", "cl", "margin", "args": [...]}}   (paths relative to ROOT)
"optimiser" is the exact command that produced the shipped line, minus --cda/--cl/--margin/--out.

P1 drives the shipped line. Each other car gets the SAME optimiser re-run with a small setup change
(cda/cl -/+3/4 %, wall margin +/- delta), auto-tuned so its mean lateral gap to the shipped line is ~1 %
of the road width, with a cap on the single worst spot (no corner may swing). Lines are cached per
shipped-line hash, so re-renders are instant and a new optimal lap invalidates them automatically.
"""
import hashlib, json, os, shutil, subprocess, sys
import numpy as np
from scipy.spatial import cKDTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
TRACKS = os.path.join(ROOT, "F1_Pipeline_Assets", "tracks")
PYTHON = r"C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
TARGET_PCT = 1.0          # mean lateral gap / road width, %
MAX_GAP_FRAC = 0.15
RUN_TIMEOUT_S = 15 * 60   # one optimiser run normally takes 2-5 min       # worst single spot <= 15 % of road width (Singapore: 1.5 m on 10 m)


def slug(event_name):
    return event_name.strip().lower().replace(" ", "_")


def _abs(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def load_recipe(event_name, log=print):
    s = slug(event_name)
    rp = os.path.join(TRACKS, s + "_lapcomp.json")
    if os.path.exists(rp):
        r = json.load(open(rp, encoding="utf-8"))
        r["outline"], r["raceline"] = _abs(r["outline"]), _abs(r["raceline"])
        r["slug"] = s
        return r
    ol, rl = os.path.join(TRACKS, s + "_outline.json"), os.path.join(TRACKS, s + "_raceline.json")
    if os.path.exists(ol) and os.path.exists(rl):
        log(f"WARNING: no {s}_lapcomp.json recipe -> road + line found, but no optimiser recipe: "
            f"ALL cars will share the shipped line.")
        return {"track_name": event_name, "outline": ol, "raceline": rl, "zoom": 28.0, "slug": s}
    raise FileNotFoundError(f"No optimal lap for '{event_name}': expected {rp} (or {s}_outline.json + "
                            f"{s}_raceline.json). Produce the optimal lap first.")


def road_width(outline_path):
    o = json.load(open(outline_path, encoding="utf-8"))
    d, _ = cKDTree(np.array(o["inner"], float)).query(np.array(o["outer"], float))
    return float(np.median(d))


def line_gap(ref_pts, pts):
    """Distance from every point of pts to the closed polyline ref_pts."""
    P0 = np.asarray(ref_pts, float); d = np.roll(P0, -1, 0) - P0; dd = np.maximum((d * d).sum(1), 1e-12)
    near = cKDTree(P0).query(pts, k=4)[1]
    best = np.full(len(pts), np.inf)
    for j in range(near.shape[1]):
        for back in (0, 1):
            i = (near[:, j] - back) % len(P0)
            t = np.clip(((pts - P0[i]) * d[i]).sum(1) / dd[i], 0, 1)
            best = np.minimum(best, np.linalg.norm(P0[i] + t[:, None] * d[i] - pts, axis=1))
    return best


def _length(P):
    return float(np.linalg.norm(np.roll(P, -1, 0) - P, axis=1).sum())


def _launch(opt, k, cda, cl, margin, out_stem, workers):
    env = dict(os.environ); env.update({kk: str(v) for kk, v in opt.get("env", {}).items()})
    args = [a if not a.endswith((".json", ".npy", ".py")) else _abs(a) for a in opt["args"]]
    cmd = [PYTHON, _abs(opt["script"])] + args + ["--cda", f"{cda:.4f}", "--cl", f"{cl:.4f}",
                                                   "--margin", f"{margin:.3f}", "--workers", str(workers),
                                                   "--out", out_stem]
    return subprocess.Popen(cmd, env=env, cwd=ROOT, stdin=subprocess.DEVNULL,
                            stdout=open(out_stem + ".log", "w"), stderr=subprocess.STDOUT)


def variant_lines(recipe, n_variants, log=print):
    """Returns n_variants raceline json paths (outline frame), one per non-reference car."""
    if n_variants <= 0:
        return []
    opt = recipe.get("optimiser")
    if not opt:
        return [recipe["raceline"]] * n_variants
    ref = np.array(json.load(open(recipe["raceline"], encoding="utf-8"))["raceline"], float)
    W = road_width(recipe["outline"])
    h = hashlib.sha1(open(recipe["raceline"], "rb").read() + json.dumps(opt, sort_keys=True).encode()).hexdigest()[:10]
    cdir = os.path.join(HERE, "lines", recipe["slug"], h); os.makedirs(cdir, exist_ok=True)
    workers = max(2, (os.cpu_count() or 4) // max(1, n_variants))
    out = [None] * n_variants
    todo = []
    for k in range(1, n_variants + 1):
        final = os.path.join(cdir, f"var{k}.json")
        if os.path.exists(final):
            m = json.load(open(final + ".meta.json"))
            log(f"  line var{k}: cached (gap mean {m['mean_m']:.2f} m = {m['pct']:.1f}%, max {m['max_m']:.2f} m)")
            out[k - 1] = final
        else:
            sign = 1 if k % 2 else -1; mag = 1.0 + 0.5 * ((k - 1) // 2)
            todo.append(dict(k=k, sign=sign, tgt=TARGET_PCT * mag, delta=0.04 * mag, best=None, final=final))
    for attempt in range(3):
        live = [v for v in todo if v["best"] is None or not v["best"]["ok"]]
        if not live:
            break
        procs = []
        for v in live:
            margin = max(0.10, opt["margin"] + v["sign"] * v["delta"])
            cda = opt["cda"] * (1 - 0.03 * v["sign"]); cl = opt["cl"] * (1 - 0.04 * v["sign"])
            stem = os.path.join(cdir, f"var{v['k']}_try{attempt}")
            log(f"  line var{v['k']}: optimiser run {attempt + 1} (margin {margin:.3f}, cda {cda:.3f}, cl {cl:.3f}) ...")
            procs.append((v, stem, margin, _launch(opt, v["k"], cda, cl, margin, stem, workers)))
        for v, stem, margin, p in procs:
            try:
                p.wait(timeout=RUN_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                log(f"  line var{v['k']}: optimiser run stuck > {RUN_TIMEOUT_S // 60} min -> killed"); p.wait()
            if p.returncode != 0 or not os.path.exists(stem + "_rl.json"):
                log(f"  line var{v['k']}: optimiser FAILED (see {stem}.log)"); v["delta"] *= 0.6; continue
            pts = np.array(json.load(open(stem + "_rl.json"))["raceline"], float)
            if opt.get("mirror"):
                pts = pts * [-1.0, 1.0]
            g = line_gap(ref, pts); pct = 100 * g.mean() / W
            ok_max = g.max() <= MAX_GAP_FRAC * W
            ok = ok_max and 0.6 * v["tgt"] <= pct <= 1.5 * v["tgt"]
            cand = dict(pts=pts, mean_m=float(g.mean()), max_m=float(g.max()), pct=float(pct), ok=ok,
                        margin=margin, len_pct=100 * (_length(pts) - _length(ref)) / _length(ref), ok_max=ok_max)
            log(f"  line var{v['k']}: gap mean {g.mean():.2f} m = {pct:.1f}% of {W:.1f} m road, max {g.max():.2f} m"
                f" -> {'OK' if ok else 'retune'}")
            if v["best"] is None or (cand["ok_max"] and (not v["best"]["ok_max"] or
                                     abs(cand["pct"] - v["tgt"]) < abs(v["best"]["pct"] - v["tgt"]))):
                v["best"] = cand
            v["delta"] *= 0.6 if not ok_max else float(np.clip(v["tgt"] / max(pct, 1e-3), 0.4, 3.0))
    for v in todo:
        b = v["best"]
        if b is None or not b["ok_max"]:
            log(f"  line var{v['k']}: no safe variant -> uses the shipped line"); out[v["k"] - 1] = recipe["raceline"]; continue
        json.dump({"raceline": b["pts"].tolist()}, open(v["final"], "w"))
        json.dump({k: b[k] for k in ("mean_m", "max_m", "pct", "margin", "len_pct")}, open(v["final"] + ".meta.json", "w"))
        out[v["k"] - 1] = v["final"]
    return out


def seed_cache(recipe, k, line_json, meta):
    """Register an already-optimised variant (used once to keep the Singapore SQ line)."""
    opt = recipe["optimiser"]
    h = hashlib.sha1(open(recipe["raceline"], "rb").read() + json.dumps(opt, sort_keys=True).encode()).hexdigest()[:10]
    cdir = os.path.join(HERE, "lines", recipe["slug"], h); os.makedirs(cdir, exist_ok=True)
    shutil.copy(line_json, os.path.join(cdir, f"var{k}.json"))
    json.dump(meta, open(os.path.join(cdir, f"var{k}.json.meta.json"), "w"))
