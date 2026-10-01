"""DRS-open distance windows (fraction of lap) on the 2018 Q fastest laps -> drs_2018.json."""
import os, sys, json, warnings
warnings.simplefilter("ignore")
import fastf1, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
fastf1.Cache.enable_cache(os.path.join(ROOT, "F1_Pipeline_Assets", "temp_data", "f1_cache"))
TRACKS = {"canada": "Canada", "austria": "Austria", "silverstone": "Great Britain",
          "monza": "Italy", "bahrain": "Bahrain", "spa": "Belgium"}
out = {}
for slug, name in TRACKS.items():
    s = fastf1.get_session(2018, name, "Q"); s.load(laps=True, telemetry=True, weather=False, messages=False)
    tel = s.laps.pick_fastest().get_telemetry().dropna(subset=["Distance"])
    d = tel["Distance"].to_numpy(); L = d.max(); op = (tel["DRS"].to_numpy() >= 10)
    zones, i = [], 0
    while i < len(op):
        if op[i]:
            j = i
            while j + 1 < len(op) and op[j + 1]: j += 1
            if d[j] - d[i] > 50: zones.append([round(d[i] / L, 4), round(d[j] / L, 4)])
            i = j + 1
        else: i += 1
    out[slug] = zones; print(slug, zones, flush=True)
json.dump(out, open(os.path.join(HERE, "drs_2018.json"), "w"), indent=1)
