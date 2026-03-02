#!/usr/bin/env python3
"""One-off: Add 2026 driver list to database (same format as 2025)."""
import json
import os

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "F1_Pipeline_Assets", "database")

# 2026 grid (confirmed from F1.com driver numbers + team lineups)
# Format: code, number, full_name, first_name, last_name, team, team_raw
DRIVERS_2026 = [
    {"code": "NOR", "number": "1", "full_name": "Lando Norris", "first_name": "Lando", "last_name": "Norris", "team": "McLaren", "team_raw": "McLaren"},
    {"code": "PIA", "number": "81", "full_name": "Oscar Piastri", "first_name": "Oscar", "last_name": "Piastri", "team": "McLaren", "team_raw": "McLaren"},
    {"code": "VER", "number": "3", "full_name": "Max Verstappen", "first_name": "Max", "last_name": "Verstappen", "team": "Red Bull Racing", "team_raw": "Red Bull Racing"},
    {"code": "HAD", "number": "6", "full_name": "Isack Hadjar", "first_name": "Isack", "last_name": "Hadjar", "team": "Red Bull Racing", "team_raw": "Red Bull Racing"},
    {"code": "RUS", "number": "63", "full_name": "George Russell", "first_name": "George", "last_name": "Russell", "team": "Mercedes", "team_raw": "Mercedes"},
    {"code": "ANT", "number": "12", "full_name": "Kimi Antonelli", "first_name": "Kimi", "last_name": "Antonelli", "team": "Mercedes", "team_raw": "Mercedes"},
    {"code": "LEC", "number": "16", "full_name": "Charles Leclerc", "first_name": "Charles", "last_name": "Leclerc", "team": "Ferrari", "team_raw": "Ferrari"},
    {"code": "HAM", "number": "44", "full_name": "Lewis Hamilton", "first_name": "Lewis", "last_name": "Hamilton", "team": "Ferrari", "team_raw": "Ferrari"},
    {"code": "ALO", "number": "14", "full_name": "Fernando Alonso", "first_name": "Fernando", "last_name": "Alonso", "team": "Aston Martin", "team_raw": "Aston Martin"},
    {"code": "STR", "number": "18", "full_name": "Lance Stroll", "first_name": "Lance", "last_name": "Stroll", "team": "Aston Martin", "team_raw": "Aston Martin"},
    {"code": "ALB", "number": "23", "full_name": "Alexander Albon", "first_name": "Alexander", "last_name": "Albon", "team": "Williams", "team_raw": "Williams"},
    {"code": "SAI", "number": "55", "full_name": "Carlos Sainz", "first_name": "Carlos", "last_name": "Sainz", "team": "Williams", "team_raw": "Williams"},
    {"code": "GAS", "number": "10", "full_name": "Pierre Gasly", "first_name": "Pierre", "last_name": "Gasly", "team": "Alpine", "team_raw": "Alpine"},
    {"code": "COL", "number": "43", "full_name": "Franco Colapinto", "first_name": "Franco", "last_name": "Colapinto", "team": "Alpine", "team_raw": "Alpine"},
    {"code": "BOR", "number": "5", "full_name": "Gabriel Bortoleto", "first_name": "Gabriel", "last_name": "Bortoleto", "team": "Audi", "team_raw": "Audi"},
    {"code": "HUL", "number": "27", "full_name": "Nico Hulkenberg", "first_name": "Nico", "last_name": "Hulkenberg", "team": "Audi", "team_raw": "Audi"},
    {"code": "BEA", "number": "87", "full_name": "Oliver Bearman", "first_name": "Oliver", "last_name": "Bearman", "team": "Haas F1 Team", "team_raw": "Haas F1 Team"},
    {"code": "OCO", "number": "31", "full_name": "Esteban Ocon", "first_name": "Esteban", "last_name": "Ocon", "team": "Haas F1 Team", "team_raw": "Haas F1 Team"},
    {"code": "LAW", "number": "30", "full_name": "Liam Lawson", "first_name": "Liam", "last_name": "Lawson", "team": "Racing Bulls", "team_raw": "Racing Bulls"},
    {"code": "LIN", "number": "41", "full_name": "Arvid Lindblad", "first_name": "Arvid", "last_name": "Lindblad", "team": "Racing Bulls", "team_raw": "Racing Bulls"},
    {"code": "PER", "number": "11", "full_name": "Sergio Perez", "first_name": "Sergio", "last_name": "Perez", "team": "Cadillac", "team_raw": "Cadillac"},
    {"code": "BOT", "number": "77", "full_name": "Valtteri Bottas", "first_name": "Valtteri", "last_name": "Bottas", "team": "Cadillac", "team_raw": "Cadillac"},
]

def main():
    os.makedirs(DB_DIR, exist_ok=True)

    # 1. drivers_by_season.json
    season_path = os.path.join(DB_DIR, "drivers_by_season.json")
    with open(season_path, encoding="utf-8") as f:
        season = json.load(f)
    season["2026"] = DRIVERS_2026
    with open(season_path, "w", encoding="utf-8") as f:
        json.dump(season, f, indent=2, ensure_ascii=False)
    print(f"Updated drivers_by_season.json: 2026 = {len(DRIVERS_2026)} drivers")

    # 2. drivers_by_race.json — 2026 events get same driver list per race
    cal_path = os.path.join(DB_DIR, "calendar_cache.json")
    with open(cal_path, encoding="utf-8") as f:
        calendar = json.load(f)
    events_2026 = [e["event_name"] for e in calendar.get("2026", [])]

    race_path = os.path.join(DB_DIR, "drivers_by_race.json")
    with open(race_path, encoding="utf-8") as f:
        by_race = json.load(f)
    by_race["2026"] = {event_name: list(DRIVERS_2026) for event_name in events_2026}

    with open(race_path, "w", encoding="utf-8") as f:
        json.dump(by_race, f, indent=2, ensure_ascii=False)
    print(f"Updated drivers_by_race.json: 2026 = {len(events_2026)} events")

if __name__ == "__main__":
    main()
