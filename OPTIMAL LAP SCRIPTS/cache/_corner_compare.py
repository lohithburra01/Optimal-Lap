"""Per-corner geometry check: sim apex speeds vs a real reference lap scaled by the
2025->2026 corner-speed ratio r(v25) (cache/transfer_2026.json). Big residuals of
BOTH signs at fixed knobs = SVG corner-shape error (CL cannot fix geometry).
  python cache/_corner_compare.py <sim.csv> <ref25.csv> <length_m>"""
import sys, json, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _track_registry as R
sim, ref, L = sys.argv[1], sys.argv[2], float(sys.argv[3])
tr = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "transfer_2026.json")))
s25, v25, t25 = R.load_ref(ref); ss, vs, ts = R.load_ref(sim)
g, va, vb, sh = R.align_pair(s25, v25, ss, vs, L)
corr = float(np.corrcoef(va, vb)[0, 1])
m25 = R.corner_minima(g, va); msim = R.corner_minima(g, vb)
pairs, rate = R.pair_minima(m25, msim, L)
print(f"lap sim {ts:.2f} vs ref {t25:.2f}  trace corr {corr:.3f}  corner pairing {rate:.0%}")
res = []
for sa, va_, sb, vb_ in pairs:
    tgt = va_ * np.interp(va_, tr["knots_v25"], tr["r_knots"])
    res.append(vb_ - tgt)
    flag = "  <-- " + ("TOO FAST" if vb_ - tgt > 10 else "TOO SLOW") if abs(vb_ - tgt) > 10 else ""
    print(f"  {sa:6.0f} m  2025 {va_:5.0f}  2026 target {tgt:5.0f}  sim {vb_:5.0f}  resid {vb_ - tgt:+5.0f}{flag}")
r = np.array(res)
print(f"median resid {np.median(r):+.1f}  |resid| max {np.abs(r).max():.0f}  n>10: {(np.abs(r) > 10).sum()}/{len(r)}")
