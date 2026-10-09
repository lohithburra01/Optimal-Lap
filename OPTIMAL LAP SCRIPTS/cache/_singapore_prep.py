"""Singapore 2026 prep (2026-10-08).
1) Roll the outline so index 0 = the REAL S/F line. svg_to_outline's low-curvature
   heuristic put S/F 855 m early; a physics-lite speed profile on the outline
   matches the 2025 Q trace at corr 0.942 (fwd) with telemetry d=0 at arc 855 m.
2) Marina Bay runs ANTICLOCKWISE (as-drawn SVG order; reversed corr 0.39) but
   sim_2026_lap.build_raceline always drives CW. Instead of touching the engine,
   simulate on an x-mirrored outline (the physics is left/right symmetric;
   no banking at Singapore) and un-mirror the raceline for the video.
Usage: python cache/_singapore_prep.py prep | mirror IN OUT |   python cache/_singapore_prep.py unmirror IN_RL OUT_RL
"""
import json, sys, os
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(ROOT, "F1_Pipeline_Assets", "tracks")
REAL = os.path.join(T, "singapore_grand_prix_outline.json")
MIRR = os.path.join(T, "singapore_grand_prix_mirror_outline.json")
SF_ARC_M = 855.0

def prep():
    src = os.path.join(ROOT, "cache", "singapore_outline_autoSF.json")
    o = json.load(open(src))
    out, inn = np.array(o["outer"]), np.array(o["inner"])
    c = (out + inn) / 2
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))]
    k = int(np.argmin(np.abs(s - SF_ARC_M)))
    out, inn = np.roll(out, -k, axis=0), np.roll(inn, -k, axis=0)
    json.dump({"outer": out.tolist(), "inner": inn.tolist()}, open(REAL, "w"))
    m = np.array([-1.0, 1.0])
    json.dump({"outer": (out * m).tolist(), "inner": (inn * m).tolist()}, open(MIRR, "w"))
    print(f"[sg] S/F rolled by {k} pts ({s[k]:.0f} m); wrote {REAL} and {MIRR}")

def mirror(src, dst):
    o = json.load(open(src)); m = np.array([-1.0, 1.0])
    o["outer"] = (np.array(o["outer"]) * m).tolist(); o["inner"] = (np.array(o["inner"]) * m).tolist()
    json.dump(o, open(dst, "w")); print(f"[sg] mirrored outline -> {dst}")

def unmirror(src, dst):
    d = json.load(open(src))
    d["raceline"] = (np.array(d["raceline"]) * [-1.0, 1.0]).tolist()
    d["kappa"] = (-np.array(d["kappa"])).tolist()
    json.dump(d, open(dst, "w"))
    print(f"[sg] un-mirrored raceline -> {dst}")

if __name__ == "__main__":
    {"prep": lambda: prep(), "mirror": lambda: mirror(sys.argv[2], sys.argv[3]),
     "unmirror": lambda: unmirror(sys.argv[2], sys.argv[3])}[sys.argv[1]]()
