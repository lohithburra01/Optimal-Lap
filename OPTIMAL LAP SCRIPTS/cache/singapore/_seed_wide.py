"""Seed opt knots with a WIDE ENTRY across the road between two corners (user: after T8 exit the
line should cross back to the far side before T9, as RUS 2025). Moves knots in [a0,a1] m toward the
bound OPPOSITE their current side (frac of the way), raised-cosine blended, then the optimiser decides.
  python cache/singapore/_seed_wide.py BASE_RL OUTLINE KNOTS_IN KNOTS_OUT a0 a1 frac"""
import os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
sys.path.insert(0, os.path.join(ROOT, "cache", "era2017")); import _opt_line_2017 as O
base, outl, kin, kout, a0, a1, frac = sys.argv[1:8]; a0, a1, frac = float(a0), float(a1), float(frac)
O.setup(base, outl, None, None, 0.3, 12)
k = np.load(kin); ka = O.G["arc"][O.G["kidx"]]; lo = O.G["lo"][O.G["kidx"]]; hi = O.G["hi"][O.G["kidx"]]
mid = (lo + hi) / 2; tgt = np.where(k < mid, hi, lo)
w = np.clip(np.sin(np.pi * (ka - a0) / (a1 - a0)), 0, None) ** 0.5 * ((ka > a0) & (ka < a1))
k2 = k + frac * w * (tgt - k)
for i in np.where(w > 0)[0]: print(f"knot arc {ka[i]:.0f}: {k[i]:+.2f} -> {k2[i]:+.2f}  (lo {lo[i]:+.1f} hi {hi[i]:+.1f})")
np.save(kout, k2)
