#!/usr/bin/env python3
"""
BACKUP: fetch_one_lap.py before adding get_clean_trace-style cleaning.
Restore by copying this file over fetch_one_lap.py.
Uses raw get_telemetry() with no dropna/drop_duplicates.
"""

import argparse
import json
import os
import sys


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--round", type=int, required=True, help="Race round 1–24")
    ap.add_argument("--session", type=str, default="Race")
    ap.add_argument("--driver", type=str, required=True, help="3-letter code e.g. NOR")
    ap.add_argument("--out", type=str, default="lap_path.json")
    ap.add_argument("--scale", type=float, default=0.1, help="Multiply X,Y by this for Blender scale")
    ap.add_argument("--center", action="store_true", default=True, help="Center track at origin")
    ap.add_argument("--no-center", action="store_false", dest="center")
    ap.add_argument("--smooth", action="store_true", default=True,
                    help="Set smooth=true so Blender uses AUTO handles (default)")
    ap.add_argument("--raw", action="store_true",
                    help="Set smooth=false so Blender uses VECTOR handles; same points")
    args = ap.parse_args()

    use_smooth_handles = args.smooth and not args.raw

    import fastf1

    cache = os.path.join(os.path.dirname(__file__) or ".", "fastf1_cache")
    os.makedirs(cache, exist_ok=True)
    fastf1.Cache.enable_cache(cache)

    session = fastf1.get_session(args.year, args.round, args.session)
    session.load(telemetry=True)

    laps = session.laps[session.laps["Driver"] == args.driver]
    if laps.empty:
        print(f"No laps for driver {args.driver}", file=sys.stderr)
        return 1

    fastest = laps.loc[laps["LapTime"].idxmin()]
    tel = fastest.get_telemetry()

    x = tel["X"].to_numpy(dtype=float)
    y = tel["Y"].to_numpy(dtype=float)

    x = x * args.scale
    y = y * args.scale
    if args.center:
        x = x - x.mean()
        y = y - y.mean()
    z = [0.0] * len(x)

    points = [{"x": float(a), "y": float(b), "z": c} for a, b, c in zip(x, y, z)]

    closed = True
    if len(points) >= 2:
        p0, pn = points[0], points[-1]
        d2 = (pn["x"] - p0["x"]) ** 2 + (pn["y"] - p0["y"]) ** 2
        if d2 > 1.0:
            closed = False

    payload = {"points": points, "closed": closed, "smooth": use_smooth_handles}

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Wrote {len(points)} points to {args.out} (smooth_handles={use_smooth_handles})")
    return 0


if __name__ == "__main__":
    sys.exit(run())
