"""HI-FI DELTA v2 engine - copied VERBATIM from the user's notebook
(Downloads/formulytics scripts.ipynb, last cell, "HI-FI DELTA v2"). Do not edit the engine code below;
only the adapter at the bottom (calculate_delta) is ours: it feeds lap-comparison traces in and returns the
delta on the reference distance axis, the same shape the old calculate_hifi_delta returned.

Pipeline (from the notebook): 1 pace integration (dt = ds/v, scaled to the official lap time),
2 stretch to the reference lap length, 3 slide (speed-profile alignment, 4 windows +-15 m),
4 rubberband refit pinned to the official S1, S2 and lap gaps.
"""

# ── CONFIG (notebook values) ──
ALIGN_MODE    = 'windows'         # 'windows' (F1InsightsHub style), 'corners', 'none'
MAX_SHIFT_M   = 40.0              # 'corners' only: global search range, metres
LOCAL_SHIFT_M = 8.0               # 'corners' only: per-corner refinement, metres
PIN_ENDS      = False             # 'corners' only: True = slide fixed at 0 on the line
ALIGN_WINDOWS = 4                 # only used by ALIGN_MODE = 'windows'
WINDOW_SHIFT_M = 15.0             # max shift per window (F1InsightsHub uses 15)
RUBBERBAND    = True              # pin delta to official sector gaps
SMOOTH_M      = 25                # centred moving average over N metres (0 = off)

# ── IMPORTS ──
import os
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import fastf1
import fastf1.plotting
from scipy.interpolate import interp1d
from scipy.signal import correlate, medfilt, find_peaks

warnings.simplefilter(action='ignore')

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
        'fidelity': round(fidelity, 3),
        'total_intervention': round(total, 3),
        'steps': {
            'scale':    round(step1, 4),
            'warp':     round(step2, 4),
            'smooth':   round(step3, 4),
            'endpoint': round(step4, 4),
        },
        'budget': budget,
    }

def global_shift_m(ref, tgt_dist_scaled, tgt_speed, master_len):
    """Global lag between full-lap speed profiles (used by Shape Integrity)."""
    grid_len = 10000
    common_grid = np.linspace(0, master_len, grid_len)
    v_ref = np.interp(common_grid, ref['dist'], ref['speed'])
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

def get_trace(session, driver):
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
    v = tel['Speed'].to_numpy(dtype=float)
    t = tel['Time'].dt.total_seconds().to_numpy(dtype=float)
    keep = np.r_[True, np.diff(d) > 0]          # strictly increasing distance
    d, v, t = d[keep], v[keep], t[keep]

    # Official sector gates: (distance in own telemetry, cumulative official time)
    s1, s2 = _secs(lap['Sector1Time']), _secs(lap['Sector2Time'])
    gates = {}
    if s1 is not None:
        gates['S1'] = (float(np.interp(s1, t, d)), s1)
        if s2 is not None:
            gates['S2'] = (float(np.interp(s1 + s2, t, d)), s1 + s2)

    try:
        info = session.get_driver(driver)
        last_name = str(info.get('LastName', driver))
    except Exception:
        last_name = driver

    return {'driver': driver, 'last_name': last_name,
            'dist': d, 'speed': v, 'time': t,
            'lap_time': lap['LapTime'].total_seconds(),
            'sector_times': (s1, s2), 'gates': gates}

# ══════════════════════════════════════════════════════════════════
# HI-FI DELTA v2 ENGINE
# ══════════════════════════════════════════════════════════════════
def pace_time(d, v_kmh, lap_time):
    """Time rebuilt from distance and speed, scaled to the official lap time."""
    v = np.maximum(v_kmh, 5.0) / 3.6
    dt = np.diff(d) / ((v[:-1] + v[1:]) / 2)
    t = np.r_[0.0, np.cumsum(dt)]
    return t * (lap_time / t[-1])

def interp_extrap(x, xp, fp, v_lo_kmh, v_hi_kmh):
    """np.interp, but beyond the data it continues at the edge speed
    instead of clamping (clamping corrupts the finish-line pin)."""
    y = np.interp(x, xp, fp)
    lo, hi = x < xp[0], x > xp[-1]
    y[lo] = fp[0] - (xp[0] - x[lo]) / (max(v_lo_kmh, 5.0) / 3.6)
    y[hi] = fp[-1] + (x[hi] - xp[-1]) / (max(v_hi_kmh, 5.0) / 3.6)
    return y

def _best_shift(grid, v_ref, v_tgt, lo, hi, offsets):
    """Shift (m) to ADD to target distance that best matches ref speed on [lo, hi]
    (mean-removed MSE, so a faster car doesn't bias the match)."""
    m = (grid >= lo) & (grid <= hi)
    x = grid[m]
    r = v_ref[m] - v_ref[m].mean()
    errs = np.empty(len(offsets))
    for i, off in enumerate(offsets):
        s = np.interp(x - off, grid, v_tgt)
        errs[i] = np.mean((r - (s - s.mean())) ** 2)
    return float(offsets[int(np.argmin(errs))])

def window_align(grid, v_ref, v_tgt, n_windows, max_shift, step=0.5):
    """F1InsightsHub-style: fixed windows, constant shift at the ends."""
    D = grid[-1]
    if n_windows <= 0:
        return np.array([0.0, D]), np.array([0.0, 0.0])
    offsets = np.arange(-max_shift, max_shift + step / 2, step)
    edges = np.linspace(0, D, n_windows + 1)
    knots = (edges[:-1] + edges[1:]) / 2
    shifts = np.array([_best_shift(grid, v_ref, v_tgt, a, b, offsets)
                       for a, b in zip(edges[:-1], edges[1:])])
    return np.r_[0.0, knots, D], np.r_[shifts[0], shifts, shifts[-1]]

def corner_align(grid, v_ref, v_tgt, max_shift, local_shift, pin_ends=True, step=0.5):
    """Corner-anchored slide.
    1. Find corners (speed minima) in the reference.
    2. Coarse shift per corner (+-max_shift) using braking zone + apex + exit.
    3. Robust linear trend through those shifts = global offset + scale error.
    4. Refine each corner within +-local_shift of the trend.
    pin_ends=True: shift is 0 at the start/finish line (FastF1 slices both laps
    at the timing line), so the rubberband is fixed at both ends and slides at
    every corner in between."""
    D = grid[-1]
    peaks, _ = find_peaks(-v_ref, prominence=25, distance=80)
    if len(peaks) < 3:
        return window_align(grid, v_ref, v_tgt, 4, max_shift, step)
    centers = grid[peaks]
    lo_of = lambda c: c - 220.0          # braking zone
    hi_of = lambda c: c + 150.0          # exit
    coarse_offs = np.arange(-max_shift, max_shift + step / 2, step)
    coarse = np.array([_best_shift(grid, v_ref, v_tgt, lo_of(c), hi_of(c), coarse_offs)
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
    fine = np.array([_best_shift(grid, v_ref, v_tgt, lo_of(c), hi_of(c), t + local_offs)
                     for c, t in zip(centers, trend)])
    if pin_ends:
        return np.r_[0.0, centers, D], np.r_[0.0, fine, 0.0]
    return np.r_[0.0, centers, D], np.r_[b, fine, k * D + b]

def hifi_delta_v2(ref, tgt, mode=ALIGN_MODE, rubberband=RUBBERBAND, pin_ends=PIN_ENDS,
                  smooth_m=None):
    if smooth_m is None: smooth_m = SMOOTH_M
    D = ref['dist'][-1]
    grid = np.r_[np.arange(0.0, D, 1.0), D]

    # 1. Pace integration
    t_ref = pace_time(ref['dist'], ref['speed'], ref['lap_time'])
    t_tgt = pace_time(tgt['dist'], tgt['speed'], tgt['lap_time'])

    # 2. Stretch
    scale = D / tgt['dist'][-1]
    d_t = tgt['dist'] * scale
    length_offset = abs(D - tgt['dist'][-1])

    # 3. Slide
    v_r = np.interp(grid, ref['dist'], ref['speed'])
    v_t = np.interp(grid, d_t, tgt['speed'])
    if mode == 'corners':
        knots, shifts = corner_align(grid, v_r, v_t, MAX_SHIFT_M, LOCAL_SHIFT_M, pin_ends)
    elif mode == 'windows':
        knots, shifts = window_align(grid, v_r, v_t, ALIGN_WINDOWS, WINDOW_SHIFT_M)
    else:
        knots, shifts = np.array([0.0, D]), np.array([0.0, 0.0])
    applied = np.interp(d_t, knots, shifts)
    d_al = np.maximum.accumulate(d_t + applied)

    tr = interp_extrap(grid, ref['dist'], t_ref, ref['speed'][0], ref['speed'][-1])
    tt = interp_extrap(grid, d_al, t_tgt, tgt['speed'][0], tgt['speed'][-1])
    raw = tt - tr
    raw = raw - raw[0]
    unsmoothed = raw
    if smooth_m and smooth_m > 1:                 # grid is 1 m, so N metres = N samples
        k = int(smooth_m) | 1
        pad = np.pad(raw, k // 2, mode='edge')
        raw = np.convolve(pad, np.ones(k) / k, mode='valid')

    # 4. Rubberband refit to official gaps
    gap = tgt['lap_time'] - ref['lap_time']
    pins = [(0.0, 0.0)]
    if rubberband:
        for g in ('S1', 'S2'):
            if g in ref['gates'] and g in tgt['gates']:
                x = ref['gates'][g][0]
                if 0.0 < x < D:
                    pins.append((x, tgt['gates'][g][1] - ref['gates'][g][1]))
    pins.append((D, gap))
    pins.sort()
    px = np.array([p[0] for p in pins]); py = np.array([p[1] for p in pins])
    resid = py - np.interp(px, grid, raw)
    delta = raw + np.interp(grid, px, resid)

    # Metrics
    integrity = calculate_integrity_score(
        length_offset, global_shift_m(ref, d_t, tgt['speed'], D))
    fidelity = calculate_fidelity(
        scale_factor=scale, local_shifts=applied, track_length=D,
        raw_delta=unsmoothed, smooth_delta=raw, lap_time=ref['lap_time'],
        endpoint_correction=float(np.max(np.abs(resid))))

    info = {'pins': list(zip(px, py)), 'knots': knots, 'shifts': shifts}
    return grid, delta, integrity, fidelity, info


# ══════════════════════════════════════════════════════════════════
# ADAPTER (ours): lap-comparison trace -> v2 trace -> delta on ref['dist']
# ══════════════════════════════════════════════════════════════════
def _v2_trace(tr):
    """Lap-comparison traces carry speed in m/s and optional 'gates'; v2 wants km/h and strictly
    increasing distance (same mask as the notebook's get_trace)."""
    d = np.asarray(tr['dist'], float); v = np.asarray(tr['speed'], float) * 3.6
    keep = np.r_[True, np.diff(d) > 0]
    return {'driver': tr.get('driver'), 'dist': d[keep], 'speed': v[keep], 'lap_time': float(tr['lap_time']),
            'gates': tr.get('gates', {})}


def calculate_delta(ref_trace, tgt_trace, return_info=False):
    ref, tgt = _v2_trace(ref_trace), _v2_trace(tgt_trace)
    grid, delta, integrity, fidelity, info = hifi_delta_v2(ref, tgt)
    out = np.interp(np.asarray(ref_trace['dist'], float), grid, delta)
    if return_info:
        return ref_trace['dist'], out, dict(integrity=integrity, fidelity=fidelity, **info)
    return ref_trace['dist'], out
