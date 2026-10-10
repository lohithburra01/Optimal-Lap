"""Per-driver racing line from CAR CHARACTER (no geometric edits).

1. Measure each car's character from its real lap: top speed at the end of every straight (drag/power) and
   minimum speed in every corner (grip), as P2 / P1 ratios (medians over the lap).
2. Turn it into the car the optimiser drives:  v_top ~ (P/CdA)^(1/3)  ->  CdA_P2 = CdA * (top1/top2)^3
                                               v_corner^2 ~ grip       ->  CL_P2  = CL  * (min2/min1)^2
3. Re-run the SAME optimiser that produced the shipped line (recipe command: same margin, same apex-touch
   penalty, same start knots). P1 keeps the shipped line. Nothing is added to the line afterwards.

  python character_lines.py --track "Singapore Grand Prix" --year 2026 --session SQ --drivers TOP2
"""
import argparse, hashlib, json, os, subprocess, sys
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import optimal_lines as OL

MAX_SCALE = 0.08     # never move CdA / CL more than 8 % from the shipped car
WORKERS = 4          # keep the machine responsive (it crashed on 2026-10-09); optimiser runs slower but safe


def character(ref, tgt, n=5000):
    L = ref['dist'].max(); g = np.linspace(0, L, n, endpoint=False)
    v1 = gaussian_filter1d(np.interp(g, ref['dist'], ref['speed'] * 3.6), 4, mode='wrap')
    v2 = gaussian_filter1d(np.interp(g, tgt['dist'] * L / tgt['dist'].max(), tgt['speed'] * 3.6), 4, mode='wrap')
    w = int(60 / (L / n))

    def pair(sign):
        pk, _ = find_peaks(sign * np.tile(v1, 3), prominence=15, distance=w)
        pk = [p - n for p in pk if n <= p < 2 * n]
        out = []
        for p in pk:
            i = (np.arange(p - w, p + w)) % n
            out.append((v1[i].max() if sign > 0 else v1[i].min(), v2[i].max() if sign > 0 else v2[i].min()))
        return np.array(out)
    tops, mins = pair(+1), pair(-1)
    return dict(top_ratio=float(np.median(tops[:, 1] / tops[:, 0])), min_ratio=float(np.median(mins[:, 1] / mins[:, 0])),
                tops=tops.round(1).tolist(), mins=mins.round(1).tolist())


def car_line(recipe, ref, tgt, log=print):
    opt = recipe['optimiser']
    ch = character(ref, tgt)
    cda = opt['cda'] * float(np.clip((1 / ch['top_ratio']) ** 3, 1 - MAX_SCALE, 1 + MAX_SCALE))
    cl = opt['cl'] * float(np.clip(ch['min_ratio'] ** 2, 1 - MAX_SCALE, 1 + MAX_SCALE))
    log(f"[character] {tgt['label']} vs {ref['label']}: top speed x{ch['top_ratio']:.4f} "
        f"({len(ch['tops'])} straights), corner min speed x{ch['min_ratio']:.4f} ({len(ch['mins'])} corners)")
    log(f"[character] car: CdA {opt['cda']:.4f} -> {cda:.4f}, CL {opt['cl']:.4f} -> {cl:.4f} (margin {opt['margin']} unchanged)")
    h = hashlib.sha1(open(recipe['raceline'], 'rb').read() + json.dumps([opt, round(cda, 4), round(cl, 4)]).encode()).hexdigest()[:10]
    cdir = os.path.join(HERE, "lines", recipe['slug'], "character"); os.makedirs(cdir, exist_ok=True)
    stem = os.path.join(cdir, f"{tgt['label']}_vs_{ref['label']}_{h}")
    if not os.path.exists(stem + "_rl.json"):
        log(f"[character] optimiser run (a few minutes) -> {stem}.log")
        p = OL._launch(opt, 1, cda, cl, opt['margin'], stem, WORKERS)
        p.wait()
        if p.returncode != 0 or not os.path.exists(stem + "_rl.json"):
            raise SystemExit(f"optimiser failed, see {stem}.log")
    pts = np.array(json.load(open(stem + "_rl.json"))['raceline'], float)
    if opt.get('mirror'):
        pts = pts * [-1.0, 1.0]
    out = stem + "_line.json"
    json.dump({"raceline": pts.tolist(), "cda": cda, "cl": cl, "character": ch}, open(out, "w"))
    return out, ch, cda, cl


# ---------------------------------------------------------------- one optimiser line PER DRIVER (user's method)
D_CDA, D_CL, D_MARGIN = 0.015, 0.02, 0.03     # "very very slight" parameter changes


def per_driver_lines(recipe, traces, log=print):
    """Both drivers get their OWN optimiser run (same recipe command, same apex touch, nothing edited afterwards).
    Direction from the data: the better cornering car (higher corner min speed) gets +downforce/+drag,
    the better straight-line car -drag/-downforce. Size is fixed and tiny."""
    opt = recipe['optimiser']; ref, tgt = traces[0], traces[1]
    ch = character(ref, tgt)
    s2 = 1.0 if ch['min_ratio'] / ch['top_ratio'] >= 1.0 else -1.0      # +1: P2 is the cornering car
    signs = {ref['label']: -s2, tgt['label']: s2}
    log(f"[lines] {tgt['label']} vs {ref['label']}: top x{ch['top_ratio']:.4f}, corner min x{ch['min_ratio']:.4f} -> "
        f"cornering car = {tgt['label'] if s2 > 0 else ref['label']}")
    cdir = os.path.join(HERE, "lines", recipe['slug'], "per_driver"); os.makedirs(cdir, exist_ok=True)
    out = {}
    for tr in traces:
        sg = signs[tr['label']]
        cda = opt['cda'] * (1 + sg * D_CDA); cl = opt['cl'] * (1 + sg * D_CL); margin = opt['margin'] + sg * D_MARGIN
        h = hashlib.sha1(open(recipe['raceline'], 'rb').read() +
                         json.dumps([opt, round(cda, 4), round(cl, 4), round(margin, 3)]).encode()).hexdigest()[:10]
        stem = os.path.join(cdir, f"{tr['label']}_{h}")
        log(f"[lines] {tr['label']}: CdA {cda:.4f}, CL {cl:.4f}, margin {margin:.3f}")
        if not os.path.exists(stem + "_rl.json"):
            log(f"[lines] {tr['label']}: optimiser run, {WORKERS} workers -> {stem}.log")
            p = OL._launch(opt, 1, cda, cl, margin, stem, WORKERS); p.wait()
            if p.returncode != 0 or not os.path.exists(stem + "_rl.json"):
                raise SystemExit(f"optimiser failed, see {stem}.log")
        pts = np.array(json.load(open(stem + "_rl.json"))['raceline'], float)
        if opt.get('mirror'):
            pts = pts * [-1.0, 1.0]
        json.dump({"raceline": pts.tolist(), "cda": cda, "cl": cl, "margin": margin}, open(stem + "_line.json", "w"))
        out[tr['label']] = stem + "_line.json"
    return out


def mockup(recipe, ref_label, tgt_label, line2, out_png, line1=None):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    o = json.load(open(recipe['outline'], encoding='utf-8'))
    outer, inner = np.array(o['outer']), np.array(o['inner'])
    P1 = np.array(json.load(open(line1 or recipe['raceline'], encoding='utf-8'))['raceline'], float)
    P2 = np.array(json.load(open(line2))['raceline'], float)
    gap = OL.line_gap(P1, P2); W = OL.road_width(recipe['outline'])
    # 6 spots where the lines differ most (>= 150 m apart)
    order = np.argsort(-gap); spots = []
    for i in order:
        if all(np.linalg.norm(P2[i] - P2[j]) > 150 for j in spots): spots.append(i)
        if len(spots) == 6: break
    fig = plt.figure(figsize=(16, 11), facecolor='black')
    ax0 = fig.add_axes([0.0, 0.0, 0.42, 1.0])
    ax0.fill(*outer.T, color='#282828'); ax0.fill(*inner.T, color='black')
    ax0.plot(*np.vstack([P1, P1[:1]]).T, color='#00e0ff', lw=1); ax0.plot(*np.vstack([P2, P2[:1]]).T, color='#ff9a3c', lw=1)
    for k, i in enumerate(spots): ax0.text(*P2[i], f"  {k + 1}", color='white', fontsize=11)
    ax0.set_aspect('equal'); ax0.axis('off')
    ax0.set_title(f"{ref_label} cyan  vs  {tgt_label} orange\n"
                  f"gap mean {gap.mean():.2f} m ({100 * gap.mean() / W:.1f}% of {W:.0f} m road), max {gap.max():.2f} m",
                  color='white', fontsize=11)
    for k, i in enumerate(spots):
        ax = fig.add_axes([0.44 + (k % 3) * 0.188, 0.52 - (k // 3) * 0.48, 0.18, 0.44])
        c = P2[i]; R = 40
        ax.fill(*outer.T, color='#282828'); ax.fill(*inner.T, color='black')
        ax.plot(*outer.T, color='white', lw=1); ax.plot(*inner.T, color='white', lw=1)
        ax.plot(*P1.T, color='#00e0ff', lw=2); ax.plot(*P2.T, color='#ff9a3c', lw=2)
        ax.set_xlim(c[0] - R, c[0] + R); ax.set_ylim(c[1] - R, c[1] + R); ax.set_aspect('equal'); ax.axis('off')
        ax.set_title(f"{k + 1}: lines {gap[i]:.2f} m apart", color='white', fontsize=10)
    fig.savefig(out_png, dpi=110, facecolor='black'); plt.close(fig)
    return gap


def main():
    import optimal_x_quali as Q
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default=Q.TRACK); ap.add_argument("--year", type=int, default=Q.YEAR)
    ap.add_argument("--session", default=Q.SESSION); ap.add_argument("--drivers", default=Q.DRIVERS)
    a = ap.parse_args()
    traces, event, _ = Q.load_traces(a.track, a.year, a.session.upper(), a.drivers)
    recipe = OL.load_recipe(event)
    lines = per_driver_lines(recipe, traces)
    r, t = traces[0]['label'], traces[1]['label']
    out = os.path.join(HERE, "mockups", f"per_driver_lines_{r}_vs_{t}.png")
    gap = mockup(recipe, r, t, lines[t], out, line1=lines[r])
    g1 = OL.line_gap(np.array(json.load(open(recipe['raceline']))['raceline']), np.array(json.load(open(lines[r]))['raceline']))
    print(f"{r} line vs shipped: mean {g1.mean():.2f} m, max {g1.max():.2f} m")
    print(f"{r} vs {t}: gap mean {gap.mean():.2f} m, p95 {np.percentile(gap, 95):.2f} m, max {gap.max():.2f} m\nmockup -> {out}")

if __name__ == "__main__":
    main()
