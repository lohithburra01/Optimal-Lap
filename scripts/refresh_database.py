#!/usr/bin/env python3
"""
Refresh the local F1 database files from FastF1.

Fetches event schedule, testing event info, and driver data for specified years.

Usage:
  python refresh_database.py --year 2026
  python refresh_database.py --year 2025 2026
  python refresh_database.py --year 2026 --calendar-only   # skip driver fetch (fast)

Output files (in F1_Pipeline_Assets/database/):
  - calendar_cache.json      : race calendar per year
  - drivers_by_season.json   : unique driver list per year
  - drivers_by_race.json     : driver list per race per year
  - testing_events.json      : testing event locations per year
"""

import argparse
import json
import os
import sys
import time


def get_db_dir():
    """Resolve database directory relative to this script."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "F1_Pipeline_Assets", "database")


def load_json(path):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  [OK] Saved {path}")


def refresh_year(year, calendar_only=False):
    import fastf1

    cache_dir = os.path.join(os.path.dirname(__file__) or ".", "fastf1_cache")
    os.makedirs(cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)

    db_dir = get_db_dir()
    os.makedirs(db_dir, exist_ok=True)

    # Load existing files so we can merge
    cal_path = os.path.join(db_dir, "calendar_cache.json")
    drv_race_path = os.path.join(db_dir, "drivers_by_race.json")
    drv_season_path = os.path.join(db_dir, "drivers_by_season.json")
    test_path = os.path.join(db_dir, "testing_events.json")

    calendar = load_json(cal_path)
    drv_by_race = load_json(drv_race_path)
    drv_by_season = load_json(drv_season_path)
    testing_events = load_json(test_path)

    year_str = str(year)

    # ── 1. FETCH EVENT SCHEDULE ──────────────────────────────────────────
    print(f"\n[*] Fetching {year} event schedule...")
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=True)
    except Exception as e:
        print(f"  [X] Failed to load schedule for {year}: {e}")
        return

    # ── 2. BUILD CALENDAR (race events only) ─────────────────────────────
    race_events = []
    for _, ev in schedule.iterrows():
        if ev['EventFormat'] == 'testing':
            continue
        race_events.append({
            "round": int(ev['RoundNumber']),
            "event_name": ev['EventName'],
            "location": ev['Location'],
            "country": ev['Country'],
        })

    calendar[year_str] = race_events
    save_json(cal_path, calendar)
    print(f"  [*] {len(race_events)} race events for {year}")

    # ── 3. BUILD TESTING EVENTS ──────────────────────────────────────────
    test_list = []
    test_counter = 0
    for _, ev in schedule.iterrows():
        if ev['EventFormat'] != 'testing':
            continue
        test_counter += 1
        test_list.append({
            "test_number": test_counter,
            "event_name": ev['EventName'],
            "location": ev['Location'],
            "country": ev['Country'],
        })

    testing_events[year_str] = test_list
    save_json(test_path, testing_events)
    print(f"  [*] {len(test_list)} testing events for {year}")

    if calendar_only:
        print(f"  [>] Skipping driver fetch (--calendar-only)")
        return

    # ── 4. FETCH DRIVERS PER RACE ────────────────────────────────────────
    print(f"\n[*] Fetching drivers for {year} (this may take a while)...")
    race_drivers = {}
    all_drivers = {}  # code -> driver dict (deduped for season)

    for ev_info in race_events:
        event_name = ev_info['event_name']
        print(f"  [...] Loading {event_name}...", end=" ", flush=True)
        try:
            session = fastf1.get_session(year, ev_info['round'], 'Race')
            session.load(telemetry=False, laps=True, weather=False, messages=False)
        except Exception as e:
            print(f"[!] {e}")
            race_drivers[event_name] = []
            time.sleep(1)
            continue

        drivers_list = []
        try:
            results = session.results
            if results is not None and not results.empty:
                for _, row in results.iterrows():
                    code = str(row.get('Abbreviation', ''))
                    if not code or code == 'nan':
                        continue
                    entry = {
                        "code": code,
                        "number": str(row.get('DriverNumber', '')),
                        "full_name": f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip(),
                        "first_name": str(row.get('FirstName', '')),
                        "last_name": str(row.get('LastName', '')),
                        "team": str(row.get('TeamName', '')),
                        "team_raw": str(row.get('TeamName', '')),
                    }
                    drivers_list.append(entry)
                    all_drivers[code] = entry
        except Exception as e:
            print(f"[!] parse error: {e}")

        race_drivers[event_name] = drivers_list
        print(f"[OK] {len(drivers_list)} drivers")
        time.sleep(0.5)  # Be kind to the API

    drv_by_race[year_str] = race_drivers
    save_json(drv_race_path, drv_by_race)

    drv_by_season[year_str] = list(all_drivers.values())
    save_json(drv_season_path, drv_by_season)
    print(f"  [*] {len(all_drivers)} unique drivers for {year} season")


def main():
    ap = argparse.ArgumentParser(description="Refresh F1 database from FastF1")
    ap.add_argument("--year", type=int, nargs='+', required=True,
                    help="Year(s) to refresh, e.g. --year 2025 2026")
    ap.add_argument("--calendar-only", action="store_true",
                    help="Only fetch calendar + testing info, skip driver data")
    args = ap.parse_args()

    print("=" * 60)
    print("F1 Database Refresh Tool")
    print(f"Target years: {args.year}")
    print(f"Database dir: {get_db_dir()}")
    print("=" * 60)

    for y in args.year:
        refresh_year(y, calendar_only=args.calendar_only)

    print("\n[OK] All done!")


if __name__ == "__main__":
    main()
