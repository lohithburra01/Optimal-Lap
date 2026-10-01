"""Top-down 2017 vs 2026 line comparison, zoomed where the lines differ most.
  python cache/era2017/_plot_lines.py <line2017_rl.json> <out.png>"""
import json, os, sys
import numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
o = json.load(open(os.path.join(ROOT, "F1_Pipeline_Assets", "tracks", "malaysian_grand_prix_outline.json")))
L26 = np.asarray(json.load(open(os.path.join(ROOT, "F1_Pipeline_Assets", "tracks", "malaysian_grand_prix_raceline.json")))["raceline"])[:, :2]
L17 = np.asarray(json.load(open(sys.argv[1]))["raceline"])[:, :2]
outer, inner = np.asarray(o["outer"]), np.asarray(o["inner"])
dist = cKDTree(L26).query(L17)[0]                       # lateral gap 2017 -> 2026 line
seg = np.linalg.norm(np.diff(L17, axis=0, append=L17[:1]), axis=1); arc = np.cumsum(seg) - seg
# pick up to 8 windows around the biggest separations, >= 250 m apart
order = np.argsort(-dist); picks = []
for i in order:
    if dist[i] < 0.8 or len(picks) == 8: break
    if all(min(abs(arc[i] - arc[j]), arc[-1] - abs(arc[i] - arc[j])) > 250 for j in picks): picks.append(i)
picks.sort(key=lambda i: arc[i])
n = max(1, len(picks)); cols = 2; rows = (n + 1) // 2
fig = plt.figure(figsize=(14, 4 + 6 * rows), facecolor="#111")
ax0 = fig.add_subplot(rows + 1, 1, 1); ax0.set_facecolor("#111")
for e in (outer, inner): ax0.plot(*np.vstack([e, e[:1]]).T, color="#888", lw=0.8)
ax0.plot(*L26.T, color="#00cdff", lw=0.8); ax0.plot(*L17.T, color="#ff9600", lw=0.8)
for k, i in enumerate(picks): ax0.annotate(str(k + 1), L17[i], color="w", fontsize=12, weight="bold")
ax0.set_aspect("equal"); ax0.axis("off")
ax0.set_title("orange = 2017 car (physics line)   cyan = 2026 shipped line   - numbers = zooms below",
              color="w", loc="left")
for k, i in enumerate(picks):
    ax = fig.add_subplot(rows + 1, cols, cols + k + 1); ax.set_facecolor("#111")
    c = L17[i]; R = 90
    for e in (outer, inner): ax.plot(*np.vstack([e, e[:1]]).T, color="#ddd", lw=1.5)
    ax.plot(*L26.T, color="#00cdff", lw=2.0, label="2026"); ax.plot(*L17.T, color="#ff9600", lw=2.0, label="2017")
    ax.set_xlim(c[0] - R, c[0] + R); ax.set_ylim(c[1] - R, c[1] + R); ax.set_aspect("equal")
    ax.set_title(f"{k + 1}: arc {arc[i]:.0f} m, max gap {dist[i]:.1f} m", color="w", fontsize=11)
    ax.tick_params(colors="#666")
plt.tight_layout(); plt.savefig(sys.argv[2], dpi=70, facecolor="#111")
print("windows:", [(round(arc[i]), round(dist[i], 2)) for i in picks])
