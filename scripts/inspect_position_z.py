#!/usr/bin/env python3
"""Inspect Position.z structure in live.jsonl: snapshots per message, timestamps, rate."""
import base64
import json
import sys
import zlib
from datetime import datetime, timezone

def parse(s):
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t

def decompress_position_z(payload_b64):
    raw = base64.b64decode(payload_b64)
    out = zlib.decompress(raw, -zlib.MAX_WBITS)
    return json.loads(out.decode("utf-8")).get("Position") or []

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "live.jsonl"
    driver_key = sys.argv[2] if len(sys.argv) > 2 else "4"

    line_timestamps = []  # DateTime of each Position.z line (message time)
    snapshot_counts = []
    first_ts_per_line = []
    all_ts_driver = []

    with open(path, "r", encoding="utf-8") as f:
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
            msg_dt = o.get("DateTime") or ""
            payload = o.get("Json")
            if not isinstance(payload, str):
                continue
            try:
                snapshots = decompress_position_z(payload)
            except Exception as e:
                print(f"Decompress error: {e}", file=sys.stderr)
                continue
            snapshot_counts.append(len(snapshots))
            line_timestamps.append(msg_dt)
            for snap in snapshots:
                ts = snap.get("Timestamp") or ""
                entries = snap.get("Entries") or {}
                if not first_ts_per_line or len(first_ts_per_line) < len(snapshot_counts):
                    first_ts_per_line.append(ts)
                if driver_key in entries and entries[driver_key].get("Status") == "OnTrack":
                    all_ts_driver.append(ts)

    n_lines = len(line_timestamps)
    n_points_driver = len(all_ts_driver)
    print(f"Position.z lines: {n_lines}")
    print(f"Total snapshots (all lines): {sum(snapshot_counts)}")
    print(f"Snapshots per line: min={min(snapshot_counts)}, max={max(snapshot_counts)}, avg={sum(snapshot_counts)/n_lines:.1f}")
    print(f"Points for driver {driver_key} (OnTrack): {n_points_driver}")

    # Sample: first 3 lines - how many snapshots and what timestamps
    print("\nFirst 3 Position.z lines (snapshot count and first/last Timestamp in payload):")
    idx = 0
    with open(path, "r", encoding="utf-8") as f:
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
            msg_dt = o.get("DateTime", "")
            if len(snapshots) > 0:
                first_ts = snapshots[0].get("Timestamp", "")
                last_ts = snapshots[-1].get("Timestamp", "")
                print(f"  Line {idx}: msg DateTime={msg_dt[:23]}, snapshots={len(snapshots)}, first_ts={first_ts[:28]}, last_ts={last_ts[:28]}")
            else:
                print(f"  Line {idx}: msg DateTime={msg_dt[:23]}, snapshots=0")
            idx += 1
            if idx >= 3:
                break

    # Time span and effective rate for driver
    if len(all_ts_driver) >= 2:
        all_ts_driver.sort()
        t0 = parse(all_ts_driver[0])
        t1 = parse(all_ts_driver[-1])
        span_s = (t1 - t0).total_seconds()
        print(f"\nDriver {driver_key} time span: {t0.isoformat()[:23]} to {t1.isoformat()[:23]} = {span_s:.0f}s")
        print(f"Effective rate: {n_points_driver / span_s:.2f} Hz")

    # Message rate: time between Position.z line DateTimes
    if len(line_timestamps) >= 10:
        msg_times = []
        for dt_str in line_timestamps[:500]:
            try:
                msg_times.append(parse(dt_str).timestamp())
            except Exception:
                pass
        if len(msg_times) >= 2:
            msg_gaps = [(msg_times[i] - msg_times[i-1]) * 1000 for i in range(1, len(msg_times))]
            print(f"\nPosition.z message interval (first 500), ms: min={min(msg_gaps):.0f}, max={max(msg_gaps):.0f}, median={msg_gaps[len(msg_gaps)//2]:.0f}")
            avg_gap = sum(msg_gaps) / len(msg_gaps)
            snap_avg = sum(snapshot_counts) / n_lines
            print(f"  => Message rate ~{1000.0/avg_gap:.1f} msg/s, x {snap_avg:.1f} snap/msg => ~{1000.0/avg_gap * snap_avg:.1f} Hz")

    # Gap analysis: time between consecutive points for driver
    if len(all_ts_driver) >= 100:
        gaps_ms = []
        for i in range(1, min(500, len(all_ts_driver))):
            try:
                a = parse(all_ts_driver[i-1]).timestamp()
                b = parse(all_ts_driver[i]).timestamp()
                gaps_ms.append((b - a) * 1000)
            except Exception:
                pass
        if gaps_ms:
            gaps_ms.sort()
            print(f"\nGap between consecutive points (first 500), ms: min={min(gaps_ms):.0f}, max={max(gaps_ms):.0f}, median={gaps_ms[len(gaps_ms)//2]:.0f}")

if __name__ == "__main__":
    main()
