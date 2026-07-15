"""Track registry + shared analysis utilities for the pre-FP1 2026 calibration.

Single source of truth for: which reference CSVs / outlines belong to which
track, per-track altitude and official length, and the pure numeric helpers
(corner detection, 2025<->2026 corner pairing, monotone ratio fit, ISA air
density) used by _transfer_2026.py / _predict_track.py / _autofit_2026.py /
_backtest_2026.py.

All paths are absolute, anchored at the repo root (parent of cache/), so the
scripts work regardless of caller cwd.

Spec: docs/2026-07-15-prefp1-universal-calibration-design.md
"""
from __future__ import annotations

import os

import numpy as np
from scipy.signal import find_peaks

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _p(rel: str) -> str:
    return os.path.join(REPO_ROOT, rel)


# kind26: how the 2026 reference lap was set. "Q" laps anchor fits;
# "FP1" laps are non-push -> validation only, never fitted.
TRACKS: dict[str, dict] = {
    "canada": dict(
        outline=_p("F1_Pipeline_Assets/tracks/canadian_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_canada_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_canada_q.csv"),
        kind26="Q", altitude_m=13.0, length_m=4361.0,
    ),
    "catalunya": dict(
        outline=_p("F1_Pipeline_Assets/tracks/catalunya_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_spain_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_spain_q.csv"),
        kind26="Q", altitude_m=130.0, length_m=4657.0,
    ),
    "austria": dict(
        outline=_p("F1_Pipeline_Assets/tracks/austrian_grand_prix.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_austria_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_austria_fp1.csv"),
        kind26="FP1", altitude_m=680.0, length_m=4318.0,
    ),
    "silverstone": dict(
        outline=_p("F1_Pipeline_Assets/tracks/british_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_silverstone_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_silverstone_fp1.csv"),
        kind26="FP1", altitude_m=150.0, length_m=5891.0,
    ),
    "miami": dict(
        outline=None,
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_miami_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_miami_q.csv"),
        kind26="Q", altitude_m=2.0, length_m=5412.0,
    ),
    "china": dict(
        outline=None,
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_china_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_china_q.csv"),
        kind26="Q", altitude_m=4.0, length_m=5451.0,
    ),
    "spa": dict(
        outline=_p("F1_Pipeline_Assets/tracks/belgian_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_spa_q.csv"),
        csv26=None,
        kind26=None, altitude_m=420.0, length_m=7004.0,
    ),
}


def rho_isa(altitude_m: float) -> float:
    """ISA air density [kg/m^3] at altitude (troposphere model)."""
    return 1.225 * (1.0 - 2.25577e-5 * altitude_m) ** 4.2561


def load_ref(path: str) -> tuple[np.ndarray, np.ndarray, float]:
    """Load a reference lap CSV -> (s_m, v_kmh, t_lap_s), distance monotone.

    Schema (both fetchers): frame,time_s,distance,speed,throttle,brake,gear,rpm,ers_deploy
    """
    d = np.genfromtxt(path, delimiter=",", names=True)
    t = np.asarray(d["time_s"], dtype=float)
    s = np.asarray(d["distance"], dtype=float)
    v = np.asarray(d["speed"], dtype=float)
    ok = np.isfinite(t) & np.isfinite(s) & np.isfinite(v)
    t, s, v = t[ok], s[ok], v[ok]
    order = np.argsort(s, kind="stable")
    s, v, t = s[order], v[order], t[order]
    keep = np.concatenate(([True], np.diff(s) > 1e-9))  # strictly increasing s
    s, v, t = s[keep], v[keep], t[keep]
    t_lap = float(np.max(t) - np.min(t))
    return s, v, t_lap


def corner_minima(s: np.ndarray, v: np.ndarray,
                  prominence_kmh: float = 8.0,
                  min_sep_m: float = 80.0) -> list[tuple[float, float]]:
    """Local speed minima (corners) as [(s_m, v_kmh)], ascending s.

    Endpoints are not detected (fine: start/finish sits on a straight).
    """
    ds = float(np.median(np.diff(s)))
    dist = max(1, int(round(min_sep_m / max(ds, 1e-6))))
    idx, _ = find_peaks(-v, prominence=prominence_kmh, distance=dist)
    return [(float(s[i]), float(v[i])) for i in idx]


def pair_minima(m25: list[tuple[float, float]],
                m26: list[tuple[float, float]],
                s_total: float,
                tol_frac: float = 0.015) -> tuple[list[tuple[float, float, float, float]], float]:
    """One-to-one greedy pairing of corner minima by distance along the lap.

    Returns ([(s25, v25, s26, v26), ...] sorted by s25, pairing_rate) where
    pairing_rate = matched / max(len(m25), len(m26)).
    """
    if not m25 or not m26:
        return [], 0.0
    tol = tol_frac * s_total
    cands = sorted(
        (abs(a[0] - b[0]), i, j)
        for i, a in enumerate(m25) for j, b in enumerate(m26)
        if abs(a[0] - b[0]) <= tol
    )
    used25: set[int] = set()
    used26: set[int] = set()
    pairs = []
    for _, i, j in cands:
        if i in used25 or j in used26:
            continue
        used25.add(i)
        used26.add(j)
        pairs.append((m25[i][0], m25[i][1], m26[j][0], m26[j][1]))
    pairs.sort(key=lambda p: p[0])
    rate = len(pairs) / max(len(m25), len(m26))
    return pairs, rate


def resample_speed(s: np.ndarray, v: np.ndarray, s_grid: np.ndarray) -> np.ndarray:
    """Speed linearly interpolated onto s_grid (for cross-trace correlation)."""
    return np.interp(s_grid, s, v)


def pava_nonincreasing(v: np.ndarray, r: np.ndarray, w: np.ndarray,
                       knots: np.ndarray) -> np.ndarray:
    """Weighted non-increasing fit of ratio r(v), evaluated at `knots`.

    Points are binned to their nearest knot (weighted means), then
    pool-adjacent-violators enforces r monotone non-increasing in v.
    Knots with no data are filled by interpolation from fitted neighbours
    (flat extrapolation at the ends).
    """
    v = np.asarray(v, float)
    r = np.asarray(r, float)
    w = np.asarray(w, float)
    knots = np.asarray(knots, float)
    nearest = np.argmin(np.abs(v[:, None] - knots[None, :]), axis=1)

    kv, ky, kw = [], [], []
    for k in range(len(knots)):
        m = nearest == k
        if np.any(m) and np.sum(w[m]) > 0:
            kv.append(knots[k])
            ky.append(float(np.average(r[m], weights=w[m])))
            kw.append(float(np.sum(w[m])))
    if not kv:
        raise ValueError("pava_nonincreasing: no data points")

    # PAVA for non-increasing: negate -> non-decreasing isotonic -> negate.
    y = [-x for x in ky]
    wt = list(kw)
    blocks = [[i] for i in range(len(y))]
    vals = y[:]
    i = 0
    while i < len(vals) - 1:
        if vals[i] > vals[i + 1] + 1e-15:
            merged_w = wt[i] + wt[i + 1]
            merged_v = (vals[i] * wt[i] + vals[i + 1] * wt[i + 1]) / merged_w
            vals[i:i + 2] = [merged_v]
            wt[i:i + 2] = [merged_w]
            blocks[i:i + 2] = [blocks[i] + blocks[i + 1]]
            i = max(i - 1, 0)
        else:
            i += 1
    fitted = np.empty(len(y))
    for bval, blk in zip(vals, blocks):
        for idx in blk:
            fitted[idx] = -bval

    return np.interp(knots, np.asarray(kv), fitted)
