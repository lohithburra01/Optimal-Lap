"""Singapore v4 track (2026-10-08): the OFFICIAL map-matched path (cache/singapore/official_path.json, from the
top-10 2025 Q laps) as centreline, scaled to the FIA length 4927 m, 2000 stations, min radius 10 m, constant
10 m width (fitted: 12 m gave worst corner 46 km/h, 10 m 18). S/F = official timing line (index 0).
Writes the real-frame outline and its x-mirror (the engine drives CW; Marina Bay is CCW)."""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, ROOT)
import svg_to_outline as SO
op = json.load(open(os.path.join(H, "official_path.json"))); Q = np.array(op["xy"]); mb = Q.mean(0)
Q = mb + (4927.0 / op["length_m"] / op["scale"]) * (Q - mb)
c = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.vstack([Q, Q[:1]]), axis=0), axis=1))]; u = np.linspace(0, c[-1], 2000, endpoint=False)
C = np.column_stack([np.interp(u, c, np.r_[Q[:, k], Q[0, k]]) for k in (0, 1)])
C = SO.limit_min_radius(C, 10.0); C12o, C12i = SO.generate_edges_constant_width(C, 12.0); C = (C12o + C12i) / 2   # as built
O, I = SO.generate_edges_constant_width(C, 10.0)
T = os.path.join(ROOT, "F1_Pipeline_Assets", "tracks")
json.dump(dict(outer=O.tolist(), inner=I.tolist()), open(os.path.join(T, "singapore_grand_prix_outline.json"), "w"))
m = np.array([-1.0, 1.0])
json.dump(dict(outer=(O * m).tolist(), inner=(I * m).tolist()), open(os.path.join(T, "singapore_grand_prix_mirror_outline.json"), "w"))
print(f"[official] centreline {c[-1]*0+np.sum(np.linalg.norm(np.diff(np.vstack([C, C[:1]]), axis=0), axis=1)):.0f} m, width 10 m -> outline + mirror")
