# live.jsonl — F1 live stream capture (UndercutF1-style)

One JSON object per line. Each line has:

- **`Type`** — Message type (e.g. `TimingData`, `Position.z`, `CarData.z`).
- **`Json`** — Payload. For most types this is an object; for **`Position.z`** and **`CarData.z`** it is a **base64-encoded, raw-deflate compressed** string.
- **`DateTime`** — Timestamp (UTC).

---

## Position data (track x,y,z)

**Type:** `Position.z`  
**Count in your file:** 4,991 records (Qualifying).

**Decompression:**

1. Base64-decode the `Json` string.
2. Decompress with **raw deflate** (no zlib header):  
   `zlib.decompress(raw, -zlib.MAX_WBITS)`
3. Parse the result as JSON.

**Decompressed structure:**

```json
{
  "Position": [
    {
      "Timestamp": "2025-11-22T03:46:40.6348434Z",
      "Entries": {
        "1": { "Status": "OnTrack", "X": 1234, "Y": 5678, "Z": 90 },
        "4": { "Status": "OnTrack", "X": ..., "Y": ..., "Z": ... }
      }
    }
  ]
}
```

- **`Position`** is an **array** of snapshots (each snapshot = one timestamp, all drivers).
- **`Entries`** is keyed by **driver number** (string: `"1"`, `"4"`, etc.).
- **`X`, `Y`, `Z`** — coordinates in **centimeters** (per MASTER_DATA_GUIDE).
- **`Status`** — e.g. `"OnTrack"`, `"OffTrack"`.

So **lap path (x,y,z) for Blender** can be built from `Position.z` by: decompressing each line, iterating `Position[]` → `Entries` for one driver, collecting (X, Y, Z) and timestamp, then optionally filtering by lap (e.g. by time range) and applying scale/center like the other scripts.

---

## What rate does your live.jsonl actually have?

The effective position rate is **message rate × snapshots per message**. The script uses every snapshot; it doesn’t drop data.

To measure your file:

```bash
python inspect_position_z.py live.jsonl 4
```

Example output (from one Qualifying capture):

- **Position.z lines:** ~4,500 (messages).
- **Snapshots per line:** 1–7, avg ~3.9 (each message is a batch of timestamps).
- **Message interval:** median ~960 ms ⇒ ~1 message/sec.
- **Effective rate:** ~1 msg/s × 3.9 snap/msg ⇒ **~4 Hz** per driver.

So that file is **~4 Hz**, similar to FastF1/OpenF1. Points per lap = rate × lap time (e.g. 4 × 90 ≈ 360 points per 90 s lap). If your capture delivers Position.z more often (e.g. 20 ms between messages) or with more snapshots per message, you’ll get higher rate and more points per lap; the table below is “up to” when the feed is high-rate.

---

## How much better than FastF1 / OpenF1?

| Source            | Typical rate (per driver) | Points per 90s lap | Use for path? |
|-------------------|---------------------------|---------------------|----------------|
| **live.jsonl (Position.z)** | **Depends on capture** (e.g. ~4 Hz or up to ~75 Hz) | **~350–6,750** | ✅ Yes (`path_from_live_jsonl.py`) |
| FastF1 telemetry  | ~4–5 Hz                   | ~400–500            | ✅ Yes (`fetch_one_lap.py`) |
| OpenF1 location   | ~3.7 Hz                   | ~330                | ✅ Yes (`fetch_one_lap_openf1.py`) |

If the live feed delivers Position.z at high rate (e.g. ~75 Hz), you get ~15–20× more points per lap than FastF1/OpenF1. If it batches to ~1 msg/s with ~4 snapshots/msg (as in the inspected file), you get ~4 Hz, similar to FastF1. Use **`inspect_position_z.py`** on your `live.jsonl` to see your actual rate.

---

## Other message types in this file

| Type | Count (this file) | Description |
|------|-------------------|-------------|
| TimingData | 10,938 | Positions, sectors, gaps, lap times |
| **Position.z** | **4,991** | **GPS positions (compressed)** |
| CarData.z | 4,946 | Telemetry: speed, RPM, gear, throttle, brake, DRS (compressed) |
| TimingStats | 1,354 | Speed traps |
| TimingAppData | 695 | Tyres, stints |
| Heartbeat | 420 | Keep-alive |
| DriverList | 262 | Driver info |
| TopThree | 236 | Top 3 |
| … | … | RaceControlMessages, WeatherData, SessionData, etc. |

---

## Scripts

**`inspect_position_z.py`** — Inspect your `live.jsonl`: Position.z message count, snapshots per message, effective Hz per driver, and gap stats. Usage:

```bash
python inspect_position_z.py live.jsonl 4
```

**`decompress_position_z.py`** — Reads `live.jsonl`, finds the first `Position.z` line, decompresses it, and prints the structure. Usage:

```bash
python decompress_position_z.py live.jsonl
```

**Yes — you can use this to create a path.** Use the script below; it outputs the same JSON as `fetch_one_lap.py` so **create_lap_path_in_blender.py** works as-is.

---

## Script: path_from_live_jsonl.py

Builds a path from `live.jsonl` and writes the same JSON as the other fetch scripts (for use with **create_lap_path_in_blender.py**).

```bash
python path_from_live_jsonl.py --live live.jsonl --driver 4 --out lap_path.json
```

- **--driver** — Driver number (e.g. `4` = Norris, `63` = Russell).
- **--out** — Output JSON (default `lap_path.json`).
- **--scale** — Default `0.001` (cm → same Blender scale as FastF1).
- **--center** / **--no-center** — Center track at origin (default center).
- **--start**, **--end** — Optional ISO UTC times to trim to one lap (e.g. `--start 2025-11-22T03:50:00Z --end 2025-11-22T03:51:30Z`).
- **--on-track-only** — Skip OffTrack points (default True).
- **--smooth** — Set `smooth: true` in JSON for Blender AUTO handles (default True).

Output: **points**, **closed**, **smooth** — same format as `fetch_one_lap.py`, so you can open it in Blender with **create_lap_path_in_blender.py**.
