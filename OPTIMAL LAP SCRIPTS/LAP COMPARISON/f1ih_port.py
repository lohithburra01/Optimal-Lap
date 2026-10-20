# Faithful Python port of F1InsightsHub's alignData (their browser bundle main-3OEVT2VU.js, class read in f1ih_src/).
# Only the code paths that affect the delta are ported; JS semantics (toFixed / Math.round half-up, `||` on 0,
# binary searches on unsorted distances, float accumulation order) are kept on purpose.
import math
from decimal import Decimal, ROUND_HALF_UP
import numpy as np

NAN = float('nan'); INF = float('inf')

FIXED_RESAMPLING_INTERVAL = 4
SPEED_SPIKE_MEDIAN_THRESHOLD_KPH = 12
SPEED_SPIKE_NEIGHBOR_GAP_THRESHOLD_KPH = 6
MAX_SHORT_ARTIFACT_RUN_SAMPLES = 6
SHORT_ARTIFACT_DEVIATION_THRESHOLD_KPH = 12
SHORT_ARTIFACT_ENDPOINT_DELTA_KPH = 35
SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH = 3
MAX_MICRO_STUTTER_RUN_SAMPLES = 4
MICRO_STUTTER_DEVIATION_THRESHOLD_KPH = 4.5
MICRO_STUTTER_ENDPOINT_DELTA_KPH = 12
MICRO_STUTTER_MIN_SIGN_CHANGES = 1
MAX_BRAKING_STEP_RUN_SAMPLES = 4
BRAKING_STEP_DEVIATION_THRESHOLD_KPH = 5.5
BRAKING_STEP_ENDPOINT_DROP_MIN_KPH = 10
BRAKING_STEP_CONTEXT_MIN_DROP_KPH = 2.5
BRAKING_STEP_MAX_NEGATIVE_DEVIATION_KPH = 3.5
CLEAN_SPEED_BOUNDARY_GUARD_SAMPLES = 8
MAX_EXTENDED_BRIDGE_RUN_SAMPLES = 12
EXTENDED_BRIDGE_DEVIATION_THRESHOLD_KPH = 18
EXTENDED_BRIDGE_ENDPOINT_DELTA_KPH = 18
EXTENDED_BRIDGE_MIN_CONSECUTIVE_SAMPLES = 3
EXTENDED_BRIDGE_MAX_INTERNAL_VARIANCE_KPH = 10
MAX_FALSE_VALLEY_SPAN_SAMPLES = 10
FALSE_VALLEY_DEPTH_THRESHOLD_KPH = 14
FALSE_VALLEY_ANCHOR_GAIN_THRESHOLD_KPH = 10
FALSE_VALLEY_CONTEXT_RISE_THRESHOLD_KPH = 1.5
FALSE_VALLEY_KEEP_MARGIN_KPH = 4
RAW_ARTIFACT_SEARCH_SAMPLES = 8
RAW_ARTIFACT_MAX_WINDOW_MS = 1200
RAW_ARTIFACT_MIN_THROTTLE = 80
RAW_ARTIFACT_MAX_BRAKE = 5
RAW_ARTIFACT_MIN_VALLEY_DEPTH_KPH = 30
RAW_ARTIFACT_MIN_ANCHOR_GAIN_KPH = 8
RAW_ARTIFACT_MAX_ANCHOR_DROP_KPH = 5
RAW_ARTIFACT_KEEP_MARGIN_KPH = 10
RAW_ARTIFACT_MAX_OVERSHOOT_KPH = 6
RAW_ARTIFACT_EXTENDED_SEARCH_SAMPLES = 14
RAW_ARTIFACT_EXTENDED_MAX_WINDOW_MS = 2200
RAW_ARTIFACT_EXTENDED_MIN_VALLEY_DEPTH_KPH = 18
RAW_ARTIFACT_EXTENDED_MIN_CONSECUTIVE_SAMPLES = 3
RAW_ARTIFACT_EXTENDED_MAX_INTERNAL_VARIANCE_KPH = 12
RAW_ARTIFACT_BOUNDARY_GUARD_SAMPLES = 12
MAX_ACCELERATION_KPH_PER_5M = 10
MAX_BRAKING_KPH_PER_5M = 20
GLOBAL_SEARCH_RANGE = 25
GLOBAL_SEARCH_STEP = 1
LOCAL_SEARCH_RANGE = 20
LOCAL_SEARCH_STEP = 1
GRID_SLOT_OFFSET = FIXED_RESAMPLING_INTERVAL * 2
ALIGNMENT_SIGNAL_WEIGHT_SCALE = 1
ALIGNMENT_HUBER_DELTA = 0.8
ALIGNMENT_GRID_STEP = 1
START_DELTA_STABILIZATION_DISTANCE_METERS = 80
START_DELTA_STABILIZATION_MAX_SAMPLES = 20
START_DELTA_STABILIZATION_MIN_SAMPLES = 6
START_DELTA_STABILIZATION_MAX_BRAKE = 12
START_DELTA_STABILIZATION_MAX_NET_SPEED_DROP_KPH = 15
START_DELTA_STABILIZATION_MAX_NEGATIVE_STEPS = 2
START_DELTA_STABILIZATION_STEP_ERROR_THRESHOLD_S = 0.04
START_DELTA_STABILIZATION_TOTAL_ERROR_THRESHOLD_S = 0.08
START_DELTA_STABILIZATION_ANCHOR_THRESHOLD_S = 0.06
START_DELTA_STABILIZATION_MAX_CORRECTION_S = 0.35
BOUNDARY_SPEED_REPAIR_MAX_SAMPLES = 10
BOUNDARY_SPEED_REPAIR_WINDOW_SAMPLES = 3
BOUNDARY_SPEED_REPAIR_DEVIATION_THRESHOLD_KPH = 35
BOUNDARY_SPEED_REPAIR_EXPECTATION_TOLERANCE_KPH = 18
BOUNDARY_SPEED_REPAIR_BLEND_TOLERANCE_KPH = 25
BOUNDARY_SPEED_REPAIR_MAX_STEP_SECONDS = 0.35
BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_MIN_SAMPLES = 3
BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_MIN_ANCHOR_SPEED_KPH = 220
BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_MIN_GAP_KPH = 55
BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_EXPECTATION_GAP_KPH = 40
BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_JUMP_THRESHOLD_KPH = 20
BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_REGRESSION_SAMPLES = 4
BOUNDARY_ACCELERATION_REPAIR_MAX_SAMPLES = 12
BOUNDARY_ACCELERATION_REPAIR_MIN_RUN_SAMPLES = 2
BOUNDARY_ACCELERATION_REPAIR_MAX_TRACTION_G = 3.25
BOUNDARY_ACCELERATION_REPAIR_EXPECTATION_GAP_KPH = 28
BOUNDARY_START_PREFIX_SEARCH_SAMPLES = 14
BOUNDARY_START_PREFIX_WINDOW_SAMPLES = 4
BOUNDARY_START_PREFIX_MIN_STABLE_SPEED_KPH = 220
BOUNDARY_START_PREFIX_MAX_WINDOW_RANGE_KPH = 18
BOUNDARY_START_PREFIX_MIN_GAP_KPH = 55
BOUNDARY_START_PREFIX_RELEASE_GAP_KPH = 22
BOUNDARY_START_PREFIX_FORCE_SEARCH_SAMPLES = 18
BOUNDARY_START_PREFIX_FORCE_MIN_GAP_KPH = 45


# ---------- JS semantics ----------
def fin(x):
    """`x != null && isFinite(x)` on a number."""
    return x is not None and not isinstance(x, bool) and math.isfinite(x) if isinstance(x, (int, float)) else False

def jsfin(x):
    """Global isFinite(x): null coerces to 0 (finite), undefined/NaN not."""
    return True if x is None else fin(x)

def num(x):
    """Number(x): null -> 0."""
    return 0.0 if x is None else float(x)

def tofixed(x, d):
    """Number(x.toFixed(d)): exact binary value, ties away from zero."""
    return float(Decimal(x).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP))

def jround(x):
    return math.floor(x + 0.5)

def jsign(x):
    return 0 if x == 0 else (1 if x > 0 else -1)

def sl(lst, i):
    """lst[i] with JS out-of-range -> undefined (None)."""
    return lst[i] if 0 <= i < len(lst) else None


# ---------- interpolation ----------
def interpolate_simple(n, e, t):
    if not n: return None
    i, a = n[0], n[-1]
    if not fin(i.get('distance')) or not fin(a.get('distance')): return None
    if e <= i['distance']:
        k = i.get(t); return None if not fin(k) else float(k)
    if e >= a['distance']:
        k = a.get(t); return None if not fin(k) else float(k)
    s, o, l = 0, len(n) - 1, 0
    while s <= o:
        k = (s + o) // 2; I = n[k]; M = I.get('distance')
        if not fin(M):
            if o == k: o -= 1
            else: o = k - 1
            if s > o: break
            continue
        if M == e:
            A = I.get(t); return None if not fin(A) else float(A)
        elif M < e: l = k; s = k + 1
        else: o = k - 1
    p = l + 1
    if p >= len(n) or l < 0:
        k, I = i.get(t), a.get(t)
        if abs(e - i['distance']) < abs(e - a['distance']): return None if not fin(k) else float(k)
        return None if not fin(I) else float(I)
    m, f = n[l], n[p]
    if not (fin(m.get('distance')) and fin(f.get('distance')) and fin(m.get(t)) and fin(f.get(t))):
        k = m.get(t); return float(k) if fin(k) else None
    g, v, y, b = m['distance'], float(m[t]), f['distance'], float(f[t])
    if y - g <= 1e-9: return v
    C = (b - v) / (y - g); w = v + C * (e - g)
    return w if math.isfinite(w) else None

def interpolate_step(n, e, t):
    if not n: return None
    i, a = n[0], n[-1]
    if not fin(i.get('distance')) or not fin(a.get('distance')): return None
    if e <= i['distance']: return i.get(t)
    if e >= a['distance']: return a.get(t)
    s, o, l = 0, len(n) - 1, 0
    while s <= o:
        p = (s + o) // 2; f = n[p].get('distance')
        if not fin(f):
            if o == p: o -= 1
            else: o = p - 1
            if s > o: break
            continue
        if f <= e: l = p; s = p + 1
        else: o = p - 1
    return n[l].get(t) if 0 <= l < len(n) else i.get(t)


# ---------- raw samples ----------
def ts_ms(rec):
    return rec.get('_ms', NAN) if rec is not None else NAN

def is_raw_power_sample(n):
    if n is None or not fin(n.get('speed')): return False
    e = num(n.get('throttle')); t = num(n.get('brake')); i = ts_ms(n)
    return math.isfinite(i) and e >= RAW_ARTIFACT_MIN_THROTTLE and t <= RAW_ARTIFACT_MAX_BRAKE

def interpolate_speed_by_time(n, e, t):
    i, a = ts_ms(n), ts_ms(e)
    s = num(n.get('speed')) if n.get('speed') is not None else NAN
    o = num(e.get('speed')) if e.get('speed') is not None else NAN
    if not (math.isfinite(i) and math.isfinite(a) and math.isfinite(t) and math.isfinite(s) and math.isfinite(o)) or a <= i: return None
    p = max(0.0, min(1.0, (t - i) / (a - i)))
    return s + (o - s) * p

def reconstruct_raw_speed_run(n, e, t):
    i, a = e - 1, t + 1
    if i < 0 or a >= len(n): return
    s, o = n[i], n[a]
    if fin(s.get('speed')) and fin(o.get('speed')):
        for l in range(e, t + 1):
            m = interpolate_speed_by_time(s, o, ts_ms(n[l]))
            if m is not None and math.isfinite(m): n[l]['speed'] = m

def mark_extended_raw_power_artifacts(n, e):
    t = min(RAW_ARTIFACT_BOUNDARY_GUARD_SAMPLES, max(0, (len(n) - 3) // 2))
    for i in range(t, len(n) - 3 - t):
        a = n[i]
        if not is_raw_power_sample(a): continue
        s = ts_ms(a)
        if not math.isfinite(s): continue
        o = min(len(n) - 1 - t, i + RAW_ARTIFACT_EXTENDED_SEARCH_SAMPLES)
        for l in range(i + 4, o + 1):
            p = n[l]
            if not is_raw_power_sample(p): continue
            m = ts_ms(p)
            if not math.isfinite(m): continue
            if m - s > RAW_ARTIFACT_EXTENDED_MAX_WINDOW_MS: break
            if (not fin(p.get('speed')) or not fin(a.get('speed')) or p['speed'] < a['speed'] - RAW_ARTIFACT_MAX_ANCHOR_DROP_KPH
                    or p['speed'] - a['speed'] < RAW_ARTIFACT_MIN_ANCHOR_GAIN_KPH): continue
            f = g = 0.0; v = y = 0; b = INF; C = -INF; w = False
            for I in range(i + 1, l):
                M = n[I]
                if not is_raw_power_sample(M): v = y = 0; w = False; break
                w = True
                A = interpolate_speed_by_time(a, p, ts_ms(M))
                if A is None: v = y = 0; w = False; break
                P = float(M['speed']); b = min(b, P); C = max(C, P)
                N = P - A; f = min(f, N); g = max(g, N)
                if N <= -RAW_ARTIFACT_EXTENDED_MIN_VALLEY_DEPTH_KPH: v += 1; y = max(y, v)
                else: v = 0
            k = C - b if math.isfinite(b) and math.isfinite(C) else 0
            if not (not w or y < RAW_ARTIFACT_EXTENDED_MIN_CONSECUTIVE_SAMPLES or abs(f) < RAW_ARTIFACT_EXTENDED_MIN_VALLEY_DEPTH_KPH
                    or g > RAW_ARTIFACT_MAX_OVERSHOOT_KPH or k > RAW_ARTIFACT_EXTENDED_MAX_INTERNAL_VARIANCE_KPH):
                for I in range(i + 1, l):
                    M = n[I]; A = interpolate_speed_by_time(a, p, ts_ms(M))
                    if A is not None and fin(M.get('speed')) and M['speed'] <= A - (RAW_ARTIFACT_EXTENDED_MIN_VALLEY_DEPTH_KPH - RAW_ARTIFACT_KEEP_MARGIN_KPH):
                        e[I] = True

def clean_raw_speed_artifacts(n):
    if not n: return []
    e = [dict(a) for a in n]; t = [False] * len(e)
    i = min(RAW_ARTIFACT_BOUNDARY_GUARD_SAMPLES, max(0, (len(e) - 3) // 2))
    for a in range(max(1, i), min(len(e) - 1, len(e) - i)):
        s = e[a]
        if not is_raw_power_sample(s): continue
        o = None; l = max(i, a - RAW_ARTIFACT_SEARCH_SAMPLES)
        for f in range(a - 1, l - 1, -1):
            g = e[f]
            if not is_raw_power_sample(g): continue
            v, y = ts_ms(g), ts_ms(s)
            if not math.isfinite(v) or not math.isfinite(y): continue
            if y - v > RAW_ARTIFACT_MAX_WINDOW_MS: break
            b = min(len(e) - 1 - i, a + RAW_ARTIFACT_SEARCH_SAMPLES)
            for C in range(a + 1, b + 1):
                w = e[C]
                if not is_raw_power_sample(w): continue
                k = ts_ms(w)
                if not math.isfinite(k): continue
                if k - v > RAW_ARTIFACT_MAX_WINDOW_MS: break
                if (not fin(w.get('speed')) or not fin(g.get('speed')) or w['speed'] < g['speed'] - RAW_ARTIFACT_MAX_ANCHOR_DROP_KPH
                        or w['speed'] - g['speed'] < RAW_ARTIFACT_MIN_ANCHOR_GAIN_KPH): continue
                I = interpolate_speed_by_time(g, w, y)
                if I is None or I - s['speed'] < RAW_ARTIFACT_MIN_VALLEY_DEPTH_KPH: continue
                M = A = 0.0; P = False
                for H in range(f + 1, C):
                    z = e[H]
                    if not is_raw_power_sample(z): P = False; break
                    Q = interpolate_speed_by_time(g, w, ts_ms(z))
                    if Q is None: P = False; break
                    J = z['speed'] - Q; M = min(M, J); A = max(A, J)
                    if J <= -(RAW_ARTIFACT_MIN_VALLEY_DEPTH_KPH - RAW_ARTIFACT_KEEP_MARGIN_KPH): P = True
                if not P or abs(M) < RAW_ARTIFACT_MIN_VALLEY_DEPTH_KPH or A > RAW_ARTIFACT_MAX_OVERSHOOT_KPH: continue
                N = I - s['speed']
                if o is None or N > o['depth']: o = {'left': f, 'right': C, 'depth': N}
        if o is None: continue
        p, m = e[o['left']], e[o['right']]
        for f in range(o['left'] + 1, o['right']):
            g = e[f]; v = interpolate_speed_by_time(p, m, ts_ms(g))
            if v is not None and fin(g.get('speed')) and g['speed'] <= v - (RAW_ARTIFACT_MIN_VALLEY_DEPTH_KPH - RAW_ARTIFACT_KEEP_MARGIN_KPH):
                t[f] = True
    mark_extended_raw_power_artifacts(e, t)
    a = 0
    while a < len(t):
        if t[a]:
            s = a
            while s + 1 < len(t) and t[s + 1]: s += 1
            reconstruct_raw_speed_run(e, a, s); a = s
        a += 1
    return e

def calculate_distances(n):
    if not n: return []
    e = []; t = 0.0
    if not math.isfinite(ts_ms(n[0])): return []
    a = ts_ms(n[0]); s = a; o = []; l = 3
    for p, m in enumerate(n):
        g = ts_ms(m)
        if not math.isfinite(g) or not fin(m.get('speed')): continue
        v = 0.0
        if p > 0:
            v = (g - s) / 1e3
            if v < -0.001:
                s = g; continue
            v = max(0.0, v)
            if v > 5: v = 0.0
        y = m['speed']
        if y < 0: y = 0
        if y > 400: y = 400
        o.append(y)
        if len(o) > l: o.pop(0)
        mean = 0.0
        if o:
            acc = 0
            for x in o: acc = acc + x
            mean = acc / len(o)
        C = mean * 1e3 / 3600 * v
        if C >= 0 and math.isfinite(C): t += C
        r = dict(m); r['distance'] = t
        r['delta'] = m['delta'] if fin(m.get('delta')) else tofixed((g - a) / 1e3, 3)
        e.append(r); s = g
    for p in range(1, len(e)):
        if e[p]['distance'] < e[p - 1]['distance'] - 1e-6: e[p]['distance'] = e[p - 1]['distance']
    return e


# ---------- alignment helpers ----------
def get_robust_minimum_distance(n, e=0.07):
    if not n: return 0
    t = []
    for p in n:
        m = p[-1].get('distance') if p else 0
        t.append(m if fin(m) else 0)
    t = sorted(x for x in t if x > 100)
    if not t: return 0
    a = len(t) // 2
    i = (t[a - 1] + t[a]) / 2 if len(t) % 2 == 0 else t[a]
    s, o = i * (1 - e), i * (1 + e)
    l = [p for p in t if s <= p <= o]
    return min(l) if l else min(t)

def get_finite_min_distance(n):
    e = INF
    for t in n:
        i = t.get('distance')
        if fin(i) and i < e: e = i
    return e if math.isfinite(e) else 0

def build_distance_grid(n, e, t):
    if not math.isfinite(n) or not math.isfinite(e) or t <= 0 or e < n: return []
    i = []; a = n
    while a <= e + t / 2:
        i.append(a); a += t
    return i

def compute_speed_gradient_signal(n):
    if len(n) < 2: return []
    e = []
    for i in range(len(n)):
        a = n[max(0, i - 1)]; s = n[min(len(n) - 1, i + 1)]
        o, l, p, m = a.get('distance'), s.get('distance'), a.get('speed'), s.get('speed')
        if not (fin(o) and fin(l) and fin(p) and fin(m)):
            if fin(n[i].get('distance')): e.append({'distance': n[i]['distance'], 'signal': 0.0})
            continue
        f = l - o
        if f <= 1e-6:
            e.append({'distance': n[i]['distance'], 'signal': 0.0}); continue
        v = (m - p) / f
        e.append({'distance': n[i]['distance'], 'signal': v if math.isfinite(v) else 0.0})
    if len(e) < 3: return e
    t = [dict(i) for i in e]
    for i in range(1, len(e) - 1):
        t[i]['signal'] = (e[i - 1]['signal'] + e[i]['signal'] + e[i + 1]['signal']) / 3
    return t

def resample_signal_to_grid(n, e):
    if not e: return []
    t = [s for s in n if fin(s.get('distance')) and fin(s.get('signal'))]
    if not t: return [0.0] * len(e)
    if len(t) == 1: return [t[0]['signal']] * len(e)
    i = [0.0] * len(e); a = 0
    for s, o in enumerate(e):
        while a < len(t) - 2 and t[a + 1]['distance'] < o: a += 1
        l = t[a]; p = t[min(a + 1, len(t) - 1)]
        if o <= l['distance']: i[s] = l['signal']; continue
        if o >= p['distance']: i[s] = p['signal']; continue
        m = p['distance'] - l['distance']
        if m <= 1e-9: i[s] = l['signal']; continue
        g = l['signal'] + (o - l['distance']) / m * (p['signal'] - l['signal'])
        i[s] = g if math.isfinite(g) else l['signal']
    return i

def alignment_weight(n, e, t):
    i = (abs(n) + abs(e)) / 2
    return 0 if not math.isfinite(i) or i <= 0 else min(1, i / t)

def huber_loss(n, e):
    t = abs(n)
    return 0.5 * n * n if t <= e else e * (t - 0.5 * e)


# ---------- speed cleaning on the resampled grid ----------
def apply_median_filter(n, e):
    t = e // 2; i = list(n)
    for a in range(t, len(n) - t):
        s = sorted(n[a - t:a + t + 1]); i[a] = s[t]
    return i

def is_slope_violation(n, e, t):
    if not math.isfinite(n) or e <= 0 or t <= 0: return False
    i = e * t
    return n > MAX_ACCELERATION_KPH_PER_5M / 5 * i or n < -MAX_BRAKING_KPH_PER_5M / 5 * i

def median_of_three(n, e, t):
    return sorted([n, e, t])[1]

def median_of_array(n):
    e = sorted(x for x in n if math.isfinite(x))
    if not e: return NAN
    t = len(e) // 2
    return (e[t - 1] + e[t]) / 2 if len(e) % 2 == 0 else e[t]

def reconstruct_corrupted_speed_run(n, e, t, i):
    a, s = e - 1, t + 1
    o = n[a] if a >= 0 else NAN
    l = n[s] if s < len(n) else NAN
    if not math.isfinite(o) and not math.isfinite(l): return
    if not math.isfinite(o):
        for m in range(e, t + 1): n[m] = l
        return
    if not math.isfinite(l):
        for m in range(e, t + 1): n[m] = o
        return
    if e == t:
        n[e] = (o + l) / 2; return
    p = s - a
    for m in range(e, t + 1): n[m] = o + (l - o) * ((m - a) / p)

def mark_micro_stutter_artifacts(n, e):
    for t in range(len(n) - 2):
        i = n[t]
        if not math.isfinite(i): continue
        a = min(len(n) - 1, t + MAX_MICRO_STUTTER_RUN_SAMPLES + 1)
        for s in range(t + 2, a + 1):
            o = n[s]
            if not math.isfinite(o) or abs(o - i) > MICRO_STUTTER_ENDPOINT_DELTA_KPH: continue
            l = s - t; p = False; m = 0.0; f = 0; g = 0; v = False
            for y in range(t + 1, s):
                b = n[y]
                if not math.isfinite(b): v = True; break
                p = True
                C = i + (o - i) * (y - t) / l; w = b - C; m = max(m, abs(w))
                I = 1 if w > 0.75 else (-1 if w < -0.75 else 0)
                if I != 0:
                    if g != 0 and I != g: f += 1
                    g = I
            if not (v or not p or m < MICRO_STUTTER_DEVIATION_THRESHOLD_KPH or f < MICRO_STUTTER_MIN_SIGN_CHANGES):
                for y in range(t + 1, s): e[y] = True

def mark_braking_step_artifacts(n, e):
    for t in range(1, len(n) - 3):
        i, a = n[t], n[t - 1]
        if not math.isfinite(i) or not math.isfinite(a) or i - a > -BRAKING_STEP_CONTEXT_MIN_DROP_KPH: continue
        o = min(len(n) - 2, t + MAX_BRAKING_STEP_RUN_SAMPLES + 1)
        for l in range(t + 2, o + 1):
            p, m = n[l], n[l + 1]
            if not math.isfinite(p) or not math.isfinite(m) or m - p > -BRAKING_STEP_CONTEXT_MIN_DROP_KPH or i - p < BRAKING_STEP_ENDPOINT_DROP_MIN_KPH: continue
            g = False; v = 0.0; y = 0.0; b = 0; C = l - t
            for w in range(t + 1, l):
                k = n[w]
                if not math.isfinite(k): g = False; break
                g = True
                M = k - (i + (p - i) * (w - t) / C); v = max(v, M); y = min(y, M)
                if M >= BRAKING_STEP_DEVIATION_THRESHOLD_KPH * 0.5: b += 1
            if not (not g or v < BRAKING_STEP_DEVIATION_THRESHOLD_KPH or abs(y) > BRAKING_STEP_MAX_NEGATIVE_DEVIATION_KPH or b == 0):
                for w in range(t + 1, l):
                    k = n[w]; I = i + (p - i) * (w - t) / C
                    if math.isfinite(k) and k >= I + BRAKING_STEP_DEVIATION_THRESHOLD_KPH * 0.5: e[w] = True

def should_flag_short_artifact_run(n, e, t):
    i, a = n[e], n[t]
    if not math.isfinite(i) or not math.isfinite(a) or abs(a - i) > SHORT_ARTIFACT_ENDPOINT_DELTA_KPH: return False
    s = 0.0; o = 0.0; l = False
    for b in range(e + 1, t):
        C = n[b]
        if not math.isfinite(C): return True
        l = True
        I = C - (i + (b - e) / (t - e) * (a - i)); s = max(s, I); o = min(o, I)
    if not l: return False
    p = i - n[e - 1] if e > 0 and math.isfinite(n[e - 1]) else 0
    m = n[t + 1] - a if t + 1 < len(n) and math.isfinite(n[t + 1]) else 0
    f = abs(p) <= SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH; g = abs(m) <= SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH
    if (p != 0 and m != 0 and jsign(p) == jsign(m)) or (f and g):
        return bool(((p >= 0 or f) and (m >= 0 or g) and abs(o) >= SHORT_ARTIFACT_DEVIATION_THRESHOLD_KPH and s <= SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH)
                    or ((p <= 0 or f) and (m <= 0 or g) and s >= SHORT_ARTIFACT_DEVIATION_THRESHOLD_KPH and abs(o) <= SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH))
    return False

def mark_short_bridge_artifacts(n, e):
    for t in range(len(n) - 2):
        if not math.isfinite(n[t]): continue
        i = min(len(n) - 1, t + MAX_SHORT_ARTIFACT_RUN_SAMPLES + 1)
        for a in range(t + 2, i + 1):
            if math.isfinite(n[a]) and should_flag_short_artifact_run(n, t, a):
                for s in range(t + 1, a): e[s] = True

def mark_extended_bridge_artifacts(n, e):
    for t in range(len(n) - 3):
        if not math.isfinite(n[t]): continue
        i = min(len(n) - 1, t + MAX_EXTENDED_BRIDGE_RUN_SAMPLES + 1)
        for a in range(t + 4, i + 1):
            if not math.isfinite(n[a]) or abs(n[a] - n[t]) > EXTENDED_BRIDGE_ENDPOINT_DELTA_KPH: continue
            s = n[t] - n[t - 1] if t > 0 and math.isfinite(n[t - 1]) else 0
            o = n[a + 1] - n[a] if a + 1 < len(n) and math.isfinite(n[a + 1]) else 0
            if s < -SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH or o < -SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH: continue
            l = 0.0; p = 0.0; m = 0; f = 0; g = INF; v = -INF
            for b in range(t + 1, a):
                C = n[b]
                if not math.isfinite(C):
                    m += 1; f = max(f, m); continue
                g = min(g, C); v = max(v, C)
                I = C - (n[t] + (b - t) / (a - t) * (n[a] - n[t]))
                l = min(l, I); p = max(p, I)
                if I <= -EXTENDED_BRIDGE_DEVIATION_THRESHOLD_KPH: m += 1; f = max(f, m)
                else: m = 0
            y = v - g if math.isfinite(g) and math.isfinite(v) else 0
            if not (f < EXTENDED_BRIDGE_MIN_CONSECUTIVE_SAMPLES or abs(l) < EXTENDED_BRIDGE_DEVIATION_THRESHOLD_KPH
                    or p > SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH or y > EXTENDED_BRIDGE_MAX_INTERNAL_VARIANCE_KPH):
                for b in range(t + 1, a):
                    C = n[b]
                    if not math.isfinite(C): e[b] = True; continue
                    k = n[t] + (b - t) / (a - t) * (n[a] - n[t])
                    if C <= k - (EXTENDED_BRIDGE_DEVIATION_THRESHOLD_KPH - 6): e[b] = True

def is_false_valley_in_acceleration_context(n, e, t, i):
    a, s, o = n[e], n[t], n[i]
    if not (math.isfinite(a) and math.isfinite(s) and math.isfinite(o)) or o - a < FALSE_VALLEY_ANCHOR_GAIN_THRESHOLD_KPH: return False
    l = a - n[e - 1] if e > 0 and math.isfinite(n[e - 1]) else FALSE_VALLEY_CONTEXT_RISE_THRESHOLD_KPH
    p = n[i + 1] - o if i + 1 < len(n) and math.isfinite(n[i + 1]) else FALSE_VALLEY_CONTEXT_RISE_THRESHOLD_KPH
    if l < -SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH or p < -SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH: return False
    m = 0.0; f = 0.0
    for g in range(e + 1, i):
        v = n[g]
        if not math.isfinite(v): return True
        C = v - (a + (g - e) / (i - e) * (o - a)); m = min(m, C); f = max(f, C)
    return (abs(m) >= FALSE_VALLEY_DEPTH_THRESHOLD_KPH and f <= SHORT_ARTIFACT_CONTEXT_FLAT_THRESHOLD_KPH
            and l >= -FALSE_VALLEY_CONTEXT_RISE_THRESHOLD_KPH and p >= -FALSE_VALLEY_CONTEXT_RISE_THRESHOLD_KPH)

def mark_below_envelope_samples(n, e, t, i, a):
    s = False
    for o in range(t + 1, i):
        l = n[o]
        if not math.isfinite(l): e[o] = True; s = True; continue
        f = l - (n[t] + (o - t) / (i - t) * (n[i] - n[t]))
        if a and f <= -(FALSE_VALLEY_DEPTH_THRESHOLD_KPH - FALSE_VALLEY_KEEP_MARGIN_KPH): e[o] = True; s = True
        if not a and f >= FALSE_VALLEY_DEPTH_THRESHOLD_KPH - FALSE_VALLEY_KEEP_MARGIN_KPH: e[o] = True; s = True
    if not s: e[(t + i) // 2] = True

def mark_false_valley_artifacts(n, e):
    for t in range(1, len(n) - 1):
        i = n[t]
        if not math.isfinite(i): continue
        a = -1
        for p in range(t - 1, max(0, t - MAX_FALSE_VALLEY_SPAN_SAMPLES) - 1, -1):
            m = n[p]
            if not math.isfinite(m): break
            if m >= i + FALSE_VALLEY_DEPTH_THRESHOLD_KPH: a = p; break
        if a < 0: continue
        o = -1
        for p in range(t + 1, min(len(n) - 1, t + MAX_FALSE_VALLEY_SPAN_SAMPLES) + 1):
            m = n[p]
            if not math.isfinite(m): break
            if m >= i + FALSE_VALLEY_DEPTH_THRESHOLD_KPH: o = p; break
        if o < 0 or o - a < 2: continue
        if is_false_valley_in_acceleration_context(n, a, t, o): mark_below_envelope_samples(n, e, a, o, True)

def clean_speed_artifacts(n, e):
    if not n or not math.isfinite(e) or e <= 0: return list(n or [])
    t = min(CLEAN_SPEED_BOUNDARY_GUARD_SAMPLES, max(0, (len(n) - 3) // 2))
    i = list(n)
    for p in range(1 + t, len(n) - 1 - t):
        m, f, g = n[p - 1], n[p], n[p + 1]
        if not all(math.isfinite(x) for x in (m, f, g)): continue
        v = median_of_three(m, f, g)
        y = abs(f - v) >= SPEED_SPIKE_MEDIAN_THRESHOLD_KPH
        b = (f > m and f > g) or (f < m and f < g)
        C = jsign(f - m) != 0 and jsign(g - f) != 0 and jsign(f - m) != jsign(g - f)
        w = abs(m - g) <= SPEED_SPIKE_NEIGHBOR_GAP_THRESHOLD_KPH
        k = is_slope_violation(f - m, 1, e) and is_slope_violation(g - f, 1, e)
        if y and b and C and (w or k): i[p] = v
    a = [False] * len(i)
    mark_micro_stutter_artifacts(i, a); mark_braking_step_artifacts(i, a); mark_false_valley_artifacts(i, a)
    mark_short_bridge_artifacts(i, a); mark_extended_bridge_artifacts(i, a)
    for p in range(t):
        a[p] = False; a[len(a) - 1 - p] = False
    s = -1
    for p in range(t, len(i) - t):
        if math.isfinite(i[p]): s = p; break
    if s == -1: s = next((p for p, x in enumerate(i) if math.isfinite(x)), -1)
    if s == -1: return i
    o = s + 1
    while o < len(i) - t:
        p = i[o]
        if not math.isfinite(p):
            a[o] = True; o += 1; continue
        if not is_slope_violation(p - i[s], o - s, e):
            s = o; o += 1; continue
        g = o + 1
        while g < len(i):
            v = i[g]
            if math.isfinite(v) and not is_slope_violation(v - i[s], g - s, e): break
            g += 1
        if g >= len(i) - t: break
        for v in range(o, g): a[v] = True
        s = g; o = g + 1
    l = list(i); p = 0
    while p < len(a):
        if a[p]:
            m = p
            while m + 1 < len(a) and a[m + 1]: m += 1
            reconstruct_corrupted_speed_run(l, p, m, e); p = m
        p += 1
    return l

def clamp_speed_kph(n):
    return min(400, max(0, n)) if math.isfinite(n) else NAN

def fit_boundary_speed_line(n, e, t):
    if e < 0 or t < 2 or e + t > len(n): return None
    i = a = s = o = l = 0.0; p = []
    for v in range(e, e + t):
        y = n[v]
        if not math.isfinite(y): return None
        i += 1; a += v; s += y; o += v * v; l += v * y; p.append(y)
    m = i * o - a * a
    if abs(m) <= 1e-9: return None
    f = (i * l - a * s) / m; g = (s - f * a) / i
    if not math.isfinite(f) or not math.isfinite(g): return None
    return {'slope': f, 'intercept': g, 'medianSpeed': median_of_array(p)}

def find_leading_stable_high_speed_window_start(n, e, t):
    W = BOUNDARY_START_PREFIX_WINDOW_SAMPLES
    i = t - W + 1; a = -1; s = -INF; o = INF
    for l in range(e + 1, i + 1):
        p = n[l:l + W]
        if len(p) < W or any(not math.isfinite(y) for y in p): continue
        m, f, g = min(p), max(p), median_of_array(p)
        if not math.isfinite(g) or g < BOUNDARY_START_PREFIX_MIN_STABLE_SPEED_KPH or f - m > BOUNDARY_START_PREFIX_MAX_WINDOW_RANGE_KPH: continue
        v = f - m
        if g > s or (g == s and v < o) or (g == s and v == o and l > a): a, s, o = l, g, v
    return a

def repair_resampled_leading_speed_collapse(n):
    if not n or len(n) < 6: return n
    e = [dict(m) for m in n]
    t = next((k for k, m in enumerate(e) if fin(m.get('distance')) and m['distance'] >= 0 and fin(m.get('speed'))), -1)
    if t == -1: return e
    i = -1
    for m in range(len(e) - 1, t - 1, -1):
        if fin(e[m].get('speed')): i = m; break
    if i <= t: return e
    sp = [num(m.get('speed')) for m in e]
    a = find_leading_stable_high_speed_window_start(sp, t, min(i, t + BOUNDARY_START_PREFIX_FORCE_SEARCH_SAMPLES))
    if a == -1 or a <= t: return e
    s = min(BOUNDARY_START_PREFIX_WINDOW_SAMPLES, i - a + 1)
    o = fit_boundary_speed_line(sp, a, s)
    if not o or not math.isfinite(o['medianSpeed']): return e
    l = num(e[t].get('speed'))
    if not math.isfinite(l) or o['medianSpeed'] - l < BOUNDARY_START_PREFIX_FORCE_MIN_GAP_KPH: return e
    for m in range(t, a):
        if not math.isfinite(num(e[m].get('speed'))): return e
    for m in range(t, a):
        f = o['intercept'] + o['slope'] * m
        if math.isfinite(f): e[m]['speed'] = tofixed(clamp_speed_kph(f), 1)
    return e

def build_elapsed_time_expected_point_speeds(n):
    e = [NAN] * len(n)
    for i in range(1, len(n)):
        a, s = n[i - 1].get('rawElapsedTime'), n[i].get('rawElapsedTime')
        o = n[i]['distance'] - n[i - 1]['distance']
        if not fin(a) or not fin(s) or not math.isfinite(o) or o <= 1e-6: continue
        l = float(s) - float(a)
        if not (l <= 1e-6 or l > BOUNDARY_SPEED_REPAIR_MAX_STEP_SECONDS): e[i] = clamp_speed_kph(o / l * 3.6)
    t = [NAN] * len(n)
    for i in range(len(n)):
        a = e[i]; s = e[i + 1] if i + 1 < len(e) else NAN
        if math.isfinite(a) and math.isfinite(s): t[i] = (a + s) / 2
        elif math.isfinite(a): t[i] = a
        elif math.isfinite(s): t[i] = s
    return t

def combine_boundary_expectations(n, e):
    if math.isfinite(n) and math.isfinite(e):
        return (n + e) / 2 if abs(n - e) <= BOUNDARY_SPEED_REPAIR_BLEND_TOLERANCE_KPH else n
    return n if math.isfinite(n) else (e if math.isfinite(e) else NAN)

def get_reliable_speed_window_stats(n, e, t, i, a):
    if t < 0 or t + i > len(n): return False
    s = o = 0
    for p in range(t, t + i):
        if not math.isfinite(n[p]): return False
        m = e[p]
        if math.isfinite(m):
            o += 1
            if abs(n[p] - m) <= BOUNDARY_SPEED_REPAIR_EXPECTATION_TOLERANCE_KPH: s += 1
        if p > t and is_slope_violation(n[p] - n[p - 1], 1, a): return False
    return o == 0 or s >= max(1, i - 1)

def is_reliable_speed_window(n, e, t, i, a):
    return get_reliable_speed_window_stats(n, e, t, i, a)

def find_leading_reliable_window_start_from(n, e, t, i, a):
    W = BOUNDARY_SPEED_REPAIR_WINDOW_SAMPLES
    for o in range(t, min(i - W + 1, t + BOUNDARY_SPEED_REPAIR_MAX_SAMPLES) + 1):
        if is_reliable_speed_window(n, e, o, W, a): return o
    return -1

def find_leading_reliable_window_start(n, e, t, i, a):
    W = BOUNDARY_SPEED_REPAIR_WINDOW_SAMPLES
    for o in range(t + 1, min(i - W + 1, t + BOUNDARY_SPEED_REPAIR_MAX_SAMPLES) + 1):
        if is_reliable_speed_window(n, e, o, W, a): return o
    return -1

def find_trailing_reliable_window_end(n, e, t, i, a):
    W = BOUNDARY_SPEED_REPAIR_WINDOW_SAMPLES
    s = max(t + W - 1, i - BOUNDARY_SPEED_REPAIR_MAX_SAMPLES)
    for o in range(i - 1, s - 1, -1):
        if is_reliable_speed_window(n, e, o - W + 1, W, a): return o
    return -1

def estimate_boundary_slope(n, e, t, i):
    a = []
    for o in range(e + 1, e + t):
        l = (n[o] if o < len(n) else NAN) - n[o - 1]
        if math.isfinite(l) and not is_slope_violation(l, 1, i): a.append(l)
    s = median_of_array(a)
    return s if math.isfinite(s) else 0

def repair_leading_high_speed_prefix_drop(n, e, t, i, a):
    s = find_leading_stable_high_speed_window_start(n, t, min(i, t + BOUNDARY_START_PREFIX_SEARCH_SAMPLES))
    if s == -1: return
    l = fit_boundary_speed_line(n, s, min(BOUNDARY_START_PREFIX_WINDOW_SAMPLES, i - s + 1))
    if not l: return
    p = l['medianSpeed']
    if not math.isfinite(p) or p < BOUNDARY_START_PREFIX_MIN_STABLE_SPEED_KPH: return
    m = -1
    for f in range(t, s):
        if not math.isfinite(n[f]): return
        if p - n[f] < BOUNDARY_START_PREFIX_RELEASE_GAP_KPH: break
        m = f
    if not (m < t or p - n[t] < BOUNDARY_START_PREFIX_MIN_GAP_KPH):
        for f in range(t, m + 1):
            v = combine_boundary_expectations(l['intercept'] + l['slope'] * f, e[f])
            if math.isfinite(v) and v > n[f]: n[f] = clamp_speed_kph(v)

def repair_leading_boundary_speed_artifacts(n, e, t, i, a):
    s = find_leading_reliable_window_start(n, e, t, i, a)
    if s == -1: return
    o = n[s]; l = estimate_boundary_slope(n, s, BOUNDARY_SPEED_REPAIR_WINDOW_SAMPLES, a); p = t - 1
    for m in range(t, s):
        f = combine_boundary_expectations(o - l * (s - m), e[m])
        if not math.isfinite(f) or abs(n[m] - f) < BOUNDARY_SPEED_REPAIR_DEVIATION_THRESHOLD_KPH: break
        p = m
    if not (p < t):
        for m in range(t, p + 1):
            f = combine_boundary_expectations(o - l * (s - m), e[m])
            if math.isfinite(f): n[m] = clamp_speed_kph(f)

def repair_trailing_boundary_speed_artifacts(n, e, t, i, a):
    s = find_trailing_reliable_window_end(n, e, t, i, a)
    if s == -1: return
    o = s - BOUNDARY_SPEED_REPAIR_WINDOW_SAMPLES + 1; l = n[s]
    p = estimate_boundary_slope(n, o, BOUNDARY_SPEED_REPAIR_WINDOW_SAMPLES, a); m = i + 1
    for f in range(i, s, -1):
        g = combine_boundary_expectations(l + p * (f - s), e[f])
        if not math.isfinite(g) or abs(n[f] - g) < BOUNDARY_SPEED_REPAIR_DEVIATION_THRESHOLD_KPH: break
        m = f
    if not (m > i):
        for f in range(m, i + 1):
            g = combine_boundary_expectations(l + p * (f - s), e[f])
            if math.isfinite(g): n[f] = clamp_speed_kph(g)

def find_leading_collapsed_prefix_jump_index(n, e, t):
    for a in range(e, max(e, t)):
        if not math.isfinite(n[a]) or not math.isfinite(n[a + 1]): return -1
        if n[a + 1] - n[a] >= BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_JUMP_THRESHOLD_KPH: return a
    return -1

def repair_leading_collapsed_prefix_artifacts(n, e, t, i, a):
    s = find_leading_collapsed_prefix_jump_index(n, t, min(i, t + BOUNDARY_SPEED_REPAIR_MAX_SAMPLES))
    if s == -1: return
    o = find_leading_reliable_window_start_from(n, e, s + 1, i, a)
    if o == -1: return
    l = min(BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_REGRESSION_SAMPLES, i - o + 1)
    if l < BOUNDARY_SPEED_REPAIR_WINDOW_SAMPLES: return
    p = fit_boundary_speed_line(n, o, l)
    if not p or p['medianSpeed'] < BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_MIN_ANCHOR_SPEED_KPH: return
    m = 0; f = s
    for g in range(t, s + 1):
        v = p['intercept'] + p['slope'] * g; y = e[g]
        if not math.isfinite(y) or not math.isfinite(v): f = -1; break
        if not (v - n[g] >= BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_MIN_GAP_KPH and y - n[g] >= BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_EXPECTATION_GAP_KPH):
            f = -1; break
        m += 1
    if not (f < t or m < BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_MIN_SAMPLES):
        for g in range(t, f + 1):
            y = combine_boundary_expectations(p['intercept'] + p['slope'] * g, e[g])
            if math.isfinite(y) and y > n[g]: n[g] = clamp_speed_kph(y)

def compute_boundary_step_acceleration_g(n, e, t):
    if not math.isfinite(n) or not math.isfinite(e) or not math.isfinite(t) or t <= 0: return NAN
    i, a = n / 3.6, e / 3.6
    return (a * a - i * i) / (2 * t) / 9.80665

def is_leading_boundary_acceleration_artifact_step(n, e, t, i):
    if t < 0 or t + 1 >= len(n): return False
    a, s = n[t], n[t + 1]
    if not math.isfinite(a) or not math.isfinite(s) or s <= a: return False
    o = compute_boundary_step_acceleration_g(a, s, i)
    if not math.isfinite(o) or o <= BOUNDARY_ACCELERATION_REPAIR_MAX_TRACTION_G: return False
    l, p = e[t], e[t + 1]
    return max(l - a if math.isfinite(l) else 0, p - s if math.isfinite(p) else 0) >= BOUNDARY_ACCELERATION_REPAIR_EXPECTATION_GAP_KPH

def repair_leading_boundary_acceleration_artifacts(n, e, t, i, a):
    s = min(i - 1, t + BOUNDARY_ACCELERATION_REPAIR_MAX_SAMPLES); o = l = -1; p = 0
    for v in range(t, s + 1):
        if is_leading_boundary_acceleration_artifact_step(n, e, v, a):
            if o == -1: o = v
            p += 1; l = v + 1; continue
        if p >= BOUNDARY_ACCELERATION_REPAIR_MIN_RUN_SAMPLES: break
        o = l = -1; p = 0
    if o == -1 or l == -1 or p < BOUNDARY_ACCELERATION_REPAIR_MIN_RUN_SAMPLES: return
    m = find_leading_reliable_window_start_from(n, e, l + 1, i, a)
    if m == -1: return
    g = fit_boundary_speed_line(n, m, min(BOUNDARY_SPEED_REPAIR_COLLAPSED_PREFIX_REGRESSION_SAMPLES, i - m + 1))
    if g:
        for v in range(o, l + 1):
            C = combine_boundary_expectations(g['intercept'] + g['slope'] * v, e[v])
            if math.isfinite(C) and C > n[v]: n[v] = clamp_speed_kph(C)

def force_repair_leading_collapsed_start_prefix(n, e, t):
    i = find_leading_stable_high_speed_window_start(n, e, min(t, e + BOUNDARY_START_PREFIX_FORCE_SEARCH_SAMPLES))
    if i == -1 or i <= e: return
    s = fit_boundary_speed_line(n, i, min(BOUNDARY_START_PREFIX_WINDOW_SAMPLES, t - i + 1))
    if not s or not math.isfinite(s['medianSpeed']): return
    o = -1
    for l in range(e, i):
        if not math.isfinite(n[l]): return
        if s['medianSpeed'] - n[l] < BOUNDARY_START_PREFIX_RELEASE_GAP_KPH: break
        o = l
    if not (o < e or s['medianSpeed'] - n[e] < BOUNDARY_START_PREFIX_FORCE_MIN_GAP_KPH):
        for l in range(e, o + 1):
            p = s['intercept'] + s['slope'] * l
            if math.isfinite(p) and p > n[l]: n[l] = clamp_speed_kph(p)

def repair_boundary_speed_artifacts(n, e):
    if not n or len(n) < 5: return n
    t = [float(l['speed']) if fin(l.get('speed')) else NAN for l in n]
    i = build_elapsed_time_expected_point_speeds(n)
    a = next((p for p, l in enumerate(n) if fin(l.get('distance')) and l['distance'] >= 0 and math.isfinite(t[p])), -1)
    if a == -1: return n
    s = -1
    for l in range(len(n) - 1, a - 1, -1):
        if fin(n[l].get('distance')) and n[l]['distance'] >= 0 and math.isfinite(t[l]): s = l; break
    if s <= a: return n
    o = list(t)
    repair_leading_high_speed_prefix_drop(o, i, a, s, e)
    repair_leading_boundary_speed_artifacts(o, i, a, s, e)
    repair_leading_collapsed_prefix_artifacts(o, i, a, s, e)
    repair_leading_boundary_acceleration_artifacts(o, i, a, s, e)
    repair_trailing_boundary_speed_artifacts(o, i, a, s, e)
    force_repair_leading_collapsed_start_prefix(o, a, s)
    out = []
    for p, l in enumerate(n):
        r = dict(l)
        if not (l.get('speed') is None or not math.isfinite(o[p])): r['speed'] = tofixed(clamp_speed_kph(o[p]), 1)
        out.append(r)
    return out


# ---------- resample + integrate ----------
def resample_lap_data_by_distance(n, e, t):
    i = t if t else n
    if not i: return []
    a = FIXED_RESAMPLING_INTERVAL; s = n[0] if n else {}
    o = -(s['position'] - 1) * GRID_SLOT_OFFSET if s.get('lapNumber') == 1 and s.get('position') is not None else 0
    l, p = o, e + o; m = []; y = l
    while y <= p:
        b = y - o; C = None; w = 0; k = 0; I = 0; M = None; A = None
        if b >= 0:
            C = interpolate_simple(i, b, 'rpm'); w = interpolate_simple(i, b, 'speed'); k = interpolate_simple(i, b, 'throttle')
            I = interpolate_step(i, b, 'brake'); M = interpolate_step(i, b, 'nGear'); A = interpolate_step(i, b, 'drs')
        m.append({'distance': y, 'rawElapsedTime': interpolate_simple(i, b, 'delta') if b >= 0 else None, 'delta': None,
                  'speed': None if w is None or (isinstance(w, float) and math.isnan(w)) else tofixed(w, 1),
                  'brake': 0 if I is None else min(100, max(0, I)), 'lapDuration': s.get('lapDuration'),
                  'lapDurationS1': s.get('lapDurationS1'), 'lapDurationS2': s.get('lapDurationS2'), 'lapNumber': s.get('lapNumber'),
                  'position': s.get('position')})
        y += a
    if len(m) < 3: return m
    f = repair_resampled_leading_speed_collapse(m)
    g = clean_speed_artifacts([float(x['speed']) if fin(x.get('speed')) else NAN for x in f], a)
    v = []
    for b, x in enumerate(f):
        r = dict(x)
        if not (x.get('speed') is None or not math.isfinite(g[b])): r['speed'] = tofixed(g[b], 1)
        v.append(r)
    return repair_boundary_speed_artifacts(v, a)

def interpolate_elapsed_time_at_distance(n, e, t, i):
    a, s, o, l = n.get('distance'), e.get('distance'), n.get(i), e.get(i)
    if not (fin(a) and fin(s) and fin(o) and fin(l)): return None
    p = s - a
    if p <= 1e-9: return float(o)
    return float(o) + (t - a) / p * (float(l) - float(o))

def compute_delta_increment_seconds(n, e, t):
    if not math.isfinite(t) or t <= 0: return 0
    i = n if jsfin(n) else 0; a = e if jsfin(e) else 0
    s = (num(i) + num(a)) / 2 / 3.6
    return t / s if s > 0.1 else t / 0.278

def stabilize_starting_delta_prefix(n):
    if not n: return n
    e = next((j for j, x in enumerate(n) if fin(x.get('distance')) and x['distance'] >= 0 and fin(x.get('delta')) and fin(x.get('speed'))), -1)
    if e < 0 or e >= len(n) - 1: return n
    t = float(n[e]['distance']); i = -1
    for j in range(e + 1, min(len(n) - 1, e + START_DELTA_STABILIZATION_MAX_SAMPLES) + 1):
        le = n[j].get('distance')
        if fin(le) and j - e >= START_DELTA_STABILIZATION_MIN_SAMPLES and le - t >= START_DELTA_STABILIZATION_DISTANCE_METERS:
            i = j; break
    if i == -1: return n
    s = n[e:i + 1]
    if len(s) < START_DELTA_STABILIZATION_MIN_SAMPLES + 1: return n
    o = 0.0; l = 0
    for j in range(len(s)):
        le = s[j].get('speed')
        if not fin(le): return n
        Z = s[j].get('brake')
        if fin(Z): o = max(o, float(Z))
        if j > 0 and fin(s[j - 1].get('speed')) and le < s[j - 1]['speed'] - 1.5: l += 1
    if o > START_DELTA_STABILIZATION_MAX_BRAKE or s[-1]['speed'] < s[0]['speed'] - START_DELTA_STABILIZATION_MAX_NET_SPEED_DROP_KPH or l > START_DELTA_STABILIZATION_MAX_NEGATIVE_STEPS:
        return n
    p = 5 if len(s) >= 5 else 3
    m = apply_median_filter([float(j['speed']) for j in s], p)
    f = g = v = y = 0.0; b = []
    for j in range(1, len(s)):
        le = s[j]['distance'] - s[j - 1]['distance']
        if not math.isfinite(le) or le <= 1e-6: return n
        Z = compute_delta_increment_seconds(float(s[j - 1]['speed']), float(s[j]['speed']), le)
        se = compute_delta_increment_seconds(m[j - 1], m[j], le)
        ce = Z - se; f += Z; g += se; v = max(v, abs(ce)); y += abs(ce); b.append(se)
    C, w = s[0].get('rawElapsedTime'), s[-1].get('rawElapsedTime')
    if not fin(C) or not fin(w): return n
    k = float(w) - float(C)
    if not math.isfinite(k) or k <= 0 or g <= 0: return n
    I = k - f; M = g - f; A = jsign(I)
    if (A == 0 or A != jsign(M) or abs(I) < START_DELTA_STABILIZATION_ANCHOR_THRESHOLD_S or abs(M) < START_DELTA_STABILIZATION_ANCHOR_THRESHOLD_S
            or v < START_DELTA_STABILIZATION_STEP_ERROR_THRESHOLD_S or y < START_DELTA_STABILIZATION_TOTAL_ERROR_THRESHOLD_S):
        return n
    P = num(s[0].get('delta')); N = median_of_array([f, k, g])
    if not math.isfinite(N) or N <= 0: return n
    H = max(-START_DELTA_STABILIZATION_MAX_CORRECTION_S, min(START_DELTA_STABILIZATION_MAX_CORRECTION_S, N - f))
    if abs(H) < START_DELTA_STABILIZATION_ANCHOR_THRESHOLD_S: return n
    z = [dict(j) for j in n]; J = (f + H) / g; ee = P
    z[e]['delta'] = tofixed(P, 6)
    for j in range(1, len(s)):
        ee += b[j - 1] * J; z[e + j]['delta'] = tofixed(ee, 6)
    for j in range(i + 1, len(z)):
        le = z[j].get('delta')
        if fin(le): z[j]['delta'] = tofixed(float(le) + H, 6)
    return z

def calculate_lap_deltas_integration_based(n):
    if not n: return []
    e = 'rawElapsedTime' if any(fin(y.get('rawElapsedTime')) for y in n) else 'time'
    t = 0.0
    i = next((k for k, y in enumerate(n) if y['distance'] >= 0), -1)
    if i > 0:
        r = interpolate_elapsed_time_at_distance(n[i - 1], n[i], 0, e); t = r if r is not None else 0
    elif i == 0 and fin(n[0].get(e)): t = float(n[0][e])
    elif i == -1: return [dict(y, delta=0) for y in n]
    a = n[i:]
    s = a[-1].get(e); o = a[-1].get('lapDuration')
    l = s - t if fin(s) and math.isfinite(t) and s >= t else o
    p = []; m = 0.0; f = 0.0; g = a[0].get('speed') if a[0].get('speed') is not None else 0
    for y, b in enumerate(a):
        C = b.get(e); w = C - t if fin(C) and math.isfinite(t) else None
        if y == 0:
            p.append(dict(b, time=w, delta=0)); continue
        k = b['distance']; I = k - f
        m += compute_delta_increment_seconds(g, b.get('speed'), I)
        p.append(dict(b, time=w, delta=m)); f = k; g = b.get('speed')
    p = stabilize_starting_delta_prefix(p)
    m = float(p[-1]['delta']) if fin(p[-1].get('delta')) else m
    if l is not None and l > 0 and abs(m - l) > 0.1:
        y = l / m
        p = [dict(b, delta=tofixed(b['delta'] * y, 3)) for b in p]
    return [dict(y, delta=None) for y in n[:i]] + p

def find_nearest_index(n, e, t='distance'):
    if not n or e is None or not math.isfinite(e): return -1
    i, a, s, o = 0, len(n) - 1, -1, INF
    l, p = n[0].get(t), n[a].get(t)
    if fin(l) and e <= l + 1e-6: return 0
    if fin(p) and e >= p - 1e-6: return a
    while i <= a:
        m = (i + a) // 2; g = n[m].get(t)
        if not fin(g):
            if a == m: a -= 1
            else: a = m - 1
            if i > a and s == -1: i = m + 1; a = len(n) - 1
            continue
        v = abs(g - e)
        if v < o: o = v; s = m
        if g < e: i = m + 1
        elif g > e: a = m - 1
        else: return m
    if s != -1:
        for f in [x for x in (s - 1, s, s + 1) if 0 <= x < len(n)]:
            g = n[f].get(t)
            if fin(g):
                v = abs(g - e)
                if v < o: o = v; s = f
    return s

def improve_delta_by_sector_scaling(n, e):
    if not n or len(n) < 2 or len(e) < 2 or any(A is None or not math.isfinite(A) or A < 0 for A in e): return n
    t = n[0]; i, a, s = t.get('lapDurationS1'), t.get('lapDurationS2'), t.get('lapDuration')
    if not (fin(i) and i > 0 and fin(a) and a > 0 and fin(s) and s > 0): return n
    o = s - (i + a)
    if o < -1e-6: return n
    l = find_nearest_index(n, e[0], 'distance'); p = find_nearest_index(n, e[1], 'distance'); m = len(n) - 1
    if l < 0 or p < 0 or l >= m or p >= m or l > p: return n
    f, g, v = n[l].get('delta'), n[p].get('delta'), n[m].get('delta')
    if not (fin(f) and f >= -1e-6 and fin(g) and g >= -1e-6 and fin(v) and v >= -1e-6): return n
    y, b, C = max(0, f), max(0, g - f), max(0, v - g)
    if y <= 1e-6 or b <= 1e-6 or C <= 1e-6: return n
    w, k, I = i / y, a / b, o / C; M = 0; out = []
    for P, A in enumerate(n):
        if not fin(A.get('delta')):
            out.append(A); continue
        if P <= l: N = A['delta'] * w
        elif P <= p: N = i + (A['delta'] - f) * k
        else: N = i + a + (A['delta'] - g) * I
        N = max(M, min(N, s)); M = N
        out.append(dict(A, delta=tofixed(N, 3)))
    return out


# ---------- main ----------
def align_data(n, e=0):
    """n: list of laps, each a list of raw sample dicts with keys date_ms ('_ms'), speed, throttle, brake, rpm, nGear, drs,
    lapDuration, lapDurationS1, lapDurationS2, lapNumber, position. Returns (alignedData, offsets, referenceIndex)."""
    t = []
    for Z in n:
        ce = calculate_distances(clean_raw_speed_artifacts(Z))
        ve = Z[0] if Z else {}
        if ve.get('lapNumber') == 1 and ve.get('position') is not None:
            Qe = -(ve['position'] - 1) * GRID_SLOT_OFFSET
            ce = [dict(x, distance=x['distance'] + Qe) for x in ce]
        if len(ce) > 1: t.append(ce)
    if not t: return [], [], 0
    i = get_robust_minimum_distance(t, 0.07)
    a = [[x for x in Z if x['distance'] <= i] for Z in t]
    s, o = e, a[e]
    l = get_finite_min_distance(o)
    p = build_distance_grid(l, i, ALIGNMENT_GRID_STEP)
    f = [resample_signal_to_grid(compute_speed_gradient_signal(Z), p) for Z in a]
    g = f[s] if s < len(f) and f[s] else [0.0] * len(p)
    v = sorted(abs(Z) for Z in g if math.isfinite(abs(Z)) and abs(Z) > 0)
    y = v[len(v) // 2] if v else 0
    b = min(2, max(0.2, y * 1.5 if y > 1e-6 else ALIGNMENT_SIGNAL_WEIGHT_SCALE))
    C = min(1.5, max(0.2, y * 0.75 if y > 1e-6 else ALIGNMENT_HUBER_DELTA))
    gA = np.asarray(g, float)
    def cost(ce, it, lo, hi):
        # weighted Huber over grid indices lo..hi of ref signal g vs ce shifted by it (same loop order as JS)
        Me = Ye = 0.0
        for Ue in range(lo, hi + 1):
            qe = Ue - it
            if qe < 0 or qe >= len(ce): continue
            Vt = ce[qe]; Ft = alignment_weight(g[Ue], Vt, b)
            if Ft > 0: Me += Ft * huber_loss(Vt - g[Ue], C); Ye += Ft
        return Me, Ye
    w = []
    for se in range(len(t)):
        if se == s: w.append(0); continue
        ce = f[se] if se < len(f) else []; ve = 0; Qe = INF
        for sh in range(-GLOBAL_SEARCH_RANGE, GLOBAL_SEARCH_RANGE + 1, GLOBAL_SEARCH_STEP):
            Me, Ye = cost(ce, jround(sh / ALIGNMENT_GRID_STEP), 0, len(p) - 1)
            if Ye:
                Ue = Me / Ye
                if Ue < Qe: Qe = Ue; ve = sh
        w.append(ve)
    k = [[dict(x, distance=x['distance'] + w[se]) for x in Z] for se, Z in enumerate(t)]
    I = i / 4; M = math.ceil((i - 15) / I)
    A = []
    for se, Z in enumerate(k):
        if se == s: A.append([0] * M); continue
        ce = f[se] if se < len(f) else []; ve = w[se]; Qe = []; p0 = p[0] if p else 0
        for Me in range(M):
            Ye = 15 + Me * I; it = min(i, Ye + I)
            Ue = max(0, math.floor((Ye - p0) / ALIGNMENT_GRID_STEP)); qe = min(len(p) - 1, math.ceil((it - p0) / ALIGNMENT_GRID_STEP))
            if Ue > qe: Qe.append(0); continue
            Vt = 0; Ft = INF
            for gi in range(-LOCAL_SEARCH_RANGE, LOCAL_SEARCH_RANGE + 1, LOCAL_SEARCH_STEP):
                Li, Ct = cost(ce, jround((gi + ve) / ALIGNMENT_GRID_STEP), Ue, qe)
                Ki = Li / Ct if Ct else INF
                if Ki < Ft: Ft = Ki; Vt = gi
            Qe.append(Vt)
        # JS: ((it[Ye-1] || Me) + Me + (it[Ye+1] || Me)) / 3  -- 0 and out-of-range fall back to Me
        sm = []
        for j, x in enumerate(Qe):
            lft = sl(Qe, j - 1); rgt = sl(Qe, j + 1)
            sm.append(((lft if lft else x) + x + (rgt if rgt else x)) / 3)
        A.append(sm)
    P = []
    for se, Z in enumerate(k):
        out = []
        for x in Z:
            ve = min(max(0, math.floor(x['distance'] / I)), M - 1)
            d = x['distance'] + (A[se][ve] or 0)
            if 0 <= d <= i: out.append(dict(x, distance=d))
        P.append(out)
    N = [calculate_lap_deltas_integration_based(resample_lap_data_by_distance(n[se], i, Z)) for se, Z in enumerate(P)]
    H = N[s]; z, Q = H[0].get('lapDurationS1'), H[0].get('lapDurationS2'); J = []
    if fin(z) and fin(Q) and z > 0 and Q > 0:
        Z1 = find_nearest_index(H, z, 'delta'); Z2 = find_nearest_index(H, z + Q, 'delta')
        if Z1 > -1: J.append(H[Z1]['distance'])
        if Z2 > -1: J.append(H[Z2]['distance'])
    out = []
    for Z in N:
        ce = [dict(x) for x in Z]
        if ce[0].get('lapNumber') == 1:
            raise NotImplementedError('lap-1 grid-slot base delta not ported')
        out.append(improve_delta_by_sector_scaling(ce, J) if len(J) == 2 else ce)
    return out, [x for row in A for x in row], s, w

def chart_delta(aligned, ref_index=0, max_points=800):
    """Delta series as their chart (and its CSV download) shows it: tgt.delta - ref.delta per index, downsampled."""
    ref = aligned[ref_index]; series = []
    for lap in aligned:
        pts = [(x['distance'], 0.0 if lap is ref else (x['delta'] - ref[j]['delta'] if x.get('delta') is not None and j < len(ref) and ref[j].get('delta') is not None else None))
               for j, x in enumerate(lap)]
        if len(pts) > max_points:
            step = math.ceil(len(pts) / max_points); d = pts[::step]
            if d[-1] is not pts[-1]: d.append(pts[-1])
            pts = d
        series.append(pts)
    return series
