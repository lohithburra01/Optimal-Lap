"""Physics optimal laps (shipped 2026 sims) vs the pattern HYBRID, both scored against the REAL 2026 Q lap:
lap-time error and speed-trace RMSE (corner-anchored alignment onto the real 2026 lap)."""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, H); import hlib
E = os.path.join(ROOT, "F1_Pipeline_Assets", "exports")
MAP = {"austria": "Spielberg", "canada": "Montreal", "catalunya": "Catalunya", "hungary": "Hungaroring", "monaco": "Monte Carlo",
       "monza": "Monza", "silverstone": "Silverstone", "spa": "Spa-Francorchamps", "zandvoort": "Zandvoort"}
FP1_TUNED = {"silverstone", "monaco", "canada", "catalunya"}
L3 = json.load(open(os.path.join(H, "loo3.json"))); rows = []
def simlap(path):
    d = np.genfromtxt(path, delimiter=",", names=True, dtype=None, encoding=None)
    t, s, v = d["time_s"].astype(float), d["distance"].astype(float), d["speed"].astype(float)
    z = np.zeros(len(t)); return dict(t=t, d=s, v=v, thr=z, brk=z, gear=z, drs=z, lap=float(t[-1]), D=float(s[-1]))
print(f"{'track':12s} {'kind':9s} real26  | physics  err   rmse | hybrid  err   rmse")
for k, c in MAP.items():
    b = hlib.lap(c, 2026); p = simlap(os.path.join(E, f"{k}_2026_synthetic.csv")); A = hlib.align(b, p)
    rp = np.sqrt(np.mean((A["v26"] - A["v25"]) ** 2))                     # here "25" = real 2026, "26" = physics sim
    o = L3[c]; a = hlib.lap(c, 2025); s = np.array(o["s"]); v = np.array(o["v"]) * o["model"] / o["naive"]
    hyb = dict(t=np.cumsum(np.r_[0, np.diff(s)] / (v / 3.6)), d=s, v=v, thr=np.zeros(len(s)), brk=np.zeros(len(s)), gear=np.zeros(len(s)), drs=np.zeros(len(s)), lap=o["naive"], D=float(s[-1]))
    B = hlib.align(b, hyb); rh = np.sqrt(np.mean((B["v26"] - B["v25"]) ** 2))
    rows.append((k, p["lap"] - b["lap"], rp, o["naive"] - b["lap"], rh))
    print(f"{k:12s} {'FP1-tuned' if k in FP1_TUNED else 'pre-FP1':9s} {b['lap']:7.3f} | {p['lap']:7.3f} {p['lap']-b['lap']:+5.2f} {rp:5.1f} | {o['naive']:7.3f} {o['naive']-b['lap']:+5.2f} {rh:5.1f}")
r = np.array([x[1:] for x in rows])
print(f"\nmedian |lap err|: physics {np.median(abs(r[:,0])):.2f} s, hybrid {np.median(abs(r[:,2])):.2f} s;  median trace rmse: physics {np.median(r[:,1]):.1f}, hybrid {np.median(r[:,3]):.1f} km/h")
pre = [i for i, x in enumerate(rows) if x[0] not in FP1_TUNED]
print(f"pre-FP1 only: |lap err| physics {np.median(abs(r[pre,0])):.2f} vs hybrid {np.median(abs(r[pre,2])):.2f}; rmse physics {np.median(r[pre,1]):.1f} vs hybrid {np.median(r[pre,3]):.1f}")
json.dump(rows, open(os.path.join(H, "vs_physics.json"), "w"))
