"""
raceline_video.py

Spatial path:  IQP min-curvature ideal racing line, computed once from the
               track outline JSON.
Animation:     Plays VER's real telemetry (time / distance / speed) on top
               of that path, like the formulytics lap-comparison script —
               just with one driver, on the optimal line.

Inputs:
  --outline       <track>_outline.json  (from extract_track_outline.py)
  --telemetry-csv VER_telemetry.csv     (REQUIRED; columns: frame,time_s,distance,speed,...)

Output: <track>_optimal_lap.mp4

Requires:
  pip install numpy scipy opencv-python Pillow trajectory-planning-helpers cvxopt
"""

import argparse
import csv
import json
import math
import os
import sys
import time
import types

# trajectory_planning_helpers' __init__ eagerly imports opt_min_curv (needs
# quadprog). We use cvxopt for the QP, so stub quadprog out.
if 'quadprog' not in sys.modules:
    _stub = types.ModuleType('quadprog')
    _stub.solve_qp = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("quadprog stub"))
    sys.modules['quadprog'] = _stub

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
from scipy.interpolate import splprep, splev
from scipy.ndimage import gaussian_filter1d
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import spsolve
from cvxopt import matrix as cvx_matrix, solvers as cvx_solvers
cvx_solvers.options['show_progress'] = False


# =============================================================
# Constants
# =============================================================

# Corridor / IQP — fast solve (~5-8 s per iter at N=800).
N_CORRIDOR_POINTS = 800       # IQP corridor density (heavily smoothed, INSET applied)
N_VISUAL_POINTS   = 4000      # visual edges density (lightly smoothed, NO inset → wider than IQP corridor)
CORR_SMOOTH_S     = 30.0      # heavy smoothing for IQP corridor
VISUAL_SMOOTH_S   = 10.0      # light smoothing for rendered edges (close to raw shape)
INSET_M           = 1.5       # IQP-corridor inset on each side
VISUAL_OUTSET_M   = 2.5       # push rendered edges outward this far → visual always wider than IQP corridor
KAPPA_BOUND       = 0.40
VEH_WIDTH         = 1.9
RACELINE_STEPSIZE = 2.0
IQP_ITERS         = 5
ALPHA_TOL         = 0.10
SAFETY_MARGIN     = 0.15
IQP_OUTPUT_SMOOTH = 1.0       # gaussian sigma on cur_ref before final splprep

# Render
WIDTH, HEIGHT     = 1080, 1920
DEFAULT_FPS       = 30
DEFAULT_ZOOM      = 15.0
DEFAULT_TRAIL     = 180
TRACK_FILL        = (40, 40, 40)
TRACK_EDGE        = (255, 255, 255)
EDGE_THICKNESS    = 4
RACELINE_COLOR    = (90, 90, 90)
TRAIL_THICKNESS   = 18
DOT_COLOR         = (255, 255, 255)
DOT_RADIUS        = 28
WATERMARK_TEXT    = "@formulytics"

# Kerbs — solid white trapezoidal attachments OUTSIDE each corner edge.
# Drawn beyond the white edge line, in the runoff (outer) or infield (inner).
KERB_KAPPA_THRESH = 0.005    # |kappa| > this = corner zone (radius < 200m)
KERB_DEPTH_M      = 1.5      # how far OUT of the track edge the kerb extends
KERB_ZONE_DILATE  = 10       # extend each corner zone by this many polyline pts (smooth transitions)
KERB_TAPER_M      = 0.8      # absolute arc length of the trapezium taper at each end (metres) — does NOT scale with kerb length
KERB_BLOCK_M      = 0.8      # length of each white block in the middle section
KERB_GAP_M        = 0.8      # length of each empty (hole) section between blocks
KERB_COLOR        = (240, 240, 240)    # solid white BGR

# Layout — Instagram Reels + YouTube Shorts safe zones.
TITLE_LINE_1      = "THE OPTIMAL LAP"
TITLE_Y_1         = 320
TITLE_Y_2         = 400
CAMERA_Y_FRAC     = 0.45
SPEED_Y           = 1200
KMH_Y_OFFSET      = 78
LAP_Y             = 1320
WATERMARK_Y       = 1410
MAP_SIZE          = 240
MAP_Y_TOP         = 460
MAP_X_RIGHT_INSET = 40


# =============================================================
# Stage 1: Outline → corridor + widths
# =============================================================

def signed_area(poly):
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def smooth_resample_loop(poly, n_out, smooth_s):
    """Smoothing periodic spline + uniform arc-length resample."""
    poly = np.asarray(poly, dtype=float)
    if not np.allclose(poly[0], poly[-1]):
        poly_closed = np.vstack([poly, poly[0]])
    else:
        poly_closed = poly
    seg = np.linalg.norm(np.diff(poly_closed, axis=0), axis=1)
    keep = np.concatenate([[True], seg > 1e-6])
    poly_closed = poly_closed[keep]
    if not np.allclose(poly_closed[0], poly_closed[-1]):
        poly_closed = np.vstack([poly_closed, poly_closed[0]])
    seg = np.linalg.norm(np.diff(poly_closed, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    u_norm = cum / cum[-1]
    tck, _ = splprep([poly_closed[:, 0], poly_closed[:, 1]],
                     u=u_norm, s=smooth_s, per=True, k=3)
    u_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    rx, ry = splev(u_new, tck)
    return np.column_stack([rx, ry])


def offset_loop_outward(poly, dist, is_outer):
    """Push every point of a CCW closed polyline AWAY FROM THE ROAD by `dist`
    metres. For the track-outer edge, that means along the right-normal
    (outward of the outer loop). For the track-inner edge, that means along
    the left-normal (toward the infield, i.e., inward of the inner loop).
    Both operations enlarge the visual road corridor."""
    poly = np.asarray(poly, dtype=float)
    n = len(poly)
    out = np.zeros_like(poly)
    for i in range(n):
        d = poly[(i + 3) % n] - poly[(i - 3) % n]
        nm = np.linalg.norm(d)
        if nm < 1e-8:
            out[i] = poly[i]
            continue
        t = d / nm
        if is_outer:
            normal = np.array([ t[1], -t[0]])   # right normal -> outward of CCW outer loop
        else:
            normal = np.array([-t[1],  t[0]])   # left normal  -> into infield (CCW inner)
        out[i] = poly[i] + dist * normal
    return out


def compute_kerb_polygons(poly, is_outer):
    """Build closed white trapezoidal polygons sitting OUTSIDE the track edge
    along each corner zone. Inner side of each polygon hugs the track edge;
    outer side is the same edge offset OUTWARD (away from road) by
    KERB_DEPTH_M, with a small taper at each end so the polygon looks like a
    trapezium fitted around the corner from outside.

    Returns a list of np.ndarray closed polygons (each shape (M,2)), suitable
    for cv2.fillPoly."""
    poly = np.asarray(poly, dtype=float)
    n = len(poly)
    if n < 6:
        return []

    # Discrete curvature with 6-point span.
    kappa = np.zeros(n)
    for i in range(n):
        a = poly[(i - 3) % n]
        b = poly[i]
        c = poly[(i + 3) % n]
        ab = b - a
        bc = c - b
        cross = ab[0] * bc[1] - ab[1] * bc[0]
        nab = np.linalg.norm(ab)
        nbc = np.linalg.norm(bc)
        nac = np.linalg.norm(c - a)
        denom = nab * nbc * nac
        kappa[i] = 0.0 if denom < 1e-9 else 2.0 * cross / denom

    abs_k = gaussian_filter1d(np.tile(np.abs(kappa), 3), sigma=10)[n:2 * n]
    in_corner = abs_k > KERB_KAPPA_THRESH

    # Dilate corner zones (extend by KERB_ZONE_DILATE points each side) for
    # smooth transitions where curvature is just below threshold but the
    # corner is still in progress.
    if KERB_ZONE_DILATE > 0:
        k = 2 * KERB_ZONE_DILATE + 1
        kernel = np.ones(k, dtype=int)
        dilated = np.convolve(np.tile(in_corner.astype(int), 3), kernel, mode='same') > 0
        in_corner = dilated[n:2 * n]

    if not in_corner.any():
        return []
    if in_corner.all():
        return []  # whole track is one corner zone — no kerbs (shouldn't happen)

    # Shift array so a non-corner index sits at 0; eliminates wrap-around runs.
    shift = int(np.where(~in_corner)[0][0])
    poly_s = np.roll(poly, -shift, axis=0)
    in_corner_s = np.roll(in_corner, -shift)

    # Find contiguous corner runs in the shifted array.
    runs = []
    i = 0
    while i < n:
        if in_corner_s[i]:
            j = i
            while j < n and in_corner_s[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1

    polygons = []
    for start, end in runs:
        L = end - start
        if L < 3:
            continue
        edge_pts = poly_s[start:end]

        # Outward normals (away from road) along this zone.
        normals = np.zeros_like(edge_pts)
        for k_local in range(L):
            i_poly = start + k_local
            d = poly_s[(i_poly + 3) % n] - poly_s[(i_poly - 3) % n]
            nm = np.linalg.norm(d)
            if nm < 1e-8:
                normals[k_local] = np.array([1.0, 0.0])
                continue
            t = d / nm
            if is_outer:
                normals[k_local] = np.array([ t[1], -t[0]])    # right normal of CCW outer = away from road
            else:
                normals[k_local] = np.array([-t[1],  t[0]])    # left normal of CCW inner = into infield = away from road

        # Per-point arc length within this zone.
        seg_in_zone = np.linalg.norm(np.diff(edge_pts, axis=0), axis=1)
        arc_in_zone = np.concatenate([[0.0], np.cumsum(seg_in_zone)])  # length L
        zone_arc_total = float(arc_in_zone[-1])

        def make_segment_polygon(idx_lo, idx_hi, depth_fn):
            """Build a closed kerb polygon from edge index lo..hi inclusive,
            using `depth_fn(arc)` to set the outward kerb depth at each pt."""
            if idx_hi <= idx_lo:
                return None
            seg_pts = edge_pts[idx_lo:idx_hi + 1]
            seg_norm = normals[idx_lo:idx_hi + 1]
            seg_depths = np.array([depth_fn(arc_in_zone[idx_lo + k]) for k in range(idx_hi - idx_lo + 1)])
            outer_pts = seg_pts + seg_norm * seg_depths[:, None]
            return np.vstack([seg_pts, outer_pts[::-1]])

        # If zone is too short for taper-in + middle + taper-out, just draw a
        # single small tapered polygon spanning the whole zone.
        if zone_arc_total <= 2 * KERB_TAPER_M:
            def short_depth(a):
                d = min(a, zone_arc_total - a)
                return KERB_DEPTH_M * (d / KERB_TAPER_M)
            poly_seg = make_segment_polygon(0, L - 1, short_depth)
            if poly_seg is not None:
                polygons.append(poly_seg)
            continue

        # Boundaries (in zone arc length).
        a_taper_in_end  = KERB_TAPER_M
        a_taper_out_beg = zone_arc_total - KERB_TAPER_M

        # Convert arc-position to nearest index in arc_in_zone.
        idx_taper_in_end  = int(np.searchsorted(arc_in_zone, a_taper_in_end))
        idx_taper_out_beg = int(np.searchsorted(arc_in_zone, a_taper_out_beg))
        idx_taper_in_end  = min(idx_taper_in_end, L - 1)
        idx_taper_out_beg = max(idx_taper_out_beg, 0)

        # 1. Taper-in triangle (depth: 0 at start → KERB_DEPTH_M at idx_taper_in_end).
        def depth_in(a):
            return KERB_DEPTH_M * min(1.0, a / KERB_TAPER_M)
        poly_seg = make_segment_polygon(0, idx_taper_in_end, depth_in)
        if poly_seg is not None:
            polygons.append(poly_seg)

        # 2. Middle: alternating white blocks and empty gaps. Each block is
        #    KERB_BLOCK_M long; each gap is KERB_GAP_M long. Same metric size
        #    regardless of corner length.
        a = a_taper_in_end
        block_idx = 0
        while a < a_taper_out_beg - 1e-6:
            if block_idx % 2 == 0:
                # White block.
                a_end = min(a + KERB_BLOCK_M, a_taper_out_beg)
                k_lo = int(np.searchsorted(arc_in_zone, a))
                k_hi = int(np.searchsorted(arc_in_zone, a_end))
                k_lo = max(0, min(k_lo, L - 1))
                k_hi = max(0, min(k_hi, L - 1))
                poly_seg = make_segment_polygon(k_lo, k_hi, lambda _a: KERB_DEPTH_M)
                if poly_seg is not None:
                    polygons.append(poly_seg)
                a = a_end
            else:
                # Gap (no polygon drawn).
                a += KERB_GAP_M
            block_idx += 1

        # 3. Taper-out triangle (depth: KERB_DEPTH_M at idx_taper_out_beg → 0 at end).
        def depth_out(a):
            d_from_end = zone_arc_total - a
            return KERB_DEPTH_M * min(1.0, d_from_end / KERB_TAPER_M)
        poly_seg = make_segment_polygon(idx_taper_out_beg, L - 1, depth_out)
        if poly_seg is not None:
            polygons.append(poly_seg)

    return polygons


def compute_curvature(poly):
    """Discrete curvature for a closed polyline."""
    n = len(poly)
    kappa = np.zeros(n)
    for i in range(n):
        a = poly[(i - 1) % n]
        b = poly[i]
        c = poly[(i + 1) % n]
        ab = b - a
        bc = c - b
        cross = ab[0] * bc[1] - ab[1] * bc[0]
        nab = np.linalg.norm(ab)
        nbc = np.linalg.norm(bc)
        nac = np.linalg.norm(c - a)
        denom = nab * nbc * nac
        kappa[i] = 0.0 if denom < 1e-9 else 2.0 * cross / denom
    return kappa


def align_raceline_to_telemetry(raceline, ver_d, ver_v):
    """Find the parameter offset (and direction) that makes the IDEAL line's
    curvature pattern align with VER's slow-corner pattern. Without this the
    raceline's index-0 is wherever Blender's boundary walk happened to start,
    while VER's distance-0 is the start/finish line — completely unrelated.

    Strategy: corners are slow on telemetry AND high-curvature on the
    raceline. Resample both onto a common 0..1 lap-fraction grid, then
    circularly cross-correlate |κ(p)| with 1/v(p). Try forward and reversed
    raceline direction; pick whichever has the higher correlation peak.
    Roll the raceline so its index-0 matches VER's distance-0.
    """
    n = len(raceline)
    n_grid = 1024

    rl_seg = np.linalg.norm(np.roll(raceline, -1, axis=0) - raceline, axis=1)
    rl_arc = np.concatenate([[0.0], np.cumsum(rl_seg)])
    rl_frac = rl_arc[:-1] / rl_arc[-1]
    kappa = np.abs(compute_curvature(raceline))
    grid = np.linspace(0.0, 1.0, n_grid, endpoint=False)
    kappa_grid = np.interp(grid, rl_frac, kappa)

    ver_frac = ver_d / ver_d[-1]
    inv_speed = 1.0 / np.maximum(ver_v, 1.0)
    inv_speed_grid = np.interp(grid, ver_frac, inv_speed)

    def normalize(a):
        a = a - a.mean()
        s = a.std()
        return a / s if s > 1e-9 else a
    k_n = normalize(kappa_grid)
    s_n = normalize(inv_speed_grid)

    # Circular cross-correlation via FFT.
    # corr_fwd[k] = sum_i k_n[i] * s_n[(i+k) % n_grid]
    K = np.fft.fft(k_n)
    S = np.fft.fft(s_n)
    corr_fwd = np.fft.ifft(K * np.conj(S)).real   # peak at lag = -shift_we_want
    corr_rev = np.fft.ifft(np.conj(K) * np.conj(S)).real   # for reversed raceline

    # The "shift" we need to apply: argmax of cross-correlation gives the lag
    # that maximizes alignment. We want to convert grid lag → raceline-pts lag.
    if corr_rev.max() > corr_fwd.max():
        raceline = raceline[::-1].copy()
        kappa = kappa[::-1]
        rl_frac = 1.0 - rl_frac[::-1]   # not needed below, but keep semantics
        peak_lag = int(np.argmax(corr_rev))
        peak_val = float(corr_rev.max())
        direction = "REVERSED"
    else:
        peak_lag = int(np.argmax(corr_fwd))
        peak_val = float(corr_fwd.max())
        direction = "forward"

    # Convert lag (in n_grid samples) → raceline-pts shift.
    # In our convention the lag is the offset to apply to the raceline's
    # parameter so that raceline_new[i] aligns with VER's i.
    shift_frac = peak_lag / n_grid
    shift_n = int(round(shift_frac * n)) % n
    raceline_aligned = np.roll(raceline, -shift_n, axis=0)

    print(f"[align] direction={direction}  shift={shift_n}/{n} pts "
          f"({shift_frac * 100:.1f}% of lap)  corr_peak={peak_val:.2f}")
    return raceline_aligned


def align_loops(outer, inner):
    if signed_area(outer) < 0: outer = outer[::-1]
    if signed_area(inner) < 0: inner = inner[::-1]
    d2 = np.sum((inner - outer[0]) ** 2, axis=1)
    j0 = int(np.argmin(d2))
    inner = np.roll(inner, -j0, axis=0)
    return outer, inner


def build_centerline_and_widths(outer, inner):
    """Index-based pairing (fast). Both loops are uniformly arc-length sampled
    and rotationally aligned, so outer[i] / inner[i] are at matching stations
    to within sub-meter for our densities. Centerline = midpoint, widths
    = signed projection onto local left-normal."""
    n = len(outer)
    assert len(inner) == n

    centerline = 0.5 * (outer + inner)

    tang = np.zeros_like(centerline)
    for i in range(n):
        d = centerline[(i + 3) % n] - centerline[(i - 3) % n]
        nm = np.linalg.norm(d)
        tang[i] = d / nm if nm > 1e-8 else np.array([1.0, 0.0])
    left_normal = np.column_stack([-tang[:, 1], tang[:, 0]])

    off_outer = np.einsum('ij,ij->i', outer - centerline, left_normal)
    off_inner = np.einsum('ij,ij->i', inner - centerline, left_normal)

    w_left  = np.maximum(off_outer, off_inner)
    w_right = -np.minimum(off_outer, off_inner)

    w_left  = np.maximum(w_left  - INSET_M, VEH_WIDTH / 2.0 + 0.5)
    w_right = np.maximum(w_right - INSET_M, VEH_WIDTH / 2.0 + 0.5)
    w_left  = gaussian_filter1d(np.tile(w_left,  3), sigma=3)[n:2 * n]
    w_right = gaussian_filter1d(np.tile(w_right, 3), sigma=3)[n:2 * n]

    return centerline, w_right, w_left


def clamp_raceline_to_corridor(raceline, centerline, w_right, w_left, clearance_m):
    """Project each raceline pt onto the local left-normal at the nearest
    centerline station; clamp alpha into [-w_left+c, +w_right-c]. Guarantees
    the line stays inside the (passed-in) corridor — guard against any
    bow-out from final spline interpolation."""
    from scipy.spatial import cKDTree
    n_c = len(centerline)
    tree = cKDTree(centerline)
    out = raceline.copy()
    n_changed = 0
    max_correction = 0.0
    for i in range(len(out)):
        _, j = tree.query(out[i])
        d = centerline[(j + 3) % n_c] - centerline[(j - 3) % n_c]
        nm = float(np.linalg.norm(d))
        if nm < 1e-8:
            continue
        t_hat = d / nm
        nl = np.array([-t_hat[1], t_hat[0]])
        alpha = float(np.dot(out[i] - centerline[j], nl))
        amin = -float(w_left[j])  + clearance_m
        amax =  float(w_right[j]) - clearance_m
        if amin > amax:
            amid = 0.5 * (amin + amax); amin = amax = amid
        if alpha < amin or alpha > amax:
            alpha_new = max(amin, min(amax, alpha))
            out[i] = centerline[j] + alpha_new * nl
            n_changed += 1
            max_correction = max(max_correction, abs(alpha_new - alpha))
    return out, n_changed, max_correction


# =============================================================
# Stage 2: IQP min-curvature racing line (port from addon)
# =============================================================

def opt_min_curv_sparse(reftrack, normvectors, A, kappa_bound, w_veh):
    no_points = reftrack.shape[0]
    no_splines = no_points

    A_ex_b = np.zeros((no_points, no_splines * 4), dtype=float)
    for i in range(no_splines):
        A_ex_b[i, i * 4 + 1] = 1.0
    A_ex_c = np.zeros((no_points, no_splines * 4), dtype=float)
    for i in range(no_splines):
        A_ex_c[i, i * 4 + 2] = 2.0

    A_sp = csc_matrix(A)
    T_c = spsolve(A_sp.T, A_ex_c.T).T
    T_b = spsolve(A_sp.T, A_ex_b.T).T

    M_x = np.zeros((no_splines * 4, no_points))
    M_y = np.zeros((no_splines * 4, no_points))
    for i in range(no_splines):
        j = i * 4
        if i < no_points - 1:
            M_x[j,     i]     = normvectors[i,   0]
            M_x[j + 1, i + 1] = normvectors[i + 1, 0]
            M_y[j,     i]     = normvectors[i,   1]
            M_y[j + 1, i + 1] = normvectors[i + 1, 1]
        else:
            M_x[j,     i] = normvectors[i, 0]
            M_x[j + 1, 0] = normvectors[0, 0]
            M_y[j,     i] = normvectors[i, 1]
            M_y[j + 1, 0] = normvectors[0, 1]

    q_x = np.zeros((no_splines * 4, 1))
    q_y = np.zeros((no_splines * 4, 1))
    for i in range(no_splines):
        j = i * 4
        nxt = (i + 1) % no_points
        q_x[j, 0] = reftrack[i, 0];  q_x[j + 1, 0] = reftrack[nxt, 0]
        q_y[j, 0] = reftrack[i, 1];  q_y[j + 1, 0] = reftrack[nxt, 1]

    x_prime = np.eye(no_points) * (T_b @ q_x)
    y_prime = np.eye(no_points) * (T_b @ q_y)
    x_prime_sq = x_prime ** 2
    y_prime_sq = y_prime ** 2
    x_prime_y_prime = -2.0 * (x_prime @ y_prime)

    curv_den = (x_prime_sq + y_prime_sq) ** 1.5
    curv_part = np.divide(1.0, curv_den, out=np.zeros_like(curv_den), where=curv_den != 0)
    curv_part_sq = curv_part ** 2

    P_xx = curv_part_sq @ y_prime_sq
    P_yy = curv_part_sq @ x_prime_sq
    P_xy = curv_part_sq @ x_prime_y_prime

    T_nx = T_c @ M_x
    T_ny = T_c @ M_y

    H = T_nx.T @ (P_xx @ T_nx) + T_ny.T @ (P_xy @ T_nx) + T_ny.T @ (P_yy @ T_ny)
    H = (H + H.T) * 0.5

    f_x  = 2.0 * (q_x.T @ T_c.T @ P_xx @ T_nx)
    f_xy = (q_x.T @ T_c.T @ P_xy @ T_ny + q_y.T @ T_c.T @ P_xy @ T_nx)
    f_y  = 2.0 * (q_y.T @ T_c.T @ P_yy @ T_ny)
    f = np.squeeze(f_x + f_xy + f_y)

    Q_x = curv_part @ y_prime
    Q_y = curv_part @ x_prime
    E_kappa = Q_y @ T_ny - Q_x @ T_nx
    k_kappa_ref = (Q_y @ (T_c @ q_y)) - (Q_x @ (T_c @ q_x))
    con_ge = np.ones((no_points, 1)) * kappa_bound - k_kappa_ref
    con_le = -(np.ones((no_points, 1)) * (-kappa_bound) - k_kappa_ref)
    con_stack = np.concatenate([con_ge, con_le]).ravel()

    half_veh = w_veh / 2.0
    dev_max_right = np.maximum(reftrack[:, 2] - half_veh, 0.05)
    dev_max_left  = np.maximum(reftrack[:, 3] - half_veh, 0.05)

    G = np.vstack([np.eye(no_points), -np.eye(no_points), E_kappa, -E_kappa])
    h = np.concatenate([dev_max_right, dev_max_left, con_stack])

    H += np.eye(H.shape[0]) * 1e-8

    P_cvx = cvx_matrix(H.astype(np.double))
    q_cvx = cvx_matrix(f.astype(np.double).reshape(-1))
    G_cvx = cvx_matrix(G.astype(np.double))
    h_cvx = cvx_matrix(h.astype(np.double).reshape(-1))
    sol = cvx_solvers.qp(P_cvx, q_cvx, G_cvx, h_cvx)
    if sol['status'] != 'optimal':
        raise RuntimeError(f"cvxopt QP status: {sol['status']}")
    return np.array(sol['x']).ravel()


def run_iqp(centerline, w_right, w_left):
    import trajectory_planning_helpers as tph

    cur_ref = centerline.copy()
    cur_wr  = w_right.copy()
    cur_wl  = w_left.copy()

    print(f"[iqp] sparse IQP, up to {IQP_ITERS} iters at N={len(cur_ref)}")
    converged = False
    for it in range(IQP_ITERS):
        t_it = time.perf_counter()
        refpath = np.vstack([cur_ref, cur_ref[0]])
        coeffs_x, coeffs_y, A_mat, _ = tph.calc_splines.calc_splines(
            path=refpath, use_dist_scaling=True)
        ind_s = np.arange(len(coeffs_x))
        t_s = np.zeros(len(coeffs_x))
        psi, kappa = tph.calc_head_curv_an.calc_head_curv_an(
            coeffs_x=coeffs_x, coeffs_y=coeffs_y,
            ind_spls=ind_s, t_spls=t_s,
            calc_curv=True, calc_dcurv=False)[:2]
        normvec = tph.calc_normal_vectors.calc_normal_vectors(psi=psi)

        reftrack_it = np.column_stack([cur_ref, cur_wr, cur_wl])
        try:
            alpha = opt_min_curv_sparse(reftrack_it, normvec, A_mat, KAPPA_BOUND, VEH_WIDTH)
        except Exception as e:
            print(f"  iter {it}: QP failed: {e}")
            if it == 0: raise
            break

        alpha = np.clip(alpha,
                        -cur_wl + VEH_WIDTH / 2.0 + SAFETY_MARGIN,
                         cur_wr - VEH_WIDTH / 2.0 - SAFETY_MARGIN)

        print(f"  iter {it}: max|a|={np.max(np.abs(alpha)):.3f} "
              f"mean|a|={np.mean(np.abs(alpha)):.3f} "
              f"({time.perf_counter() - t_it:.2f}s)")

        cur_ref = cur_ref + normvec * alpha[:, None]
        cur_wr  = np.maximum(cur_wr - alpha, VEH_WIDTH / 2.0 + SAFETY_MARGIN)
        cur_wl  = np.maximum(cur_wl + alpha, VEH_WIDTH / 2.0 + SAFETY_MARGIN)

        if np.max(np.abs(alpha)) < ALPHA_TOL and it >= 1:
            print(f"  converged at iter {it}")
            converged = True
            break

    # Light gaussian on cur_ref kills any high-freq sawtooth between adjacent
    # IQP stations before the final spline — eliminates "bumps" on the line.
    if IQP_OUTPUT_SMOOTH > 0:
        n_ref = len(cur_ref)
        cx_t = gaussian_filter1d(np.tile(cur_ref[:, 0], 3), sigma=IQP_OUTPUT_SMOOTH)[n_ref:2 * n_ref]
        cy_t = gaussian_filter1d(np.tile(cur_ref[:, 1], 3), sigma=IQP_OUTPUT_SMOOTH)[n_ref:2 * n_ref]
        cur_ref = np.column_stack([cx_t, cy_t])

    rl_closed = np.vstack([cur_ref, cur_ref[0]])
    arc = np.concatenate([[0.0],
            np.cumsum(np.linalg.norm(np.diff(rl_closed, axis=0), axis=1))])
    total_len = arc[-1]
    n_out = max(10, int(total_len / RACELINE_STEPSIZE))
    s_out = max(1.0, len(rl_closed) * 0.005)
    try:
        tck, _ = splprep([rl_closed[:, 0], rl_closed[:, 1]], u=arc, s=s_out, per=True)
    except Exception:
        tck, _ = splprep([rl_closed[:, 0], rl_closed[:, 1]], u=arc, s=0, per=True)
    u_new = np.linspace(0, total_len, n_out, endpoint=False)
    rx, ry = splev(u_new, tck)
    raceline = np.column_stack([rx, ry])

    print(f"[iqp] {n_out} pts, {total_len:.0f} m, converged={converged}")
    return raceline, total_len


# =============================================================
# Stage 3: Telemetry  →  animation timing
# =============================================================

def load_ver_telemetry(csv_path):
    """Read time_s, distance, speed columns. Speed is km/h in source.
    Returns: (times[s], distances[m], speeds[m/s], lap_time[s]) sorted, deduped."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((float(r['time_s']),
                             float(r['distance']),
                             float(r['speed']) / 3.6))
            except (ValueError, KeyError):
                continue
    if len(rows) < 50:
        raise RuntimeError(f"Telemetry too short: {len(rows)} rows")
    rows.sort(key=lambda r: r[0])
    # Dedupe identical timestamps
    out = [rows[0]]
    for r in rows[1:]:
        if r[0] > out[-1][0]:
            out.append(r)
    t = np.array([r[0] for r in out])
    d = np.array([r[1] for r in out])
    v = np.array([r[2] for r in out])
    lap_time = float(t[-1] - t[0])
    print(f"[telemetry] {len(t)} samples, lap_time={lap_time:.3f}s, "
          f"dist=[{d.min():.0f},{d.max():.0f}]m, "
          f"v=[{v.min() * 3.6:.0f},{v.max() * 3.6:.0f}] km/h")
    return t - t[0], d - d[0], v, lap_time


# =============================================================
# Speed -> color (BGR) heatmap.  Slow=red, mid=yellow, fast=cyan.
# =============================================================

def speed_color_bgr(t):
    t = max(0.0, min(1.0, float(t)))
    if t < 0.5:
        u = t * 2.0
        return (0, int(255 * u), 255)
    u = (t - 0.5) * 2.0
    return (int(255 * u), 255, int(255 * (1.0 - u)))


# =============================================================
# Stage 4: Render
# =============================================================

def load_font(size, prefer_bold=True):
    candidates = [
        r"C:\Users\91910\Downloads\Formula1\Formula1-Bold_web_0.ttf.ttf" if prefer_bold else None,
        r"C:\Users\91910\Downloads\Formula1\Formula1-Regular_web_0.ttf.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if prefer_bold else None,
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_centered(draw, x, y, text, font, fill):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]; h = bbox[3] - bbox[1]
    except Exception:
        w, h = draw.textsize(text, font=font)
    draw.text((x - w / 2, y - h / 2 - 4), text, font=font, fill=fill)


def render_video(outer, inner, raceline, ver_t, ver_d, ver_v_ms, lap_time,
                 out_path, track_name, zoom, trail_frames, fps,
                 outer_kerbs=None, inner_kerbs=None):
    """ver_t,ver_d,ver_v_ms come from real telemetry. The dot's position at
    video time `t` is found by:  d_at_t = interp(t, ver_t, ver_d), then
    d_at_t is mapped to arc-length on `raceline` (linear scale by ratio of
    raceline length to ver total distance)."""
    total_frames = int(math.ceil(lap_time * fps))
    print(f"[render] {total_frames} frames at {fps}fps ({lap_time:.2f}s)")

    v_min_global = float(np.min(ver_v_ms))
    v_max_global = float(np.max(ver_v_ms))
    v_span = max(v_max_global - v_min_global, 1e-6)

    all_pts = np.vstack([outer, inner, raceline])
    track_w = all_pts[:, 0].max() - all_pts[:, 0].min()
    track_h = all_pts[:, 1].max() - all_pts[:, 1].min()
    cam_scale = (min(WIDTH, HEIGHT * 0.5) / max(track_w, track_h)) * zoom

    def w2s(pt, cam_x, cam_y):
        sx = int(WIDTH / 2 + (pt[0] - cam_x) * cam_scale)
        sy = int(HEIGHT * CAMERA_Y_FRAC - (pt[1] - cam_y) * cam_scale)
        return sx, sy

    MAP_X = WIDTH - MAP_SIZE - MAP_X_RIGHT_INSET
    MAP_Y = MAP_Y_TOP
    map_scale = MAP_SIZE / max(track_w, track_h) * 0.95
    map_cx = (all_pts[:, 0].max() + all_pts[:, 0].min()) / 2
    map_cy = (all_pts[:, 1].max() + all_pts[:, 1].min()) / 2

    def w2map(pt):
        return (int(MAP_X + MAP_SIZE / 2 + (pt[0] - map_cx) * map_scale),
                int(MAP_Y + MAP_SIZE / 2 - (pt[1] - map_cy) * map_scale))

    map_outer = np.array([w2map(p) for p in outer], np.int32)
    map_inner = np.array([w2map(p) for p in inner], np.int32)

    font_title      = load_font(42, True)
    font_sub        = load_font(26, False)
    font_speed      = load_font(72, True)
    font_speed_unit = load_font(28, False)
    font_wm         = load_font(24, True)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(out_path, fourcc, fps, (WIDTH, HEIGHT))

    # Pre-compute raceline arc-length grid for d -> position interp.
    rl = raceline
    rl_seg = np.linalg.norm(np.roll(rl, -1, axis=0) - rl, axis=1)
    rl_arc = np.concatenate([[0.0], np.cumsum(rl_seg)])  # len = N+1
    rl_total_arc = float(rl_arc[-1])
    ver_total_d = float(ver_d[-1])
    arc_scale = rl_total_arc / max(ver_total_d, 1e-6)

    def pos_at_arc(s):
        """Position on raceline at cumulative arc length s (clamped/wrapped)."""
        s_mod = s % rl_total_arc
        idx = int(np.searchsorted(rl_arc, s_mod)) - 1
        idx = max(0, min(idx, len(rl) - 1))
        seg_len = rl_arc[idx + 1] - rl_arc[idx]
        frac = 0.0 if seg_len <= 0 else (s_mod - rl_arc[idx]) / seg_len
        a = rl[idx]; b = rl[(idx + 1) % len(rl)]
        return a + frac * (b - a)

    trail = []  # list of (x, y, v_ms) in world coords

    title_line1 = TITLE_LINE_1
    title_line2 = track_name.upper()

    for f in range(total_frames):
        t = f / fps
        if t > ver_t[-1]: t = ver_t[-1]

        # VER's distance + speed at video time t (real data, no model)
        d_now = float(np.interp(t, ver_t, ver_d))
        v_now = float(np.interp(t, ver_t, ver_v_ms))
        s_on_rl = d_now * arc_scale
        pos = pos_at_arc(s_on_rl)
        cam_x, cam_y = float(pos[0]), float(pos[1])

        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        # Track
        outer_s = np.array([w2s(p, cam_x, cam_y) for p in outer], np.int32)
        inner_s = np.array([w2s(p, cam_x, cam_y) for p in inner], np.int32)
        cv2.fillPoly(frame, [outer_s], TRACK_FILL)
        cv2.fillPoly(frame, [inner_s], (0, 0, 0))

        # Kerbs — solid white trapezoids attached OUTSIDE the track edge at each corner.
        for kerb_polys in (outer_kerbs or [], inner_kerbs or []):
            for polygon in kerb_polys:
                pts_s = np.array([w2s((p[0], p[1]), cam_x, cam_y) for p in polygon], np.int32)
                cv2.fillPoly(frame, [pts_s], KERB_COLOR, lineType=cv2.LINE_AA)

        cv2.polylines(frame, [outer_s.reshape((-1, 1, 2))], True, TRACK_EDGE,
                      thickness=EDGE_THICKNESS, lineType=cv2.LINE_AA)
        cv2.polylines(frame, [inner_s.reshape((-1, 1, 2))], True, TRACK_EDGE,
                      thickness=EDGE_THICKNESS, lineType=cv2.LINE_AA)

        # Ideal racing line (subtle)
        rl_s = np.array([w2s(p, cam_x, cam_y) for p in rl], np.int32)
        cv2.polylines(frame, [rl_s.reshape((-1, 1, 2))], True, RACELINE_COLOR,
                      thickness=3, lineType=cv2.LINE_AA)

        # Trail with speed heatmap
        trail.append((float(pos[0]), float(pos[1]), v_now))
        if len(trail) > trail_frames: trail.pop(0)
        if len(trail) > 1:
            for k in range(len(trail) - 1):
                p0 = trail[k]; p1 = trail[k + 1]
                v_avg = 0.5 * (p0[2] + p1[2])
                t_norm = (v_avg - v_min_global) / v_span
                col = speed_color_bgr(t_norm)
                x0, y0 = w2s((p0[0], p0[1]), cam_x, cam_y)
                x1, y1 = w2s((p1[0], p1[1]), cam_x, cam_y)
                cv2.line(frame, (x0, y0), (x1, y1), col,
                         thickness=TRAIL_THICKNESS, lineType=cv2.LINE_AA)

        # Dot
        sx, sy = w2s(pos, cam_x, cam_y)
        t_now_norm = (v_now - v_min_global) / v_span
        dot_col = speed_color_bgr(t_now_norm)
        cv2.circle(frame, (sx, sy), DOT_RADIUS, dot_col, -1, cv2.LINE_AA)
        cv2.circle(frame, (sx, sy), DOT_RADIUS, (255, 255, 255), 4, cv2.LINE_AA)

        # Minimap
        cv2.fillPoly(frame, [map_outer], TRACK_FILL)
        cv2.fillPoly(frame, [map_inner], (0, 0, 0))
        cv2.polylines(frame, [map_outer.reshape((-1, 1, 2))], True, (120, 120, 120),
                      thickness=2, lineType=cv2.LINE_AA)
        cv2.polylines(frame, [map_inner.reshape((-1, 1, 2))], True, (120, 120, 120),
                      thickness=2, lineType=cv2.LINE_AA)
        mx, my = w2map(pos)
        cv2.circle(frame, (mx, my), 9, dot_col, -1, cv2.LINE_AA)
        cv2.circle(frame, (mx, my), 9, (255, 255, 255), 2, cv2.LINE_AA)

        # Text overlays
        img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        draw_centered(draw, WIDTH // 2, TITLE_Y_1, title_line1, font_title, (255, 255, 255))
        draw_centered(draw, WIDTH // 2, TITLE_Y_2, title_line2, font_sub, (200, 200, 200))
        speed_kmh = int(round(v_now * 3.6))
        draw_centered(draw, WIDTH // 2, SPEED_Y, f"{speed_kmh}", font_speed, (255, 255, 255))
        draw_centered(draw, WIDTH // 2, SPEED_Y + KMH_Y_OFFSET, "KM/H", font_speed_unit, (200, 200, 200))
        lap_str = f"LAP TIME  {int(lap_time // 60):d}:{lap_time % 60:06.3f}"
        draw_centered(draw, WIDTH // 2, LAP_Y, lap_str, font_sub, (180, 180, 180))
        draw_centered(draw, WIDTH // 2, WATERMARK_Y, WATERMARK_TEXT, font_wm, (150, 150, 150))

        out.write(cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR))

        if (f + 1) % 60 == 0 or f == total_frames - 1:
            print(f"  frame {f + 1}/{total_frames}")

    out.release()
    print(f"[render] saved -> {out_path}")


# =============================================================
# Main
# =============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outline", required=True, help="Path to <track>_outline.json")
    ap.add_argument("--raceline", required=False, default=None,
                    help="Precomputed raceline JSON (from sim_2026_lap.py). "
                         "If omitted, IQP is run inline (Miami-compatible path).")
    ap.add_argument("--telemetry-csv", required=True,
                    help="REQUIRED: real telemetry CSV (frame,time_s,distance,speed,...). "
                         "Drives the animation timing AND the speed readout.")
    ap.add_argument("--track-name", default=None, help="Subtitle text (track name)")
    ap.add_argument("--out", default=None, help="Output MP4 path")
    ap.add_argument("--zoom", type=float, default=DEFAULT_ZOOM)
    ap.add_argument("--trail-frames", type=int, default=DEFAULT_TRAIL)
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    args = ap.parse_args()

    with open(args.outline, "r", encoding="utf-8") as f:
        data = json.load(f)
    outer_raw = np.array(data["outer"], dtype=float)
    inner_raw = np.array(data["inner"], dtype=float)
    print(f"[load] outer={len(outer_raw)} pts, inner={len(inner_raw)} pts")

    ver_t, ver_d, ver_v, ver_lap = load_ver_telemetry(args.telemetry_csv)

    # IQP corridor: heavily smoothed, INSET applied via build_centerline_and_widths.
    outer_corr = smooth_resample_loop(outer_raw, N_CORRIDOR_POINTS, CORR_SMOOTH_S)
    inner_corr = smooth_resample_loop(inner_raw, N_CORRIDOR_POINTS, CORR_SMOOTH_S)
    outer_corr, inner_corr = align_loops(outer_corr, inner_corr)

    # Visual edges: lightly smoothed raw, then PUSHED OUTWARD by VISUAL_OUTSET_M
    # so the rendered corridor is guaranteed wider than the IQP corridor at every
    # station — including at any localised inward jags in the user's hand-separated
    # mesh that heavy IQP-smoothing averages out but light visual smoothing keeps.
    outer_visual = smooth_resample_loop(outer_raw, N_VISUAL_POINTS, VISUAL_SMOOTH_S)
    inner_visual = smooth_resample_loop(inner_raw, N_VISUAL_POINTS, VISUAL_SMOOTH_S)
    outer_visual, inner_visual = align_loops(outer_visual, inner_visual)
    outer_visual = offset_loop_outward(outer_visual, VISUAL_OUTSET_M, is_outer=True)
    inner_visual = offset_loop_outward(inner_visual, VISUAL_OUTSET_M, is_outer=False)

    # Kerbs at corners on both edges — solid white trapezoids OUTSIDE the road.
    outer_kerbs = compute_kerb_polygons(outer_visual, is_outer=True)
    inner_kerbs = compute_kerb_polygons(inner_visual, is_outer=False)
    print(f"[kerbs] outer={len(outer_kerbs)} corner zones, inner={len(inner_kerbs)} corner zones")

    centerline_iqp, w_right_iqp, w_left_iqp = build_centerline_and_widths(outer_corr, inner_corr)
    print(f"[corridor.iqp] widths: right=[{w_right_iqp.min():.2f},{w_right_iqp.max():.2f}]  "
          f"left=[{w_left_iqp.min():.2f},{w_left_iqp.max():.2f}]")

    if args.raceline:
        with open(args.raceline, encoding="utf-8") as f:
            rl_data = json.load(f)
        raceline = np.array(rl_data["raceline"], dtype=float)
        print(f"[raceline] loaded precomputed: {len(raceline)} pts, "
              f"track_length={rl_data['track_length_m']:.0f} m")
    else:
        raceline, _ = run_iqp(centerline_iqp, w_right_iqp, w_left_iqp)

    # Critical: align the raceline's parameter origin (and possibly its direction)
    # with VER's lap. Without this, dot-position vs. speed-readout is desynced
    # because Blender's boundary walk starts at an arbitrary point.
    raceline = align_raceline_to_telemetry(raceline, ver_d, ver_v)

    track_name = args.track_name or os.path.splitext(os.path.basename(args.outline))[0]
    out_path = args.out or f"{os.path.splitext(os.path.basename(args.outline))[0]}_optimal_lap.mp4"

    render_video(
        outer_visual, inner_visual, raceline,
        ver_t, ver_d, ver_v, ver_lap,
        out_path, track_name, args.zoom, args.trail_frames, args.fps,
        outer_kerbs=outer_kerbs, inner_kerbs=inner_kerbs
    )


if __name__ == "__main__":
    main()
