import json, os, sys, numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import _eval_2017 as E
if __name__ == "__main__":
    res = E.evaluate(json.load(open(sys.argv[1])))
    fig, ax = plt.subplots(6, 1, figsize=(14, 18), facecolor="#111")
    for a, r in zip(ax, res):
        a.set_facecolor("#111"); x = E.GRID
        a.plot(x, r["vr"], color="#bbb", lw=1.6, label="real 2018 Q")
        a.plot(x, r["vs"], color="#ff9a1a", lw=1.4, label="2017-era sim (corner-aligned)")
        a.set_title(f"{r['slug']}  sim {r['lap']:.3f} / real {r['real']:.3f}  corr {r['corr']:.3f}  rmse {r['rmse']:.1f}",
                    color="w", fontsize=11, loc="left"); a.tick_params(colors="#999"); a.set_ylim(50, 360)
        a.grid(color="#333", lw=0.5)
    ax[0].legend(facecolor="#222", labelcolor="w")
    plt.tight_layout(); plt.savefig(sys.argv[2], dpi=70, facecolor="#111")
