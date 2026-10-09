"""Leave-one-out: fit the pattern model on 11 tracks, predict the 12th from its 2025 lap; compare with the real 2026
lap (lap time, trace correlation, RMSE) and with the naive baseline 2026 = 2025 lap x median growth."""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); import hlib, pmodel
TR = [c for c in hlib.pairs() if c != "Suzuka"]; out = {}
growth = {c: hlib.lap(c, 2026)["lap"] / hlib.lap(c, 2025)["lap"] for c in TR}
print(f"{'track':18s} real26   model   err    | naive   err   | corr  rmse km/h")
for c in TR:
    M = pmodel.fit([x for x in TR if x != c]); a, b = hlib.lap(c, 2025), hlib.lap(c, 2026)
    s, v, t = pmodel.predict(M, a); T = t[-1]
    naive = a["lap"] * np.median([growth[x] for x in TR if x != c])
    vr = np.interp(s / a["D"], b["d"] / b["D"], b["v"])
    A = hlib.align(a, b); vm = np.interp(A["s"], s, v)
    corr = np.corrcoef(vm, A["v26"])[0, 1]; rmse = np.sqrt(np.mean((vm - A["v26"]) ** 2))
    out[c] = dict(real=b["lap"], model=float(T), naive=float(naive), corr=float(corr), rmse=float(rmse))
    print(f"{c:18s} {b['lap']:7.3f} {T:7.3f} {T-b['lap']:+6.2f}  | {naive:7.3f} {naive-b['lap']:+5.2f} | {corr:.3f} {rmse:5.1f}")
e = np.array([o["model"] - o["real"] for o in out.values()]); en = np.array([o["naive"] - o["real"] for o in out.values()])
print(f"\nMODEL lap error: mean {e.mean():+.2f} s, |err| median {np.median(abs(e)):.2f} s, max {abs(e).max():.2f} s")
print(f"NAIVE lap error: mean {en.mean():+.2f} s, |err| median {np.median(abs(en)):.2f} s, max {abs(en).max():.2f} s")
json.dump(out, open(os.path.join(H, "loo.json"), "w"), indent=1)
