#!/usr/bin/env python3
"""
Build a lap/session path from live.jsonl (UndercutF1-style capture) and write
the same JSON format as fetch_one_lap.py for use with create_lap_path_in_blender.py.

Uses Position.z (~75 Hz) so you get many more points than FastF1/OpenF1.

Usage:
  python path_from_live_jsonl.py --live live.jsonl --driver 4 --out lap_path.json
  python path_from_live_jsonl.py --live live.jsonl --driver 4 --lap 1 --out lap1.json   # just lap 1
  python path_from_live_jsonl.py --live live.jsonl --driver 4 --fastest --out fastest.json   # fastest lap by duration

Lap boundaries for --lap and --fastest are detected from position data (start/finish
crossings), not TimingData, so the full lap gets all points in that time range. Point
count per lap depends on your capture rate (Position.z can be ~4–75 Hz).
Optional --resample-hz N resamples the path (spline if scipy available, else linear).
Optional --start and --end (ISO UTC) override and trim by time.
"""

import argparse
import base64
import json
import re
import sys
import zlib
from datetime import datetime, timezone

try:
    from scipy.interpolate import CubicSpline
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def parse_lap_time_string(s: str) -> float | None:
    """Parse F1 lap time string 'm:ss.mmm' or 'mm:ss.mmm' to seconds, or None if invalid."""
    if not s or not isinstance(s, str):
        return None
    m = re.match(r"^(\d+):(\d{2})\.(\d+)$", s.strip())
    if not m:
        return None
    try:
        minutes, seconds, frac = int(m.group(1)), int(m.group(2)), m.group(3)
        frac_len = len(frac)
        frac_sec = int(frac) / (10 ** frac_len)
        return minutes * 60 + seconds + frac_sec
    except (ValueError, TypeError):
        return None


def parse_iso(s: str) -> datetime:
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def resample_path(points_with_time: list, hz: float) -> list:
    """
    Resample (ts, x, y, z) to uniform interval 1/hz seconds; return list of (x, y, z).
    Uses linear interpolation. points_with_time must be sorted by time.
    """
    if len(points_with_time) < 2 or hz <= 0:
        return [(p[1], p[2], p[3]) for p in points_with_time]
    t0_sec = parse_iso(points_with_time[0][0]).timestamp()
    t_sec = [parse_iso(p[0]).timestamp() - t0_sec for p in points_with_time]
    x = [p[1] for p in points_with_time]
    y = [p[2] for p in points_with_time]
    z = [p[3] for p in points_with_time]
    t_end = t_sec[-1]
    n_out = max(2, int(round(t_end * hz)))
    dt_out = t_end / (n_out - 1) if n_out > 1 else 0.0
    out = []
    for i in range(n_out):
        t = i * dt_out
        # find segment: t_sec[j] <= t <= t_sec[j+1]
        j = 0
        while j < len(t_sec) - 1 and t_sec[j + 1] < t:
            j += 1
        if j >= len(t_sec) - 1:
            out.append((x[-1], y[-1], z[-1]))
            continue
        t_a, t_b = t_sec[j], t_sec[j + 1]
        frac = (t - t_a) / (t_b - t_a) if t_b > t_a else 0.0
        xv = x[j] + frac * (x[j + 1] - x[j])
        yv = y[j] + frac * (y[j + 1] - y[j])
        zv = z[j] + frac * (z[j + 1] - z[j])
        out.append((xv, yv, zv))
    return out


def decompress_position_z(payload_b64: str) -> list:
    """Decompress Position.z Json string; return list of {Timestamp, Entries}."""
    raw = base64.b64decode(payload_b64)
    out = zlib.decompress(raw, -zlib.MAX_WBITS)
    data = json.loads(out.decode("utf-8"))
    return data.get("Position") or []


def detect_lap_boundaries_from_positions(
    points_with_time: list,
    min_lap_s: float = 50.0,
    sf_radius_cm: float = 15000.0,
) -> list:
    """
    Detect lap boundaries from position data by finding start/finish line crossings.
    points_with_time = [(ts, x, y, z), ...] in cm, sorted by ts.
    Returns list of (lap_num, start_idx, end_idx) where indices are into points_with_time.
    Reference = centroid of points where the car is moving (exclude pit/stationary).
    """
    if len(points_with_time) < 100:
        return []
    # Reference: centroid of points where car moved > 50 cm from previous (on-track only, exclude pit)
    moving = []
    for i in range(1, len(points_with_time)):
        dx = points_with_time[i][1] - points_with_time[i - 1][1]
        dy = points_with_time[i][2] - points_with_time[i - 1][2]
        if (dx * dx + dy * dy) >= 2500:  # (50 cm)^2
            moving.append(i)
    if len(moving) < 100:
        moving = list(range(len(points_with_time)))  # fallback: use all
    # Use middle of "moving" indices so we're on a flying lap
    n_m = len(moving)
    start_m = n_m // 4
    end_m = min(start_m + 1500, n_m)
    ref_x = sum(points_with_time[moving[j]][1] for j in range(start_m, end_m)) / (end_m - start_m)
    ref_y = sum(points_with_time[moving[j]][2] for j in range(start_m, end_m)) / (end_m - start_m)
    radius_sq = (sf_radius_cm ** 2)

    def dist_sq(i: int) -> float:
        x, y = points_with_time[i][1], points_with_time[i][2]
        return (x - ref_x) ** 2 + (y - ref_y) ** 2

    def parse_ts(i: int) -> float:
        try:
            t = parse_iso(points_with_time[i][0])
            return t.timestamp()
        except Exception:
            return 0.0

    # Find crossings: local minimum of distance to ref; only count if segment has real spread (full lap, not pit)
    min_spread_sq = (10000.0 ** 2)  # 100 m span in cm^2 (reject stationary/pit segments)
    crossings = [0]  # first lap starts at index 0
    i = 1
    while i < len(points_with_time) - 1:
        d_sq = dist_sq(i)
        d_prev = dist_sq(i - 1) if i > 0 else 1e30
        d_next = dist_sq(i + 1) if i + 1 < len(points_with_time) else 1e30
        if d_sq <= radius_sq and d_sq <= d_prev and d_sq <= d_next:
            last_ts = parse_ts(crossings[-1])
            curr_ts = parse_ts(i)
            if curr_ts - last_ts >= min_lap_s:
                # Require segment to span a real lap (not 70s stationary in pit)
                seg_x = [points_with_time[k][1] for k in range(crossings[-1], i + 1)]
                seg_y = [points_with_time[k][2] for k in range(crossings[-1], i + 1)]
                spread_sq = (max(seg_x) - min(seg_x)) ** 2 + (max(seg_y) - min(seg_y)) ** 2
                if spread_sq >= min_spread_sq:
                    crossings.append(i)
                    i += 80  # skip ahead to avoid double-counting same crossing
                    continue
        i += 1

    if len(crossings) < 2:
        return []
    result = []
    for lap_num in range(1, len(crossings)):
        result.append((lap_num, crossings[lap_num - 1], crossings[lap_num]))
    return result


def get_lap_boundaries_from_live(live_path: str, driver_key: str) -> list:
    """
    Scan live.jsonl for TimingData; return list of (lap_num, start_dt, end_dt, official_time_s).
    end_dt = first DateTime when NumberOfLaps >= lap_num (driver crossed line).
    start_dt for lap 1 is None; else previous lap's end_dt.
    official_time_s = LastLapTime.Value parsed to seconds when present, else None.
    """
    updates = []  # (dt_str, num_laps, last_lap_value_str or None)
    with open(live_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("Type") != "TimingData":
                continue
            j = o.get("Json") or {}
            lines = j.get("Lines") or {}
            if driver_key not in lines:
                continue
            line_data = lines[driver_key]
            num_laps = line_data.get("NumberOfLaps")
            if num_laps is None:
                continue
            try:
                num_laps = int(num_laps)
            except (TypeError, ValueError):
                continue
            last_lap = line_data.get("LastLapTime") or {}
            value_str = last_lap.get("Value") if isinstance(last_lap, dict) else None
            dt = o.get("DateTime") or ""
            if dt:
                updates.append((dt, num_laps, value_str))
    if not updates:
        return []
    updates.sort(key=lambda r: r[0])
    first_end_by_lap = {}
    official_time_by_lap = {}
    for dt_str, n, value_str in updates:
        for lap_num in range(1, n + 1):
            if lap_num not in first_end_by_lap:
                first_end_by_lap[lap_num] = parse_iso(dt_str)
                if lap_num == n and value_str:
                    official_time_by_lap[lap_num] = parse_lap_time_string(value_str)
    result = []
    for lap_num in sorted(first_end_by_lap):
        end_dt = first_end_by_lap[lap_num]
        start_dt = first_end_by_lap.get(lap_num - 1)
        official_s = official_time_by_lap.get(lap_num)
        result.append((lap_num, start_dt, end_dt, official_s))
    return result


def run():
    ap = argparse.ArgumentParser(description="Build path from live.jsonl Position.z")
    ap.add_argument("--live", required=True, help="Path to live.jsonl")
    ap.add_argument("--driver", required=True, help="Driver number (e.g. 4 for NOR)")
    ap.add_argument("--out", default="lap_path.json", help="Output JSON path")
    ap.add_argument("--scale", type=float, default=0.001,
                    help="Scale position (cm→Blender; default 0.001 = same scale as FastF1 0.1 for m)")
    ap.add_argument("--center", action="store_true", default=True)
    ap.add_argument("--no-center", action="store_false", dest="center")
    ap.add_argument("--lap", type=int, default=None,
                    help="Extract only this lap number (uses TimingData NumberOfLaps)")
    ap.add_argument("--fastest", action="store_true",
                    help="Extract fastest lap (TimingData LastLapTime.Value, else duration; excludes bogus lap 1)")
    ap.add_argument("--start", type=str, default=None,
                    help="Only include points at or after this UTC time (ISO); overrides --lap")
    ap.add_argument("--end", type=str, default=None,
                    help="Only include points before this UTC time (ISO); overrides --lap")
    ap.add_argument("--on-track-only", action="store_true", default=True,
                    help="Only include points with Status OnTrack (default True)")
    ap.add_argument("--smooth", action="store_true", default=True,
                    help="Output smooth=true for Blender AUTO handles")
    ap.add_argument("--resample-hz", type=float, default=0,
                    help="Resample path to this many points per second (0=off); e.g. 20 for smoother curve")
    args = ap.parse_args()

    driver_key = str(args.driver).strip()
    points_with_time = []  # (ts_str, x, y, z)

    with open(args.live, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("Type") != "Position.z":
                continue
            payload = o.get("Json")
            if not isinstance(payload, str):
                continue
            try:
                snapshots = decompress_position_z(payload)
            except Exception:
                continue
            for snap in snapshots:
                ts = snap.get("Timestamp") or ""
                entries = snap.get("Entries") or {}
                if driver_key not in entries:
                    continue
                ent = entries[driver_key]
                if args.on_track_only and ent.get("Status") != "OnTrack":
                    continue
                x = ent.get("X", 0)
                y = ent.get("Y", 0)
                z = ent.get("Z", 0)
                try:
                    x, y, z = int(x), int(y), int(z)
                except (TypeError, ValueError):
                    continue
                points_with_time.append((ts, x, y, z))

    if not points_with_time:
        print("No position points found for driver", args.driver, file=sys.stderr)
        return 1

    # Sort by time
    points_with_time.sort(key=lambda r: r[0])

    # Lap boundaries from position data (S/F crossings) — same timebase as points, so full laps get full point count
    MIN_LAP_SECONDS = 50
    # Position-based lap boundaries (S/F crossings); same timebase as points so we get full point count
    pos_laps = detect_lap_boundaries_from_positions(
        points_with_time, min_lap_s=70.0, sf_radius_cm=20000.0
    )
    pos_lap_by_num = {lap_num: (s, e) for lap_num, s, e in pos_laps}

    # --fastest: pick lap with smallest duration (from position crossings)
    if args.fastest:
        if not pos_laps:
            print("No lap boundaries detected from position (S/F crossings); cannot compute --fastest", file=sys.stderr)
            return 1
        best_lap, best_duration = None, None
        for lap_num, start_idx, end_idx in pos_laps:
            try:
                t0 = parse_iso(points_with_time[start_idx][0]).timestamp()
                t1 = parse_iso(points_with_time[end_idx][0]).timestamp()
            except Exception:
                continue
            duration_s = t1 - t0
            if duration_s < MIN_LAP_SECONDS or duration_s > 300:
                continue
            if best_duration is None or duration_s < best_duration:
                best_duration = duration_s
                best_lap = lap_num
        if best_lap is None:
            print(f"Could not determine fastest lap (no lap with duration {MIN_LAP_SECONDS}s–300s)", file=sys.stderr)
            return 1
        print(f"Fastest lap: {best_lap} (duration {best_duration:.2f}s)", file=sys.stderr)
        args.lap = best_lap

    # Apply filter: --start/--end (ISO times) or --lap N (position-based indices)
    if args.start or args.end:
        t_start = parse_iso(args.start) if args.start else None
        t_end = parse_iso(args.end) if args.end else None
        if t_start and t_start.tzinfo is None:
            t_start = t_start.replace(tzinfo=timezone.utc)
        if t_end and t_end.tzinfo is None:
            t_end = t_end.replace(tzinfo=timezone.utc)
        filtered = []
        for ts, x, y, z in points_with_time:
            try:
                t = parse_iso(ts)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t_start and t < t_start:
                    continue
                if t_end and t >= t_end:
                    continue
                filtered.append((ts, x, y, z))
            except Exception:
                filtered.append((ts, x, y, z))
        points_with_time = filtered
    elif args.lap is not None:
        if args.lap not in pos_lap_by_num:
            available = sorted(pos_lap_by_num.keys())
            print(f"Lap {args.lap} not found for driver {args.driver} (have laps {available})", file=sys.stderr)
            return 1
        start_idx, end_idx = pos_lap_by_num[args.lap]
        points_with_time = points_with_time[start_idx:end_idx]

    if not points_with_time:
        print("No points in time range", file=sys.stderr)
        return 1

    # Optional resample to higher point rate for smoother Blender curve
    if args.resample_hz > 0:
        points_xyz = resample_path(points_with_time, args.resample_hz)
    else:
        points_xyz = [(p[1], p[2], p[3]) for p in points_with_time]

    # Apply scale
    x = [p[0] * args.scale for p in points_xyz]
    y = [p[1] * args.scale for p in points_xyz]
    z = [p[2] * args.scale for p in points_xyz]

    if args.center:
        cx = sum(x) / len(x)
        cy = sum(y) / len(y)
        x = [v - cx for v in x]
        y = [v - cy for v in y]

    out_points = [{"x": float(a), "y": float(b), "z": float(c)} for a, b, c in zip(x, y, z)]

    # Closed: single-lap extraction or if start/end points are very close
    closed = args.lap is not None
    if not closed and len(out_points) >= 10:
        p0, pn = out_points[0], out_points[-1]
        d2 = (pn["x"] - p0["x"]) ** 2 + (pn["y"] - p0["y"]) ** 2
        if d2 < 1.0:
            closed = True

    payload = {"points": out_points, "closed": closed, "smooth": args.smooth}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    lap_info = f", lap={args.lap}" if args.lap is not None else ""
    if args.fastest:
        lap_info = lap_info + " [fastest]"
    resample_info = f", resample={args.resample_hz}Hz" if args.resample_hz > 0 else ""
    print(f"Wrote {len(out_points)} points to {args.out} (driver={args.driver}{lap_info}, scale={args.scale}, center={args.center}{resample_info})")
    return 0


if __name__ == "__main__":
    sys.exit(run())
