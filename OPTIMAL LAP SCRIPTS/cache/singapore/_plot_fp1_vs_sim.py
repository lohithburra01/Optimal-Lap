"""Speed vs distance: 2026 Singapore FP1 fastest lap (RUS 1:32.274, OpenF1) vs our 2026 optimal lap (1:33.008).
Both normalised to the FIA 4927 m lap and start-line aligned (align_pair FFT shift). -> singapore_fp1_vs_optimal_speed_delta.png"""
import os, sys, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H)); sys.path.insert(0, os.path.join(ROOT, "cache"))
import _track_registry as R
E = os.path.join(ROOT, "F1_Pipeline_Assets", "exports")
sf, vf, tf = R.load_ref(os.path.join(E, "reference_2026_singapore_fp1.csv")); ss, vs, ts = R.load_ref(os.path.join(E, "singapore_2026_synthetic.csv"))
s, a, b, shift = R.align_pair(sf, vf, ss, vs, 4927.0, n=4096)
print(f"align shift {shift*4927:+.0f} m; corr {np.corrcoef(a, b)[0,1]:.3f}; vmax FP1 {a.max():.0f} sim {b.max():.0f}")
INK, MUTED, GRID = "#1a1a19", "#6b6a63", "#e6e5df"; C_SIM, C_FP1 = "#2a78d6", "#eb6834"
# cumulative time from the aligned speed traces, each scaled to its official lap time
ds = s[1] - s[0]; tA = np.cumsum(ds / (a / 3.6)); tB = np.cumsum(ds / (b / 3.6))
tA *= 92.274 / tA[-1]; tB *= 93.008 / tB[-1]; delta = tB - tA          # + = our lap behind FP1
print(f"delta at the flag {delta[-1]:+.3f} s; max {delta.max():+.3f} at {s[np.argmax(delta)]:.0f} m; min {delta.min():+.3f} at {s[np.argmin(delta)]:.0f} m")
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(16, 9.5), dpi=110, sharex=True, gridspec_kw=dict(height_ratios=[3, 2]))
fig.patch.set_facecolor("white")
ax.plot(s, a, color=C_FP1, lw=2, label="FP1 fastest - Russell 1:32.274")
ax.plot(s, b, color=C_SIM, lw=2, label="Our 2026 optimal lap 1:33.008")
for sp in ("top", "right"): ax.spines[sp].set_visible(False)
for sp in ("left", "bottom"): ax.spines[sp].set_color(GRID)
ax.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True); ax.tick_params(colors=MUTED)
ax.set_xlim(0, 4927); ax.set_ylim(50, 340); ax.set_xlabel("Lap distance (m)", color=MUTED); ax.set_ylabel("Speed (km/h)", color=MUTED)
ax.set_title("Singapore 2026 - FP1 fastest lap vs our optimal lap", loc="left", color=INK, fontsize=15, fontweight="bold", pad=14)
ax.legend(loc="lower right", frameon=False, labelcolor=INK); ax.set_xlabel("")
ax2.axhline(0, color=MUTED, lw=1)
ax2.fill_between(s, delta, 0, where=delta >= 0, color=C_FP1, alpha=0.18, lw=0); ax2.fill_between(s, delta, 0, where=delta < 0, color=C_SIM, alpha=0.18, lw=0)
ax2.plot(s, delta, color=INK, lw=2)
for sp in ("top", "right"): ax2.spines[sp].set_visible(False)
for sp in ("left", "bottom"): ax2.spines[sp].set_color(GRID)
ax2.grid(True, color=GRID, lw=0.8); ax2.set_axisbelow(True); ax2.tick_params(colors=MUTED)
ax2.set_ylabel("Delta (s)", color=MUTED); ax2.set_xlabel("Lap distance (m)", color=MUTED)
ax2.set_title("Time delta: our optimal lap minus FP1 fastest  (above 0 = we are behind)", loc="left", color=INK, fontsize=12, pad=8)
ax2.annotate(f"{delta[-1]:+.2f} s", (s[-1], delta[-1]), xytext=(-8, 8), textcoords="offset points", ha="right", color=INK, fontsize=11, fontweight="bold")
plt.tight_layout(); out = os.path.join(ROOT, "singapore_fp1_vs_optimal_speed_delta.png"); plt.savefig(out); print("wrote", out)
