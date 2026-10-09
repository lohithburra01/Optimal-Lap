"""Braking-zone length (peak speed -> next minimum, m) and mean decel, per big stop (drop > 100 km/h).
Real 2026 Q vs real 2025 Q pairs, and Singapore: our 2026 sim vs RUS 2025 raw (unwarped) telemetry."""
import os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, os.path.join(ROOT, "cache"))
import _track_registry as R
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
def stops(s, v):
    g = np.arange(s[0], s[-1], 2.0); vv = gaussian_filter1d(np.interp(g, s, v), 2)
    mx, _ = find_peaks(vv, prominence=30); out = []
    for i in mx:
        j = i
        while j + 1 < len(vv) and vv[j + 1] <= vv[j]: j += 1
        if vv[i] - vv[j] > 100:
            L = g[j] - g[i]; dec = ((vv[i] / 3.6) ** 2 - (vv[j] / 3.6) ** 2) / (2 * L) / 9.81
            out.append((g[i], vv[i], vv[j], L, dec))
    return out
def show(name, s25, v25, s26, v26):
    a, b = stops(s25, v25), stops(s26, v26); r = []
    for x in a:
        y = min(b, key=lambda y: abs(y[2] - x[2]) + abs(y[0] - x[0]) * 0.2)
        r.append(y[3] / x[3])
    print(f"{name:26s} stops {len(a):2d}  2026/2025 braking-length ratio median {np.median(r):.2f}  "
          f"decel 2025 {np.median([x[4] for x in a]):.2f} g  2026 {np.median([y[4] for y in b]):.2f} g")
    return r
allr = []
for tr in ["canada", "miami", "china", "spa", "hungary", "zandvoort"]:
    sp = R.TRACKS[tr]; s25, v25, _ = R.load_ref(sp["csv25"]); s26, v26, _ = R.load_ref(sp["csv26"])
    allr += show(tr + " REAL/REAL", s25, v25, s26, v26)
print(f"{'REAL pairs overall':26s} median ratio {np.median(allr):.2f}")
sA, vA, _ = R.load_ref(os.path.join(ROOT, "F1_Pipeline_Assets", "exports", "reference_2025_singapore_q.csv"))
sB, vB, _ = R.load_ref(os.path.join(ROOT, "F1_Pipeline_Assets", "exports", "singapore_2026_synthetic.csv"))
show("SINGAPORE sim2026/RUS", sA, vA, sB, vB)
sC, vC, _ = R.load_ref(os.path.join(H, "sim2025_own_line.csv"))
show("SINGAPORE sim2025/RUS", sA, vA, sC, vC)
