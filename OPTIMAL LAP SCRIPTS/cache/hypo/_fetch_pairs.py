"""Hypothesis study (2026-10-09): fetch the fastest Qualifying lap (OpenF1 car_data: speed, throttle, brake, gear,
rpm, drs; lap meta incl. sectors) for every circuit raced in BOTH 2025 and 2026 (2026 session already run).
Raw cache: cache/hypo/raw/<circuit>_<year>.json  (skips existing)."""
import os, sys, json, time
from datetime import timedelta, datetime, timezone
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, ROOT)
import fetch_openf1_lap as F
OUT = os.path.join(H, "raw"); os.makedirs(OUT, exist_ok=True)
now = datetime.now(timezone.utc)
s25 = {s["circuit_short_name"]: s for s in F.get("sessions", year=2025, session_name="Qualifying")}
s26 = {s["circuit_short_name"]: s for s in F.get("sessions", year=2026, session_name="Qualifying") if F.parse_dt(s["date_end"]) < now}
for c in [c for c in s26 if c in s25]:
    for y, s in ((2025, s25[c]), (2026, s26[c])):
        fn = os.path.join(OUT, f"{c.replace(' ', '_')}_{y}.json")
        if os.path.exists(fn): continue
        try:
            laps = [l for l in F.get("laps", session_key=s["session_key"]) if l.get("lap_duration") and not l.get("is_pit_out_lap")]
        except Exception as e:
            print(f"{c} {y}: laps unavailable ({e}) - skipped", flush=True); continue
        if not laps: print(f"{c} {y}: no laps (session not held?)", flush=True); continue
        best = min(laps, key=lambda l: l["lap_duration"]); st = F.parse_dt(best["date_start"])
        cd = F.get("car_data", session_key=s["session_key"], driver_number=best["driver_number"],
                   **{"date>": (st - timedelta(seconds=1)).isoformat(), "date<": (st + timedelta(seconds=best["lap_duration"] + 1)).isoformat()})
        json.dump(dict(circuit=c, year=y, session=s, lap=best, car_data=cd), open(fn, "w"))
        print(f"{c} {y}: drv {best['driver_number']} {best['lap_duration']:.3f}s, {len(cd)} samples", flush=True); time.sleep(1)
