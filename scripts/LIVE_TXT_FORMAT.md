# live.txt — F1 live-session stream format

`live.txt` is **stored data from the F1 live timing stream** (one JSON object per line).  
Date in your sample: **2024-05-18** (Imola — Sprint Qualifying).

---

## Does it have track position (x, y, z) data?

**No.** This stream contains **timing and classification** only, not car location on the track.

- **Position** in the payload means **race position** (1st, 2nd, 3rd…), not x,y,z coordinates.
- There are **no** `PositionStream`, `LocationStream`, or any message type with `x`, `y`, `z` in this file.
- Building a **lap path** (curve for Blender) requires **location/telemetry** (e.g. FastF1 `get_telemetry()` or OpenF1 `/location`). This file cannot be used for that.

---

## What message types are in the file?

| Type             | Meaning |
|------------------|--------|
| **TimingData**   | Race order, sector/segment crossings, pit status, lap count, speeds at timing loops (I1, I2, ST, FL). |
| **TimingAppData**| Stints, tyre compound. |
| **TimingStats**  | Best sectors, best speeds per driver. |
| **Heartbeat**    | Keep-alive (~every 15 s). |
| **DriverList**   | Driver order (Line 1–20). |
| **TopThree**     | Top 3 drivers, TLA, team, LapState. |
| **WeatherData**  | Air/track temp, wind, pressure, etc. |
| **SessionData**  | Session status (e.g. Started). |
| **RaceControlMessages** | Flags, messages. |
| **ExtrapolatedClock**   | Session clock, remaining time. |
| **TrackStatus**  | Track status. |

---

## Update frequency (from your sample)

- **TimingData:** ~1.5 Hz on average (message every ~0.65 s when something changes — segment crossing, position change, etc.). Event-driven, not a fixed sample rate.
- **Heartbeat:** ~every 15 s.
- No continuous position stream → **no frequency for “points along the lap”**, because there are no such points in this feed.

---

## How to interpret each line

Each line is a single JSON object:

```json
{
  "H": "Streaming",
  "M": "feed",
  "A": [ "MessageType", { ...payload... }, "2024-05-18T14:00:05.043Z" ]
}
```

- **`A[0]`** — Message type (e.g. `"TimingData"`, `"Heartbeat"`).
- **`A[1]`** — Payload (object; structure depends on type).
- **`A[2]`** — Timestamp (UTC, ISO 8601).

**Driver identification:** Drivers are keyed by **racing number** (e.g. `"4"` = Lando Norris, `"10"` = Pierre Gasly). `TimingData.Lines` and similar use these numbers.

**Segment/Sector:** `TimingData` includes `Sectors` → `Segments` with `Status` (e.g. 2049, 2051, 2064). These indicate progress through mini-sectors, not x,y,z.

---

## Summary

| Question | Answer |
|----------|--------|
| Does it have data? | Yes — timing, order, sectors, speeds at timing loops, weather, etc. |
| Does it have **track position** (x,y,z)? | **No.** |
| Frequency of position updates? | N/A (no position data). TimingData ~1.5 Hz for *timing* updates. |
| Can we build a lap path from it? | **No.** Use FastF1 telemetry or OpenF1 `/location` for path points. |

To get **more points along the lap** you need a feed or API that provides **car location** (x, y, z or equivalent), which the public live timing stream does not expose in this format.
