#!/usr/bin/env python3
"""
BACKUP: Raw path (no smoothing). Original fetch_one_lap.py.
Restore with: copy this file over fetch_one_lap.py to get raw behaviour back.
"""

import argparse
import json
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
    args = ap.parse_args()

    import fastf1
    import os

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

    payload = {"points": points, "closed": closed}

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Wrote {len(points)} points to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
