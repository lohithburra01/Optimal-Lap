"""Where does a 2026 lap lose time to a 2025 lap? Splits the time delta by phase of the 2025 trace:
BRAKE (speed falling), CORNER (within 12 km/h of a local minimum), TRACTION (accelerating, <230 km/h),
HIGH-SPEED (accelerating/flat, >=230 km/h = where 2026 energy clipping/superclip acts).
REAL 2026 Q vs REAL 2025 Q pairs (align_pair) vs our Singapore 2026 sim vs RUS 2025 real."""
import os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, os.path.join(ROOT, "cache"))
import _track_registry as R
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
E = os.path.join(ROOT, "F1_Pipeline_Assets", "exports")
def phases(s, v25, v26):
    ds = s[1] - s[0]; dt = ds / (v26 / 3.6) - ds / (v25 / 3.6)
    vs = gaussian_filter1d(v25, 2, mode="wrap"); dv = np.gradient(vs)
    p, _ = find_peaks(-vs, prominence=10); near = np.zeros(len(s), bool)
    for i in p:
        j = i
        while j > 0 and vs[j] < vs[i] + 12: near[j] = True; j -= 1
        j = i
        while j < len(s) - 1 and vs[j] < vs[i] + 12: near[j] = True; j += 1
    brake = (dv < -0.15) & ~near; trac = (dv >= -0.15) & ~near & (vs < 230); hs = (dv >= -0.15) & ~near & (vs >= 230)
    tot = dt.sum(); out = {k: dt[m].sum() for k, m in (("BRAKE", brake), ("CORNER", near), ("TRACTION", trac), ("HIGH-SPEED", hs))}
    top = []
    for i in find_peaks(vs, prominence=30)[0]: top.append(v26[i] - v25[i])
    return tot, out, np.median(top)
rows = []
for tr in ["canada", "miami", "china", "spa", "hungary", "zandvoort"]:
    sp = R.TRACKS[tr]; s25, v25, t25 = R.load_ref(sp["csv25"]); s26, v26, t26 = R.load_ref(sp["csv26"])
    s, a, b, _ = R.align_pair(s25, v25, s26, v26, sp["length_m"], n=4096); rows.append((tr + " (REAL vs REAL)",) + phases(s, a, b))
sA, vA, _ = R.load_ref(os.path.join(H, "rus2025_exact.csv")); sB, vB, _ = R.load_ref(os.path.join(E, "singapore_2026_synthetic.csv"))
g = np.arange(4096) / 4096; s = g * 4927
a = np.interp(g, sA / (sA[-1] + sA[-1] - sA[-2]), vA); b = np.interp(g, sB / (sB[-1] + sB[-1] - sB[-2]), vB)
rows.append(("SINGAPORE ours (sim vs RUS)",) + phases(s, a, b))
print(f"{'pair':30s} {'delta':>7s} | {'BRAKE':>6s} {'CORNER':>7s} {'TRACTION':>8s} {'HI-SPD':>7s}  (% of delta) | top-speed diff")
for name, tot, o, top in rows:
    print(f"{name:30s} {tot:+6.2f}s | " + " ".join(f"{100*o[k]/tot:6.0f}%" if k != "CORNER" else f"{100*o[k]/tot:7.0f}%" for k in ("BRAKE", "CORNER", "TRACTION", "HIGH-SPEED"))
          + f"  | {top:+5.1f} km/h")

print("\nlongest-straight peaks (2026 - 2025, km/h), 3 fastest peaks of the 2025 trace:")
def peaks3(s, a, b):
    vs = gaussian_filter1d(a, 2, mode="wrap"); p, _ = find_peaks(vs, prominence=30); p = p[np.argsort(-vs[p])][:3]
    return [f"{a[i]:.0f}->{b[i]:+.0f}" for i in sorted(p, key=lambda i: -a[i])], [b[i] - a[i] for i in p]
allr = []
for tr in ["canada", "miami", "china", "spa", "hungary", "zandvoort"]:
    sp = R.TRACKS[tr]; s25, v25, _ = R.load_ref(sp["csv25"]); s26, v26, _ = R.load_ref(sp["csv26"])
    s_, a_, b_, _ = R.align_pair(s25, v25, s26, v26, sp["length_m"], n=4096)
    vs = gaussian_filter1d(a_, 2, mode="wrap"); p, _ = find_peaks(vs, prominence=30); p = p[np.argsort(-vs[p])][:3]
    d = [float(gaussian_filter1d(b_, 2, mode="wrap")[i] - vs[i]) for i in p]; allr += d
    print(f"  {tr:10s} " + "  ".join(f"{vs[i]:.0f}:{x:+.0f}" for i, x in zip(p, d)))
vs = gaussian_filter1d(a, 2, mode="wrap"); p, _ = find_peaks(vs, prominence=30); p = p[np.argsort(-vs[p])][:3]
d = [float(gaussian_filter1d(b, 2, mode="wrap")[i] - vs[i]) for i in p]
print(f"  REAL median {np.median(allr):+.1f} (range {min(allr):+.0f}..{max(allr):+.0f})")
print(f"  SINGAPORE  " + "  ".join(f"{vs[i]:.0f}:{x:+.0f}" for i, x in zip(p, d)))
