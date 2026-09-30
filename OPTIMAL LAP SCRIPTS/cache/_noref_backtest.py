"""No-reference (no 2025 lap of this track) calibration backtest.

For each fitted track: run the 2026 sim with the leave-one-out MEDIAN cda/cl of
the other tracks' autofit results (+ this track's ISA rho), then score the lap
against the track's real 2026 lap (csv26). This measures how well a track with
NO reference data (Sepang 2026) can be predicted from fleet knobs alone.
Usage: python cache/_noref_backtest.py [--jobs 4]
"""
import argparse, json, os, subprocess, sys, statistics as st
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _track_registry as R

FITTED = ["austria", "canada", "catalunya", "hungary", "silverstone", "spa", "zandvoort"]
PY = sys.executable
OUT = os.path.join(HERE, "noref_backtest")

def knobs(slug):
    return json.load(open(os.path.join(HERE, f"autofit_{slug}.json")))

def run(slug):
    others = [knobs(s) for s in FITTED if s != slug]
    cda = st.median(o["cda"] for o in others); cl = st.median(o["cl"] for o in others)
    rho = knobs(slug)["rho"]; spec = R.TRACKS[slug]
    csv = os.path.join(OUT, f"{slug}.csv")
    cmd = [PY, os.path.join(ROOT, "sim_2026_lap.py"), "--outline", spec["outline"],
           "--raceline-out", os.path.join(OUT, f"{slug}_rl.json"), "--csv-out", csv,
           "--reference-csv", spec["csv25"], "--inset", "0",
           "--cda", f"{cda:.4f}", "--cl", f"{cl:.4f}", "--rho", f"{rho:.4f}"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        return dict(track=slug, error=r.stderr[-400:])
    _, _, lap = R.load_ref(csv)
    _, _, real = R.load_ref(spec["csv26"])
    fit = knobs(slug)["lap_s"]
    return dict(track=slug, kind26=spec.get("kind26"), cda=round(cda, 4), cl=round(cl, 4),
                rho=rho, lap_noref=round(lap, 3), lap_fitted=fit, real26=round(real, 3),
                err_noref_s=round(lap - real, 3), err_noref_pct=round(100 * (lap / real - 1), 2),
                err_fitted_s=round(fit - real, 3))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args(); os.makedirs(OUT, exist_ok=True)
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(run, FITTED))
    for r in res: print(json.dumps(r))
    json.dump(res, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
