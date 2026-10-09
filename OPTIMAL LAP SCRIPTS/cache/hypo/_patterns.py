"""2025 -> 2026 universal patterns from 12 real Q pairs (Suzuka excluded: 2026 trace inconsistent).
Writes cache/hypo/patterns.json (pooled curves) + patterns.png, prints per-track tables."""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); import hlib
from scipy.ndimage import gaussian_filter1d
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
EXCL = {"Suzuka"}; TR = [c for c in hlib.pairs() if c not in EXCL]
VB = np.arange(60, 341, 20)
def accel(L):
    t, v = L["t"], gaussian_filter1d(L["v"], 1.0); a = np.gradient(v, t) / 3.6   # m/s^2
    return a
def full_throttle_curve(L):
    a = accel(L); m = (L["thr"] >= 98) & (L["brk"] == 0)
    # time since this full-throttle run began
    tau = np.zeros(len(a)); start = None
    for i in range(len(a)):
        if m[i]: start = L["t"][i] if start is None else start; tau[i] = L["t"][i] - start
        else: start = None
    return a[m], L["v"][m], tau[m]
def brake_curve(L):
    a = accel(L); m = (L["brk"] > 0) & (a < -3); return -a[m], L["v"][m]
def binmed(x, y, bins=VB, nmin=4):
    out = []
    for lo in bins[:-1]:
        s = (x >= lo) & (x < lo + 20); out.append(float(np.median(y[s])) if s.sum() >= nmin else np.nan)
    return np.array(out)
res = dict(tracks=TR, vbins=VB[:-1].tolist()); per = {}
pool = {k: [] for k in ("mn25", "mn26", "a25v", "a25", "a26v", "a26", "a26tau", "b25v", "b25", "b26v", "b26")}
print(f"{'track':18s} lap%  | corner ratio med | full-thr accel ratio 26/25 @100-180 / 200-260 / 280+ | brake decel 26/25 | top 25->26 | lift>200 s 25/26")
for c in TR:
    a, b = hlib.lap(c, 2025), hlib.lap(c, 2026); A = hlib.align(a, b)
    s25, m25 = hlib.minima(a["d"], a["v"]); s26, m26 = hlib.minima(b["d"], b["v"])
    pr = []
    for x, y in zip(s25, m25):
        j = np.argmin(abs(s26 / b["D"] - x / a["D"]))
        if abs(s26[j] / b["D"] - x / a["D"]) < 0.02: pr.append((y, m26[j]))
    pr = np.array(pr); pool["mn25"] += pr[:, 0].tolist(); pool["mn26"] += pr[:, 1].tolist()
    x5, v5, _ = full_throttle_curve(a); x6, v6, tau6 = full_throttle_curve(b)
    pool["a25v"] += v5.tolist(); pool["a25"] += x5.tolist(); pool["a26v"] += v6.tolist(); pool["a26"] += x6.tolist(); pool["a26tau"] += tau6.tolist()
    d5, w5 = brake_curve(a); d6, w6 = brake_curve(b)
    pool["b25v"] += w5.tolist(); pool["b25"] += d5.tolist(); pool["b26v"] += w6.tolist(); pool["b26"] += d6.tolist()
    rr = lambda lo, hi: np.median(x6[(v6 >= lo) & (v6 < hi)]) / np.median(x5[(v5 >= lo) & (v5 < hi)])
    lift = lambda L: float(np.sum(np.diff(L["t"], append=L["t"][-1])[(L["thr"] < 90) & (L["brk"] == 0) & (L["v"] > 200)]))
    per[c] = dict(lap=100 * (b["lap"] / a["lap"] - 1), corner=float(np.median(pr[:, 1] / pr[:, 0])),
                  acc=[rr(100, 180), rr(200, 260), rr(280, 400)], brake=float(np.median(d6) / np.median(d5)),
                  top=[float(a["v"].max()), float(b["v"].max())], lift=[lift(a), lift(b)])
    p = per[c]
    print(f"{c:18s} {p['lap']:+4.1f} |      {p['corner']:.3f}      |   {p['acc'][0]:.2f} / {p['acc'][1]:.2f} / {p['acc'][2]:.2f}      |     {p['brake']:.2f}      | {p['top'][0]:.0f}->{p['top'][1]:.0f} |  {p['lift'][0]:.1f}/{p['lift'][1]:.1f}")
P = {k: np.array(v) for k, v in pool.items()}
res["corner_v25"] = P["mn25"].tolist(); res["corner_ratio"] = (P["mn26"] / P["mn25"]).tolist()
res["acc25"] = binmed(P["a25v"], P["a25"]).tolist(); res["acc26"] = binmed(P["a26v"], P["a26"]).tolist()
res["brk25"] = binmed(P["b25v"], P["b25"]).tolist(); res["brk26"] = binmed(P["b26v"], P["b26"]).tolist()
# 2026 full-throttle accel vs time into the run, at high speed (energy-clipping signature)
TB = np.arange(0, 16, 2); hs = P["a26v"] >= 250; hs5 = P["a25v"] >= 250
res["tau_bins"] = TB[:-1].tolist()
res["acc26_tau_hs"] = [float(np.median(P["a26"][hs & (P["a26tau"] >= t0) & (P["a26tau"] < t0 + 2)])) if (hs & (P["a26tau"] >= t0) & (P["a26tau"] < t0 + 2)).sum() > 5 else None for t0 in TB[:-1]]
res["per_track"] = per
json.dump(res, open(os.path.join(H, "patterns.json"), "w"), indent=1)
print("\npooled full-throttle accel (m/s^2) by speed bin:")
print(" v   " + " ".join(f"{x:5d}" for x in VB[:-1])); print(" 25  " + " ".join(f"{x:5.1f}" for x in res["acc25"])); print(" 26  " + " ".join(f"{x:5.1f}" for x in res["acc26"]))
print("pooled braking decel (m/s^2):"); print(" 25  " + " ".join(f"{x:5.1f}" for x in res["brk25"])); print(" 26  " + " ".join(f"{x:5.1f}" for x in res["brk26"]))
print("2026 full-throttle accel at >=250 km/h vs seconds into the run:", [None if x is None else round(x, 2) for x in res["acc26_tau_hs"]])
# figure
fig, ax = plt.subplots(2, 2, figsize=(15, 10)); C25, C26 = "#2a78d6", "#eb6834"
ax[0, 0].scatter(P["mn25"], P["mn26"] / P["mn25"], s=14, c=C26); ax[0, 0].axhline(1, c="#999", lw=1); ax[0, 0].set_title("Corner minimum: 2026/2025 ratio vs 2025 speed"); ax[0, 0].set_xlabel("2025 corner speed (km/h)")
vc = VB[:-1] + 10
ax[0, 1].plot(vc, res["acc25"], c=C25, lw=2, label="2025"); ax[0, 1].plot(vc, res["acc26"], c=C26, lw=2, label="2026"); ax[0, 1].legend(); ax[0, 1].set_title("Full-throttle acceleration vs speed (m/s²)"); ax[0, 1].set_xlabel("speed (km/h)")
ax[1, 0].plot(vc, res["brk25"], c=C25, lw=2, label="2025"); ax[1, 0].plot(vc, res["brk26"], c=C26, lw=2, label="2026"); ax[1, 0].legend(); ax[1, 0].set_title("Braking deceleration vs speed (m/s²)"); ax[1, 0].set_xlabel("speed (km/h)")
tt = [x for x in res["acc26_tau_hs"]]; ax[1, 1].plot(np.array(res["tau_bins"]) + 1, [np.nan if x is None else x for x in tt], c=C26, lw=2, marker="o", label="2026 (>=250 km/h)")
a5 = [float(np.median(P["a25"][hs5 & (np.array([0]*0 or [0]) == 0)])) ] if False else None
ax[1, 1].axhline(float(np.median(P["a25"][hs5])), c=C25, lw=2, ls="--", label="2025 median (>=250 km/h)"); ax[1, 1].axhline(0, c="#999", lw=1)
ax[1, 1].set_title("2026 high-speed acceleration vs seconds into the straight (clipping)"); ax[1, 1].set_xlabel("seconds since full throttle"); ax[1, 1].legend()
for x in ax.flat: x.grid(True, color="#e6e5df"); [x.spines[s].set_visible(False) for s in ("top", "right")]
plt.tight_layout(); plt.savefig(os.path.join(H, "patterns.png"), dpi=80)
