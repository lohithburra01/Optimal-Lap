# One-Lap Path Scripts

Two scripts: fetch (system Python) and create path in Blender.

**Backups:**  
- `fetch_one_lap_raw_backup.py` — raw telemetry, no get_clean_trace.  
- `fetch_one_lap_backup_before_get_clean_trace.py` — before get_clean_trace cleaning.  
- `fetch_one_lap_backup_before_racing_line.py` — get_clean_trace only, no racing-line smoothing.  
- `create_lap_path_in_blender_raw_backup.py` — VECTOR handles.  
Copy over the main script to restore a previous behaviour.

---

## 1. fetch_one_lap.py (system Python)

Fetches one F1 lap and writes path points to JSON. By default keeps one point per telemetry sample; use **--point-spacing** to add more points for better track alignment.

- **--racing-line** (default) — build a path that makes sense from the data (same point count before resampling).
  - **--racing-line-method mit** (default) — MIT-thesis style: curvature + forward-looking.
  - **--racing-line-method b-spline** — smooth B-spline; **--smoothing** (default 8).
- **--no-racing-line** — output cleaned telemetry as-is (can show kinks).
- **--point-spacing N** — resample path every N meters; 0 = off (default). Interpolation can look unnatural; the API gives ~4–5 Hz (~600–800 points/lap) and that’s the real data.
- **--resample-spline N** — resample to N points via cubic spline (chord-length, periodic) for a smooth path; 0 = off. e.g. `--resample-spline 1500`.
- **--smooth** (default) / **--raw** — Blender handle hint: AUTO vs VECTOR.

MIT-style options: **--lookahead**, **--max-offset**, **--offset-smooth**.

```bash
pip install fastf1 scipy
python fetch_one_lap.py --year 2024 --round 3 --session Race --driver NOR --out lap_path.json
python fetch_one_lap.py --year 2024 --round 3 --session Race --driver NOR --out lap_path.json --point-spacing 2
python fetch_one_lap.py --year 2024 --round 3 --session Race --driver NOR --out lap_path.json --racing-line-method b-spline --smoothing 8
python fetch_one_lap.py --year 2024 --round 3 --session Race --driver NOR --out lap_path.json --no-racing-line
python fetch_one_lap.py --year 2024 --round 3 --session Race --driver NOR --out lap_path.json --resample-spline 1500
```

Output JSON: `points`, `closed`, `smooth`. Point count = telemetry count (~4–5 Hz from F1 API) unless **--point-spacing** is used.

**Data density:** FastF1 uses the F1 API; telemetry is stored at ~4–5 Hz. For **past** sessions there is no higher-rate or “live” source—what you get is what was stored. Capturing **live timing** during a session could in theory log at stream rate, but that’s a separate real-time pipeline; after the session, the API only has the same ~4–5 Hz data.

---

## 1b. fetch_one_lap_openf1.py (OpenF1 API)

Uses [OpenF1](https://openf1.org) (live-stream–stored data). **Historical from 2023 onwards, no auth.** Same JSON output; use with **create_lap_path_in_blender.py** as-is.

- **--country** (required) — e.g. `Australia`, `Bahrain`.
- **--session** — `Race`, `Qualifying`, etc. (default `Race`).
- **--driver** — 3-letter code (e.g. `NOR`).
- **--racing-line** (default) / **--no-racing-line** — MIT-style.
- **--scale**, **--center**, **--lookahead**, **--max-offset**, **--smooth** / **--raw** — same as FastF1 script.

```bash
python fetch_one_lap_openf1.py --year 2024 --country Australia --session Race --driver NOR --out lap_path.json
```

**OpenF1 vs FastF1:** OpenF1 location is ~3.7 Hz; FastF1 ~4–5 Hz. OpenF1 often gives *fewer* points per lap. Both use stored data; neither has higher-rate history for past sessions.

---

## 1c. path_from_live_jsonl.py (live capture)

Builds a path from **live.jsonl** (UndercutF1-style capture) using **Position.z** (~75 Hz). Same JSON output as above; use with **create_lap_path_in_blender.py**.

- **--live** — path to live.jsonl.
- **--driver** — driver number (e.g. `4` for NOR).
- **--lap N** — output only that lap (lap boundaries from position S/F crossings).
- **--fastest** — output the driver’s fastest lap (shortest duration between S/F crossings).
- **--start** / **--end** — optional UTC time trim (ISO); overrides **--lap** / **--fastest** if set.
- **--scale**, **--center**, **--on-track-only**, **--smooth** — same idea as other scripts.
- **--resample-hz N** — resample path to N points per second (linear interpolation) for a smoother curve in Blender; e.g. `--resample-hz 20` gives ~1,400 points for a 70 s lap.

```bash
python path_from_live_jsonl.py --live live.jsonl --driver 4 --out lap_path.json
python path_from_live_jsonl.py --live live.jsonl --driver 4 --lap 1 --out lap1.json
python path_from_live_jsonl.py --live live.jsonl --driver 4 --fastest --out fastest.json
python path_from_live_jsonl.py --live live.jsonl --driver 4 --fastest --out fastest.json --resample-hz 20
```

See **LIVE_JSONL_FORMAT.md** for live data format and decompression.

---

## 2. create_lap_path_in_blender.py (Blender)

Creates one curve from the JSON. If JSON has `"smooth": true`, uses **AUTO** handles for smooth interpolation; otherwise **VECTOR** (point-to-point).

1. Set **FILEPATH** at the top to your JSON.
2. Scripting workspace → Run script (Alt+P).

Curve name: **LapPath**. No addons.
