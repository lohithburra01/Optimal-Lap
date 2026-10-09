"""Pattern-model (hybrid) prediction of the 2026 Singapore Q lap from RUS's 2025 pole, fitted on all 12 pairs;
plotted against our physics optimal lap and the 2026 FP1 fastest lap. -> singapore_pattern_vs_physics.png"""
import os, sys, json, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, H); sys.path.insert(0, os.path.join(ROOT, "cache"))
import hlib, rmodel, _track_registry as R
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
TR = [c for c in hlib.pairs() if c != "Suzuka"]; G = np.array([hlib.lap(c, 2026)["lap"] / hlib.lap(c, 2025)["lap"] for c in TR])
M = rmodel.fit(TR); a = hlib.lap("Singapore", 2025); s, v, t = rmodel.predict(M, a)
g = np.median(G); Tq = a["lap"] * g; v = v * t[-1] / Tq                       # hybrid: pattern shape, naive lap time
lo, hi = a["lap"] * np.percentile(G, 10), a["lap"] * np.percentile(G, 90)
print(f"growth over 12 pairs: median {100*(g-1):+.2f}% (p10 {100*(np.percentile(G,10)-1):+.2f}, p90 {100*(np.percentile(G,90)-1):+.2f})")
print(f"PREDICTED 2026 Singapore Q (pattern): {Tq:.3f} s = {int(Tq//60)}:{Tq%60:06.3f}  (p10-p90 {lo:.2f}-{hi:.2f})")
E = os.path.join(ROOT, "F1_Pipeline_Assets", "exports")
sp, vp, tp = R.load_ref(os.path.join(E, "singapore_2026_synthetic.csv")); sf, vf, tf = R.load_ref(os.path.join(E, "reference_2026_singapore_fp1.csv"))
D = 4927.0; g4 = np.linspace(0, D, 4000, endpoint=False)
fit_ = lambda ss, vv: np.interp(g4 / D, (ss - ss[0]) / (ss[-1] - ss[0]), vv)
vP = fit_(s, v); _, _, vPh, shp = R.align_pair(s, v, sp, vp, D, n=4000); _, _, vF, shf = R.align_pair(s, v, sf, vf, D, n=4000)
print(f"align shifts: physics {shp*D:+.0f} m, FP1 {shf*D:+.0f} m")
ds = g4[1] - g4[0]; T = lambda vv, lap: np.cumsum(ds / (vv / 3.6)) * lap / np.sum(ds / (vv / 3.6))
dPh = T(vPh, 93.008) - T(vP, Tq); dF = T(vF, 92.274) - T(vP, Tq)
for x0, x1, nm in ((0, 600, "S/F-T3"), (600, 1000, "T5"), (1000, 1700, "to T7"), (1700, 2250, "T7-T9"), (2250, 3100, "T10-T13"), (3100, 3800, "to T14"), (3800, 4400, "to T16"), (4400, 4927, "final")):
    i0, i1 = np.searchsorted(g4, x0), min(np.searchsorted(g4, x1), len(g4) - 1); print(f"  {nm:9s} physics vs pattern {dPh[i1]-dPh[i0]:+.2f} s | FP1 vs pattern {dF[i1]-dF[i0]:+.2f} s")
INK, MUTED, GRID = "#1a1a19", "#6b6a63", "#e6e5df"
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(16, 9.5), dpi=110, sharex=True, gridspec_kw=dict(height_ratios=[3, 2]))
ax.plot(g4, vF, color="#9a9990", lw=1.4, ls="--", label="FP1 fastest 2026 - Russell 1:32.274")
ax.plot(g4, vP, color="#eb6834", lw=2.2, label=f"Pattern prediction 2026 Q {int(Tq//60)}:{Tq%60:06.3f}")
ax.plot(g4, vPh, color="#2a78d6", lw=2.0, label="Our physics optimal lap 1:33.008")
for x in (ax, ax2):
    for sp_ in ("top", "right"): x.spines[sp_].set_visible(False)
    for sp_ in ("left", "bottom"): x.spines[sp_].set_color(GRID)
    x.grid(True, color=GRID, lw=0.8); x.set_axisbelow(True); x.tick_params(colors=MUTED)
ax.set_ylabel("Speed (km/h)", color=MUTED); ax.set_ylim(50, 345); ax.legend(loc="lower right", frameon=False, labelcolor=INK)
ax.set_title("Singapore 2026 - pattern-predicted Q lap vs our physics optimal lap", loc="left", color=INK, fontsize=15, fontweight="bold", pad=14)
ax2.axhline(0, color=MUTED, lw=1); ax2.plot(g4, dPh, color="#2a78d6", lw=2, label="physics optimal minus pattern"); ax2.plot(g4, dF, color="#9a9990", lw=1.4, ls="--", label="FP1 minus pattern")
ax2.set_ylabel("Delta (s)", color=MUTED); ax2.set_xlabel("Lap distance (m)", color=MUTED); ax2.legend(loc="upper left", frameon=False, labelcolor=INK)
ax2.set_title("Time delta to the pattern prediction (above 0 = slower than the prediction)", loc="left", color=INK, fontsize=12, pad=8)
ax2.annotate(f"{dPh[-1]:+.2f} s", (g4[-1], dPh[-1]), xytext=(-8, 6), textcoords="offset points", ha="right", color="#2a78d6", fontweight="bold")
ax2.annotate(f"{dF[-1]:+.2f} s", (g4[-1], dF[-1]), xytext=(-8, -16), textcoords="offset points", ha="right", color=MUTED, fontweight="bold")
plt.tight_layout(); out = os.path.join(ROOT, "singapore_pattern_vs_physics.png"); plt.savefig(out); print("wrote", out)
json.dump(dict(pred_lap=Tq, p10=lo, p90=hi, growth_median=g, s=g4[::4].tolist(), v=vP[::4].tolist()), open(os.path.join(H, "singapore_pattern.json"), "w"))
