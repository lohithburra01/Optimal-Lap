# f1_style_extract.py
# Extracts 8 racing-line style parameters from FastF1 telemetry.
# Output ranges match the F1 Track Visualizer standalone addon's slider ranges.

import json
import math
import os
from datetime import datetime, timezone

import numpy as np


STYLE_PARAM_KEYS = (
    "apex_phase", "apex_tightness", "entry_width", "exit_width",
    "vu_shape", "straight_bias", "smoothness", "lr_asymmetry",
)


def _default_params():
    return {
        "apex_phase":     0.0,
        "apex_tightness": 0.5,
        "entry_width":    0.0,
        "exit_width":     0.0,
        "vu_shape":       0.0,
        "straight_bias":  0.0,
        "smoothness":     0.5,
        "lr_asymmetry":   0.0,
    }


def _detect_corners(coords, kappa_hi_frac=0.25, kappa_lo_frac=0.08, min_len=6):
    """Hysteresis corner detection on a closed 2D loop. Returns rolled coords/kappa
    so station 0 sits on a straight."""
    from scipy.ndimage import gaussian_filter1d
    n = len(coords)

    tang = np.zeros((n, 2))
    for i in range(n):
        d = coords[(i + 3) % n] - coords[(i - 3) % n]
        nm = np.linalg.norm(d)
        tang[i] = d / nm if nm > 1e-8 else np.array([1.0, 0.0])

    kappa = np.zeros(n)
    for i in range(n):
        t1, t2 = tang[i], tang[(i + 1) % n]
        cross = t1[0] * t2[1] - t1[1] * t2[0]
        dot = float(np.clip(np.dot(t1, t2), -1.0, 1.0))
        kappa[i] = math.copysign(math.acos(dot), cross)

    ks = gaussian_filter1d(np.tile(kappa, 3), sigma=5.0)[n:2 * n]
    ks_abs = np.abs(ks)
    kmax = float(ks_abs.max())
    if kmax < 1e-6:
        return [], ks_abs, ks, 0

    hi = kappa_hi_frac * kmax
    lo = kappa_lo_frac * kmax
    above_hi = ks_abs > hi
    above_lo = ks_abs > lo

    straights = np.where(~above_lo)[0]
    if len(straights) == 0:
        return [], ks_abs, ks, 0
    roll = int(straights[0])
    above_hi_r = np.roll(above_hi, -roll)
    above_lo_r = np.roll(above_lo, -roll)
    ks_abs_r = np.roll(ks_abs, -roll)
    ks_r = np.roll(ks, -roll)

    corners = []
    i = 0
    while i < n:
        if above_hi_r[i]:
            core_start = i
            while i < n and above_hi_r[i]:
                i += 1
            core_end = i - 1
            entry = core_start
            while entry > 0 and above_lo_r[entry - 1]:
                entry -= 1
            exit_ = core_end
            while exit_ < n - 1 and above_lo_r[exit_ + 1]:
                exit_ += 1
            L = exit_ - entry + 1
            if L >= min_len:
                apex = core_start + int(np.argmax(ks_abs_r[core_start:core_end + 1]))
                corners.append({
                    "entry": entry, "apex": apex, "exit": exit_, "L": L,
                    "kappa_sign": int(math.copysign(1, ks_r[apex])),
                })
        else:
            i += 1

    return corners, ks_abs_r, ks_r, roll


def extract_style_params(x, y, speed=None):
    """
    Extract 8 driver-style parameters from telemetry.

    Args:
        x, y:  1D arrays of XY lap positions. Any unit (FastF1 defaults to 1/10 m).
        speed: optional 1D array of speed. Improves apex_phase (uses speed-min
               phase vs curvature-peak phase when available).

    Returns:
        (params, corners) tuple.
        params:  dict with 8 floats (lap-wide aggregates) in the standalone
                 addon's slider ranges. Used as fallback when per-corner data
                 isn't consumable (e.g. corner count mismatch).
        corners: list of per-corner dicts in lap order, each with apex_phase,
                 apex_tightness, vu_shape, smoothness, kappa_sign, length. The
                 visualizer applies these per-corner instead of the aggregates.
        entry_width, exit_width, straight_bias default to 0.0 — they need a
        centerline reference unavailable from telemetry alone.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 50:
        return _default_params(), []

    coords = np.column_stack([x, y])
    n = len(coords)
    corners, ks_abs_r, _ks_r, roll = _detect_corners(coords)
    if not corners:
        return _default_params(), []

    coords_r = np.column_stack([np.roll(x, -roll), np.roll(y, -roll)])
    speed_r = None
    if speed is not None:
        speed_arr = np.asarray(speed, dtype=float)
        if len(speed_arr) == n:
            speed_r = np.roll(speed_arr, -roll)

    kappa_max = float(ks_abs_r.max())
    features = []
    for c in corners:
        e, a, x_, L = c["entry"], c["apex"], c["exit"], c["L"]
        ks = c["kappa_sign"]

        # apex_phase: position of speed-min in corner, mapped [0,1] → [-1,+1]
        if speed_r is not None:
            rel = int(np.argmin(speed_r[e:x_ + 1]))
            phi = rel / max(L - 1, 1)
        else:
            phi = (a - e) / max(L - 1, 1)
        apex_phase = float(np.clip((phi - 0.5) / 0.25, -1.0, 1.0))

        # apex_tightness: peak curvature dominance
        peak = float(ks_abs_r[a])
        apex_tightness = float(np.clip(peak / (0.8 * kappa_max), 0.0, 1.0))

        # vu_shape: peak width at half-max / corner length; narrow = V, broad = U
        hm = peak * 0.5
        left = 0
        for k in range(a, e - 1, -1):
            if ks_abs_r[k] < hm: break
            left += 1
        right = 0
        for k in range(a, x_ + 1):
            if ks_abs_r[k] < hm: break
            right += 1
        peak_w = (left + right) / max(L, 1)
        vu_shape = float(np.clip((peak_w - 0.30) / 0.30, -1.0, 1.0))

        # smoothness: inverse normalized 2nd-difference (jerk proxy)
        seg = coords_r[e:x_ + 1]
        if len(seg) >= 4:
            d2 = np.diff(seg, n=2, axis=0)
            jerk = float(np.linalg.norm(d2, axis=1).mean())
            avg_seg = float(np.linalg.norm(np.diff(seg, axis=0), axis=1).mean())
            if avg_seg > 1e-8:
                jerk_norm = jerk / avg_seg
                smoothness = float(np.clip(1.0 - jerk_norm / 0.5, 0.0, 1.0))
            else:
                smoothness = 0.5
        else:
            smoothness = 0.5

        features.append({
            "ks": ks, "L": L,
            "apex_phase": apex_phase,
            "apex_tightness": apex_tightness,
            "vu_shape": vu_shape,
            "smoothness": smoothness,
        })

    w = np.array([f["L"] for f in features], dtype=float)
    w /= w.sum()

    def wmean(k):
        return float(np.sum(np.array([f[k] for f in features]) * w))

    params = _default_params()
    params["apex_phase"]     = wmean("apex_phase")
    params["apex_tightness"] = wmean("apex_tightness")
    params["vu_shape"]       = wmean("vu_shape")
    params["smoothness"]     = wmean("smoothness")

    lefts  = [f["apex_tightness"] for f in features if f["ks"] > 0]
    rights = [f["apex_tightness"] for f in features if f["ks"] < 0]
    if lefts and rights:
        lm, rm = float(np.mean(lefts)), float(np.mean(rights))
        denom = max(lm + rm, 1e-6)
        params["lr_asymmetry"] = float(np.clip((lm - rm) / denom, -1.0, 1.0))

    corners_out = [
        {
            "apex_phase":     float(f["apex_phase"]),
            "apex_tightness": float(f["apex_tightness"]),
            "vu_shape":       float(f["vu_shape"]),
            "smoothness":     float(f["smoothness"]),
            "kappa_sign":     int(f["ks"]),
            "length":         int(f["L"]),
        }
        for f in features
    ]

    return params, corners_out


def write_style_json(params, path, meta=None, corners=None):
    """Write style params to JSON, creating parent dirs as needed. Returns path."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    meta = meta or {}
    payload = {
        "version": 2,
        "source": {
            "driver":       meta.get("driver",     ""),
            "season":       meta.get("season",     ""),
            "grand_prix":   meta.get("grand_prix", ""),
            "session":      meta.get("session",    ""),
            "lap":          meta.get("lap",        ""),
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        },
        "style_params": {k: float(params.get(k, 0.0)) for k in STYLE_PARAM_KEYS},
        "corners": list(corners) if corners else [],
        "notes": (
            "style_params are lap-wide aggregates kept as fallback. The "
            "consumer should prefer corners[] (per-corner apex_phase/"
            "apex_tightness/vu_shape/smoothness in lap order) when its own "
            "corner count matches len(corners). entry_width, exit_width and "
            "straight_bias default to 0 when no centerline is available — "
            "the standalone addon refines them."
        ),
    }
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    return path
