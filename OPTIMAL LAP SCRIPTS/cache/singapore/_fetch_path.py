"""Official (map-matched) position path for RUS 2025 Q lap 17, Singapore: OpenF1 location x,y,z (decimetres)
within [lap start, lap end]. Cached raw -> cache/singapore/rus2025_location.json."""
import os, sys, json
from datetime import timedelta
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, ROOT)
import fetch_openf1_lap as F
lap = json.load(open(os.path.join(H, "rus2025_car_data.json")))["lap"]
st = F.parse_dt(lap["date_start"]); en = st + timedelta(seconds=lap["lap_duration"] + 1.0)
loc = F.get("location", session_key=9892, driver_number=63, **{"date>": (st - timedelta(seconds=1)).isoformat(), "date<": en.isoformat()})
json.dump(dict(lap=lap, location=loc), open(os.path.join(H, "rus2025_location.json"), "w")); print(len(loc), "samples")
