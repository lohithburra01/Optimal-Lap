import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); import hlib, rmodel
TR = [c for c in hlib.pairs() if c != "Suzuka"]; out = {}
growth = {c: hlib.lap(c, 2026)["lap"] / hlib.lap(c, 2025)["lap"] for c in TR}
print(f"{'track':18s} real26   model   err   | naive   err  | corr model/naive  rmse model/naive")
for c in TR:
    M = rmodel.fit([x for x in TR if x != c]); a, b = hlib.lap(c, 2025), hlib.lap(c, 2026)
    s, v, t = rmodel.predict(M, a); T = t[-1]; g = np.median([growth[x] for x in TR if x != c]); naive = a["lap"] * g
    A = hlib.align(a, b); vm = np.interp(A["s"], s, v); vn = A["v25"] / g
    cm, cn = np.corrcoef(vm, A["v26"])[0, 1], np.corrcoef(vn, A["v26"])[0, 1]
    rm, rn = np.sqrt(np.mean((vm - A["v26"]) ** 2)), np.sqrt(np.mean((vn - A["v26"]) ** 2))
    out[c] = dict(real=b["lap"], model=float(T), naive=float(naive), corr=float(cm), corr_naive=float(cn), rmse=float(rm), rmse_naive=float(rn), s=s[::5].tolist(), v=v[::5].tolist())
    print(f"{c:18s} {b['lap']:7.3f} {T:7.3f} {T-b['lap']:+5.2f}  | {naive:7.3f} {naive-b['lap']:+5.2f} | {cm:.3f}/{cn:.3f}       {rm:4.1f}/{rn:4.1f}")
e = np.array([o["model"] - o["real"] for o in out.values()]); en = np.array([o["naive"] - o["real"] for o in out.values()])
print(f"\nMODEL lap |err| median {np.median(abs(e)):.2f} s (mean {e.mean():+.2f}, max {abs(e).max():.2f}); trace rmse median {np.median([o['rmse'] for o in out.values()]):.1f} km/h")
print(f"NAIVE lap |err| median {np.median(abs(en)):.2f} s (mean {en.mean():+.2f}, max {abs(en).max():.2f}); trace rmse median {np.median([o['rmse_naive'] for o in out.values()]):.1f} km/h")
json.dump(out, open(os.path.join(H, "loo3.json"), "w"))
