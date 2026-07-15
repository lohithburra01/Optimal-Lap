"""Predict a track's 2026 calibration targets from its OWN 2025 lap + the
empirical 2025->2026 transfer. Zero dependency on the track's 2026 sessions.

  python cache/_predict_track.py --track spa [--transfer cache/transfer_2026.json]
                                 [--out cache/predicted_spa.json]

Output JSON (consumed by _autofit_2026.py and _gate_2026.py --targets):
  track, rho, t25_s, lap_band_s [lo,hi], vtop_target_kmh,
  corners [{s_m, s_frac, v25_kmh, v26_target_kmh}], cda0, cl0, ref_used, warnings
Spec: docs/2026-07-15-prefp1-universal-calibration-design.md §3.2
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _track_registry import TRACKS, corner_minima, load_ref, rho_isa  # noqa: E402

VTOP_PCTL = 99.5
CDA0_DEFAULT = 0.75
CL0_DEFAULT = 4.6
LAP_BAND_FLOOR_PCT = 0.8       # never predict less than +0.8% over 2025


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True, choices=sorted(TRACKS))
    ap.add_argument("--transfer", default=os.path.join(here, "transfer_2026.json"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    spec = TRACKS[args.track]
    out_path = args.out or os.path.join(here, f"predicted_{args.track}.json")
    with open(args.transfer, encoding="utf-8") as f:
        tr = json.load(f)
    if tr.get("excluded") == args.track:
        print(f"[predict] using transfer WITHOUT {args.track} (leave-one-out)")

    warnings = []
    ref_used = "2025_q"
    csv25 = spec["csv25"]
    if not os.path.exists(csv25):
        print(f"[predict] ABORT: no 2025 ref at {csv25}", file=sys.stderr)
        return 2
    s, v, t25 = load_ref(csv25)
    total = float(s[-1] - s[0])
    dist_err = abs(total - spec["length_m"]) / spec["length_m"]
    if dist_err > 0.05:
        fb = csv25.replace("_2025_", "_2024_")
        if os.path.exists(fb):
            warnings.append(f"2025 ref distance off by {dist_err:.1%}; fell back to 2024")
            s, v, t25 = load_ref(fb)
            total = float(s[-1] - s[0])
            ref_used = "2024_q"
        else:
            print(f"[predict] ABORT: ref distance {total:.0f} m vs official "
                  f"{spec['length_m']:.0f} m ({dist_err:.1%} off) and no 2024 fallback",
                  file=sys.stderr)
            return 2
    elif dist_err > 0.02:
        warnings.append(f"ref distance {dist_err:.1%} off official (kept)")

    knots = np.array(tr["knots_v25"], float)
    r_knots = np.array(tr["r_knots"], float)
    corners = []
    for (cs, cv) in corner_minima(s, v):
        r = float(np.interp(cv, knots, r_knots))
        corners.append(dict(
            s_m=round(cs, 1),
            s_frac=round((cs - s[0]) / total, 5),
            v25_kmh=round(cv, 1),
            v26_target_kmh=round(r * cv, 1),
        ))
    if len(corners) < 4:
        print(f"[predict] ABORT: only {len(corners)} corners found — bad ref?",
              file=sys.stderr)
        return 2

    vtop25 = float(np.percentile(v, VTOP_PCTL))
    vtop_target = vtop25 + float(tr["vtop_delta_kmh"]["mean"])

    mean = float(tr["lap_delta_pct"]["mean"])
    sd = float(tr["lap_delta_pct"]["sd"])
    lo_pct = max(LAP_BAND_FLOOR_PCT, mean - 2.0 * sd)
    hi_pct = mean + 2.0 * sd
    lap_band = [round(t25 * (1.0 + lo_pct / 100.0), 3),
                round(t25 * (1.0 + hi_pct / 100.0), 3)]

    out = dict(
        track=args.track,
        rho=round(rho_isa(spec["altitude_m"]), 4),
        t25_s=round(t25, 3),
        lap_band_s=lap_band,
        vtop_target_kmh=round(vtop_target, 1),
        corners=corners,
        cda0=CDA0_DEFAULT,
        cl0=CL0_DEFAULT,
        ref_used=ref_used,
        transfer=os.path.basename(args.transfer),
        warnings=warnings,
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    hs = [c for c in corners if c["v25_kmh"] > 170.0]
    print(f"[predict] {args.track}: t25={t25:.2f}s  lap_band=[{lap_band[0]:.2f},"
          f"{lap_band[1]:.2f}]s  vtop {vtop25:.0f}->{vtop_target:.0f}  "
          f"rho={out['rho']}  corners={len(corners)} (hs>{170}: {len(hs)})")
    for c in corners:
        print(f"[predict]   s={c['s_m']:7.1f} ({c['s_frac']:.3f})  "
              f"v25={c['v25_kmh']:6.1f} -> v26={c['v26_target_kmh']:6.1f}")
    if warnings:
        print(f"[predict] WARNINGS: {warnings}")
    print(f"[predict] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
