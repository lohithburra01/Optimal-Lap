# 📘 MASTER DATA GUIDE - Complete F1 Timing Data Reference

**Everything you need to understand, access, and analyze F1 timing data from the UndercutF1 system.**

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Data Formats](#data-formats)
3. [File Structure](#file-structure)
4. [CSV Files Reference](#csv-files-reference)
5. [JSON Files Reference](#json-files-reference)
6. [Complete Data Points](#complete-data-points)
7. [Message Types](#message-types)
8. [Code Examples](#code-examples)
9. [Status Codes & Enums](#status-codes--enums)
10. [FAQ](#faq)

---

## 📖 Overview

### What is This?

The UndercutF1 system captures **every single data point** from Formula 1's live timing feed and exports it in two formats:

- **CSV files** - Easy to analyze in Excel, Python pandas, R, etc.
- **JSON files** - Full structured data for programmatic access

### Data Sources

1. **F1 Live Timing API** - Official F1 timing data via SignalR
2. **UndercutF1.Console** (C#) - Connects to F1 API, writes to `live.jsonl`
3. **undercut-f1-api** (Python) - Reads `live.jsonl`, exports to CSV + JSON

### Sessions Available

- **Las Vegas Race** - `C:\Users\bhavi\AppData\Local\undercut-f1\data\2025_Las_Vegas_Race\Race_2\`
- **Las Vegas Qualifying** - `C:\Users\bhavi\AppData\Local\undercut-f1\data\2025_Las_Vegas_Qualifying\Qualifying\`

---

## 📊 Data Formats

### CSV Format

**Purpose:** Easy analysis in spreadsheet tools

**Structure:**
- One row per data point update
- Headers match DATA_POINTS.md field names
- Timestamps in ISO 8601 format (UTC)
- Empty cells = no data for that field

**Example:**
```csv
timestamp,driver_number,position,best_lap_time,gap_to_leader
2025-11-23T03:20:15.9050631+00:00,1,1,1:32.123,LEADER
2025-11-23T03:20:15.9050631+00:00,4,2,1:32.456,+0.333
```

### JSON Format (JSONL)

**Purpose:** Full structured data with nested objects

**Structure:**
- One JSON object per line (JSON Lines format)
- Each line is a complete, valid JSON object
- Stream-friendly (can process line-by-line)
- Preserves all nested structures

**Example:**
```json
{"timestamp": "2025-11-23T03:20:15.9050631+00:00", "type": "TimingData", "data": {"Lines": {"1": {"Position": "1", "BestLapTime": {"Value": "1:32.123"}}}}}
```

---

## 📁 File Structure

### Directory Layout

```
2025_Las_Vegas_Race/
├── live.jsonl                    # Raw F1 data stream (source)
├── Race_2/                       # Processed exports
│   ├── *.csv                     # 16 CSV files
│   └── json/
│       └── *.jsonl               # 19 JSON files
```

### CSV Files (16 files)

| File | Purpose | Rows (Race) | Rows (Qual) |
|------|---------|-------------|-------------|
| `timing_tower.csv` | Main timing screen | 46,159 | 14,030 |
| `driver_tracker_telemetry.csv` | Speed, RPM, gear, etc. | 627,981 | 371,481 |
| `driver_tracker_position.csv` | GPS coordinates | 32,354 | 19,219 |
| `mini_sectors.csv` | 22 mini-sector segments | 21,649 | 8,571 |
| `timing_stats.csv` | Speed trap data | 1,811 | 3,878 |
| `tyre_stints.csv` | Tyre strategy | 1,309 | 678 |
| `weather.csv` | Weather conditions | 142 | 86 |
| `race_control.csv` | Flags, penalties | 61 | 190 |
| `team_radio.csv` | Radio messages | 83 | 8 |
| `championship_drivers.csv` | Driver standings | 193 | 1 |
| `championship_teams.csv` | Team standings | 164 | 1 |
| `pit_stops.csv` | Pit stop times | 5 | 1 |
| `pit_lane_times.csv` | Pit lane duration | 24 | 62 |
| `track_status.csv` | Track status changes | 16 | 52 |
| `lap_count.csv` | Lap counter | 51 | 1 |
| `session_info.csv` | Session metadata | 1 | 1 |

**Total:** ~731,373 rows (Race), ~418,256 rows (Qualifying)

### JSON Files (19 files for Race, 15 for Qualifying)

| File | Purpose | Records (Race) | Records (Qual) |
|------|---------|----------------|----------------|
| `timingdata.jsonl` | Timing tower data | 44,222 | 10,938 |
| `cardata.jsonl` | Telemetry (decompressed) | 8,283 | 4,946 |
| `position.jsonl` | GPS positions (decompressed) | 8,372 | 4,991 |
| `timingstats.jsonl` | Speed traps | 1,510 | 1,354 |
| `topthree.jsonl` | Top 3 positions | 2,333 | 236 |
| `timingappdata.jsonl` | Tyre data | 945 | 695 |
| `driverlist.jsonl` | Driver info | 123 | 262 |
| `racecontrolmessages.jsonl` | Race control | 61 | 190 |
| `weatherdata.jsonl` | Weather | 141 | 85 |
| `heartbeat.jsonl` | System heartbeat | 643 | 420 |
| `sessiondata.jsonl` | Session info | 70 | 66 |
| `trackstatus.jsonl` | Track status | 15 | 51 |
| `teamradio.jsonl` | Team radio | 23 | 7 |
| `lapcount.jsonl` | Lap count | 50 | - |
| `championshipprediction.jsonl` | Championship | 71 | - |
| `pitstopseries.jsonl` | Pit stops | 22 | - |
| `pitstop.jsonl` | Pit stop details | 22 | - |
| `pitlanetimecollection.jsonl` | Pit lane times | 46 | 122 |
| `extrapolatedclock.jsonl` | Session clock | 3 | 10 |

**Total:** 66,952 records (Race), 24,373 records (Qualifying)

---

## 📄 CSV Files Reference

### 1. timing_tower.csv

**Purpose:** Main timing screen - positions, gaps, lap times, sectors

**Columns (42):**
```
timestamp, driver_number, driver_tla, team_name, team_color,
position, position_change, best_lap_time, last_lap_time,
gap_to_leader, smart_gap_to_leader, interval_to_ahead,
sector_0_value, sector_0_status, sector_1_value, sector_1_status, sector_2_value, sector_2_status,
pit_stops, in_pit, pit_out,
tyre_compound, tyre_age, tyre_is_new,
speed_i1_value, speed_i1_position, speed_i2_value, speed_i2_position,
speed_fl_value, speed_fl_position, speed_st_value, speed_st_position,
lap_current, lap_total,
session_name, session_location, session_circuit_key, session_session_key,
track_status, track_status_message
```

**Example:**
```csv
timestamp,driver_number,driver_tla,team_name,position,best_lap_time,gap_to_leader
2025-11-23T03:20:15.9050631+00:00,1,VER,Red Bull Racing,1,1:32.123,LEADER
2025-11-23T03:20:15.9050631+00:00,4,NOR,McLaren,2,1:32.456,+0.333
```

**Key Fields:**
- `position_change` - Computed: negative = gained positions, positive = lost
- `smart_gap_to_leader` - Computed: "LEADER", "+1.234", or "2L" (laps down)
- `sector_X_status` - Status code: 2051 (purple), 2049 (green), 2048 (yellow), 0 (white)

---

### 2. driver_tracker_telemetry.csv

**Purpose:** Real-time car telemetry data

**Columns (8):**
```
timestamp, driver_number, speed, rpm, gear, throttle, brake, drs
```

**Example:**
```csv
timestamp,driver_number,speed,rpm,gear,throttle,brake,drs
2025-11-23T03:20:15.9050631+00:00,1,295,11500,7,100,0,8
```

**Field Details:**
- `speed` - Speed in km/h (0-350)
- `rpm` - Engine RPM (0-15000)
- `gear` - Current gear (0=neutral, 1-8)
- `throttle` - Throttle position 0-100%
- `brake` - Brake pressure 0-100%
- `drs` - DRS status: 0 (not available), 8 (available), 10/12/14 (activated)

**Update Frequency:** ~75 updates per second per driver

---

### 3. driver_tracker_position.csv

**Purpose:** GPS coordinates for track visualization

**Columns (6):**
```
timestamp, driver_number, position_x, position_y, position_z, status
```

**Example:**
```csv
timestamp,driver_number,position_x,position_y,position_z,status
2025-11-23T03:20:15.9050631+00:00,1,1234,5678,90,OnTrack
```

**Field Details:**
- `position_x` - X coordinate in centimeters
- `position_y` - Y coordinate in centimeters
- `position_z` - Z coordinate (elevation) in centimeters
- `status` - "OnTrack" or "OffTrack"

**Update Frequency:** ~75 updates per second per driver

---

### 4. mini_sectors.csv

**Purpose:** Mini-sector (segment) status for detailed sector analysis

**Columns (24):**
```
timestamp, driver_number,
sector_0_seg_0, sector_0_seg_1, sector_0_seg_2, sector_0_seg_3, sector_0_seg_4, sector_0_seg_5,
sector_1_seg_0, sector_1_seg_1, sector_1_seg_2, sector_1_seg_3, sector_1_seg_4, sector_1_seg_5, sector_1_seg_6,
sector_2_seg_0, sector_2_seg_1, sector_2_seg_2, sector_2_seg_3, sector_2_seg_4, sector_2_seg_5, sector_2_seg_6, sector_2_seg_7, sector_2_seg_8
```

**Example:**
```csv
timestamp,driver_number,sector_0_seg_0,sector_0_seg_1,sector_0_seg_2,...
2025-11-23T03:20:15.9050631+00:00,1,,,2048,2049,2051,,,,,,,,,,,,,,,,,
```

**Segment Breakdown (Las Vegas):**
- **Sector 0:** 6 segments
- **Sector 1:** 7 segments
- **Sector 2:** 9 segments
- **Total:** 22 mini-sectors per lap

**Status Codes:**
- `2051` = 🟣 Purple (overall fastest)
- `2049` = 🟢 Green (personal best)
- `2048` = 🟡 Yellow (slower than previous)
- `0` = ⚪ No data
- Empty = No update for this segment

**Note:** Segment count varies by circuit. Las Vegas has 22 total segments.

---

### 5. timing_stats.csv

**Purpose:** Speed trap measurements at various track locations

**Columns (5):**
```
timestamp, driver_number, trap, value, position
```

**Example:**
```csv
timestamp,driver_number,trap,value,position
2025-11-23T03:20:15.9050631+00:00,1,I1,295,3
2025-11-23T03:20:15.9050631+00:00,1,I2,310,2
2025-11-23T03:20:15.9050631+00:00,1,FL,285,5
2025-11-23T03:20:15.9050631+00:00,1,ST,320,1
```

**Trap Types:**
- `I1` - Intermediate 1 (first sector)
- `I2` - Intermediate 2 (second sector)
- `FL` - Finish Line
- `ST` - Speed Trap (fastest point on track)

**Field Details:**
- `value` - Speed in km/h
- `position` - Rank among all drivers (1 = fastest)

---

### 6. tyre_stints.csv

**Purpose:** Tyre strategy - compound, age, stint history

**Columns (8):**
```
timestamp, driver_number, driver_tla, stint_number, compound, is_new, total_laps, start_lap
```

**Example:**
```csv
timestamp,driver_number,driver_tla,stint_number,compound,is_new,total_laps,start_lap
2025-11-23T03:20:15.9050631+00:00,1,VER,0,SOFT,true,15,1
2025-11-23T03:20:15.9050631+00:00,1,VER,1,MEDIUM,true,20,16
```

**Field Details:**
- `stint_number` - 0-indexed stint number (0 = first stint)
- `compound` - "SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"
- `is_new` - true = new tyres, false = used tyres
- `total_laps` - Total laps completed on this stint
- `start_lap` - Lap number when stint started

---

### 7. weather.csv

**Purpose:** Weather conditions at the circuit

**Columns (8):**
```
timestamp, air_temp, track_temp, wind_speed, wind_direction, humidity, pressure, rainfall
```

**Example:**
```csv
timestamp,air_temp,track_temp,wind_speed,wind_direction,humidity,pressure,rainfall
2025-11-23T03:20:15.9050631+00:00,22.5,35.2,3.5,180,45,1013.2,false
```

**Field Details:**
- `air_temp` - Air temperature in °C
- `track_temp` - Track surface temperature in °C
- `wind_speed` - Wind speed in m/s
- `wind_direction` - Wind direction in degrees (0-360)
- `humidity` - Relative humidity in %
- `pressure` - Air pressure in mbar
- `rainfall` - Boolean: true if rain detected

**Update Frequency:** ~1 update per minute

---

### 8. race_control.csv

**Purpose:** Race control messages, flags, penalties

**Columns (6):**
```
timestamp, message_time, message, category, flag, lap
```

**Example:**
```csv
timestamp,message_time,message,category,flag,lap
2025-11-23T03:20:15.9050631+00:00,2025-11-23T03:20:10Z,BLUE FLAG - CAR 44,Flag,BLUE,15
2025-11-23T03:20:20.9050631+00:00,2025-11-23T03:20:15Z,TRACK CLEAR,Flag,,15
```

**Common Categories:**
- `Flag` - Flag notifications
- `Drs` - DRS zone status
- `SafetyCar` - Safety car deployment
- `Other` - General messages

**Common Flags:**
- `BLUE` - Blue flag (let faster car pass)
- `YELLOW` - Yellow flag (caution)
- `GREEN` - Green flag (all clear)
- `RED` - Red flag (session stopped)
- `BLACK AND WHITE` - Warning flag
- `BLACK` - Disqualification

---

### 9. team_radio.csv

**Purpose:** Team radio message captures

**Columns (4):**
```
timestamp, utc, driver_number, path
```

**Example:**
```csv
timestamp,utc,driver_number,path
2025-11-23T03:20:15.9050631+00:00,2025-11-23T03:20:10.000Z,1,https://livetiming.formula1.com/static/2025/2025-11-23_Race/TeamRadio/MAXVER01_1.mp3
```

**Field Details:**
- `utc` - UTC timestamp when radio was captured
- `driver_number` - Driver number
- `path` - URL to audio file (MP3)

**Note:** Audio files are hosted by F1, not stored locally

---

### 10. championship_drivers.csv

**Purpose:** Driver championship standings and predictions

**Columns (6):**
```
timestamp, driver_number, current_position, predicted_position, current_points, predicted_points
```

**Example:**
```csv
timestamp,driver_number,current_position,predicted_position,current_points,predicted_points
2025-11-23T03:20:15.9050631+00:00,1,1,1,393.0,418.0
```

---

### 11. championship_teams.csv

**Purpose:** Constructor championship standings and predictions

**Columns (6):**
```
timestamp, team_name, current_position, predicted_position, current_points, predicted_points
```

**Example:**
```csv
timestamp,team_name,current_position,predicted_position,current_points,predicted_points
2025-11-23T03:20:15.9050631+00:00,Red Bull Racing,1,1,860.0,910.0
```

---

### 12. pit_stops.csv

**Purpose:** Pit stop duration and timing

**Columns (6):**
```
timestamp, pit_timestamp, driver_number, lap, pit_stop_time, pit_lane_time
```

**Example:**
```csv
timestamp,pit_timestamp,driver_number,lap,pit_stop_time,pit_lane_time
2025-11-23T03:20:15.9050631+00:00,2025-11-23T03:20:10.000Z,1,15,2.3,25.6
```

**Field Details:**
- `pit_timestamp` - When pit stop occurred
- `lap` - Lap number of pit stop
- `pit_stop_time` - Duration in pit box (seconds)
- `pit_lane_time` - Total pit lane time (seconds)

---

### 13. pit_lane_times.csv

**Purpose:** Pit lane entry/exit timing

**Columns (4):**
```
timestamp, driver_number, lap, duration
```

**Example:**
```csv
timestamp,driver_number,lap,duration
2025-11-23T03:20:15.9050631+00:00,1,15,25.6
```

---

### 14. track_status.csv

**Purpose:** Track status changes (green, yellow, red, safety car)

**Columns (3):**
```
timestamp, track_status, track_status_message
```

**Example:**
```csv
timestamp,track_status,track_status_message
2025-11-23T03:20:15.9050631+00:00,1,AllClear
2025-11-23T03:25:30.9050631+00:00,2,Yellow
2025-11-23T03:30:45.9050631+00:00,4,SCDeployed
```

**Status Codes:**
- `1` = All Clear (Green)
- `2` = Yellow Flag
- `4` = Safety Car
- `5` = Red Flag
- `6` = Virtual Safety Car
- `7` = VSC Ending

---

### 15. lap_count.csv

**Purpose:** Current lap number and total laps

**Columns (3):**
```
timestamp, current, total
```

**Example:**
```csv
timestamp,current,total
2025-11-23T03:20:15.9050631+00:00,15,60
```

---

### 16. session_info.csv

**Purpose:** Session metadata

**Columns (5):**
```
timestamp, name, location, circuit_key, session_key
```

**Example:**
```csv
timestamp,name,location,circuit_key,session_key
2025-11-23T03:20:15.9050631+00:00,Race,Las Vegas,las-vegas,9686
```

---

## 📦 JSON Files Reference

### JSON Structure

All JSON files follow the **JSON Lines (JSONL)** format:
- One JSON object per line
- Each line is complete and valid JSON
- No commas between lines
- Stream-friendly (process line-by-line)

**Standard Format:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "MessageType",
  "data": {
    // Message-specific data
  }
}
```

---

### 1. timingdata.jsonl

**Purpose:** Complete timing tower data - positions, gaps, sectors, mini-sectors

**Record Count:** 44,222 (Race), 10,938 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "TimingData",
  "data": {
    "Lines": {
      "1": {
        "Position": "1",
        "GapToLeader": "0.000",
        "IntervalToPositionAhead": {"Value": ""},
        "BestLapTime": {"Value": "1:32.123"},
        "LastLapTime": {"Value": "1:32.456"},
        "Sectors": {
          "0": {
            "Value": "28.123",
            "Status": 2051,
            "Segments": [
              {"Status": 0},
              {"Status": 2051},
              {"Status": 2049},
              {"Status": 2048},
              {"Status": 2049},
              {"Status": 2051}
            ]
          },
          "1": {
            "Value": "35.456",
            "Status": 2049,
            "Segments": [...]
          },
          "2": {
            "Value": "31.544",
            "Status": 2048,
            "Segments": [...]
          }
        },
        "Speeds": {
          "I1": {"Value": "295", "Position": "3"},
          "I2": {"Value": "310", "Position": "2"},
          "FL": {"Value": "285", "Position": "5"},
          "ST": {"Value": "320", "Position": "1"}
        },
        "NumberOfPitStops": "1",
        "InPit": false,
        "PitOut": false
      }
    }
  }
}
```

**Key Nested Paths:**
- `data.Lines.{driver_num}.Position` - Current position
- `data.Lines.{driver_num}.BestLapTime.Value` - Best lap time
- `data.Lines.{driver_num}.Sectors.{0|1|2}.Value` - Sector time
- `data.Lines.{driver_num}.Sectors.{0|1|2}.Status` - Sector status code
- `data.Lines.{driver_num}.Sectors.{0|1|2}.Segments` - Array of mini-sector objects
- `data.Lines.{driver_num}.Speeds.{I1|I2|FL|ST}.Value` - Speed trap value

---

### 2. cardata.jsonl

**Purpose:** Real-time telemetry - speed, RPM, gear, throttle, brake, DRS

**Record Count:** 8,283 (Race), 4,946 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "CarData",
  "data": {
    "Entries": {
      "1": {
        "Channels": {
          "0": 295,    // Speed (km/h)
          "2": 11500,  // RPM
          "3": 7,      // Gear
          "4": 100,    // Throttle (%)
          "5": 0,      // Brake (%)
          "45": 8      // DRS
        }
      }
    }
  }
}
```

**Channel Mapping:**
- `0` = Speed (km/h)
- `2` = RPM
- `3` = Gear (0-8)
- `4` = Throttle (0-100%)
- `5` = Brake (0-100%)
- `45` = DRS status

**Note:** This file was originally compressed as `CarData.z` but is now decompressed during export.

---

### 3. position.jsonl

**Purpose:** GPS coordinates for track visualization

**Record Count:** 8,372 (Race), 4,991 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "Position",
  "data": {
    "Position": {
      "1": {
        "X": 1234,
        "Y": 5678,
        "Z": 90,
        "Status": "OnTrack"
      }
    }
  }
}
```

**Field Details:**
- `X`, `Y`, `Z` - Coordinates in centimeters
- `Status` - "OnTrack" or "OffTrack"

**Note:** This file was originally compressed as `Position.z` but is now decompressed during export.

---

### 4. driverlist.jsonl

**Purpose:** Driver information - names, teams, colors

**Record Count:** 123 (Race), 262 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:06:30.3700631+00:00",
  "type": "DriverList",
  "data": {
    "1": {
      "RacingNumber": "1",
      "BroadcastName": "M VERSTAPPEN",
      "FullName": "Max VERSTAPPEN",
      "Tla": "VER",
      "Line": 2,
      "TeamName": "Red Bull Racing",
      "TeamColour": "4781D7",
      "FirstName": "Max",
      "LastName": "Verstappen",
      "Reference": "MAXVER01",
      "HeadshotUrl": "https://media.formula1.com/...",
      "PublicIdRight": "common/f1/2025/redbullracing/maxver01/..."
    }
  }
}
```

**Key Fields:**
- `RacingNumber` - Driver number (e.g., "1")
- `Tla` - Three-letter abbreviation (e.g., "VER")
- `TeamName` - Full team name
- `TeamColour` - Hex color code (without #)

---

### 5. timingappdata.jsonl

**Purpose:** Tyre compound, age, stint information

**Record Count:** 945 (Race), 695 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "TimingAppData",
  "data": {
    "Lines": {
      "1": {
        "Stints": {
          "0": {
            "Compound": "SOFT",
            "New": "true",
            "TotalLaps": 15,
            "StartLaps": 1
          },
          "1": {
            "Compound": "MEDIUM",
            "New": "true",
            "TotalLaps": 20,
            "StartLaps": 16
          }
        }
      }
    }
  }
}
```

---

### 6. timingstats.jsonl

**Purpose:** Speed trap statistics

**Record Count:** 1,510 (Race), 1,354 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "TimingStats",
  "data": {
    "Lines": {
      "1": {
        "Speeds": {
          "I1": {"Value": "295", "Position": "3"},
          "I2": {"Value": "310", "Position": "2"},
          "FL": {"Value": "285", "Position": "5"},
          "ST": {"Value": "320", "Position": "1"}
        }
      }
    }
  }
}
```

---

### 7. racecontrolmessages.jsonl

**Purpose:** Race control messages, flags, penalties

**Record Count:** 61 (Race), 190 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "RaceControlMessages",
  "data": {
    "Messages": {
      "1": {
        "Utc": "2025-11-23T03:20:10.000Z",
        "Message": "BLUE FLAG - CAR 44",
        "Category": "Flag",
        "Flag": "BLUE",
        "Lap": 15
      }
    }
  }
}
```

---

### 8. weatherdata.jsonl

**Purpose:** Weather conditions

**Record Count:** 141 (Race), 85 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "WeatherData",
  "data": {
    "AirTemp": "22.5",
    "TrackTemp": "35.2",
    "WindSpeed": "3.5",
    "WindDirection": "180",
    "Humidity": "45",
    "Pressure": "1013.2",
    "Rainfall": "0"
  }
}
```

---

### 9. trackstatus.jsonl

**Purpose:** Track status changes

**Record Count:** 15 (Race), 51 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "TrackStatus",
  "data": {
    "Status": "1",
    "Message": "AllClear"
  }
}
```

---

### 10. sessiondata.jsonl

**Purpose:** Session information and metadata

**Record Count:** 70 (Race), 66 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "SessionData",
  "data": {
    "Series": "Formula 1",
    "SessionName": "Race",
    "Location": "Las Vegas",
    "CircuitKey": "las-vegas",
    "SessionKey": 9686
  }
}
```

---

### 11. championshipprediction.jsonl

**Purpose:** Championship standings and predictions

**Record Count:** 71 (Race only)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "ChampionshipPrediction",
  "data": {
    "Drivers": {
      "1": {
        "CurrentPosition": 1,
        "PredictedPosition": 1,
        "CurrentPoints": 393.0,
        "PredictedPoints": 418.0
      }
    },
    "Teams": {
      "Red Bull Racing": {
        "CurrentPosition": 1,
        "PredictedPosition": 1,
        "CurrentPoints": 860.0,
        "PredictedPoints": 910.0
      }
    }
  }
}
```

---

### 12. teamradio.jsonl

**Purpose:** Team radio message captures

**Record Count:** 23 (Race), 7 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "TeamRadio",
  "data": {
    "Captures": {
      "1": {
        "Utc": "2025-11-23T03:20:10.000Z",
        "RacingNumber": "1",
        "Path": "https://livetiming.formula1.com/static/.../MAXVER01_1.mp3"
      }
    }
  }
}
```

---

### 13. pitstopseries.jsonl / pitstop.jsonl

**Purpose:** Pit stop details and timing

**Record Count:** 22 (Race only)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "PitStopSeries",
  "data": {
    "Stops": {
      "1": {
        "Lap": 15,
        "Duration": "2.3"
      }
    }
  }
}
```

---

### 14. pitlanetimecollection.jsonl

**Purpose:** Pit lane entry/exit times

**Record Count:** 46 (Race), 122 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "PitLaneTimeCollection",
  "data": {
    "PitTimes": {
      "1": {
        "Lap": 15,
        "Duration": "25.6"
      }
    }
  }
}
```

---

### 15. topthree.jsonl

**Purpose:** Top 3 positions display

**Record Count:** 2,333 (Race), 236 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "TopThree",
  "data": {
    "Lines": {
      "1": {"RacingNumber": "1", "Tla": "VER"},
      "2": {"RacingNumber": "4", "Tla": "NOR"},
      "3": {"RacingNumber": "55", "Tla": "SAI"}
    }
  }
}
```

---

### 16. lapcount.jsonl

**Purpose:** Lap counter

**Record Count:** 50 (Race only)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "LapCount",
  "data": {
    "CurrentLap": 15,
    "TotalLaps": 60
  }
}
```

---

### 17. heartbeat.jsonl

**Purpose:** System heartbeat / keepalive

**Record Count:** 643 (Race), 420 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "Heartbeat",
  "data": {
    "Utc": "2025-11-23T03:20:15.000Z"
  }
}
```

---

### 18. extrapolatedclock.jsonl

**Purpose:** Session clock / time remaining

**Record Count:** 3 (Race), 10 (Qualifying)

**Structure:**
```json
{
  "timestamp": "2025-11-23T03:20:15.9050631+00:00",
  "type": "ExtrapolatedClock",
  "data": {
    "Utc": "2025-11-23T03:20:15.000Z",
    "Remaining": "01:45:30",
    "Extrapolating": true
  }
}
```

---

## 📊 Complete Data Points

### Detailed Field-by-Field Breakdown

This section lists **EVERY SINGLE DATA POINT** available in the exported data, matching the complete reference in DATA_POINTS.md.

---

### Per-Driver Data Points (Timing Tower)

#### Core Position & Timing Fields (15 fields)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `position` | integer | Current position | timing_tower.csv: position | data.Lines.{driver}.Position |
| `position_change` | integer | Position change (negative = gained) | timing_tower.csv: position_change | Computed |
| `driver_number` | string | Driver racing number | timing_tower.csv: driver_number | data.Lines.{driver} (key) |
| `driver_tla` | string | Driver 3-letter code | timing_tower.csv: driver_tla | driverlist.jsonl: data.{driver}.Tla |
| `team_name` | string | Team name | timing_tower.csv: team_name | driverlist.jsonl: data.{driver}.TeamName |
| `team_color` | string | Team hex color | timing_tower.csv: team_color | driverlist.jsonl: data.{driver}.TeamColour |
| `gap_to_leader` | string | Gap to leader (raw) | timing_tower.csv: gap_to_leader | data.Lines.{driver}.GapToLeader |
| `smart_gap_to_leader` | string | Smart gap ("LEADER", "+1.234", "2L") | timing_tower.csv: smart_gap_to_leader | Computed |
| `interval_to_ahead` | string | Interval to car ahead | timing_tower.csv: interval_to_ahead | data.Lines.{driver}.IntervalToPositionAhead.Value |
| `best_lap_time` | string | Best lap time | timing_tower.csv: best_lap_time | data.Lines.{driver}.BestLapTime.Value |
| `last_lap_time` | string | Last lap time | timing_tower.csv: last_lap_time | data.Lines.{driver}.LastLapTime.Value |
| `pit_stops` | integer | Number of pit stops | timing_tower.csv: pit_stops | data.Lines.{driver}.NumberOfPitStops |
| `in_pit` | boolean | Currently in pit lane | timing_tower.csv: in_pit | data.Lines.{driver}.InPit |
| `pit_out` | boolean | Just exited pit lane | timing_tower.csv: pit_out | data.Lines.{driver}.PitOut |
| `track_status` | string | Track status code | timing_tower.csv: track_status | trackstatus.jsonl: data.Status |

#### Sector Fields (6 fields: 3 sectors × 2 fields)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `sector_0_value` | string | Sector 0 time | timing_tower.csv: sector_0_value | data.Lines.{driver}.Sectors.0.Value |
| `sector_0_status` | integer | Sector 0 status code | timing_tower.csv: sector_0_status | data.Lines.{driver}.Sectors.0.Status |
| `sector_1_value` | string | Sector 1 time | timing_tower.csv: sector_1_value | data.Lines.{driver}.Sectors.1.Value |
| `sector_1_status` | integer | Sector 1 status code | timing_tower.csv: sector_1_status | data.Lines.{driver}.Sectors.1.Status |
| `sector_2_value` | string | Sector 2 time | timing_tower.csv: sector_2_value | data.Lines.{driver}.Sectors.2.Value |
| `sector_2_status` | integer | Sector 2 status code | timing_tower.csv: sector_2_status | data.Lines.{driver}.Sectors.2.Status |

#### Mini-Sector Fields (22 fields for Las Vegas: 6+7+9 segments)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `sector_0_seg_0` to `sector_0_seg_5` | integer | Sector 0 segments (6) | mini_sectors.csv | data.Lines.{driver}.Sectors.0.Segments[0-5].Status |
| `sector_1_seg_0` to `sector_1_seg_6` | integer | Sector 1 segments (7) | mini_sectors.csv | data.Lines.{driver}.Sectors.1.Segments[0-6].Status |
| `sector_2_seg_0` to `sector_2_seg_8` | integer | Sector 2 segments (9) | mini_sectors.csv | data.Lines.{driver}.Sectors.2.Segments[0-8].Status |

**Note:** Segment count varies by circuit. Las Vegas has 22 total segments.

#### Speed Trap Fields (8 fields: 4 traps × 2 fields)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `speed_trap_I1_value` | integer | Speed at Intermediate 1 (km/h) | timing_tower.csv: speed_trap_I1_value | data.Lines.{driver}.Speeds.I1.Value |
| `speed_trap_I1_position` | integer | Position rank at I1 | timing_tower.csv: speed_trap_I1_position | data.Lines.{driver}.Speeds.I1.Position |
| `speed_trap_I2_value` | integer | Speed at Intermediate 2 (km/h) | timing_tower.csv: speed_trap_I2_value | data.Lines.{driver}.Speeds.I2.Value |
| `speed_trap_I2_position` | integer | Position rank at I2 | timing_tower.csv: speed_trap_I2_position | data.Lines.{driver}.Speeds.I2.Position |
| `speed_trap_FL_value` | integer | Finish line speed (km/h) | timing_tower.csv: speed_trap_FL_value | data.Lines.{driver}.Speeds.FL.Value |
| `speed_trap_FL_position` | integer | Position rank at FL | timing_tower.csv: speed_trap_FL_position | data.Lines.{driver}.Speeds.FL.Position |
| `speed_trap_ST_value` | integer | Speed trap speed (km/h) | timing_tower.csv: speed_trap_ST_value | data.Lines.{driver}.Speeds.ST.Value |
| `speed_trap_ST_position` | integer | Position rank at ST | timing_tower.csv: speed_trap_ST_position | data.Lines.{driver}.Speeds.ST.Position |

#### Tyre Fields (3 fields)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `tyre_compound` | string | Tyre compound | timing_tower.csv: tyre_compound | timingappdata.jsonl: data.Lines.{driver}.Stints.{N}.Compound |
| `tyre_age` | integer | Laps on current tyres | timing_tower.csv: tyre_age | timingappdata.jsonl: data.Lines.{driver}.Stints.{N}.TotalLaps |
| `tyre_is_new` | boolean | New or used tyres | timing_tower.csv: tyre_is_new | timingappdata.jsonl: data.Lines.{driver}.Stints.{N}.New |

**Total Timing Tower Fields:** 15 + 6 + 22 + 8 + 3 = **54 fields per driver**

---

### Per-Driver Data Points (Telemetry & Position)

#### Telemetry Fields (6 fields)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `speed` | integer | Current speed (km/h) | driver_tracker_telemetry.csv: speed | cardata.jsonl: data.Entries.{driver}.Channels.0 |
| `rpm` | integer | Engine RPM | driver_tracker_telemetry.csv: rpm | cardata.jsonl: data.Entries.{driver}.Channels.2 |
| `gear` | integer | Current gear (0-8) | driver_tracker_telemetry.csv: gear | cardata.jsonl: data.Entries.{driver}.Channels.3 |
| `throttle` | integer | Throttle position (0-100%) | driver_tracker_telemetry.csv: throttle | cardata.jsonl: data.Entries.{driver}.Channels.4 |
| `brake` | integer | Brake pressure (0-100%) | driver_tracker_telemetry.csv: brake | cardata.jsonl: data.Entries.{driver}.Channels.5 |
| `drs` | integer | DRS status | driver_tracker_telemetry.csv: drs | cardata.jsonl: data.Entries.{driver}.Channels.45 |

#### GPS Position Fields (4 fields)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `position_x` | integer | X coordinate (cm) | driver_tracker_position.csv: position_x | position.jsonl: data.Position.{driver}.X |
| `position_y` | integer | Y coordinate (cm) | driver_tracker_position.csv: position_y | position.jsonl: data.Position.{driver}.Y |
| `position_z` | integer | Z coordinate (cm) | driver_tracker_position.csv: position_z | position.jsonl: data.Position.{driver}.Z |
| `status` | string | Driver status | driver_tracker_position.csv: status | position.jsonl: data.Position.{driver}.Status |

**Total Telemetry & Position Fields:** 6 + 4 = **10 fields per driver**

---

### Session-Level Data Points

#### Session Info (4 fields)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `session_name` | string | Session name | session_info.csv: name | sessiondata.jsonl: data.SessionName |
| `session_location` | string | Circuit location | session_info.csv: location | sessiondata.jsonl: data.Location |
| `circuit_key` | string | Circuit identifier | session_info.csv: circuit_key | sessiondata.jsonl: data.CircuitKey |
| `session_key` | integer | Session identifier | session_info.csv: session_key | sessiondata.jsonl: data.SessionKey |

#### Lap Count (2 fields)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `current_lap` | integer | Current lap number | lap_count.csv: current | lapcount.jsonl: data.CurrentLap |
| `total_laps` | integer | Total laps in session | lap_count.csv: total | lapcount.jsonl: data.TotalLaps |

#### Weather (7 fields)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `air_temp` | float | Air temperature (°C) | weather.csv: air_temp | weatherdata.jsonl: data.AirTemp |
| `track_temp` | float | Track temperature (°C) | weather.csv: track_temp | weatherdata.jsonl: data.TrackTemp |
| `wind_speed` | float | Wind speed (m/s) | weather.csv: wind_speed | weatherdata.jsonl: data.WindSpeed |
| `wind_direction` | integer | Wind direction (degrees) | weather.csv: wind_direction | weatherdata.jsonl: data.WindDirection |
| `humidity` | integer | Humidity (%) | weather.csv: humidity | weatherdata.jsonl: data.Humidity |
| `pressure` | float | Air pressure (mbar) | weather.csv: pressure | weatherdata.jsonl: data.Pressure |
| `rainfall` | boolean | Rainfall detected | weather.csv: rainfall | weatherdata.jsonl: data.Rainfall |

#### Track Status (2 fields)

| Field | Type | Description | CSV Column | JSON Path |
|-------|------|-------------|------------|-----------|
| `track_status` | string | Track status code | track_status.csv: track_status | trackstatus.jsonl: data.Status |
| `track_status_message` | string | Status description | track_status.csv: track_status_message | trackstatus.jsonl: data.Message |

**Total Session-Level Fields:** 4 + 2 + 7 + 2 = **15 fields**

---

### Grand Total

**Per Driver:**
- Timing Tower: **54 fields**
- Telemetry & Position: **10 fields**
- **Total per driver: 64 fields**

**For 20 drivers:**
- 64 × 20 = **1,280 driver-specific data points**
- 15 session-level data points
- **= 1,295+ total data points per update**

**Additional Data (not per-update):**
- Championship predictions (drivers & teams)
- Race control messages
- Team radio captures
- Pit stop details
- Tyre stint history

---

### Summary Table

| Category | Fields per Driver | Total for 20 Drivers |
|----------|-------------------|----------------------|
| **Timing Tower** | 54 | 1,080 |
| **Telemetry** | 6 | 120 |
| **GPS Position** | 4 | 80 |
| **Session-Level** | - | 15 |
| **TOTAL** | **64** | **1,295+** |

---

## 📨 Message Types

### All Message Types Captured

| Message Type | CSV File | JSON File | Description |
|--------------|----------|-----------|-------------|
| `TimingData` | timing_tower.csv | timingdata.jsonl | Positions, gaps, sectors, mini-sectors |
| `CarData` | driver_tracker_telemetry.csv | cardata.jsonl | Speed, RPM, gear, throttle, brake, DRS |
| `Position` | driver_tracker_position.csv | position.jsonl | GPS coordinates (X, Y, Z) |
| `DriverList` | - | driverlist.jsonl | Driver names, teams, colors |
| `TimingAppData` | tyre_stints.csv | timingappdata.jsonl | Tyre compound, age, stints |
| `TimingStats` | timing_stats.csv | timingstats.jsonl | Speed trap data |
| `WeatherData` | weather.csv | weatherdata.jsonl | Weather conditions |
| `RaceControlMessages` | race_control.csv | racecontrolmessages.jsonl | Flags, penalties |
| `TrackStatus` | track_status.csv | trackstatus.jsonl | Track status changes |
| `SessionData` | session_info.csv | sessiondata.jsonl | Session metadata |
| `LapCount` | lap_count.csv | lapcount.jsonl | Lap counter |
| `ChampionshipPrediction` | championship_*.csv | championshipprediction.jsonl | Championship standings |
| `TeamRadio` | team_radio.csv | teamradio.jsonl | Team radio captures |
| `PitStopSeries` | pit_stops.csv | pitstopseries.jsonl | Pit stop details |
| `PitStop` | pit_stops.csv | pitstop.jsonl | Pit stop timing |
| `PitLaneTimeCollection` | pit_lane_times.csv | pitlanetimecollection.jsonl | Pit lane times |
| `TopThree` | - | topthree.jsonl | Top 3 display |
| `Heartbeat` | - | heartbeat.jsonl | System heartbeat |
| `ExtrapolatedClock` | - | extrapolatedclock.jsonl | Session clock |

**Total:** 19 message types

---

## 💻 Code Examples

### Python - Reading CSV Files

#### Example 1: Load Timing Tower Data

```python
import pandas as pd

# Load timing tower data
df = pd.read_csv('timing_tower.csv')

# Filter for driver #1 (VER)
ver_data = df[df['driver_number'] == '1']

# Get best lap time
best_lap = ver_data['best_lap_time'].iloc[0]
print(f"VER best lap: {best_lap}")

# Find when VER was in P1
p1_times = ver_data[ver_data['position'] == 1]
print(f"VER was in P1 for {len(p1_times)} updates")
```

#### Example 2: Analyze Mini-Sectors

```python
import pandas as pd

# Load mini-sectors
df = pd.read_csv('mini_sectors.csv')

# Filter for driver #1
ver_data = df[df['driver_number'] == 1]

# Find all purple mini-sectors (2051)
purple_cols = [col for col in df.columns if col.startswith('sector_')]
ver_purple = ver_data[ver_data[purple_cols].eq(2051).any(axis=1)]

print(f"VER had {len(ver_purple)} updates with purple mini-sectors")

# Count purple sectors by segment
for col in purple_cols:
    purple_count = (ver_data[col] == 2051).sum()
    if purple_count > 0:
        print(f"{col}: {purple_count} purple")
```

#### Example 3: Telemetry Analysis

```python
import pandas as pd
import matplotlib.pyplot as plt

# Load telemetry
df = pd.read_csv('driver_tracker_telemetry.csv')

# Filter for driver #1
ver_data = df[df['driver_number'] == 1]

# Plot speed over time
plt.figure(figsize=(12, 6))
plt.plot(ver_data['speed'])
plt.title('VER Speed Over Time')
plt.xlabel('Update')
plt.ylabel('Speed (km/h)')
plt.show()

# Find max speed
max_speed = ver_data['speed'].max()
print(f"VER max speed: {max_speed} km/h")

# Analyze DRS usage
drs_active = ver_data[ver_data['drs'].isin([10, 12, 14])]
print(f"DRS active for {len(drs_active)} updates ({len(drs_active)/len(ver_data)*100:.1f}%)")
```

#### Example 4: Tyre Strategy

```python
import pandas as pd

# Load tyre stints
df = pd.read_csv('tyre_stints.csv')

# Filter for driver #1
ver_stints = df[df['driver_number'] == 1]

# Print stint summary
for _, stint in ver_stints.iterrows():
    print(f"Stint {stint['stint_number']}: {stint['compound']} "
          f"({'new' if stint['is_new'] else 'used'}) - "
          f"{stint['total_laps']} laps (started lap {stint['start_lap']})")
```

---

### Python - Reading JSON Files

#### Example 1: Load Timing Data

```python
import json

# Read timing data line by line
for line in open('json/timingdata.jsonl'):
    record = json.loads(line)
    timestamp = record['timestamp']
    data = record['data']

    # Access driver #1 data
    if '1' in data.get('Lines', {}):
        driver_data = data['Lines']['1']
        position = driver_data.get('Position')
        best_lap = driver_data.get('BestLapTime', {}).get('Value')

        print(f"{timestamp}: VER P{position}, Best: {best_lap}")
```

#### Example 2: Extract Mini-Sectors

```python
import json

purple_count = 0

for line in open('json/timingdata.jsonl'):
    record = json.loads(line)
    lines = record['data'].get('Lines', {})

    if '1' in lines:  # Driver #1 (VER)
        sectors = lines['1'].get('Sectors', {})

        for sector_num, sector_data in sectors.items():
            segments = sector_data.get('Segments', [])

            # Handle both list and dict formats
            if isinstance(segments, list):
                for seg in segments:
                    status = seg.get('Status', 0) if isinstance(seg, dict) else seg
                    if status == 2051:
                        purple_count += 1
            elif isinstance(segments, dict):
                for seg_data in segments.values():
                    status = seg_data.get('Status', 0) if isinstance(seg_data, dict) else seg_data
                    if status == 2051:
                        purple_count += 1

print(f"VER had {purple_count} purple mini-sectors")
```

#### Example 3: Telemetry from JSON

```python
import json

max_speed = 0

for line in open('json/cardata.jsonl'):
    record = json.loads(line)
    entries = record['data'].get('Entries', {})

    if '1' in entries:  # Driver #1
        channels = entries['1'].get('Channels', {})
        speed = channels.get('0', 0)  # Channel 0 = speed

        if speed > max_speed:
            max_speed = speed

print(f"VER max speed: {max_speed} km/h")
```

#### Example 4: Driver List

```python
import json

# Read first line (driver list)
with open('json/driverlist.jsonl') as f:
    first_line = f.readline()
    record = json.loads(first_line)
    drivers = record['data']

    # Print all drivers
    for driver_num, driver_info in drivers.items():
        print(f"{driver_num}: {driver_info['Tla']} - {driver_info['TeamName']}")
```

---

### Python - Combined CSV + JSON Analysis

#### Example: Correlate Telemetry with Lap Times

```python
import pandas as pd
import json

# Load lap times from CSV
timing_df = pd.read_csv('timing_tower.csv')
ver_timing = timing_df[timing_df['driver_number'] == '1']

# Load telemetry from JSON
telemetry_data = []
for line in open('json/cardata.jsonl'):
    record = json.loads(line)
    if '1' in record['data'].get('Entries', {}):
        channels = record['data']['Entries']['1']['Channels']
        telemetry_data.append({
            'timestamp': record['timestamp'],
            'speed': channels.get('0', 0),
            'rpm': channels.get('2', 0),
            'gear': channels.get('3', 0)
        })

telemetry_df = pd.DataFrame(telemetry_data)

# Merge on timestamp
merged = pd.merge(ver_timing, telemetry_df, on='timestamp', how='inner')

# Analyze
print(f"Average speed during best lap: {merged['speed'].mean():.1f} km/h")
print(f"Max RPM: {merged['rpm'].max()}")
```

---

## 🔢 Status Codes & Enums

### Sector Status Codes

| Code | Color | Meaning |
|------|-------|---------|
| `2051` | 🟣 Purple | Overall fastest (across all drivers) |
| `2049` | 🟢 Green | Personal best (for this driver) |
| `2048` | 🟡 Yellow | Slower than previous lap |
| `0` | ⚪ White | No data / not set |

**Usage:**
- Found in: `timing_tower.csv` (sector_X_status), `mini_sectors.csv` (all segment columns)
- JSON path: `data.Lines.{driver}.Sectors.{N}.Status`, `data.Lines.{driver}.Sectors.{N}.Segments[].Status`

---

### DRS Status Codes

| Code | Meaning |
|------|---------|
| `0` | DRS not available |
| `8` | DRS available but not activated |
| `10` | DRS activated |
| `12` | DRS activated |
| `14` | DRS activated |

**Usage:**
- Found in: `driver_tracker_telemetry.csv` (drs column)
- JSON path: `data.Entries.{driver}.Channels.45`

**Note:** Codes 10, 12, 14 all indicate DRS is active. The different values may represent different activation states or zones.

---

### Track Status Codes

| Code | Message | Meaning |
|------|---------|---------|
| `1` | AllClear | Green flag - racing |
| `2` | Yellow | Yellow flag - caution |
| `4` | SCDeployed | Safety Car deployed |
| `5` | Red | Red flag - session stopped |
| `6` | VSCDeployed | Virtual Safety Car |
| `7` | VSCEnding | VSC ending soon |

**Usage:**
- Found in: `track_status.csv`, `timing_tower.csv` (track_status column)
- JSON path: `data.Status`

---

### Tyre Compounds

| Code | Meaning |
|------|---------|
| `SOFT` | Soft compound (red) |
| `MEDIUM` | Medium compound (yellow) |
| `HARD` | Hard compound (white) |
| `INTERMEDIATE` | Intermediate (green) - wet weather |
| `WET` | Full wet (blue) - heavy rain |

**Usage:**
- Found in: `tyre_stints.csv` (compound column), `timing_tower.csv` (tyre_compound column)
- JSON path: `data.Lines.{driver}.Stints.{N}.Compound`

---

### Flag Types

| Flag | Meaning |
|------|---------|
| `BLUE` | Blue flag - let faster car pass |
| `YELLOW` | Yellow flag - caution, slow down |
| `GREEN` | Green flag - all clear |
| `RED` | Red flag - session stopped |
| `BLACK AND WHITE` | Warning flag - unsportsmanlike behavior |
| `BLACK` | Black flag - disqualification |
| `CHEQUERED` | Chequered flag - session end |

**Usage:**
- Found in: `race_control.csv` (flag column)
- JSON path: `data.Messages.{N}.Flag`

---

### Telemetry Channel Mapping

| Channel | Field | Range | Unit |
|---------|-------|-------|------|
| `0` | Speed | 0-350 | km/h |
| `2` | RPM | 0-15000 | revolutions/min |
| `3` | Gear | 0-8 | gear number (0=neutral) |
| `4` | Throttle | 0-100 | percentage |
| `5` | Brake | 0-100 | percentage |
| `45` | DRS | 0/8/10/12/14 | status code |

**Usage:**
- Found in: `driver_tracker_telemetry.csv`
- JSON path: `data.Entries.{driver}.Channels.{channel_num}`

---

## ❓ FAQ

### General Questions

**Q: What's the difference between CSV and JSON files?**

A:
- **CSV files** are flattened, tabular data - easy to open in Excel or analyze with pandas
- **JSON files** preserve the full nested structure from F1's API - better for programmatic access
- Both contain the same data, just in different formats

**Q: Why are some CSV files empty or have only 1 row?**

A: Some data types only update once per session (e.g., `session_info.csv`) or may not occur during a session (e.g., `pit_stops.csv` in qualifying).

**Q: What does "decompressed" mean for CarData and Position?**

A: F1's API sends these messages compressed (base64-encoded zlib). The export process automatically decompresses them so you get readable JSON and CSV data.

**Q: How often is data updated?**

A:
- **Telemetry (CarData, Position):** ~75 updates/second per driver
- **Timing data:** ~1-2 updates/second
- **Weather:** ~1 update/minute
- **Race control:** As events occur

---

### CSV Questions

**Q: How do I find a specific driver's data in CSV?**

A: Filter by `driver_number` column:
```python
df = pd.read_csv('timing_tower.csv')
ver_data = df[df['driver_number'] == '1']  # Driver #1 (VER)
```

**Q: What does an empty cell mean in CSV?**

A: Empty cells mean no data was available for that field at that timestamp. This is normal - not all fields update on every message.

**Q: Why are there multiple rows with the same timestamp?**

A: Each row represents one driver's data at that timestamp. For 20 drivers, you'll see 20 rows with the same timestamp.

**Q: How do I analyze mini-sectors?**

A: See [Example 2 in Code Examples](#example-2-analyze-mini-sectors) above.

---

### JSON Questions

**Q: What is JSONL format?**

A: JSON Lines (JSONL) is a format where each line is a complete, valid JSON object. This makes it stream-friendly and easy to process line-by-line without loading the entire file into memory.

**Q: How do I read JSONL files?**

A:
```python
import json

for line in open('timingdata.jsonl'):
    record = json.loads(line)
    # Process record
```

**Q: Why are Segments sometimes a list and sometimes a dict?**

A: F1's API can send segments in either format:
- **List:** `[{"Status": 0}, {"Status": 2051}, ...]`
- **Dict:** `{"0": {"Status": 0}, "2": {"Status": 2051}, ...}`

Always check the type before processing:
```python
if isinstance(segments, list):
    for seg in segments:
        status = seg.get('Status', 0)
elif isinstance(segments, dict):
    for seg_data in segments.values():
        status = seg_data.get('Status', 0)
```

**Q: What's the difference between `timingdata.jsonl` and `timing_tower.csv`?**

A: They contain the same data, but:
- `timingdata.jsonl` has the full nested structure from F1's API
- `timing_tower.csv` is flattened with one row per driver per update

---

### Data Analysis Questions

**Q: How do I calculate average lap time?**

A:
```python
df = pd.read_csv('timing_tower.csv')
ver_data = df[df['driver_number'] == '1']

# Filter out empty lap times
lap_times = ver_data['last_lap_time'].dropna()
lap_times = lap_times[lap_times != '']

# Convert to seconds (assumes format "1:32.123")
def lap_to_seconds(lap_str):
    parts = lap_str.split(':')
    return int(parts[0]) * 60 + float(parts[1])

lap_seconds = lap_times.apply(lap_to_seconds)
avg_lap = lap_seconds.mean()
print(f"Average lap: {avg_lap:.3f}s")
```

**Q: How do I find the fastest lap?**

A:
```python
df = pd.read_csv('timing_tower.csv')

# Get all best lap times
best_laps = df[['driver_number', 'driver_tla', 'best_lap_time']].dropna()
best_laps = best_laps[best_laps['best_lap_time'] != '']

# Sort by lap time
best_laps_sorted = best_laps.sort_values('best_lap_time')
fastest = best_laps_sorted.iloc[0]

print(f"Fastest lap: {fastest['driver_tla']} - {fastest['best_lap_time']}")
```

**Q: How do I visualize a driver's track position?**

A:
```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('driver_tracker_position.csv')
ver_data = df[df['driver_number'] == 1]

plt.figure(figsize=(12, 12))
plt.plot(ver_data['position_x'], ver_data['position_y'])
plt.title('VER Track Position')
plt.xlabel('X (cm)')
plt.ylabel('Y (cm)')
plt.axis('equal')
plt.show()
```

**Q: How do I compare two drivers' speeds?**

A:
```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('driver_tracker_telemetry.csv')

ver_data = df[df['driver_number'] == 1]
nor_data = df[df['driver_number'] == 4]

plt.figure(figsize=(12, 6))
plt.plot(ver_data['speed'].values[:1000], label='VER', alpha=0.7)
plt.plot(nor_data['speed'].values[:1000], label='NOR', alpha=0.7)
plt.title('Speed Comparison (First 1000 Updates)')
plt.xlabel('Update')
plt.ylabel('Speed (km/h)')
plt.legend()
plt.show()
```

---

### Technical Questions

**Q: What timezone are timestamps in?**

A: All timestamps are in **UTC** (Coordinated Universal Time), in ISO 8601 format: `2025-11-23T03:20:15.9050631+00:00`

**Q: How big are the files?**

A:
- **Race CSV:** ~38.7 MB total (16 files)
- **Race JSON:** ~96.87 MB total (19 files)
- **Qualifying CSV:** ~21.5 MB total (16 files)
- **Qualifying JSON:** ~55.01 MB total (15 files)

**Q: Can I process these files in Excel?**

A: Yes, but be aware:
- Large files (e.g., `driver_tracker_telemetry.csv` with 627,981 rows) may exceed Excel's 1,048,576 row limit
- Use Python/pandas for large files
- Smaller files (timing_tower, mini_sectors, etc.) work fine in Excel

**Q: How do I process data in real-time?**

A: The export system writes data as it arrives. You can:
1. Tail the CSV files as they're being written
2. Process JSONL files line-by-line
3. Use the WebSocket API for real-time updates (see API documentation)

**Q: Where is the source data?**

A: The source data is in `live.jsonl` in the session directory. The CSV and JSON exports are generated from this file.

---

## 📚 Additional Resources

### Documentation Files

- **DATA_POINTS.md** - Complete API data point reference
- **JSON_STRUCTURE_GUIDE.md** - Detailed JSON structure documentation
- **DATA_ACCESS_SUMMARY.md** - Quick reference guide
- **MINI_SECTORS_COMPLETE.md** - Mini-sector data documentation
- **QUALIFYING_EXPORT_SUMMARY.md** - Qualifying session summary

### Example Scripts

- **process_qualifying.py** - Process qualifying session to CSV+JSON
- **process_race.py** - Process race session to CSV+JSON
- **show_qualifying_data.py** - Display qualifying data summary

---

## 🎯 Quick Start Guide

### 1. Find Your Data

**Race:**
```
C:\Users\bhavi\AppData\Local\undercut-f1\data\2025_Las_Vegas_Race\Race_2\
├── *.csv (16 files)
└── json\*.jsonl (19 files)
```

**Qualifying:**
```
C:\Users\bhavi\AppData\Local\undercut-f1\data\2025_Las_Vegas_Qualifying\Qualifying\
├── *.csv (16 files)
└── json\*.jsonl (15 files)
```

### 2. Choose Your Format

- **Want to analyze in Excel?** → Use CSV files
- **Want full data structure?** → Use JSON files
- **Want both?** → Both are available!

### 3. Start Analyzing

**Python (CSV):**
```python
import pandas as pd
df = pd.read_csv('timing_tower.csv')
print(df.head())
```

**Python (JSON):**
```python
import json
for line in open('json/timingdata.jsonl'):
    record = json.loads(line)
    print(record)
    break  # Just show first record
```

### 4. Explore the Data

- Check [CSV Files Reference](#csv-files-reference) for column details
- Check [JSON Files Reference](#json-files-reference) for structure
- Check [Code Examples](#code-examples) for analysis patterns

---

## ✅ Data Completeness Checklist

### What's Included

- ✅ **All timing data** - positions, gaps, lap times
- ✅ **All sector data** - 3 sectors per lap
- ✅ **All mini-sector data** - 22 segments per lap (Las Vegas)
- ✅ **All telemetry** - speed, RPM, gear, throttle, brake, DRS
- ✅ **All GPS positions** - X, Y, Z coordinates
- ✅ **All speed traps** - I1, I2, FL, ST
- ✅ **All tyre data** - compound, age, stints
- ✅ **All weather data** - temperature, wind, humidity, pressure
- ✅ **All race control** - flags, penalties, messages
- ✅ **All pit data** - pit stops, pit lane times
- ✅ **All championship data** - driver and team standings
- ✅ **All team radio** - message captures
- ✅ **All session metadata** - session info, lap count, track status

### What's NOT Included

- ❌ **Historical lap-by-lap data** - Requires database storage (not implemented)
- ❌ **Audio files** - Team radio audio is hosted by F1, not stored locally
- ❌ **Video feeds** - Not part of timing data
- ❌ **Pit stop crew data** - Not available in F1 API

---

## 🏁 Summary

**You now have access to:**
- **16 CSV files** with 731,373 rows (Race) / 418,256 rows (Qualifying)
- **19 JSON files** with 66,952 records (Race) / 24,373 records (Qualifying)
- **1,275+ data points** per update
- **Every single data point** from F1's live timing feed

**Everything is documented, structured, and ready to analyze!**

---

*Last updated: 2025-11-25*
*Data from: 2025 Las Vegas Grand Prix (Race & Qualifying)*


