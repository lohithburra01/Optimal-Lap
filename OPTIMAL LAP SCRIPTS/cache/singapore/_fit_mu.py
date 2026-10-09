"""Fit the Singapore slow-corner grip knob SG_MU_SCALE (MU_LAT scale, cache/_sim_singapore.py): outer secant on
the autofit's low-speed residual median (corners v25 < 130 vs predicted 2026 targets) -> 0; each evaluation is a
full unchanged autofit (cda->vtop, cl->v25>=130 tier, lap rail). Writes cache/singapore/fit_mu.json."""
import os, sys, json, subprocess
H = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.dirname(H); ROOT = os.path.dirname(CACHE)
def run(mu):
    env = dict(os.environ, SG_MU_SCALE=f"{mu:.4f}")
    with open(os.path.join(CACHE, "_autofit_singapore.log"), "w") as f:
        subprocess.run([sys.executable, os.path.join(CACHE, "_autofit_singapore.py")], env=env, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    r = json.load(open(os.path.join(CACHE, "autofit_singapore.json")))
    print(f"[mu] {mu:.4f}: cda {r['cda']:.3f} cl {r['cl']:.3f} lap {r['lap_s']:.2f} rail {r['rail_ok']} conv {r['converged']} "
          f"hs {r['hs_median_err_kmh']} ls {r['ls_median_err_kmh']}", flush=True)
    return r
hist = []
mu = float(sys.argv[1]) if len(sys.argv) > 1 else 0.85
for it in range(6):
    r = run(mu); hist.append((mu, r["ls_median_err_kmh"], r))
    if abs(r["ls_median_err_kmh"]) < 1.5 and r["rail_ok"]: break
    if len(hist) == 1: mu = mu * (1 - r["ls_median_err_kmh"] / 80.0 * 2)       # v ~ sqrt(mu) at ~80 km/h
    else:
        (m0, e0, _), (m1, e1, _) = hist[-2], hist[-1]
        mu = m1 - e1 * (m1 - m0) / (e1 - e0) if e1 != e0 else m1 * 0.97
    mu = min(max(mu, 0.55), 1.1)
best = min(hist, key=lambda h: (not h[2]["rail_ok"], abs(h[1])))
json.dump(dict(mu_scale=best[0], autofit=best[2], history=[(h[0], h[1]) for h in hist]), open(os.path.join(H, "fit_mu.json"), "w"), indent=1)
print("[mu] best", best[0], "ls", best[1], "(re-run autofit at the best mu if it was not the last evaluation)")
