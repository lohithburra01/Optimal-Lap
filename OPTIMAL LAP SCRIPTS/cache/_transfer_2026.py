"""Fit the empirical 2025->2026 transfer from real reference-lap pairs.

The transfer is a property of the regs change, not of any single track:
  - r(v25) = v26/v25 at matched corner minima (monotone non-increasing in v25)
  - lap-time delta percent  (T26-T25)/T25
  - top-speed delta km/h    (v_top26 - v_top25)

QUALIFYING pairs anchor every fit. FP1-sourced 2026 refs are non-push laps:
they are evaluated against the fitted curve (residual report) but NEVER fitted.

Usage:
  python cache/_transfer_2026.py [--exclude SLUG] [--out cache/transfer_2026.json]
                                 [--no-plots]

Output JSON schema (consumed by _predict_track.py):
  knots_v25, r_knots, lap_delta_pct{mean,sd,per_track}, vtop_delta_kmh{...},
  pairs_used, excluded, fp1_validation{slug: {...}}
Spec: docs/2026-07-15-prefp1-universal-calibration-design.md §3.1
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _track_registry import (  # noqa: E402
    TRACKS, align_pair, corner_minima, load_ref, pair_minima, pava_nonincreasing,
)

KNOTS_V25 = np.array([80.0, 140.0, 200.0, 260.0, 320.0])
MIN_PAIR_RATE = 0.8          # below this on MAJOR corners -> layout change / bad data
MAJOR_PROM_KMH = 15.0        # micro-lifts/shoulders below this don't gate the guard
VTOP_PCTL = 99.5


def vtop(v: np.ndarray) -> float:
    return float(np.percentile(v, VTOP_PCTL))


def analyze_pair(slug: str, spec: dict) -> dict:
    s25, v25, t25 = load_ref(spec["csv25"])
    s26, v26, t26 = load_ref(spec["csv26"])
    s_total = float(spec["length_m"])
    # Align onto one grid first: kills integration drift + start-line offset
    # between fetcher eras (FastF1 vs OpenF1). Corners are detected on the
    # ALIGNED traces so pairing distances are comparable.
    sg, v25g, v26g, shift = align_pair(s25, v25, s26, v26, s_total)
    m25p = corner_minima(sg, v25g, with_prominence=True)
    m26p = corner_minima(sg, v26g, with_prominence=True)
    # all pairable minima feed the fit ...
    m25 = [(a, b) for a, b, _ in m25p]
    m26 = [(a, b) for a, b, _ in m26p]
    pairs, _ = pair_minima(m25, m26, s_total)
    # ... but the layout-change guard only counts MAJOR corners
    maj25 = [(a, b) for a, b, p in m25p if p >= MAJOR_PROM_KMH]
    maj26 = [(a, b) for a, b, p in m26p if p >= MAJOR_PROM_KMH]
    _, rate = pair_minima(maj25, maj26, s_total)
    return dict(slug=slug, kind=spec["kind26"], t25=t25, t26=t26,
                vtop25=vtop(v25g), vtop26=vtop(v26g),
                n25=len(m25), n26=len(m26), pairs=pairs, rate=rate,
                shift=shift, trace=(sg, v25g, sg, v26g))


def overlay_png(res: dict, out_png: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s25, v25, s26, v26 = res["trace"]
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(s25, v25, lw=1.2, color="#888", label=f"2025 Q ({res['t25']:.2f}s)")
    ax.plot(s26, v26, lw=1.2, color="#c00",
            label=f"2026 {res['kind']} ({res['t26']:.2f}s)")
    for (a, pv, b, qv) in res["pairs"]:
        ax.plot([a, b], [pv, qv], "o-", ms=4, lw=0.8, color="#06c", alpha=0.7)
    ax.set_title(f"{res['slug']}: matched corner minima "
                 f"(rate {res['rate']:.2f}, {len(res['pairs'])} pairs)")
    ax.set_xlabel("distance [m]"); ax.set_ylabel("speed [km/h]")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out_png, dpi=90); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude", default=None, help="track slug to leave out (LOO backtest)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "transfer_2026.json"))
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()

    results = []
    for slug, spec in TRACKS.items():
        if slug == args.exclude:
            continue
        if not spec["csv26"] or not os.path.exists(spec["csv25"]) \
                or not os.path.exists(spec["csv26"]):
            continue
        res = analyze_pair(slug, spec)
        results.append(res)
        print(f"[transfer] {slug:12s} kind={res['kind']:3s} rate={res['rate']:.2f} "
              f"pairs={len(res['pairs']):2d} t25={res['t25']:7.2f} t26={res['t26']:7.2f} "
              f"vtop {res['vtop25']:.0f}->{res['vtop26']:.0f} "
              f"shift={res['shift']*100:+.1f}%")
        if not args.no_plots:
            overlay_png(res, os.path.join(os.path.dirname(args.out),
                                          f"transfer_overlay_{slug}.png"))
        if res["kind"] == "Q" and res["rate"] < MIN_PAIR_RATE:
            print(f"[transfer] ABORT: {slug} Q-pair rate {res['rate']:.2f} < "
                  f"{MIN_PAIR_RATE} (layout change or bad ref?) — see overlay PNG",
                  file=sys.stderr)
            return 2

    q = [r for r in results if r["kind"] == "Q"]
    fp1 = [r for r in results if r["kind"] == "FP1"]
    if not q:
        print("[transfer] ABORT: no qualifying pairs to fit", file=sys.stderr)
        return 2

    pv25 = np.array([p[1] for r in q for p in r["pairs"]])
    pr = np.array([p[3] / p[1] for r in q for p in r["pairs"]])
    r_knots = pava_nonincreasing(pv25, pr, np.ones_like(pr), KNOTS_V25)

    lap_pt = {r["slug"]: 100.0 * (r["t26"] - r["t25"]) / r["t25"] for r in q}
    vtop_pt = {r["slug"]: r["vtop26"] - r["vtop25"] for r in q}

    fp1_val = {}
    for r in fp1:
        if not r["pairs"]:
            continue
        v = np.array([p[1] for p in r["pairs"]])
        ratio = np.array([p[3] / p[1] for p in r["pairs"]])
        pred = np.interp(v, KNOTS_V25, r_knots)
        fp1_val[r["slug"]] = dict(
            r_residual_median=float(np.median(ratio - pred)),
            n_pairs=len(r["pairs"]),
            lap_delta_pct=100.0 * (r["t26"] - r["t25"]) / r["t25"],
            vtop_delta_kmh=r["vtop26"] - r["vtop25"],
        )

    out = dict(
        knots_v25=KNOTS_V25.tolist(),
        r_knots=[round(float(x), 5) for x in r_knots],
        lap_delta_pct=dict(
            mean=float(np.mean(list(lap_pt.values()))),
            sd=float(np.std(list(lap_pt.values()), ddof=1)) if len(lap_pt) > 1 else 0.5,
            per_track={k: round(x, 3) for k, x in lap_pt.items()},
        ),
        vtop_delta_kmh=dict(
            mean=float(np.mean(list(vtop_pt.values()))),
            sd=float(np.std(list(vtop_pt.values()), ddof=1)) if len(vtop_pt) > 1 else 3.0,
            per_track={k: round(x, 2) for k, x in vtop_pt.items()},
        ),
        pairs_used=[r["slug"] for r in q],
        excluded=args.exclude,
        fp1_validation=fp1_val,
        n_corner_points=int(len(pv25)),
    )
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    print(f"[transfer] r(v25) at {KNOTS_V25.astype(int).tolist()} = "
          f"{[round(float(x), 3) for x in r_knots]}")
    print(f"[transfer] lap_delta_pct mean={out['lap_delta_pct']['mean']:+.2f}% "
          f"sd={out['lap_delta_pct']['sd']:.2f} per={out['lap_delta_pct']['per_track']}")
    print(f"[transfer] vtop_delta mean={out['vtop_delta_kmh']['mean']:+.1f} km/h "
          f"per={out['vtop_delta_kmh']['per_track']}")
    for slug, d in fp1_val.items():
        print(f"[transfer] FP1 check {slug}: r residual median {d['r_residual_median']:+.3f} "
              f"({d['n_pairs']} pairs)  lap_d {d['lap_delta_pct']:+.2f}%  "
              f"vtop_d {d['vtop_delta_kmh']:+.1f}")
    print(f"[transfer] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
