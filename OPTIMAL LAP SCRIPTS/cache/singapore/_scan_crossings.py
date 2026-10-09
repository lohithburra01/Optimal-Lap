"""Scan a line for missed 'cross back to the outside' between consecutive OPPOSITE-direction corners.
For each pair (apex A, apex B, opposite turn), report the max lateral swing toward B's OUTSIDE
reached between them (0 = on B's inside bound, 1 = on B's outside bound).
  python cache/singapore/_scan_crossings.py BASE_RL OUTLINE RL_JSON"""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
sys.path.insert(0, os.path.join(ROOT, "cache", "era2017")); sys.path.insert(0, os.path.join(ROOT, "cache", "bahrain"))
import _opt_line_2017 as O, _apex_gaps as AG
O.setup(sys.argv[1], sys.argv[2], None, None, 0.3, 12)
rl = np.array(json.load(open(sys.argv[3]))["raceline"])
pk, kap = AG.corners(rl, O.G["arc"], O.G["L"])
off = np.einsum("ij,ij->i", rl - O.G["P"], O.G["N"]); lo, hi, arc = O.G["lo"], O.G["hi"], O.G["arc"]
for a, b in zip(pk, pk[1:] + pk[:1]):
    if np.sign(kap[a]) == np.sign(kap[b]): continue
    idx = np.arange(a, b if b > a else b + len(rl)) % len(rl)
    pos = (hi[idx] - off[idx]) / (hi[idx] - lo[idx]) if kap[b] > 0 else (off[idx] - lo[idx]) / (hi[idx] - lo[idx])
    gap = (arc[b] - arc[a]) % O.G["L"]
    print(f"{arc[a]:5.0f} -> {arc[b]:5.0f} m (gap {gap:4.0f}, R_b {1/abs(kap[b]):4.0f} m): max toward B-outside {pos.max():.2f}"
          + ("   <-- stays inside" if pos.max() < 0.6 and gap > 80 else ""))
