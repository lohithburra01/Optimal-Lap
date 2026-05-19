"""sim_2026_lap.py

Stage 2 of the Canada 2026 pipeline:
  A1. IQP min-curv (seed)            — imported from raceline_video.py
  A2. Jerk-constrained min-curv QP   — ported verbatim from
       f1_track_visualizer_addonLastLastLasttry5.py:1717-2211
       (OBJECT_OT_GenerateRacingLineMinTime — validated 2026-05-10)
  B.  2026 physics velocity profile  — defined later in this file
  C.  Write raceline.json + synthetic telemetry CSV

Spec: docs/superpowers/specs/2026-05-19-canada-2026-revamp-design.md
"""
import argparse
import csv
import json
import math
import os
import sys

import numpy as np
import quadprog
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import spsolve

# Reuse the existing IQP min-curv stack — single source of truth.
# Importing raceline_video also handles its quadprog stub (which is overridden
# by our real `import quadprog` above) + cvxopt setup.
from raceline_video import (
    smooth_resample_loop,
    align_loops,
    build_centerline_and_widths,
    run_iqp,
    N_CORRIDOR_POINTS,
    CORR_SMOOTH_S,
)

# ── Refinement constants — addon defaults, validated 2026-05-10 ──────────
# Source: f1_track_visualizer_addonLastLastLasttry5.py:2045-2057
J_MAX_LAT_JERK       = 12.0           # m/s³, turn-in lateral-jerk bound
UNWIND_RATIO         = 3.0            # rb_dn = rb_up × this
STRAIGHT_STIFF       = 5.0            # α-regularizer peak weight at κ=0
KAPPA_FLOOR          = 0.005          # 1/m — where α-reg tent reaches zero
LAMBDA_SLACK         = 1.0e3          # cost on κ-rate slack vars
SAFETY_MARGIN_REFINE = 0.30           # m — width margin (defense-in-depth)
FB_TOL               = 1.0e-4         # tolerance for warm-profile FB sweep

# ── Warm-profile helper params (used ONLY to compute v_warm for κ-rate bounds;
# the FINAL 2026 physics sim is a separate engine defined later) ─────────
WARM_MASS_KG         = 768.0          # 2026 mass (rough is fine)
WARM_A_LAT_MAX       = 4.5 * 9.81     # ~4.5 g lat (2026 reduced DF)
WARM_A_ACC_MAX       = 4.0 * 9.81     # longitudinal accel ceiling
WARM_A_BRK_MAX       = 5.0 * 9.81     # braking ceiling
WARM_P_MAX_W         = 750_000        # combined power
WARM_CDA             = 0.55           # 2026 straight-mode drag-area
WARM_V_CAP           = 110.0          # m/s safety cap
WARM_RHO             = 1.225


def kappa_ds_menger(pts):
    """Discrete signed curvature κ and segment length ds at each station of a
    closed polyline, via Menger's formula. Verbatim from
    f1_track_visualizer_addonLastLastLasttry5.py:1984."""
    n = len(pts)
    kp = np.zeros(n); ds = np.zeros(n)
    for i in range(n):
        im, ip = (i - 1) % n, (i + 1) % n
        ax_, ay_ = pts[i]  - pts[im]
        bx_, by_ = pts[ip] - pts[i]
        cx_, cy_ = pts[ip] - pts[im]
        la_ = math.hypot(ax_, ay_) + 1e-9
        lb_ = math.hypot(bx_, by_) + 1e-9
        lc_ = math.hypot(cx_, cy_) + 1e-9
        kp[i] = 2.0 * (ax_ * by_ - ay_ * bx_) / (la_ * lb_ * lc_)
        ds[i] = lb_
    return kp, np.maximum(ds, 1e-3)


def warm_vel_profile(kappa, ds, max_outer=200, tol=FB_TOL):
    """Forward-backward velocity profile using simplified vehicle params, used
    ONLY to compute v_warm for the refinement step's κ-rate bound. Verbatim
    structure from f1_track_visualizer_addonLastLastLasttry5.py:1999, with
    addon's per-instance vehicle params replaced by module-level WARM_* consts."""
    m = WARM_MASS_KG
    a_lat = WARM_A_LAT_MAX
    a_acc = WARM_A_ACC_MAX
    a_brk = WARM_A_BRK_MAX
    P_max_W = WARM_P_MAX_W
    cdA = WARM_CDA
    v_cap = WARM_V_CAP
    rho = WARM_RHO
    D_drag = 0.5 * rho * cdA / m

    n = len(kappa)
    kappa_abs = np.maximum(np.abs(kappa), 1e-3)
    A_arr = a_lat / kappa_abs
    B_arr = (D_drag / a_acc) ** 2 * A_arr
    v_grip = np.sqrt(A_arr / np.sqrt(1.0 + B_arr * B_arr))
    v_grip = np.clip(np.minimum(v_grip, v_cap), 5.0, None)
    vv = v_grip.copy()
    for _ in range(max_outer):
        vv_prev = vv.copy()
        for i in range(n):
            ip = (i + 1) % n
            ay_i  = kappa[i] * vv[i] * vv[i]
            avail = max(0.0, 1.0 - (ay_i / a_lat) ** 2)
            ax_g  = a_acc * math.sqrt(avail)
            ax_p  = P_max_W / (m * max(vv[i], 1.0))
            ax_t  = min(ax_g, ax_p)
            drag_a = 0.5 * rho * cdA * vv[i] * vv[i] / m
            a_kin  = max(0.0, ax_t - drag_a)
            cap   = math.sqrt(max(0.0, vv[i] ** 2 + 2.0 * a_kin * ds[i]))
            if cap < vv[ip]:
                vv[ip] = cap
        for i in range(n - 1, -1, -1):
            ip = (i + 1) % n
            ay_ip = kappa[ip] * vv[ip] * vv[ip]
            avail = max(0.0, 1.0 - (ay_ip / a_lat) ** 2)
            ax_b  = a_brk * math.sqrt(avail)
            drag_a = 0.5 * rho * cdA * vv[ip] * vv[ip] / m
            a_dec  = ax_b + drag_a
            cap   = math.sqrt(max(0.0, vv[ip] ** 2 + 2.0 * a_dec * ds[i]))
            if cap < vv[i]:
                vv[i] = cap
        if float(np.max(np.abs(vv - vv_prev))) < tol:
            break
    return vv


def opt_curv_kappa_rate(reftrack, normvectors, A,
                         rate_bound_up_vec, rate_bound_down_vec,
                         alpha_reg_weights, w_veh):
    """Jerk-constrained min-curv QP with slack, ported verbatim from
    f1_track_visualizer_addonLastLastLasttry5.py:1717-1891
    (OBJECT_OT_GenerateRacingLineMinTime._opt_curv_kappa_rate).

    Differences from a plain min-curv QP:
      1. Asymmetric per-station κ-RATE constraint (slack-relaxed).
      2. Per-station α regularizer (tent function on straights)."""
    no_points  = reftrack.shape[0]
    no_splines = no_points

    A_ex_b = np.zeros((no_points, no_splines * 4), dtype=float)
    for i in range(no_splines):
        A_ex_b[i, i * 4 + 1] = 1.0
    A_ex_c = np.zeros((no_points, no_splines * 4), dtype=float)
    for i in range(no_splines):
        A_ex_c[i, i * 4 + 2] = 2.0

    A_sp = csc_matrix(A)
    T_c  = spsolve(A_sp.T, A_ex_c.T).T
    T_b  = spsolve(A_sp.T, A_ex_b.T).T

    M_x = np.zeros((no_splines * 4, no_points))
    M_y = np.zeros((no_splines * 4, no_points))
    for i in range(no_splines):
        j = i * 4
        if i < no_points - 1:
            M_x[j,     i    ] = normvectors[i,   0]
            M_x[j + 1, i + 1] = normvectors[i+1, 0]
            M_y[j,     i    ] = normvectors[i,   1]
            M_y[j + 1, i + 1] = normvectors[i+1, 1]
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
        q_x[j,   0] = reftrack[i,   0]
        q_x[j+1, 0] = reftrack[nxt, 0]
        q_y[j,   0] = reftrack[i,   1]
        q_y[j+1, 0] = reftrack[nxt, 1]

    x_prime = np.eye(no_points) * (T_b @ q_x)
    y_prime = np.eye(no_points) * (T_b @ q_y)
    x_prime_sq      = x_prime ** 2
    y_prime_sq      = y_prime ** 2
    x_prime_y_prime = -2.0 * (x_prime @ y_prime)

    curv_den  = (x_prime_sq + y_prime_sq) ** 1.5
    curv_part = np.divide(1.0, curv_den, out=np.zeros_like(curv_den), where=curv_den != 0)
    curv_part_sq = curv_part ** 2

    P_xx = curv_part_sq @ y_prime_sq
    P_yy = curv_part_sq @ x_prime_sq
    P_xy = curv_part_sq @ x_prime_y_prime

    T_nx = T_c @ M_x
    T_ny = T_c @ M_y

    H_x  = T_nx.T @ (P_xx @ T_nx)
    H_xy = T_ny.T @ (P_xy @ T_nx)
    H_y  = T_ny.T @ (P_yy @ T_ny)
    H    = H_x + H_xy + H_y
    H    = (H + H.T) * 0.5

    f_x  = 2.0 * (q_x.T @ T_c.T @ P_xx @ T_nx)
    f_xy = (q_x.T @ T_c.T @ P_xy @ T_ny
           + q_y.T @ T_c.T @ P_xy @ T_nx)
    f_y  = 2.0 * (q_y.T @ T_c.T @ P_yy @ T_ny)
    f    = np.squeeze(f_x + f_xy + f_y)

    Q_x = curv_part @ y_prime
    Q_y = curv_part @ x_prime
    E_kappa     = Q_y @ T_ny - Q_x @ T_nx
    k_kappa_ref = (Q_y @ (T_c @ q_y)) - (Q_x @ (T_c @ q_x))

    D = np.zeros((no_points, no_points), dtype=float)
    for i in range(no_points):
        D[i, i]                    = -1.0
        D[i, (i + 1) % no_points]  =  1.0
    E_rate = D @ E_kappa
    k_rate = (D @ k_kappa_ref).ravel()
    rb_up  = np.maximum(np.asarray(rate_bound_up_vec,   dtype=float).ravel(), 1e-7)
    rb_dn  = np.maximum(np.asarray(rate_bound_down_vec, dtype=float).ravel(), 1e-7)

    half_veh      = w_veh / 2.0
    dev_max_right = reftrack[:, 2] - half_veh
    dev_max_left  = reftrack[:, 3] - half_veh
    dev_max_right = np.maximum(dev_max_right, 0.05)
    dev_max_left  = np.maximum(dev_max_left,  0.05)

    N_pts     = no_points
    alpha_reg = np.maximum(np.asarray(alpha_reg_weights, dtype=float).ravel(), 0.0)
    H_aug                              = np.zeros((2*N_pts, 2*N_pts))
    H_aug[:N_pts, :N_pts]              = H + np.diag(alpha_reg)
    H_aug[N_pts:, N_pts:]              = LAMBDA_SLACK * np.eye(N_pts)
    H_aug                             += np.eye(2*N_pts) * 1e-8

    f_aug          = np.zeros(2*N_pts)
    f_aug[:N_pts]  = np.asarray(f).ravel()

    zero_NN = np.zeros((N_pts, N_pts))
    I_N     = np.eye(N_pts)
    G_aug   = np.vstack([
        np.hstack([ I_N,     zero_NN]),
        np.hstack([-I_N,     zero_NN]),
        np.hstack([ E_rate, -I_N    ]),
        np.hstack([-E_rate, -I_N    ]),
        np.hstack([ zero_NN, -I_N   ]),
    ])
    h_aug   = np.concatenate([
        dev_max_right,
        dev_max_left,
        rb_up - k_rate,
        rb_dn + k_rate,
        np.zeros(N_pts),
    ])

    try:
        x = quadprog.solve_qp(H_aug, -f_aug, -G_aug.T, -h_aug, 0)[0]
    except Exception as e:
        raise RuntimeError(f"quadprog (κ-rate slack): {e}")
    alpha = x[:N_pts]
    slack = x[N_pts:]
    return alpha, slack
