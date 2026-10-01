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
    # QUARANTINED 2026-09-30: Baku entry came from the rejected GPT run (needs
    # the GPT-only --drive-ccw engine flag). Kept commented, not deleted.
    # "baku": dict(
    #     outline=_p("F1_Pipeline_Assets/tracks/azerbaijan_grand_prix_outline.json"),
    #     csv25=_p("F1_Pipeline_Assets/exports/reference_2025_baku_q.csv"),
    #     csv26=_p("F1_Pipeline_Assets/exports/reference_2026_baku_fp1.csv"),
    #     kind26="FP1", country="Azerbaijan", circuit="Baku",
    #     altitude_m=-20.0, length_m=6003.0, drive_ccw=True,
    # ),
    "canada": dict(
        outline=_p("F1_Pipeline_Assets/tracks/canadian_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_canada_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_canada_q.csv"),
        kind26="Q", country="Canada", altitude_m=13.0, length_m=4361.0,
    ),
    "catalunya": dict(
        outline=_p("F1_Pipeline_Assets/tracks/catalunya_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_spain_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_spain_q.csv"),
        kind26="Q", country="Spain", altitude_m=130.0, length_m=4657.0,
    ),
    "austria": dict(
        outline=_p("F1_Pipeline_Assets/tracks/austrian_grand_prix.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_austria_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_austria_fp1.csv"),
        kind26="FP1", country="Austria", altitude_m=680.0, length_m=4318.0,
    ),
    "silverstone": dict(
        outline=_p("F1_Pipeline_Assets/tracks/british_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_silverstone_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_silverstone_fp1.csv"),
        kind26="FP1", country="Great Britain", altitude_m=150.0, length_m=5891.0,
    ),
    "miami": dict(
        outline=None,
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_miami_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_miami_q.csv"),
        kind26="Q", country="United States", altitude_m=2.0, length_m=5412.0,
    ),
    "china": dict(
        outline=None,
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_china_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_china_q.csv"),
        kind26="Q", country="China", altitude_m=4.0, length_m=5451.0,
    ),
    "spa": dict(
        outline=_p("F1_Pipeline_Assets/tracks/belgian_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_spa_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_spa_q.csv"),
        kind26="Q", country="Belgium", altitude_m=420.0, length_m=7004.0,
    ),
    "hungary": dict(
        outline=_p("F1_Pipeline_Assets/tracks/hungarian_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_hungary_q.csv"),
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_hungary_q.csv"),
        kind26="Q", country="Hungary", altitude_m=250.0, length_m=4381.0,
    ),
    "zandvoort": dict(
        outline=_p("F1_Pipeline_Assets/tracks/dutch_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_zandvoort_q.csv"),
        # real 2026 Q fetched 2026-09-04: lap 71.163 s, integrated 4248 m vs
        # 4259 official (-0.3%). 7th anchor pair for the transfer.
        csv26=_p("F1_Pipeline_Assets/exports/reference_2026_zandvoort_q.csv"),
        # altitude from the measured OpenF1 z-channel (51.0-59.2 m ASL, dunes),
        # not sea level: rho_isa 1.2244 -> 1.2185.
        kind26="Q", country="Netherlands", altitude_m=55.0, length_m=4259.0,
        # The only meaningfully banked corners on the calendar (2021 rebuild).
        # deg = EFFECTIVE angle fitted by cache/_apply_banking.py --fit, NOT the
        # surveyed angle (~19 / ~18 deg) — see that script's docstring for why
        # the surveyed value saturates the closed form at MU_LAT=1.95.
        banking=[
            dict(name="T3 Hugenholtz", s_frac=0.185, half_width_frac=0.020, deg=8.62),
            dict(name="T14 Arie Luyendyk", s_frac=0.810, half_width_frac=0.022, deg=0.45),
        ],
    ),
    "monza": dict(
        outline=_p("F1_Pipeline_Assets/tracks/italian_grand_prix_outline.json"),
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_monza_q.csv"),
        csv26=None,
        kind26=None, country="Italy",
        # Italy hosts TWO GPs in the OpenF1 country index (Imola 2025 Emilia-
        # Romagna + Monza): every session lookup MUST filter on this or it
        # silently picks the earlier Imola meeting.
        circuit="Monza",
        # placeholder ASL (Parco di Monza ~162 m); re-pin from the measured
        # OpenF1 z-channel after cache/_fetch_elevation.py, as Zandvoort did.
        altitude_m=162.0, length_m=5793.0,
    ),
    "bahrain": dict(
        outline=_p("F1_Pipeline_Assets/tracks/bahrain_grand_prix_outline.json"),
        # 2025 Q, PIA 1:29.841 (the real pole), 5389 m integrated vs 5412 (-0.4%),
        # fetched 2026-10-01 - long after the 2025-04-12 session.
        csv25=_p("F1_Pipeline_Assets/exports/reference_2025_bahrain_q.csv"),
        csv26=None,
        kind26=None, country="Bahrain",
        # 2026's "Bahrain GP" meeting is held at Sepang (circuit "Kuala Lumpur"):
        # every 2026 lookup MUST filter on this or it picks the Sepang weekend.
        circuit="Sakhir",
        # placeholder ASL; re-pin from the measured OpenF1 z-channel.
        altitude_m=7.0, length_m=5412.0,
        # SVG Bahrain_International_Circuit--Grand_Prix_Layout_with_DRS.svg @ 15 m, min R 9.
        # Its T10 is drawn as a sharp V; inset 1.2 is the smallest that keeps the line
        # on-track there (0/2682, worst 0.29 m) and gave the best corner fit of all
        # candidates (worst corner 12 km/h vs r(v25) targets, corr 0.975).
        inset=1.2,
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
                  min_sep_m: float = 80.0,
                  with_prominence: bool = False):
    """Local speed minima (corners) as [(s_m, v_kmh)], ascending s.

    With with_prominence=True, returns [(s_m, v_kmh, prominence_kmh)].
    Endpoints are not detected (fine: start/finish sits on a straight).
    """
    ds = float(np.median(np.diff(s)))
    dist = max(1, int(round(min_sep_m / max(ds, 1e-6))))
    idx, props = find_peaks(-v, prominence=prominence_kmh, distance=dist)
    if with_prominence:
        return [(float(s[i]), float(v[i]), float(p))
                for i, p in zip(idx, props["prominences"])]
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


def align_pair(s_a: np.ndarray, v_a: np.ndarray,
               s_b: np.ndarray, v_b: np.ndarray,
               length_m: float, n: int = 2048
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Align two laps of the SAME circuit onto one distance grid.

    Handles the two artefacts of mixing fetcher eras (FastF1 vs OpenF1):
      1. integration drift  -> each trace is normalized by its OWN total
      2. start-line offset  -> best circular shift of b via FFT cross-correlation

    Returns (s_grid [m, 0..length_m), v_a_grid, v_b_grid_aligned, shift_frac).
    """
    fa = (s_a - s_a[0]) / (s_a[-1] - s_a[0])
    fb = (s_b - s_b[0]) / (s_b[-1] - s_b[0])
    grid = np.arange(n) / n
    va = np.interp(grid, fa, v_a)
    vb = np.interp(grid, fb, v_b)
    a = va - va.mean()
    b = vb - vb.mean()
    corr = np.fft.irfft(np.fft.rfft(a) * np.conj(np.fft.rfft(b)), n=n)
    k = int(np.argmax(corr))                 # vb rolled forward by k matches va
    vb_al = np.roll(vb, k)
    shift_frac = k / n
    if shift_frac > 0.5:
        shift_frac -= 1.0
    return grid * length_m, va, vb_al, shift_frac


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
