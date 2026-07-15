"""fetch_openf1_lap.py

Alternative to fetch_fastest_lap.py that pulls from the OpenF1 API
(https://openf1.org) instead of FastF1/Ergast. OpenF1 usually publishes a
session's laps + car telemetry much sooner than the FastF1 archive, so this
is the go-to right after a session ends.

Writes the SAME CSV schema raceline_video.py / the sim comparison tools consume:
  frame,time_s,distance,speed,throttle,brake,gear,rpm,ers_deploy

Distance is integrated from the speed channel (OpenF1 car_data ~3-4 Hz); for a
speed-vs-distance overlay that is plenty. ers_deploy is not exposed by OpenF1
car_data, so it is written as 0.

Usage:
  python fetch_openf1_lap.py --year 2026 --country Spain --session "Practice 1" \
      --out F1_Pipeline_Assets/exports/reference_2026_spain_q.csv
"""
import argparse, csv, json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta

BASE = "https://api.openf1.org/v1"


def get(endpoint, **params):
    url = f"{BASE}/{endpoint}?" + urllib.parse.urlencode(params, safe="><=")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.load(r)
        except Exception as e:               # noqa: BLE001
            if attempt == 3:
                raise
            print(f"[openf1] retry {attempt+1} on {endpoint}: {e}", flush=True)
    return []


def parse_dt(s):
    return datetime.fromisoformat(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--country", required=True, help='OpenF1 country_name, e.g. "Spain"')
    ap.add_argument("--session", default="Qualifying",
                    help='session_name: "Practice 1", "Qualifying", "Race", ...')
    ap.add_argument("--circuit", default=None,
                    help='circuit_short_name filter, e.g. "Miami" — needed when a '
                         'country hosts several GPs (United States: Miami/Austin/Las Vegas)')
    ap.add_argument("--out", required=True)
    ap.add_argument("--driver", type=int, default=None,
                    help="driver_number; default = fastest-lap driver of the session")
    args = ap.parse_args()

    print(f"[openf1] sessions year={args.year} country={args.country} "
          f"session={args.session!r}", flush=True)
    sessions = get("sessions", year=args.year, country_name=args.country,
                   session_name=args.session)
    if args.circuit:
        sessions = [s for s in sessions
                    if s.get("circuit_short_name", "").lower() == args.circuit.lower()]
    if not sessions:
        print("[openf1] no matching session", file=sys.stderr); sys.exit(2)
    if len(sessions) > 1:
        names = {s.get("circuit_short_name") for s in sessions}
        if len(names) > 1:
            print(f"[openf1] ambiguous: {sorted(names)} — pass --circuit",
                  file=sys.stderr); sys.exit(2)
    sk = sessions[0]["session_key"]
    print(f"[openf1] session_key={sk} ({sessions[0].get('circuit_short_name')})", flush=True)

    laps = get("laps", session_key=sk)
    valid = [l for l in laps if l.get("lap_duration") and not l.get("is_pit_out_lap")]
    if not valid:
        print("[openf1] no valid laps yet (data may still be publishing)",
              file=sys.stderr); sys.exit(3)
    valid.sort(key=lambda l: l["lap_duration"])
    fast = valid[0]
    drv = args.driver or fast["driver_number"]
    if args.driver:                          # re-pick that driver's fastest
        dv = [l for l in valid if l["driver_number"] == drv]
        if not dv:
            print(f"[openf1] driver {drv} has no valid lap", file=sys.stderr); sys.exit(3)
        fast = dv[0]
    dur = fast["lap_duration"]
    start = parse_dt(fast["date_start"])
    end = start + timedelta(seconds=dur + 0.5)
    print(f"[openf1] fastest: drv {drv} lap {fast['lap_number']} {dur:.3f}s "
          f"start {fast['date_start']}", flush=True)

    cd = get("car_data", session_key=sk, driver_number=drv,
             **{"date>": start.isoformat(), "date<": end.isoformat()})
    cd = [c for c in cd if c.get("speed") is not None]
    cd.sort(key=lambda c: c["date"])
    # dedup identical timestamps
    seen, rows_cd = set(), []
    for c in cd:
        if c["date"] in seen:
            continue
        seen.add(c["date"]); rows_cd.append(c)
    if len(rows_cd) < 20:
        print(f"[openf1] only {len(rows_cd)} telemetry samples in window — "
              f"car_data may not be published yet", file=sys.stderr); sys.exit(3)

    t0 = parse_dt(rows_cd[0]["date"])
    rows, dist, prev_t, prev_v = [], 0.0, None, None
    for i, c in enumerate(rows_cd):
        t = (parse_dt(c["date"]) - t0).total_seconds()
        v = float(c["speed"])               # km/h
        vms = v / 3.6
        if prev_t is not None:
            dt = t - prev_t
            dist += 0.5 * (vms + prev_v) * dt   # trapezoid integrate speed
        prev_t, prev_v = t, vms
        br = c.get("brake", 0) or 0
        rows.append({
            "frame": i, "time_s": round(t, 4), "distance": round(dist, 3),
            "speed": round(v, 3),
            "throttle": round(float(c.get("throttle", 0) or 0), 2),
            "brake": round(float(br), 2),
            "gear": int(c.get("n_gear", 0) or 0),
            "rpm": int(c.get("rpm", 0) or 0),
            "ers_deploy": 0,
        })

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["frame", "time_s", "distance", "speed",
                                          "throttle", "brake", "gear", "rpm", "ers_deploy"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[openf1] wrote {len(rows)} rows to {args.out}", flush=True)
    print(f"[openf1] lap_time={rows[-1]['time_s']:.3f}s  distance={rows[-1]['distance']:.0f}m  "
          f"driver={drv}  (lap_duration={dur:.3f}s)", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
