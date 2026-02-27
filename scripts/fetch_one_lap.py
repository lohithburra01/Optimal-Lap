#!/usr/bin/env python3
"""
Fetch a single F1 lap from the FastF1 API and write 3D path points to a JSON file.

Pre-season testing: use get_testing_session (not get_session), e.g.:

  import fastf1
  fastf1.Cache.enable_cache('cache')
  YEAR = 2025
  TEST_NUMBER = 1      # Bahrain test event
  SESSION_NUMBER = 1  # Day 1 (use 2 or 3 for other days)
  session = fastf1.get_testing_session(YEAR, TEST_NUMBER, SESSION_NUMBER)
  session.load()

This script: --session Testing -> get_testing_session(year, round, test-session).
  - round = test_number (1 or 2). --test-session = session_number (1, 2, or 3).

Run with system Python (not Blender):
  pip install fastf1
  python fetch_one_lap.py --year 2024 --round 1 --session Race --driver HAM --out lap.json
  python fetch_one_lap.py --year 2025 --round 1 --session Qualifying --driver HAM --out bahrain_quali.json
  python fetch_one_lap.py --year 2025 --round 1 --session Testing --test-session 1 --driver HAM --out bahrain_2025_test.json
  python fetch_one_lap.py --year 2026 --round 1 --session Testing --test-session 2 --driver HAM --out out.json
"""

import argparse
import json
import os
import sys


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--round", type=int, required=True, help="Race round 1–24, or test_number (1 or 2) when --session Testing")
    ap.add_argument("--session", type=str, default="Race", help="Race, Qualifying, Practice 1/2/3, or Testing")
    ap.add_argument("--test-session", type=int, default=1, choices=(1, 2, 3), help="When --session Testing: session 1/2/3 (default 1)")
    ap.add_argument("--driver", type=str, required=True, help="3-letter code e.g. NOR")
    ap.add_argument("--out", type=str, default="lap_path.json")
    ap.add_argument("--scale", type=float, default=0.1, help="Multiply X,Y by this for Blender scale")
    ap.add_argument("--center", action="store_true", default=True, help="Center track at origin")
    ap.add_argument("--no-center", action="store_false", dest="center")
    ap.add_argument("--smooth", action="store_true", default=True,
                    help="Set smooth=true so Blender uses AUTO handles (default)")
    ap.add_argument("--raw", action="store_true",
                    help="Set smooth=false so Blender uses VECTOR handles")
    ap.add_argument("--debug", action="store_true", help="Enable FastF1 DEBUG logging to see real cause of API failures (e.g. rate limit)")
    args = ap.parse_args()

    use_smooth_handles = args.smooth and not args.raw

    import fastf1
    import logging
    if args.debug:
        logging.getLogger("fastf1").setLevel(logging.DEBUG)

    cache = os.path.join(os.path.dirname(__file__) or ".", "fastf1_cache")
    os.makedirs(cache, exist_ok=True)
    fastf1.Cache.enable_cache(cache)

    try:
        if args.session.strip().lower() == "testing":
            session = fastf1.get_testing_session(args.year, args.round, args.test_session)
        else:
            session = fastf1.get_session(args.year, args.round, args.session)
    except ValueError as e:
        if "Failed to load any schedule data" in str(e):
            print("ERROR: FastF1 could not load the season schedule from any API.", file=sys.stderr)
            print("", file=sys.stderr)
            print("Common causes:", file=sys.stderr)
            print("  1. No internet or firewall blocking requests.", file=sys.stderr)
            print("  2. Rate limit (e.g. 500 requests/hour). Wait and retry, or use cached data.", file=sys.stderr)
            print("  3. API temporarily down. Try again later.", file=sys.stderr)
            print("", file=sys.stderr)
            print("Run with --debug to see the underlying error (e.g. RateLimitExceededError).", file=sys.stderr)
            print("Cache dir: " + os.path.abspath(cache), file=sys.stderr)
            raise
        raise

    session.load(telemetry=True)

    try:
        laps = session.laps[session.laps["Driver"] == args.driver]
    except Exception as e:
        if "DataNotLoadedError" in type(e).__name__ or "not been loaded" in str(e):
            print("Lap/timing data did not load. For Testing sessions the F1 API often has no telemetry.", file=sys.stderr)
            print("Try a Race/Qualifying/Practice session, or retry testing later when data is published.", file=sys.stderr)
        raise
    if laps.empty:
        print(f"No laps for driver {args.driver}", file=sys.stderr)
        return 1

    fastest = laps.loc[laps["LapTime"].idxmin()]
    tel = fastest.get_telemetry()
    tel = tel.dropna(subset=["Distance", "Speed", "X", "Y"]).drop_duplicates(subset=["Time"]).drop_duplicates(subset=["Distance"])

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
