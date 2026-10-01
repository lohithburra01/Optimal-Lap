"""Sepang T1: pull the racing line onto the inside kerb at the late apex (FITTED edit).

The min-curvature optimiser runs T1 wide and its closest approach to the T1
inside edge is ~3.8 m (centre), i.e. the car never reaches the kerb, while
real drivers clip it at a late apex before the short run to the T2 left.
This moves the line laterally toward the inside edge with a raised-cosine
taper of half-length H metres centred on that closest-approach station, so
the car centre sits GAP m from the painted edge at the apex (car half-width
0.95 m -> wheels on the kerb). Entry, T2 apex and everything else unchanged.
The output is simulated with `sim_2026_lap.py --raceline-in`.

  python cache/_sepang_t1_apex.py --half 45 --out cache/sepang/t1_h45.json
"""
import argparse, json
import numpy as np
from scipy.spatial import cKDTree

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="F1_Pipeline_Assets/tracks/malaysian_grand_prix_raceline.json")
ap.add_argument("--outline", default="F1_Pipeline_Assets/tracks/malaysian_grand_prix_outline.json")
ap.add_argument("--window", default="560,640", help="arc range [m] holding the T1 late apex")
ap.add_argument("--gap", type=float, default=1.0, help="apex centre-to-edge gap [m]")
ap.add_argument("--half", type=float, required=True, help="taper half-length before the apex [m]")
ap.add_argument("--half-exit", type=float, default=None,
                help="taper half-length after the apex [m] (default = --half); keep it short "
                     "enough that the T2 apex, ~58 m after the T1 apex, is not dragged")
ap.add_argument("--out", required=True)
ap.add_argument("--hold-from", type=float, default=None,
                help="arc [m] where the car should ALREADY be on the inside kerb; the line "
                     "holds GAP from there to the apex (earlier, onboard-style inside). "
                     "Omitted = single-point apex pull (the shipped H60 edit).")
a = ap.parse_args()

src = json.load(open(a.src)); o = json.load(open(a.outline))
P = np.asarray(src["raceline"], float)[:, :2]; arc = np.asarray(src["arc_length"], float)
L = float(src["track_length_m"])
inner = np.asarray(o["inner"], float)          # T1 inside edge (verified on the zoom plot)
tree = cKDTree(inner)
lo, hi = map(float, a.window.split(","))
win = np.where((arc >= lo) & (arc <= hi))[0]
d, k = tree.query(P[win]); j0 = win[np.argmin(d)]
gap0 = float(d.min())
# unit left-normal of the line; sign it toward the inside edge at the apex
t = np.roll(P, -1, 0) - np.roll(P, 1, 0); t /= np.linalg.norm(t, axis=1)[:, None]
nrm = np.column_stack([-t[:, 1], t[:, 0]])
to_edge = inner[tree.query(P[j0])[1]] - P[j0]
sgn = np.sign(nrm[j0] @ to_edge)
d0 = gap0 - a.gap
ds = (arc - arc[j0] + L / 2) % L - L / 2           # signed distance from apex, wrapped
he = a.half if a.half_exit is None else a.half_exit
hs = np.where(ds < 0, a.half, he)                  # asymmetric raised cosine
w = np.where(np.abs(ds) < hs, 0.5 * (1 + np.cos(np.pi * ds / hs)), 0.0)
if a.hold_from is not None:
    # per-station pull so every station from hold_from to the apex sits GAP from the
    # inside edge, raised-cosine ramps outside that span, then a light smooth of the
    # shift profile (no kinks in the drawn line)
    from scipy.ndimage import gaussian_filter1d
    hold_lo = (arc[j0] - a.hold_from) % L
    gaps = tree.query(P)[0]
    shift = np.zeros(len(P))
    span = (ds >= -hold_lo) & (ds <= 0)
    shift[span] = np.maximum(gaps[span] - a.gap, 0.0)
    d_start = shift[span][np.argmin(ds[span])]        # shift at hold start
    ent = (ds < -hold_lo) & (ds > -hold_lo - a.half)
    shift[ent] = d_start * 0.5 * (1 + np.cos(np.pi * (ds[ent] + hold_lo) / a.half))
    ex = (ds > 0) & (ds < he)
    shift[ex] = d0 * 0.5 * (1 + np.cos(np.pi * ds[ex] / he))
    shift = gaussian_filter1d(shift, 3.0, mode="wrap")
    w = shift / max(d0, 1e-9)
Q = P + (sgn * d0 * w)[:, None] * nrm
print(f"apex station {j0} arc {arc[j0]:.0f} m: gap {gap0:.2f} -> {tree.query(Q[j0])[0]:.2f} m "
      f"(shift {d0:.2f} m, taper -{a.half:.0f}/+{he:.0f} m, {int((w > 0).sum())} stations)")
json.dump({"raceline": Q.tolist(), "arc_length": arc.tolist(), "track_length_m": L,
           "note": f"Sepang T1 late-apex FITTED edit: gap {a.gap} m, half {a.half}/{he} m, src {a.src}"},
          open(a.out, "w"))
