"""
HI-FI DELTA ENGINE v2  (core only, drop-in replacement for v1)

Pipeline
  1. PACE INTEGRATION  time rebuilt from Distance/Speed (dt = ds/v), scaled to
                       the official lap time. FastF1 timestamps are not used.
  2. STRETCH           target distance scaled to the reference lap length.
  3. SLIDE             speed-profile alignment by mean-removed MSE.
                       'windows': 4 windows, +-15 m (F1InsightsHub method, default)
                       'corners': one knot per corner around a robust trend
                       'none'   : no slide
                       Edges extrapolate at edge speed (no clamping).
  4. RUBBERBAND REFIT  delta pinned to the official S1, S2 and lap gaps,
                       piecewise-linear correction between the pins.
  5. SMOOTH            centred moving average over N metres.

Usage
    from hifi_delta_v2 import get_trace, calculate_hifi_delta

    ref = get_trace(session, 'VER')       # first driver = reference
    tgt = get_trace(session, 'LEC')
    dist, delta, integrity, fidelity = calculate_hifi_delta(ref, tgt)

    dist       1 m grid along the reference lap (0 .. ref lap length)
    delta      seconds, + = target slower
    integrity  dict: 'score', 'grade', 'length_offset', 'shift_offset', ...
    fidelity   dict: 'fidelity', 'steps', 'budget', ...

Trace dict fields
    required: 'dist', 'speed' (km/h), 'lap_time' (s)
    optional: 'gates' {'S1': (dist_m, cum_time_s), 'S2': (...)} for the rubberband
              (get_trace fills it; without it only start/finish are pinned)
"""

import numpy as np
import pandas as pd
from scipy.signal import correlate, find_peaks

__all__ = ['get_trace', 'calculate_hifi_delta', 'hifi_delta_v2',
           'calculate_integrity_score', 'calculate_fidelity']

# ══════════════════════════════════════════════════════════════════
# DEFAULTS
# ══════════════════════════════════════════════════════════════════
ALIGN_MODE     = 'windows'   # 'windows', 'corners', 'none'
ALIGN_WINDOWS  = 4           # 'windows' mode
WINDOW_SHIFT_M = 15.0        # 'windows' mode: max shift per window, metres
MAX_SHIFT_M    = 40.0        # 'corners' mode: global search range, metres
LOCAL_SHIFT_M  = 8.0         # 'corners' mode: per-corner refinement, metres
PIN_ENDS       = False       # 'corners' mode: shift fixed at 0 on the line
RUBBERBAND     = True        # pin delta to official sector gaps
SMOOTH_M       = 25          # moving average width, metres (0 = off)

# ══════════════════════════════════════════════════════════════════
# METRICS (Shape Integrity + Pipeline Fidelity)
# ══════════════════════════════════════════════════════════════════
INTEGRITY_TAU = 5
INTEGRITY_P = 1.5
INTEGRITY_LAMBDA = 700

def calculate_integrity_score(length_offset_m, shift_offset_m):
    total_offset = length_offset_m + shift_offset_m
    effective = max(0, total_offset - INTEGRITY_TAU)
    score = 100.0 * np.exp(-(effective ** INTEGRITY_P) / INTEGRITY_LAMBDA)

    if score >= 95:    grade, color = "Excellent", "#16813D"
    elif score >= 85:  grade, color = "Good", "#0f3460"
    elif score >= 70:  grade, color = "Acceptable", "#CC8800"
    elif score >= 50:  grade, color = "Warning", "#CC0000"
    else:              grade, color = "Critical", "#990000"

    return {
        'score': round(score, 1), 'grade': grade, 'grade_color': color,
        'total_offset': round(total_offset, 2),
        'length_offset': round(length_offset_m, 2),
        'shift_offset': round(shift_offset_m, 2),
    }

def calculate_fidelity(scale_factor, local_shifts, track_length,
                       raw_delta, smooth_delta, lap_time,
                       endpoint_correction):
    step1 = abs(scale_factor - 1.0) * 100
    if len(local_shifts) > 0:
        step2 = (np.sqrt(np.mean(np.array(local_shifts)**2)) / track_length) * 100
    else:
        step2 = 0.0
    diff = smooth_delta - raw_delta
    step3 = (np.sqrt(np.mean(diff**2)) / lap_time) * 100
    step4 = (abs(endpoint_correction) / lap_time) * 100

    total = step1 + step2 + step3 + step4
    fidelity = 100.0 - total

    if total > 0:
        budget = {
            'scale':    round((step1 / total) * 100, 1),
            'warp':     round((step2 / total) * 100, 1),
            'smooth':   round((step3 / total) * 100, 1),
            'endpoint': round((step4 / total) * 100, 1),
        }
    else:
        budget = {'scale': 0, 'warp': 0, 'smooth': 0, 'endpoint': 0}

    return {
        'fidelity': round(float(fidelity), 3),
        'total_intervention': round(float(total), 3),
        'steps': {
            'scale':    round(float(step1), 4),
            'warp':     round(float(step2), 4),
            'smooth':   round(float(step3), 4),
            'endpoint': round(float(step4), 4),
        },
        'budget': budget,
    }

def _global_shift_m(ref_dist, ref_speed, tgt_dist_scaled, tgt_speed, master_len):
    """Global lag between full-lap speed profiles (used by Shape Integrity)."""
    grid_len = 10000
    common_grid = np.linspace(0, master_len, grid_len)
    v_ref = np.interp(common_grid, ref_dist, ref_speed)
    v_tgt = np.interp(common_grid, tgt_dist_scaled, tgt_speed)
    v_ref_full = (v_ref - np.mean(v_ref)) / (np.std(v_ref) + 1e-6)
    v_tgt_full = (v_tgt - np.mean(v_tgt)) / (np.std(v_tgt) + 1e-6)
    corr_full = correlate(v_ref_full, v_tgt_full, mode='same')
    global_lag = np.argmax(corr_full) - (len(corr_full) // 2)
    return abs(global_lag * (master_len / grid_len))

# ══════════════════════════════════════════════════════════════════
# DATA
# ══════════════════════════════════════════════════════════════════
def _secs(x):
    return x.total_seconds() if pd.notna(x) else None

def get_trace(session, driver, lap=None):
    """Trace dict for the driver's fastest lap (or the given FastF1 Lap).
    Includes official sector gates for the rubberband and X/Y for rail building."""
    if lap is None:
        laps = session.laps.pick_drivers(driver)
        if laps.empty: return None
        lap = laps.pick_fastest()
    if lap is None or (hasattr(lap, 'empty') and lap.empty): return None
    if pd.isna(lap['LapTime']): return None
    try:
        tel = lap.get_telemetry()
    except Exception:
        return None
    if tel.empty: return None

    d = tel['Distance'].to_numpy(dtype=float)
    keep = np.r_[True, np.diff(d) > 0]            # strictly increasing distance
    tel = tel[keep]
    d = d[keep]
    v = tel['Speed'].to_numpy(dtype=float)
    t = tel['Time'].dt.total_seconds().to_numpy(dtype=float)

    s1, s2 = _secs(lap['Sector1Time']), _secs(lap['Sector2Time'])
    gates = {}
    if s1 is not None:
        gates['S1'] = (float(np.interp(s1, t, d)), s1)
        if s2 is not None:
            gates['S2'] = (float(np.interp(s1 + s2, t, d)), s1 + s2)

    full_name = driver
    try:
        full_name = str(session.get_driver(driver)['FullName'])
    except Exception:
        pass

    return {
        'driver': driver, 'full_name': full_name,
        'dist': d, 'speed': v, 'time': t,
        'lap_time': lap['LapTime'].total_seconds(),
        'gates': gates,
        'x': tel['X'].to_numpy(dtype=float) if 'X' in tel else np.zeros(len(tel)),
        'y': tel['Y'].to_numpy(dtype=float) if 'Y' in tel else np.zeros(len(tel)),
    }

def _clean(trace):
    """Strictly increasing distance; works on v1-style traces too."""
    d = np.asarray(trace['dist'], dtype=float)
    v = np.asarray(trace['speed'], dtype=float)
    keep = np.r_[True, np.diff(d) > 0]
    return d[keep], v[keep]

# ══════════════════════════════════════════════════════════════════
# ENGINE
# ══════════════════════════════════════════════════════════════════
def _pace_time(d, v_kmh, lap_time):
    """Time rebuilt from distance and speed, scaled to the official lap time."""
    v = np.maximum(v_kmh, 5.0) / 3.6
    dt = np.diff(d) / ((v[:-1] + v[1:]) / 2)
    t = np.r_[0.0, np.cumsum(dt)]
    return t * (lap_time / t[-1])

def _interp_extrap(x, xp, fp, v_lo_kmh, v_hi_kmh):
    """np.interp, but beyond the data it continues at the edge speed
    instead of clamping (clamping corrupts the finish-line pin)."""
    y = np.interp(x, xp, fp)
    lo, hi = x < xp[0], x > xp[-1]
    y[lo] = fp[0] - (xp[0] - x[lo]) / (max(v_lo_kmh, 5.0) / 3.6)
    y[hi] = fp[-1] + (x[hi] - xp[-1]) / (max(v_hi_kmh, 5.0) / 3.6)
    return y

def _best_shift(grid, v_ref, v_tgt, lo, hi, offsets):
    """Shift (m) to ADD to target distance that best matches ref speed on [lo, hi]."""
    m = (grid >= lo) & (grid <= hi)
    x = grid[m]
    r = v_ref[m] - v_ref[m].mean()
    errs = np.empty(len(offsets))
    for i, off in enumerate(offsets):
        s = np.interp(x - off, grid, v_tgt)
        errs[i] = np.mean((r - (s - s.mean())) ** 2)
    return float(offsets[int(np.argmin(errs))])

def _window_align(grid, v_ref, v_tgt, n_windows, max_shift, step=0.5):
    D = grid[-1]
    if n_windows <= 0:
        return np.array([0.0, D]), np.array([0.0, 0.0])
    offsets = np.arange(-max_shift, max_shift + step / 2, step)
    edges = np.linspace(0, D, n_windows + 1)
    knots = (edges[:-1] + edges[1:]) / 2
    shifts = np.array([_best_shift(grid, v_ref, v_tgt, a, b, offsets)
                       for a, b in zip(edges[:-1], edges[1:])])
    return np.r_[0.0, knots, D], np.r_[shifts[0], shifts, shifts[-1]]

def _corner_align(grid, v_ref, v_tgt, max_shift, local_shift, pin_ends, step=0.5):
    D = grid[-1]
    peaks, _ = find_peaks(-v_ref, prominence=25, distance=80)
    if len(peaks) < 3:
        return _window_align(grid, v_ref, v_tgt, 4, 15.0, step)
    centers = grid[peaks]
    coarse_offs = np.arange(-max_shift, max_shift + step / 2, step)
    coarse = np.array([_best_shift(grid, v_ref, v_tgt, c - 220.0, c + 150.0, coarse_offs)
                       for c in centers])
    keep = np.ones(len(centers), bool)
    k, b = 0.0, float(np.median(coarse))
    for _ in range(4):
        if keep.sum() < 2: break
        k, b = np.polyfit(centers[keep], coarse[keep], 1)
        res = coarse - (k * centers + b)
        mad = max(1.4826 * np.median(np.abs(res[keep])), 2.0)
        keep = np.abs(res) <= 3 * mad
    trend = k * centers + b
    local_offs = np.arange(-local_shift, local_shift + step / 2, step)
    fine = np.array([_best_shift(grid, v_ref, v_tgt, c - 220.0, c + 150.0, t + local_offs)
                     for c, t in zip(centers, trend)])
    if pin_ends:
        return np.r_[0.0, centers, D], np.r_[0.0, fine, 0.0]
    return np.r_[0.0, centers, D], np.r_[b, fine, k * D + b]

def hifi_delta_v2(ref, tgt, mode=ALIGN_MODE, rubberband=RUBBERBAND, smooth_m=SMOOTH_M,
                  align_windows=ALIGN_WINDOWS, window_shift_m=WINDOW_SHIFT_M,
                  max_shift_m=MAX_SHIFT_M, local_shift_m=LOCAL_SHIFT_M, pin_ends=PIN_ENDS):
    """Full engine. Returns (dist, delta, integrity, fidelity, info).
    info: 'pins' [(dist, gap)], 'knots', 'shifts' (slide), for debugging."""
    rd, rv = _clean(ref)
    td, tv = _clean(tgt)
    D = rd[-1]
    grid = np.r_[np.arange(0.0, D, 1.0), D]

    # 1. Pace integration
    t_ref = _pace_time(rd, rv, ref['lap_time'])
    t_tgt = _pace_time(td, tv, tgt['lap_time'])

    # 2. Stretch
    scale = D / td[-1]
    d_t = td * scale
    length_offset = abs(D - td[-1])

    # 3. Slide
    v_r = np.interp(grid, rd, rv)
    v_t = np.interp(grid, d_t, tv)
    if mode == 'windows':
        knots, shifts = _window_align(grid, v_r, v_t, align_windows, window_shift_m)
    elif mode == 'corners':
        knots, shifts = _corner_align(grid, v_r, v_t, max_shift_m, local_shift_m, pin_ends)
    else:
        knots, shifts = np.array([0.0, D]), np.array([0.0, 0.0])
    applied = np.interp(d_t, knots, shifts)
    d_al = np.maximum.accumulate(d_t + applied)

    tr = _interp_extrap(grid, rd, t_ref, rv[0], rv[-1])
    tt = _interp_extrap(grid, d_al, t_tgt, tv[0], tv[-1])
    raw = tt - tr
    raw = raw - raw[0]
    unsmoothed = raw

    # 5. Smooth (before the refit so the pins stay exact)
    if smooth_m and smooth_m > 1:                     # 1 m grid: N metres = N samples
        k = int(smooth_m) | 1
        raw = np.convolve(np.pad(raw, k // 2, mode='edge'), np.ones(k) / k, mode='valid')

    # 4. Rubberband refit to official gaps
    gap = tgt['lap_time'] - ref['lap_time']
    pins = [(0.0, 0.0)]
    rg, tg = ref.get('gates') or {}, tgt.get('gates') or {}
    if rubberband:
        for g in ('S1', 'S2'):
            if g in rg and g in tg and 0.0 < rg[g][0] < D:
                pins.append((rg[g][0], tg[g][1] - rg[g][1]))
    pins.append((D, gap))
    pins.sort()
    px = np.array([p[0] for p in pins]); py = np.array([p[1] for p in pins])
    resid = py - np.interp(px, grid, raw)
    delta = raw + np.interp(grid, px, resid)

    # Metrics
    integrity = calculate_integrity_score(
        length_offset, _global_shift_m(rd, rv, d_t, tv, D))
    fidelity = calculate_fidelity(
        scale_factor=scale, local_shifts=applied, track_length=D,
        raw_delta=unsmoothed, smooth_delta=raw, lap_time=ref['lap_time'],
        endpoint_correction=float(np.max(np.abs(resid))))

    info = {'pins': [(float(x), float(y)) for x, y in zip(px, py)],
            'knots': knots, 'shifts': shifts}
    return grid, delta, integrity, fidelity, info

def calculate_hifi_delta(ref, tgt, **kwargs):
    """Drop-in for v1. Returns (dist, delta, integrity, fidelity)."""
    grid, delta, integrity, fidelity, _ = hifi_delta_v2(ref, tgt, **kwargs)
    return grid, delta, integrity, fidelity
