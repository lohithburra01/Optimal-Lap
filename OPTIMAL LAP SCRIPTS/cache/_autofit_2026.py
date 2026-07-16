"""Closed-loop fit of the two per-track knobs (--cda, --cl) so the sim hits
the PREDICTED 2026 targets. No human in the loop, no 2026 data touched.

  python cache/_autofit_2026.py --track spa [--targets cache/predicted_spa.json]
                                [--max-iters 4]

Knob -> objective mapping (nearly decoupled):
  CDA -> f1 = sim_vtop - vtop_target      (cube-law Newton step, then secant)
  CL  -> f2 = median(sim corner minima - targets) over the CL tier set
         tier 1: corners with v25 > 170 (downforce-dominated) if >= 2
         tier 2: corners with v25 >= 130 (aero still ~half the grip) if >= 2
         tier 3: all corners
Low-speed corners stay governed by global MU (frozen); their residual is
REPORTED, never fitted. The sim's start/finish anchor uses the 2025 ref
(pre-FP1 conditions - the 2026 csv is never read here).

Output: cache/autofit_<slug>.json + cache/autofit_<slug>_sim.csv
Spec: docs/2026-07-15-prefp1-universal-calibration-design.md §3.4
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _track_registry import REPO_ROOT, TRACKS, load_ref  # noqa: E402

PYTHON = sys.executable
SIM = os.path.join(REPO_ROOT, "sim_2026_lap.py")
VTOP_PCTL = 99.5
TOL_TOP = 2.0        # km/h
TOL_HS = 3.0         # km/h
LAP_RAIL_S = 0.8     # sim must be > t25 + this (2026 slower than 2025, always)
CDA_LIM = (0.45, 1.30)
CL_LIM = (3.00, 6.50)
MATCH_TOL_FRAC = 0.015


def run_sim(slug: str, spec: dict, cda: float, cl: float, rho: float,
            tag: str) -> tuple[str, str]:
    here = os.path.dirname(os.path.abspath(__file__))
    csv_out = os.path.join(here, f"autofit_{slug}_sim.csv")
    rl_out = os.path.join(here, f"autofit_{slug}_rl.json")
    cmd = [PYTHON, SIM,
           "--outline", spec["outline"],
           "--raceline-out", rl_out,
           "--csv-out", csv_out,
           "--reference-csv", spec["csv25"],   # 2025 anchor: pre-FP1 conditions
           "--inset", "0",
           "--cda", f"{cda:.4f}", "--cl", f"{cl:.4f}", "--rho", f"{rho:.4f}"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if r.returncode != 0:
        print(r.stdout[-2000:], file=sys.stderr)
        print(r.stderr[-2000:], file=sys.stderr)
        raise RuntimeError(f"sim failed for {slug} ({tag}) rc={r.returncode}")
    return csv_out, rl_out


def measure(csv_path: str, targets: dict) -> dict:
    """Score a sim lap against predicted corner targets.

    Each target corner's sim speed = MIN sim speed within a circular window
    of +-MATCH_TOL_FRAC around the target's s_frac. No minima detection, no
    pairing: a corner the sim takes flat-out yields a large POSITIVE error
    (carries far more speed than the real car), which is exactly the signal
    the CL fit needs. Braking-point shifts stay inside the window.
    """
    s, v, lap_s = load_ref(csv_path)
    total = float(s[-1] - s[0])
    frac = (s - s[0]) / total
    matched = []
    for c in targets["corners"]:
        d = np.abs(frac - c["s_frac"])
        d = np.minimum(d, 1.0 - d)                    # circular
        w = d <= MATCH_TOL_FRAC
        sim_v = float(np.min(v[w])) if np.any(w) else float(np.min(v))
        matched.append(dict(target=c, sim_v=round(sim_v, 1),
                            err=sim_v - c["v26_target_kmh"]))
    return dict(lap_s=lap_s, vtop=float(np.percentile(v, VTOP_PCTL)),
                corners=matched)


def cl_tier(corners: list[dict]) -> tuple[list[dict], str]:
    """CL objective set: downforce-dominated corners preferred, with fallbacks
    for tracks whose fast corners were flat-out in 2025 (no target > 170)."""
    t1 = [m for m in corners if m["target"]["v25_kmh"] > 170.0]
    if len(t1) >= 2:
        return t1, "v25>170"
    t2 = [m for m in corners if m["target"]["v25_kmh"] >= 130.0]
    if len(t2) >= 2:
        return t2, "v25>=130"
    return list(corners), "all"


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True, choices=sorted(TRACKS))
    ap.add_argument("--targets", default=None)
    ap.add_argument("--max-iters", type=int, default=4,
                    help="refinement sims after the first (total sims <= 1+max-iters)")
    args = ap.parse_args()

    spec = TRACKS[args.track]
    if not spec["outline"] or not os.path.exists(spec["outline"]):
        print(f"[autofit] ABORT: no outline for {args.track}", file=sys.stderr)
        return 2
    tpath = args.targets or os.path.join(here, f"predicted_{args.track}.json")
    with open(tpath, encoding="utf-8") as f:
        targets = json.load(f)
    rho = float(targets["rho"])
    vtop_t = float(targets["vtop_target_kmh"])

    t25 = float(targets["t25_s"])
    lap_rail = t25 + LAP_RAIL_S
    cda, cl = float(targets["cda0"]), float(targets["cl0"])
    hist = []           # (cda, cl, f1, f2)
    tier_name = "?"
    m = None
    for it in range(1 + args.max_iters):
        csv_out, _ = run_sim(args.track, spec, cda, cl, rho, f"iter{it}")
        m = measure(csv_out, targets)
        tier, tier_name = cl_tier(m["corners"])
        f1 = m["vtop"] - vtop_t
        f2 = float(np.median([x["err"] for x in tier])) if tier else 0.0
        hist.append((cda, cl, f1, f2))
        rail_flag = "" if m["lap_s"] > lap_rail else "  RAIL-VIOLATION"
        print(f"[autofit] {args.track} it{it}: cda={cda:.3f} cl={cl:.3f} "
              f"lap={m['lap_s']:.2f}s vtop={m['vtop']:.1f} (f1={f1:+.1f}) "
              f"tier[{tier_name}] f2={f2:+.1f}{rail_flag}")
        if abs(f1) <= TOL_TOP and abs(f2) <= TOL_HS:
            break
        if it == args.max_iters:
            break
        # --- CDA update: v_top ~ cda^(-1/3) Newton step, then secant ---
        if len(hist) >= 2 and abs(hist[-1][0] - hist[-2][0]) > 1e-4 \
                and abs(hist[-1][2] - hist[-2][2]) > 0.2:
            d = (hist[-1][2] - hist[-2][2]) / (hist[-1][0] - hist[-2][0])
            cda_new = cda - f1 / d
        else:
            cda_new = cda * (m["vtop"] / vtop_t) ** 3
        cda_new = float(np.clip(cda_new, cda * 0.75, cda * 1.25))
        cda = float(np.clip(cda_new, *CDA_LIM))
        # --- CL update: corner grip ~ aero share; bump then secant ---
        if len(hist) >= 2 and abs(hist[-1][1] - hist[-2][1]) > 1e-3 \
                and abs(hist[-1][3] - hist[-2][3]) > 0.2:
            d = (hist[-1][3] - hist[-2][3]) / (hist[-1][1] - hist[-2][1])
            cl_new = cl - f2 / d
        else:
            cl_new = cl - np.sign(f2) * 0.4          # first bump toward target
        cl_new = float(np.clip(cl_new, cl - 0.8, cl + 0.8))
        cl = float(np.clip(cl_new, *CL_LIM))

    f1 = hist[-1][2]
    f2 = hist[-1][3]
    rail_ok = m["lap_s"] > lap_rail
    conv = abs(f1) <= TOL_TOP and abs(f2) <= TOL_HS and rail_ok
    if not rail_ok:
        print(f"[autofit] RAIL VIOLATION: lap {m['lap_s']:.2f}s <= t25+{LAP_RAIL_S}"
              f" = {lap_rail:.2f}s — a 2026 lap CANNOT beat the 2025 pole "
              f"(line too smooth? see spec §3.6)", file=sys.stderr)
    ls = [x for x in m["corners"] if x["target"]["v25_kmh"] < 130.0]
    ls_med = float(np.median([x["err"] for x in ls])) if ls else None
    out = dict(track=args.track, cda=round(cda, 4), cl=round(cl, 4),
               rho=round(rho, 4), iters=len(hist), converged=bool(conv),
               rail_ok=bool(rail_ok), lap_rail_s=round(lap_rail, 3),
               top_err_kmh=round(f1, 2), hs_median_err_kmh=round(f2, 2),
               cl_tier=tier_name,
               ls_median_err_kmh=None if ls_med is None else round(ls_med, 2),
               lap_s=round(m["lap_s"], 3),
               targets=os.path.basename(tpath),
               csv=f"cache/autofit_{args.track}_sim.csv",
               corners=[dict(s_frac=x["target"]["s_frac"],
                             v25=x["target"]["v25_kmh"],
                             v26_target=x["target"]["v26_target_kmh"],
                             sim_v=x["sim_v"], err=round(x["err"], 1))
                        for x in m["corners"]],
               history=[dict(cda=round(a, 4), cl=round(b, 4),
                             f1=round(c, 2), f2=round(d, 2))
                        for a, b, c, d in hist])
    opath = os.path.join(here, f"autofit_{args.track}.json")
    with open(opath, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"[autofit] {args.track}: converged={conv} cda={cda:.3f} cl={cl:.3f} "
          f"lap={m['lap_s']:.2f}s  low-speed residual median="
          f"{'n/a' if ls_med is None else format(ls_med, '+.1f')} (reported, not fitted)")
    print(f"[autofit] wrote {opath}")
    return 0 if conv else 1


if __name__ == "__main__":
    sys.exit(main())
