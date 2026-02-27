#!/usr/bin/env python3
"""Debug lap boundaries vs position timestamps for live.jsonl."""
import json
import sys
import zlib
import base64
from datetime import datetime, timezone

def parse_iso(s):
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t

def decompress_position_z(payload_b64):
    raw = base64.b64decode(payload_b64)
    out = zlib.decompress(raw, -zlib.MAX_WBITS)
    data = json.loads(out.decode("utf-8"))
    return data.get("Position") or []

def main():
    live_path = sys.argv[1] if len(sys.argv) > 1 else "live.jsonl"
    driver_key = sys.argv[2] if len(sys.argv) > 2 else "4"

    # Get lap boundaries (same logic as path_from_live_jsonl)
    updates = []
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
            num_laps = lines[driver_key].get("NumberOfLaps")
            if num_laps is None:
                continue
            try:
                num_laps = int(num_laps)
            except (TypeError, ValueError):
                continue
            dt = o.get("DateTime") or ""
            if dt:
                updates.append((dt, num_laps))
    updates.sort(key=lambda r: r[0])
    first_end_by_lap = {}
    for dt_str, n in updates:
        for lap_num in range(1, n + 1):
            if lap_num not in first_end_by_lap:
                first_end_by_lap[lap_num] = parse_iso(dt_str)

    print("Lap boundaries (TimingData DateTime):")
    for lap_num in sorted(first_end_by_lap)[:25]:
        end_dt = first_end_by_lap[lap_num]
        start_dt = first_end_by_lap.get(lap_num - 1)
        if start_dt:
            dur = (end_dt - start_dt).total_seconds()
            print(f"  Lap {lap_num}: start={start_dt.isoformat()[:23]} end={end_dt.isoformat()[:23]} duration={dur:.1f}s")
        else:
            print(f"  Lap {lap_num}: start=None end={end_dt.isoformat()[:23]}")
    if len(first_end_by_lap) > 25:
        print(f"  ... and {len(first_end_by_lap) - 25} more laps")

    # Collect position timestamps for driver
    pos_timestamps = []
    with open(live_path, "r", encoding="utf-8") as f:
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
                if driver_key in entries and entries[driver_key].get("Status") == "OnTrack":
                    pos_timestamps.append(ts)

    pos_timestamps.sort()
    if not pos_timestamps:
        print("No position timestamps for driver", driver_key)
        return
    first_ts = pos_timestamps[0]
    last_ts = pos_timestamps[-1]
    print(f"\nPosition timestamps (driver {driver_key}): count={len(pos_timestamps)}")
    print(f"  First: {first_ts}")
    print(f"  Last:  {last_ts}")
    try:
        first_dt = parse_iso(first_ts)
        last_dt = parse_iso(last_ts)
        print(f"  Parsed first: {first_dt.isoformat()}")
        print(f"  Parsed last:  {last_dt.isoformat()}")
    except Exception as e:
        print(f"  Parse error: {e}")

    # Compare: do position timestamps look like UTC ISO or something else?
    print("\nSample position timestamps (first 3, middle 2, last 3):")
    for i in [0, 1, 2, len(pos_timestamps)//2 - 1, len(pos_timestamps)//2, -3, -2, -1]:
        print(f"  {pos_timestamps[i]}")

    # Count points per lap using same filter as script (t_start <= t < t_end)
    print("\nPoints per lap (t_start <= position_ts < t_end):")
    for lap_num in sorted(first_end_by_lap):
        if lap_num == 1:
            continue
        start_dt = first_end_by_lap.get(lap_num - 1)
        end_dt = first_end_by_lap[lap_num]
        if not start_dt:
            continue
        count = 0
        for ts in pos_timestamps:
            try:
                t = parse_iso(ts)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if start_dt <= t < end_dt:
                    count += 1
            except Exception:
                pass
        dur = (end_dt - start_dt).total_seconds()
        print(f"  Lap {lap_num}: {count} points (window duration {dur:.1f}s)")
        if lap_num >= 15:
            break

if __name__ == "__main__":
    main()
