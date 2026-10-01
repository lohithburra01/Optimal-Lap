"""Fetch 2018 Q fastest laps (closest era with telemetry to the 2017 Sepang car).
Writes F1_Pipeline_Assets/exports/reference_2018_<slug>_q.csv. Layout must match today's outline."""
import os, sys, csv, warnings
warnings.simplefilter("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from fetch_fastest_lap import fetch_fastest, lap_to_rows
TRACKS = {"canada": "Canada", "austria": "Austria", "silverstone": "Great Britain",
          "monza": "Italy", "bahrain": "Bahrain", "spa": "Belgium"}
CACHE = os.path.join(ROOT, "F1_Pipeline_Assets", "temp_data", "f1_cache")
for slug, name in TRACKS.items():
    out = os.path.join(ROOT, "F1_Pipeline_Assets", "exports", f"reference_2018_{slug}_q.csv")
    if os.path.exists(out):
        print(slug, "exists"); continue
    try:
        t, lap, drv, _ = fetch_fastest(2018, name, "Q", CACHE)
        rows = lap_to_rows(lap)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        print(f"OK {slug} {drv} {t:.3f}s rows={len(rows)} dist={rows[-1]['distance']:.0f}", flush=True)
    except Exception as e:
        print(f"FAIL {slug}: {e!r}", flush=True)
