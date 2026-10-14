import numpy as np, json
from collections import Counter, defaultdict
per = json.load(open('lper.json')); L = np.load('lkm.npy')
g = np.array(json.load(open('gdot.json'))); dot = dict(lat=(g[:, 0] - 387.79) / 36.64, lon=(g[:, 1] - 593.0) / 36.64)
def split(items):
    """-> (neg, int_cluster, dec_cluster) using geometry: small comps are '-' (wide) or '.' (square)."""
    neg = False; dotx = None; tall = []
    for it in items:
        if it['h'] <= 8:
            if it['w'] > 1.3 * it['h'] and dotx is None: neg = True
            elif dotx is None: dotx = it['x']
        else: tall.append(it)
    if dotx is None: return None
    ints = [t for t in tall if t['x'] < dotx]; decs = [t for t in tall if t['x'] > dotx]
    if not ints or not decs: return None
    return neg, L[ints[-1]['gi']], L[decs[0]['gi']], ints[-1]['w'] > 1.3 * ints[-1]['h'] * 0.75
votes_i = defaultdict(Counter); votes_d = defaultdict(Counter); parsed = {}
for ch in ('lat', 'lon'):
    for f, row in enumerate(per):
        s = split(row[ch]); parsed[(ch, f)] = s
        val = dot[ch][f]
        if s is None or abs(val) > 1.35: continue
        a = round(abs(val), 1); votes_i[s[1]][int(a)] += 1; votes_d[s[2]][int(round(a * 10)) % 10] += 1
mi = {7: 0, 8: 0, 3: 1, 18: 0, 20: 1, 21: 1}; md = {3: 1, 0: 2, 18: 0, 6: 3, 14: 4, 4: 0, 20: 1, 19: 6, 15: 7, 16: 9, 12: 5, 2: 9, 7: 0, 21: 4}


res = {}
for ch in ('lat', 'lon'):
    vals = []
    for f in range(len(per)):
        s = parsed[(ch, f)]
        if s is None or s[1] not in mi or s[2] not in md: vals.append(np.nan); continue
        neg = s[0] or s[1] == 8
        vals.append((-1 if neg else 1) * (mi[s[1]] + md[s[2]] / 10))
    v = np.array(vals); res[ch] = v
    ok = np.isfinite(v) & (np.abs(dot[ch]) < 1.35)
    print(ch, 'parsed', np.isfinite(v).sum(), 'agree with dot (|diff|<=0.15):', (np.abs(v - dot[ch])[ok] <= 0.15).mean().round(3),
          'max', np.nanmax(np.abs(v)).round(2))
json.dump({k: [None if not np.isfinite(x) else float(x) for x in v] for k, v in res.items()}, open('glabels.json', 'w'))
