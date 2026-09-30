"""2017 pole -> 2026 pole ratio at circuits whose layout is unchanged since 2017.
Gives a data-driven, reference-free lap estimate for Sepang (last raced 2017).
Sources: jolpica (Ergast mirror) for 2017 Q; OpenF1 for 2026 Q best laps."""
import json, time, urllib.request, urllib.error, statistics as st

def get(url, tries=6):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "f1hotlap"}), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404: return []        # no data (future/cancelled session)
            print("  retry", k, url[:80], e); time.sleep(5 * 2 ** k)
        except Exception as e:
            print("  retry", k, url[:80], e); time.sleep(5 * 2 ** k)
    raise SystemExit("fetch failed " + url)

def secs(t):
    m, s = t.split(":") if ":" in t else ("0", t); return 60 * int(m) + float(s)

# 2017 pole = min(Q1,Q2,Q3) over the grid, per round
import os
q17 = json.load(open("cache/era_2017_poles.json")) if os.path.exists("cache/era_2017_poles.json") else {}
races = [] if q17 else None
if races is None: races = get("https://api.jolpi.ca/ergast/f1/2017.json?limit=30")["MRData"]["RaceTable"]["Races"]
for r in races:
    rnd = r["round"]; cid = r["Circuit"]["circuitId"]
    qr = get(f"https://api.jolpi.ca/ergast/f1/2017/{rnd}/qualifying.json?limit=30")["MRData"]["RaceTable"]["Races"]
    best = min(secs(x[k]) for x in qr[0]["QualifyingResults"] for k in ("Q1", "Q2", "Q3") if x.get(k))
    q17[cid] = dict(name=r["raceName"], country=r["Circuit"]["Location"]["country"], pole=best)
    time.sleep(0.3)
json.dump(q17, open("cache/era_2017_poles.json", "w"), indent=1)

# 2026 quali best laps from OpenF1
sess = get("https://api.openf1.org/v1/sessions?year=2026&session_name=Qualifying")
q26 = {}
for s in sess:
    laps = get(f"https://api.openf1.org/v1/laps?session_key={s['session_key']}")
    d = [l["lap_duration"] for l in laps if l.get("lap_duration")]
    if d: q26[s["circuit_short_name"]] = dict(country=s["country_name"], date=s["date_start"][:10], pole=min(d))
    time.sleep(0.5)
json.dump(q26, open("cache/era_2026_poles.json", "w"), indent=1)
print(json.dumps(q17, indent=0)); print(json.dumps(q26, indent=0))
