"""LOO for the difference model (pmodel.fit2/predict2). Lap = real 2025 lap x (model26 / model-zero-shift25), so
the integration bias cancels. Trace compared with the real 2026 lap via corner-anchored alignment."""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); import hlib, pmodel
TR = [c for c in hlib.pairs() if c != "Suzuka"]; out = {}
growth = {c: hlib.lap(c, 2026)["lap"] / hlib.lap(c, 2025)["lap"] for c in TR}
print(f"{'track':18s} real26   model   err   | naive   err  | corr  rmse")
for c in TR:
    M = pmodel.fit2([x for x in TR if x != c]); a, b = hlib.lap(c, 2025), hlib.lap(c, 2026)
    s, v, t = pmodel.predict2(M, a); s0, v0, t0 = pmodel.predict2(M, a, zero=True)
    T = a["lap"] * t[-1] / t0[-1]; naive = a["lap"] * np.median([growth[x] for x in TR if x != c])
    A = hlib.align(a, b); vm = np.interp(A["s"], s, v) * 1.0
    corr = np.corrcoef(vm, A["v26"])[0, 1]; rmse = np.sqrt(np.mean((vm - A["v26"]) ** 2))
    out[c] = dict(real=b["lap"], model=float(T), naive=float(naive), corr=float(corr), rmse=float(rmse), s=s[::5].tolist(), v=v[::5].tolist())
    print(f"{c:18s} {b['lap']:7.3f} {T:7.3f} {T-b['lap']:+5.2f}  | {naive:7.3f} {naive-b['lap']:+5.2f} | {corr:.3f} {rmse:4.1f}")
e = np.array([o["model"] - o["real"] for o in out.values()]); en = np.array([o["naive"] - o["real"] for o in out.values()])
print(f"\nMODEL lap error: mean {e.mean():+.2f}, |err| median {np.median(abs(e)):.2f}, max {abs(e).max():.2f} s;  trace corr median {np.median([o['corr'] for o in out.values()]):.3f}")
print(f"NAIVE lap error: mean {en.mean():+.2f}, |err| median {np.median(abs(en)):.2f}, max {abs(en).max():.2f} s")
json.dump(out, open(os.path.join(H, "loo2.json"), "w"))
