"""Start line for the optimiser on the satellite road: a smooth periodic spline through the centre of
the satellite edges (fit RMS ~0.3 m), so the optimiser's spline offsets are the only shape it has.
-> sepang_sat_base_rl.json"""
import json, os, sys, numpy as np
from scipy.interpolate import splprep, splev
HERE = os.path.dirname(os.path.abspath(__file__))
E = np.load(os.path.join(HERE, "sat", "edges_clean.npz")); P, N = E["P"], E["N"]
C = P + (0.5 * (E["lo_sat"] + E["hi_sat"]))[:, None] * N
tck, u = splprep([C[:, 0], C[:, 1]], s=len(C) * 0.3 ** 2, per=1)
uu = np.linspace(0, 1, len(C), endpoint=False); B = np.column_stack(splev(uu, tck))
print("fit rms %.2f m" % np.sqrt(np.mean(np.min(np.linalg.norm(C[:, None] - B[None, ::3], axis=2), axis=1) ** 2)))
json.dump({"raceline": B.tolist()}, open(os.path.join(HERE, "sepang_sat_base_rl.json"), "w"))
