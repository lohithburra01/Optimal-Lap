#!/usr/bin/env python3
"""
Fetch a single F1 lap from the OpenF1 API (live-stream–stored data) and write
3D path points to JSON. Same output format as fetch_one_lap.py for use with
create_lap_path_in_blender.py.

OpenF1: https://api.openf1.org — historical from 2023+, no auth. Location data
is ~3.7 Hz (similar to FastF1’s 4–5 Hz), so point count is comparable.

Usage:
  python fetch_one_lap_openf1.py --year 2024 --country Australia --session Race --driver NOR --out lap_path.json

Requires: requests (or use urllib), numpy. For --racing-line: scipy.
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen, Request

BASE = "https://api.openf1.org/v1"


def _get(url, params=None):
    if params:
        url = url + "?" + urlencode(params)
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _racing_line_mit_style(x, y, dist, lookahead_points=40, max_offset_scale=3.0, offset_smooth_win=7):
    """Racing line from curvature + forward-looking (same logic as fetch_one_lap.py)."""
    import numpy as np
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    dist = np.asarray(dist, dtype=float)
    n = len(x)
    if n < 5:
        return x, y
    dx = np.zeros(n)
    dy = np.zeros(n)
    dx[0], dy[0] = x[1] - x[0], y[1] - y[0]
    dx[-1], dy[-1] = x[-1] - x[-2], y[-1] - y[-2]
    dx[1:-1] = (x[2:] - x[:-2]) * 0.5
    dy[1:-1] = (y[2:] - y[:-2]) * 0.5
    ds = np.hypot(dx, dy)
    ds[ds < 1e-9] = 1e-9
    tx, ty = dx / ds, dy / ds
    nx, ny = -ty, tx
    ddx = np.zeros(n)
    ddy = np.zeros(n)
    ddx[0] = (x[1] - x[0]) / (ds[0] or 1e-9) - (x[1] - x[0]) / (ds[1] or 1e-9)
    ddy[0] = (y[1] - y[0]) / (ds[0] or 1e-9) - (y[1] - y[0]) / (ds[1] or 1e-9)
    ddx[-1] = (x[-1] - x[-2]) / (ds[-1] or 1e-9) - (x[-2] - x[-3]) / (ds[-2] or 1e-9)
    ddy[-1] = (y[-1] - y[-2]) / (ds[-1] or 1e-9) - (y[-2] - y[-3]) / (ds[-2] or 1e-9)
    for i in range(1, n - 1):
        ddx[i] = (x[i + 1] - x[i]) / (ds[i] or 1e-9) - (x[i] - x[i - 1]) / (ds[i - 1] or 1e-9)
        ddy[i] = (y[i + 1] - y[i]) / (ds[i] or 1e-9) - (y[i] - y[i - 1]) / (ds[i - 1] or 1e-9)
    k = np.clip(tx * ddy - ty * ddx, -0.5, 0.5)
    look = min(lookahead_points, n // 4, 80)
    k_ahead = np.array([np.mean(k[i:min(i + look, n)]) if i < n else k[i] for i in range(n)])
    scale = max_offset_scale / (np.max(np.abs(k_ahead)) + 1e-9)
    raw_offset = np.clip(k_ahead * scale, -max_offset_scale, max_offset_scale)
    half = offset_smooth_win // 2
    offset = np.array([np.mean(raw_offset[max(0, i - half):min(n, i + half + 1)]) for i in range(n)])
    x_new = x + offset * nx
    y_new = y + offset * ny
    return x_new, y_new


def run():
    ap = argparse.ArgumentParser(description="Fetch one F1 lap path from OpenF1 API.")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--country", type=str, required=True, help="e.g. Australia, Bahrain")
    ap.add_argument("--session", type=str, default="Race", help="Race, Qualifying, etc.")
    ap.add_argument("--driver", type=str, required=True, help="3-letter code e.g. NOR")
    ap.add_argument("--out", type=str, default="lap_path.json")
    ap.add_argument("--scale", type=float, default=0.1)
    ap.add_argument("--center", action="store_true", default=True)
    ap.add_argument("--no-center", action="store_false", dest="center")
    ap.add_argument("--racing-line", action="store_true", default=True)
    ap.add_argument("--no-racing-line", action="store_false", dest="racing_line")
    ap.add_argument("--lookahead", type=int, default=40)
    ap.add_argument("--max-offset", type=float, default=3.0)
    ap.add_argument("--offset-smooth", type=int, default=7)
    ap.add_argument("--smooth", action="store_true", default=True)
    ap.add_argument("--raw", action="store_true", help="Blender VECTOR handles")
    args = ap.parse_args()

    driver_code = args.driver.upper().strip()

    # 1) Resolve meeting_key
    meetings = _get(f"{BASE}/meetings", {"year": args.year, "country_name": args.country})
    if not meetings:
        print(f"No meeting found for year={args.year} country={args.country}", file=sys.stderr)
        return 1
    meeting_key = meetings[0]["meeting_key"]

    # 2) Resolve session_key for this session type
    sessions = _get(f"{BASE}/sessions", {"meeting_key": meeting_key})
    session_row = None
    want = args.session.lower()
    for s in sessions:
        name = (s.get("session_name") or s.get("session_type") or "").lower()
        if want in name or name.startswith(want[:3]):
            session_row = s
            break
    if not session_row:
        print(f"No session like '{args.session}' for meeting_key={meeting_key}", file=sys.stderr)
        return 1
    session_key = session_row["session_key"]

    # 3) Resolve driver_number from 3-letter code
    drivers = _get(f"{BASE}/drivers", {"session_key": session_key})
    driver_number = None
    for d in drivers:
        if (d.get("name_acronym") or "").upper() == driver_code:
            driver_number = d["driver_number"]
            break
    if driver_number is None:
        print(f"Driver '{driver_code}' not found in session", file=sys.stderr)
        return 1

    # 4) Fastest lap (exclude pit out laps)
    laps = _get(f"{BASE}/laps", {"session_key": session_key, "driver_number": driver_number})
    laps = [l for l in laps if not l.get("is_pit_out_lap") and l.get("lap_duration")]
    if not laps:
        print("No valid laps", file=sys.stderr)
        return 1
    best = min(laps, key=lambda l: float(l["lap_duration"]))
    date_start = best["date_start"]
    lap_dur = float(best["lap_duration"])
    # date_end = date_start + lap_duration
    try:
        t0 = datetime.fromisoformat(date_start.replace("Z", "+00:00"))
    except Exception:
        t0 = datetime.fromisoformat(date_start)
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=lap_dur)
    date_end = t1.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "+00:00"

    # 5) Location for this lap (date range)
    loc_params = {
        "session_key": session_key,
        "driver_number": driver_number,
        "date>": date_start,
        "date<": date_end,
    }
    locations = _get(f"{BASE}/location", loc_params)
    if not locations:
        print("No location data for this lap", file=sys.stderr)
        return 1
    locations.sort(key=lambda r: r.get("date") or "")

    x = [float(p["x"]) for p in locations]
    y = [float(p["y"]) for p in locations]
    z_vals = [float(p.get("z", 0)) for p in locations]
    # Pseudo-distance (cumulative path length) for racing-line
    import math
    dist = [0.0]
    for i in range(1, len(x)):
        dist.append(dist[-1] + math.hypot(x[i] - x[i - 1], y[i] - y[i - 1]))

    x = [v * args.scale for v in x]
    y = [v * args.scale for v in y]
    if args.center:
        cx, cy = sum(x) / len(x), sum(y) / len(y)
        x = [v - cx for v in x]
        y = [v - cy for v in y]

    if args.racing_line and len(x) > 4:
        try:
            x, y = _racing_line_mit_style(
                x, y, dist,
                lookahead_points=args.lookahead,
                max_offset_scale=args.max_offset,
                offset_smooth_win=args.offset_smooth,
            )
        except Exception as e:
            print(f"Racing-line failed: {e}", file=sys.stderr)

    z = [0.0] * len(x)  # Blender path typically flat; use OpenF1 z if you prefer: z_vals
    points = [{"x": float(a), "y": float(b), "z": c} for a, b, c in zip(x, y, z)]

    closed = True
    if len(points) >= 2:
        p0, pn = points[0], points[-1]
        if (pn["x"] - p0["x"]) ** 2 + (pn["y"] - p0["y"]) ** 2 > 1.0:
            closed = False

    use_smooth_handles = args.smooth and not args.raw
    payload = {"points": points, "closed": closed, "smooth": use_smooth_handles}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {len(points)} points to {args.out} (OpenF1, racing_line={args.racing_line}, smooth_handles={use_smooth_handles})")
    return 0


if __name__ == "__main__":
    sys.exit(run())
