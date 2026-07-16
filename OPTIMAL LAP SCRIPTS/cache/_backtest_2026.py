"""Leave-one-out back-test: THE PROOF that the pre-FP1 calibration works.

For each SVG-ready track with real 2026 data:
  1. fit the transfer WITHOUT that track       (_transfer_2026.py --exclude T)
  2. predict its targets from its 2025 ref     (_predict_track.py)
  3. autofit cda/cl to those targets           (_autofit_2026.py, 2025 anchor)
  4. score the fitted sim against the track's REAL 2026 lap it never saw.

Scoring rules (pre-registered in the plan/Task-4 notes BEFORE results existed):
  - speed-trace corr (aligned common grid)      >= 0.94
  - lap rail                                    lap > t25 + 0.8 s   (always)
  - lap band     Q tracks: [t26_real - 1.5, t26_real]
                 FP1 tracks: [t26_fp1 - 3.5, t26_fp1 - 1.0]  (non-push refs)
  - top speed    Q tracks: |err| <= max(5, 2*sd_loo(vtop_delta))
                 FP1 tracks: informational only (real FP1 tops are lifted)
  - corners (median of sim-vs-real2026 at real corner spots, +-1.5% windows)
                 Q tracks: |median| <= 5, worst |err| <= 12
                 FP1 tracks: median in [-5, +15] (optimal >= practice pace)

Usage:
  python cache/_backtest_2026.py [--tracks canada,catalunya,austria,silverstone]
                                 [--skip-fit]   # rescore existing autofit csvs

Output: cache/backtest_report.md + cache/backtest_<slug>.png
Spec: docs/2026-07-15-prefp1-universal-calibration-design.md §3.5
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _track_registry import (  # noqa: E402
    REPO_ROOT, TRACKS, align_pair, corner_minima, load_ref,
)

PYTHON = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TRACKS = ["canada", "catalunya", "austria", "silverstone"]
VTOP_PCTL = 99.5
WINDOW_FRAC = 0.015
CORR_MIN = 0.94
LAP_RAIL_S = 0.8


def run(cmd: list[str], tag: str) -> bool:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    sys.stdout.write(r.stdout[-1500:])
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-1500:])
        print(f"[backtest] {tag} FAILED rc={r.returncode}")
        return False
    return True


def window_min(frac: np.ndarray, v: np.ndarray, f0: float) -> float:
    d = np.abs(frac - f0)
    d = np.minimum(d, 1.0 - d)
    w = d <= WINDOW_FRAC
    return float(np.min(v[w])) if np.any(w) else float(np.min(v))


def score_track(slug: str, autofit: dict, loo_transfer: dict) -> dict:
    spec = TRACKS[slug]
    kind = spec["kind26"]
    s_sim, v_sim, lap_sim = load_ref(os.path.join(REPO_ROOT, autofit["csv"]))
    s26, v26, t26 = load_ref(spec["csv26"])
    _, _, t25 = load_ref(spec["csv25"])
    sg, v_sim_g, v26_g, shift = align_pair(s_sim, v_sim, s26, v26, spec["length_m"])
    frac_g = sg / spec["length_m"]
    corr = float(np.corrcoef(v_sim_g, v26_g)[0, 1])

    vtop_sim = float(np.percentile(v_sim, VTOP_PCTL))
    vtop_26 = float(np.percentile(v26, VTOP_PCTL))
    top_err = vtop_sim - vtop_26
    sd_loo = float(loo_transfer["vtop_delta_kmh"]["sd"])
    top_band = max(5.0, 2.0 * sd_loo)

    corners = []
    for (cs, cv) in corner_minima(sg, v26_g):
        f0 = cs / spec["length_m"]
        sv = window_min(frac_g, v_sim_g, f0)
        corners.append(dict(s_frac=round(f0, 4), real=round(cv, 1),
                            sim=round(sv, 1), err=round(sv - cv, 1)))
    errs = np.array([c["err"] for c in corners])
    c_med = float(np.median(errs))
    c_worst = float(errs[np.argmax(np.abs(errs))])

    lap_lo, lap_hi = ((t26 - 1.5, t26) if kind == "Q" else (t26 - 3.5, t26 - 1.0))
    checks = dict(
        corr=(corr >= CORR_MIN, f"{corr:.3f} (>= {CORR_MIN})"),
        lap_rail=(lap_sim > t25 + LAP_RAIL_S,
                  f"{lap_sim:.2f}s > {t25 + LAP_RAIL_S:.2f}s"),
        lap_band=(lap_lo <= lap_sim <= lap_hi,
                  f"{lap_sim:.2f}s in [{lap_lo:.2f},{lap_hi:.2f}] ({kind} ref)"),
        top=((abs(top_err) <= top_band) if kind == "Q" else None,
             f"{top_err:+.1f} km/h (band +-{top_band:.1f}"
             f"{', informational: FP1 ref' if kind != 'Q' else ''})"),
        corners=((abs(c_med) <= 5.0 and abs(c_worst) <= 12.0) if kind == "Q"
                 else (-5.0 <= c_med <= 15.0),
                 f"median {c_med:+.1f}, worst {c_worst:+.1f}"
                 f"{' (FP1 rule [-5,+15] on median)' if kind != 'Q' else ''}"),
    )
    n_fail = sum(1 for ok, _ in checks.values() if ok is False)
    return dict(slug=slug, kind=kind, lap_sim=lap_sim, t25=t25, t26=t26,
                cda=autofit["cda"], cl=autofit["cl"], rho=autofit["rho"],
                fit_converged=autofit["converged"], corr=corr,
                vtop_sim=vtop_sim, vtop_26=vtop_26, top_err=top_err,
                corners=corners, c_med=c_med, c_worst=c_worst,
                checks=checks, n_fail=n_fail,
                grid=(sg, v_sim_g, v26_g))


def overlay_png(sc: dict, out_png: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sg, v_sim_g, v26_g = sc["grid"]
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(sg, v26_g, lw=1.2, color="#c00",
            label=f"real 2026 {sc['kind']} ({sc['t26']:.2f}s)")
    ax.plot(sg, v_sim_g, lw=1.2, color="#06c",
            label=f"pre-FP1 sim ({sc['lap_sim']:.2f}s, cda={sc['cda']:.2f}, "
                  f"cl={sc['cl']:.2f})")
    for c in sc["corners"]:
        ax.annotate(f"{c['err']:+.0f}", (c["s_frac"] * sg[-1], c["real"]),
                    fontsize=7, color="#333")
    ax.set_title(f"{sc['slug']} leave-one-out: sim (never saw 2026 data) vs real "
                 f"2026 — corr {sc['corr']:.3f}")
    ax.set_xlabel("distance [m]"); ax.set_ylabel("speed [km/h]")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out_png, dpi=90); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks", default=",".join(DEFAULT_TRACKS))
    ap.add_argument("--skip-fit", action="store_true",
                    help="rescore existing cache/autofit_<slug>*.json without refitting")
    ap.add_argument("--report", default=os.path.join(HERE, "backtest_report.md"))
    ap.add_argument("--label", default="v1")
    args = ap.parse_args()
    slugs = [s.strip() for s in args.tracks.split(",") if s.strip()]

    scores = []
    for slug in slugs:
        tr_path = os.path.join(HERE, f"transfer_loo_{slug}.json")
        pd_path = os.path.join(HERE, f"predicted_loo_{slug}.json")
        if not args.skip_fit:
            ok = (run([PYTHON, os.path.join(HERE, "_transfer_2026.py"),
                       "--exclude", slug, "--out", tr_path, "--no-plots"],
                      f"transfer[{slug}]")
                  and run([PYTHON, os.path.join(HERE, "_predict_track.py"),
                           "--track", slug, "--transfer", tr_path, "--out", pd_path],
                          f"predict[{slug}]")
                  and run([PYTHON, os.path.join(HERE, "_autofit_2026.py"),
                           "--track", slug, "--targets", pd_path],
                          f"autofit[{slug}]"))
            if not ok:
                print(f"[backtest] {slug}: PIPELINE FAILED - no score")
                continue
        with open(os.path.join(HERE, f"autofit_{slug}.json"), encoding="utf-8") as f:
            autofit = json.load(f)
        with open(tr_path, encoding="utf-8") as f:
            loo = json.load(f)
        sc = score_track(slug, autofit, loo)
        overlay_png(sc, os.path.join(HERE, f"backtest_{slug}.png"))
        scores.append(sc)
        print(f"[backtest] {slug}: fails={sc['n_fail']} " +
              " ".join(f"{k}={'PASS' if ok else 'info' if ok is None else 'FAIL'}"
                       for k, (ok, _) in sc["checks"].items()))

    lines = [f"\n\n## Backtest {args.label} — leave-one-out, "
             f"{len(scores)} tracks\n",
             "| track | ref | cda | cl | rho | lap sim | real | corr | "
             "top err | corner med | worst | fails |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for sc in scores:
        lines.append(
            f"| {sc['slug']} | {sc['kind']} | {sc['cda']:.3f} | {sc['cl']:.2f} | "
            f"{sc['rho']:.3f} | {sc['lap_sim']:.2f} | {sc['t26']:.2f} | "
            f"{sc['corr']:.3f} | {sc['top_err']:+.1f} | {sc['c_med']:+.1f} | "
            f"{sc['c_worst']:+.1f} | **{sc['n_fail']}** |")
    lines.append("")
    for sc in scores:
        lines.append(f"### {sc['slug']} ({args.label})")
        for k, (ok, txt) in sc["checks"].items():
            tag = "PASS" if ok else ("INFO" if ok is None else "FAIL")
            lines.append(f"- {tag} `{k}`: {txt}")
        lines.append("- corners (sim vs real 2026): " + ", ".join(
            f"{c['s_frac']:.3f}:{c['err']:+.0f}" for c in sc["corners"]))
        lines.append("")
    with open(args.report, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    total_fails = sum(sc["n_fail"] for sc in scores)
    print(f"[backtest] {args.label}: total FAILs across {len(scores)} tracks: "
          f"{total_fails} -> report {args.report}")
    return 0 if total_fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
