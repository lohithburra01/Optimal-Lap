"""v4: simulate the physical 2025 car (street_grip.json, street grip 0.723) on its own line k25 -> sim2025_k25.csv
(timing reference for the line only) + real-frame line F1_Pipeline_Assets/tracks/singapore_2025_rus_raceline.json."""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "cache", "era2017")); sys.path.insert(0, H)
import sim_2026_lap as S, _sg_grip as G, _car2025 as K
sg = json.load(open(os.path.join(H, "street_grip.json"))); G.apply(S, sg["k"])
LINE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(H, "k25w_rl.json")   # k25w = with the T8->T9 wide-entry constraint
rl = np.array(json.load(open(LINE))["raceline"]); r = K.sim(rl, sg["car"], sg["drs"])
S.write_csv(os.path.join(H, "sim2025_k25.csv"), r["v"], np.ones(len(r["v"])), r["mode"], r["pkw"], r["t"], r["arc"], r["L"], fps=30)
json.dump({"raceline": (rl * [-1, 1]).tolist(), "arc_length": r["arc"].tolist(), "track_length_m": r["L"]},
          open(os.path.join(ROOT, "F1_Pipeline_Assets", "tracks", "singapore_2025_rus_raceline.json"), "w"))
print(f"[2025] physical car on own line {r['lap']:.3f} s")
