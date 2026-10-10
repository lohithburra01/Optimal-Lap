"""Delta graph from the delta engine (v2 = HI-FI DELTA v2 by default, --delta-engine v1 = original): P2's time to P1 along the lap.
  python delta_graph.py --track "Singapore Grand Prix" --year 2026 --session Q --drivers VER,LEC
+ = P2 behind P1 (red), - = P2 ahead (green): same convention as the video's METERS line."""
import argparse, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import lap_compare_optimal as LCO, optimal_x_quali as Q
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

FONT_DIR = r"C:\Users\91910\Downloads\Formula1"
RED, GREEN, INK, MUTED, GRID = "#E6463C", "#3CD264", "#FFFFFF", "#9A9A9A", "#2A2A2A"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default=Q.TRACK); ap.add_argument("--year", type=int, default=Q.YEAR)
    ap.add_argument("--session", default=Q.SESSION); ap.add_argument("--drivers", default=Q.DRIVERS)
    ap.add_argument("--out", default=None)
    ap.add_argument("--delta-engine", default=Q.DELTA_ENGINE, choices=["v1", "v2"])
    a = ap.parse_args()
    traces, event, _ = Q.load_traces(a.track, a.year, a.session.upper(), a.drivers)
    ref, tgt = traces
    dist, delta = Q.delta_fn(a.delta_engine)(ref, tgt)
    km = dist / 1000.0

    for f in ("Formula1-Bold_web_0.ttf.ttf", "Formula1-Regular_web_0.ttf.ttf"):
        p = os.path.join(FONT_DIR, f)
        if os.path.exists(p): fm.fontManager.addfont(p)
    bold = fm.FontProperties(fname=os.path.join(FONT_DIR, "Formula1-Bold_web_0.ttf.ttf"))
    reg = fm.FontProperties(fname=os.path.join(FONT_DIR, "Formula1-Regular_web_0.ttf.ttf"))

    fig, ax = plt.subplots(figsize=(16, 9), dpi=120, facecolor="black")
    ax.set_facecolor("black")
    ax.fill_between(km, 0, delta, where=delta >= 0, color=RED, alpha=0.22, linewidth=0, interpolate=True)
    ax.fill_between(km, 0, delta, where=delta < 0, color=GREEN, alpha=0.22, linewidth=0, interpolate=True)
    ax.axhline(0, color=MUTED, lw=1)
    ax.plot(km, delta, color=INK, lw=2.2, solid_capstyle="round")
    lim = max(abs(delta).max() * 1.25, 0.05)
    ax.set_ylim(-lim, lim); ax.set_xlim(0, km[-1])
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ax.spines.values(): s.set_visible(False)
    ax.tick_params(colors=MUTED, length=0, labelsize=13)
    for t in ax.get_xticklabels() + ax.get_yticklabels(): t.set_fontproperties(reg); t.set_fontsize(13)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:+.2f}s" if v else "0"))
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f} km" if v else "0"))

    r, t = ref['label'], tgt['label']
    ax.text(km[-1] * 0.995, lim * 0.92, f"{t} BEHIND {r}", color=RED, fontproperties=reg, fontsize=13, ha="right", alpha=0.85)
    ax.text(km[-1] * 0.995, -lim * 0.92, f"{t} AHEAD OF {r}", color=GREEN, fontproperties=reg, fontsize=13, ha="right",
            va="bottom", alpha=0.85)
    # selective direct labels: biggest deficit, biggest lead, finish
    i_hi, i_lo = int(np.argmax(delta)), int(np.argmin(delta))
    picks = [i for i in {i_hi, i_lo} if abs(delta[i]) > 0.02 and km[-1] - km[i] > 0.4]   # finish has its own label
    for i in picks:
        ax.plot(km[i], delta[i], "o", ms=8, color=INK, mec="black", mew=2)
        ax.annotate(f"{delta[i]:+.3f}s", (km[i], delta[i]), xytext=(0, 14 if delta[i] >= 0 else -22),
                    textcoords="offset points", ha="center", color=INK, fontproperties=reg, fontsize=14)
    ax.plot(km[-1], delta[-1], "o", ms=8, color=INK, mec="black", mew=2)
    ax.annotate(f"FINISH {delta[-1]:+.3f}s", (km[-1], delta[-1]), xytext=(-10, 14), textcoords="offset points",
                ha="right", color=INK, fontproperties=bold, fontsize=15)

    fig.text(0.06, 0.93, f"{r} vs {t}  -  LAP DELTA", color=INK, fontproperties=bold, fontsize=28)
    fig.text(0.06, 0.885, f"{event.upper()}  {a.year}  {Q.SESSION_NAMES.get(a.session.upper(), a.session.upper())}"
             f"   |   {r} {ref['lap_time'] // 60:.0f}:{ref['lap_time'] % 60:06.3f}   {t} {tgt['lap_time'] // 60:.0f}:{tgt['lap_time'] % 60:06.3f}",
             color=MUTED, fontproperties=reg, fontsize=15)
    fig.text(0.94, 0.03, "@formulytics", color=MUTED, fontproperties=bold, fontsize=13, ha="right")
    fig.subplots_adjust(left=0.08, right=0.97, top=0.84, bottom=0.08)
    out = a.out or os.path.join(HERE, f"{Q.OL.slug(event) if hasattr(Q, 'OL') else 'delta'}_{a.year}_{a.session.lower()}_{r}_vs_{t}_delta{'' if a.delta_engine == 'v2' else '_v1'}.png")
    fig.savefig(out, facecolor="black"); plt.close(fig)
    print(f"final {delta[-1]:+.3f}s, max {delta.max():+.3f}s @ {km[i_hi]:.2f} km, min {delta.min():+.3f}s @ {km[i_lo]:.2f} km")
    print("->", out)


if __name__ == "__main__":
    main()
