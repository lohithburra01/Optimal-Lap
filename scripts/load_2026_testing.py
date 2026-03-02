#!/usr/bin/env python3
"""
Load 2026 F1 pre-season testing data via FastF1.
Run: py scripts/load_2026_testing.py

API: fastf1.get_testing_session(year, test_number, session_number)
- test_number: 1 = first test (Feb 11-13), 2 = second test (Feb 18-20)
- session_number: 1 = Day 1, 2 = Day 2, 3 = Day 3
"""
import os
import sys

def main():
    try:
        import fastf1
    except ImportError:
        print("ERROR: fastf1 not installed. Run: py -m pip install fastf1>=3.8.1")
        return 1

    print(f"FastF1 version: {getattr(fastf1, '__version__', 'unknown')}")
    cache_dir = os.path.join(os.path.dirname(__file__), "..", "scripts", "fastf1_cache")
    os.makedirs(cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)
    print(f"Cache: {cache_dir}\n")

    # 2026 Pre-Season: Test 1 = Feb 11-13 (Day 1,2,3), Test 2 = Feb 18-20 (Day 1,2,3)
    to_try = [
        (2026, 1, 1, "2026 Test 1 Day 1"),
        (2026, 1, 2, "2026 Test 1 Day 2"),
        (2026, 1, 3, "2026 Test 1 Day 3"),
        (2026, 2, 1, "2026 Test 2 Day 1"),
    ]
    for year, test_num, session_num, label in to_try:
        print(f"--- {label}: get_testing_session({year}, {test_num}, {session_num}) ---")
        try:
            session = fastf1.get_testing_session(year, test_num, session_num)
            session.load(telemetry=True, laps=True, weather=False, messages=False)
            if session.laps is not None and not session.laps.empty:
                # Driver column can be number (str) or abbreviation depending on FastF1
                drivers = session.laps["Driver"].unique().tolist()
                n_laps = len(session.laps)
                print(f"  OK: {len(drivers)} drivers, {n_laps} laps")
                print(f"  Drivers: {drivers[:10]}{'...' if len(drivers) > 10 else ''}")
            else:
                print("  OK but no laps (empty).")
        except Exception as e:
            print(f"  FAILED: {e}")
        print()

    print("=" * 60)
    print("2026 pre-season testing loads with:")
    print("  fastf1.get_testing_session(2026, test_number, session_number)")
    print("  test_number: 1 = first test (Feb 11-13), 2 = second test (Feb 18-20)")
    print("  session_number: 1 = Day 1, 2 = Day 2, 3 = Day 3")
    print("In Blender: use Hot Lap panel, Event Type = Testing, pick Test 1/2 and Day 1/2/3.")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
