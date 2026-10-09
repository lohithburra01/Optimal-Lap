"""Hypothesis study library: standardised real laps + corner-anchored 2025<->2026 alignment."""
import os, json, glob, numpy as np
from datetime import datetime
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
H = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(H, "raw")
P_ = datetime.fromisoformat
def lap(circuit, year):
    """-> dict t (official clock, 0..lap), d (m), v (km/h), thr, brk, gear, drs, lap, D. Endpoints interpolated."""
    r = json.load(open(os.path.join(RAW, f"{circuit.replace(' ', '_')}_{year}.json"))); L = r["lap"]
    cd = sorted([c for c in r["car_data"] if c.get("speed") is not None], key=lambda c: c["date"]); rows, seen = [], set()
    for c in cd:
        if c["date"] not in seen: seen.add(c["date"]); rows.append(c)
    t = np.array([(P_(c["date"]) - P_(L["date_start"])).total_seconds() for c in rows]); v = np.array([float(c["speed"]) for c in rows])
    T = L["lap_duration"]; f = lambda key: np.array([float(c.get(key) or 0) for c in rows])
    thr, brk, gear, drs = f("throttle"), f("brake"), f("n_gear"), f("drs")
    tt = np.r_[0.0, t[(t > 0) & (t < T)], T]
    ip = lambda y: np.interp(tt, t, y)
    v2 = ip(v); d = np.r_[0, np.cumsum(0.5 * (v2[1:] + v2[:-1]) / 3.6 * np.diff(tt))]
    near = lambda y: y[np.clip(np.searchsorted(t, tt) , 0, len(t) - 1)]
    return dict(circuit=circuit, year=year, t=tt, d=d, v=v2, thr=near(thr), brk=near(brk), gear=near(gear), drs=near(drs),
                lap=T, D=float(d[-1]), drv=L["driver_number"], sectors=[L.get(f"duration_sector_{i}") for i in (1, 2, 3)])
def pairs():
    out = []
    for f in sorted(glob.glob(os.path.join(RAW, "*_2026.json"))):
        c = os.path.basename(f)[:-10].replace("_", " ")
        if os.path.exists(os.path.join(RAW, f"{c.replace(' ', '_')}_2025.json")): out.append(c)
    return out
def minima(d, v, prom=10.0, sep=60.0):
    g = np.arange(0, d[-1], 2.0); vv = np.interp(g, d, v); p, _ = find_peaks(-vv, prominence=prom, distance=int(sep / 2))
    return g[p], vv[p]
def align(a, b, n=4000):
    """Map lap b onto lap a's distance axis: lap-fraction first, then piecewise-linear warp anchored at paired
    corner minima (pairs within 3% lap fraction, monotone). Returns grid s (a's metres), va, vb, and the anchor pairs."""
    fa, fb = a["d"] / a["D"], b["d"] / b["D"]
    ma, _ = minima(a["d"], a["v"]); mb, _ = minima(b["d"], b["v"])
    ka, kb = [0.0], [0.0]
    for x in ma:
        j = np.argmin(abs(mb / b["D"] - x / a["D"]))
        if abs(mb[j] / b["D"] - x / a["D"]) < 0.03 and mb[j] / b["D"] > kb[-1] and x / a["D"] > ka[-1]:
            ka.append(x / a["D"]); kb.append(mb[j] / b["D"])
    ka.append(1.0); kb.append(1.0)
    g = np.linspace(0, 1, n, endpoint=False); gb = np.interp(g, ka, kb)
    S = lambda lapx, ff, key: np.interp(ff, lapx["d"] / lapx["D"], lapx[key])
    out = dict(s=g * a["D"], f=g, anchors=len(ka) - 2)
    for key in ("v", "t", "thr", "brk", "gear", "drs"):
        out[key + "25"] = S(a, g, key); out[key + "26"] = S(b, gb, key)
    return out
