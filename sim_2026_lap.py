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

# ── Telemetry-calibration constants ─────────────────────────────────────
DECEL_WINDOW_S = 0.40   # peak braking decel / accel power are measured over a
                        # ~0.4 s window, not adjacent samples: FastF1's
                        # interpolated speed channel quantizes into a
                        # plateau-then-step pattern that point-wise dv/dt
                        # misreads as unphysical (8+ g) spikes. 0.40 s (vs 0.30)
                        # also de-contaminates P_over_m_obs of a leading-edge
                        # quantization step (1266 -> 1038 W/kg).

# Override WARM_* defaults from calibration JSON if present.
# Resolve relative to THIS file, not the CWD — otherwise importing sim_2026_lap
# from any other directory silently skips the override and runs on stale defaults.
_CALIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "F1_Pipeline_Assets", "calibration",
                           "vehicle_calibration.json")
if os.path.exists(_CALIB_PATH):
    with open(_CALIB_PATH, encoding="utf-8") as _f:
        _calib = json.load(_f)
    # mu_long -> WARM_A_BRK_MAX is an accel ceiling: a_brk = mu_long * g
    if "mu_long_obs" in _calib:
        WARM_A_BRK_MAX = _calib["mu_long_obs"] * 9.81
    # P/m -> WARM_P_MAX_W = (P/m) * MASS_KG
    if "P_over_m_obs" in _calib:
        WARM_P_MAX_W = _calib["P_over_m_obs"] * WARM_MASS_KG
    # v_apex_hairpin_obs -> tighten WARM_A_LAT_MAX so v_grip at kappa_hairpin matches
    if "v_apex_hairpin_obs" in _calib:
        v_apex = _calib["v_apex_hairpin_obs"]
        kappa_hairpin = 1.0 / 15.0   # ~15 m radius for Canada T10
        WARM_A_LAT_MAX = v_apex * v_apex * kappa_hairpin
    print(f"[calibrate] overrides applied from {_CALIB_PATH}")
else:
    print(f"[calibrate] no calibration JSON at {_CALIB_PATH} — using WARM_* defaults")


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


def build_raceline(outer_raw, inner_raw):
    """Driver-physical racing line — IQP seed + jerk-constrained min-curv QP
    refinement (mirrors OBJECT_OT_GenerateRacingLineMinTime.execute() at
    f1_track_visualizer_addonLastLastLasttry5.py:1893)."""
    import trajectory_planning_helpers as tph

    # ── A1. IQP seed ─────────────────────────────────────────────────────
    outer = smooth_resample_loop(outer_raw, N_CORRIDOR_POINTS, CORR_SMOOTH_S)
    inner = smooth_resample_loop(inner_raw, N_CORRIDOR_POINTS, CORR_SMOOTH_S)
    outer, inner = align_loops(outer, inner)
    cl_qp, wr_safe, wl_safe = build_centerline_and_widths(outer, inner)
    print(f"[sim] corridor widths: r=[{wr_safe.min():.2f},{wr_safe.max():.2f}] "
          f"l=[{wl_safe.min():.2f},{wl_safe.max():.2f}]")

    iqp_seed_line, _ = run_iqp(cl_qp, wr_safe, wl_safe)

    # The IQP seed needs to be paired with its α-seed (offsets from cl_qp along
    # cl_qp's left-normals). We compute α from (iqp_seed_line − cl_qp) · nrm_init.
    # First, resample the IQP seed to match cl_qp's sample count.
    from scipy.interpolate import splprep, splev
    rl_closed = np.vstack([iqp_seed_line, iqp_seed_line[0]])
    arc_iqp = np.concatenate([[0.0],
        np.cumsum(np.linalg.norm(np.diff(rl_closed, axis=0), axis=1))])
    tck_iqp, _ = splprep([rl_closed[:, 0], rl_closed[:, 1]],
                          u=arc_iqp, s=0, per=True)
    N = len(cl_qp)
    u_new = np.linspace(0.0, arc_iqp[-1], N, endpoint=False)
    sx, sy = splev(u_new, tck_iqp)
    seed_on_cl_qp = np.column_stack([sx, sy])

    # cl_qp-frame normals (NOT tph spline normals — see
    # memory/project_mintime_jerk_constrained_qp.md key fixes)
    tang_init = np.zeros((N, 2))
    for i in range(N):
        d  = cl_qp[(i + 3) % N] - cl_qp[(i - 3) % N]
        nm = np.linalg.norm(d)
        tang_init[i] = d / nm if nm > 1e-8 else np.array([1.0, 0.0])
    nrm_init = np.column_stack([-tang_init[:, 1], tang_init[:, 0]])

    alpha_seed = np.einsum("ij,ij->i", seed_on_cl_qp - cl_qp, nrm_init)
    print(f"[sim] IQP seed alpha_seed: max|a|={np.max(np.abs(alpha_seed)):.2f}m")

    # ── A2. Jerk-constrained QP refinement ───────────────────────────────
    # Mirror addon execute() lines 2060-2151 in f1_track_visualizer_addonLastLastLasttry5.py
    w_veh = 1.9
    line_q = cl_qp + alpha_seed[:, None] * nrm_init
    kappa_q, ds_q = kappa_ds_menger(line_q)
    v_q = warm_vel_profile(kappa_q, ds_q)
    peak_kappa_q = float(np.max(np.abs(kappa_q)))

    v_floor = 5.0
    base_bound = J_MAX_LAT_JERK * ds_q / np.maximum(v_q, v_floor) ** 3
    rate_bound_up = base_bound
    rate_bound_dn = base_bound * UNWIND_RATIO

    # α-regularizer tent: nonzero on straights (κ≈0), zero in corners
    tent = np.maximum(0.0, 1.0 - np.abs(kappa_q) / max(KAPPA_FLOOR, 1e-9))
    alpha_reg_weights = STRAIGHT_STIFF * tent
    n_straight = int(np.sum(alpha_reg_weights > 1e-6))
    print(f"[sim] J_max={J_MAX_LAT_JERK} unwind×{UNWIND_RATIO} "
          f"α-reg active on {n_straight}/{N} straight stations")

    # Spline matrix on line_q geometry
    refpath = np.vstack([line_q, line_q[0]])
    _, _, A_mat, _ = tph.calc_splines.calc_splines(
        path=refpath, use_dist_scaling=True)

    # Widths relative to line_q in nrm_init frame (matches addon line 2106)
    cur_wr = np.maximum(wr_safe - alpha_seed, w_veh * 0.5 + SAFETY_MARGIN_REFINE)
    cur_wl = np.maximum(wl_safe + alpha_seed, w_veh * 0.5 + SAFETY_MARGIN_REFINE)
    reftrack_q = np.column_stack([line_q, cur_wr, cur_wl])

    alpha_perturb, slack_vec = opt_curv_kappa_rate(
        reftrack_q, nrm_init, A_mat,
        rate_bound_up, rate_bound_dn,
        alpha_reg_weights, w_veh,
    )
    n_slack_nz = int(np.sum(slack_vec > 1e-6))
    print(f"[sim] refinement slack: max={slack_vec.max():.2e} "
          f"({n_slack_nz}/{N} stations relaxed)")

    # Clip α perturbation to the width envelope (defensive)
    alpha_perturb = np.clip(
        alpha_perturb,
        -cur_wl + w_veh * 0.5 + SAFETY_MARGIN_REFINE,
         cur_wr - w_veh * 0.5 - SAFETY_MARGIN_REFINE,
    )
    refined_line = line_q + nrm_init * alpha_perturb[:, None]

    # Resample to uniform arc length on the FINAL refined line
    rl_closed = np.vstack([refined_line, refined_line[0]])
    arc_r = np.concatenate([[0.0],
        np.cumsum(np.linalg.norm(np.diff(rl_closed, axis=0), axis=1))])
    total_len = float(arc_r[-1])
    tck, _ = splprep([rl_closed[:, 0], rl_closed[:, 1]], u=arc_r, s=0, per=True)
    n_out = max(10, int(total_len / 2.0))
    u_new = np.linspace(0.0, total_len, n_out, endpoint=False)
    rx, ry = splev(u_new, tck)
    raceline = np.column_stack([rx, ry])

    # Final κ on the uniformly-sampled raceline
    seg = np.linalg.norm(np.diff(np.vstack([raceline, raceline[0]]), axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])[:-1]
    kappa_final = np.zeros(len(raceline))
    for i in range(len(raceline)):
        a = raceline[(i - 1) % len(raceline)]
        b = raceline[i]
        c = raceline[(i + 1) % len(raceline)]
        ab = b - a; bc = c - b
        cross = ab[0] * bc[1] - ab[1] * bc[0]
        denom = np.linalg.norm(ab) * np.linalg.norm(bc) * np.linalg.norm(c - a)
        kappa_final[i] = 0.0 if denom < 1e-9 else 2.0 * cross / denom

    peak_kappa_n = float(np.max(np.abs(kappa_final)))
    print(f"[sim] |κ|max: {peak_kappa_q:.4f} (IQP seed) → "
          f"{peak_kappa_n:.4f} (refined)")
    return raceline, arc, kappa_final, total_len


def _read_telemetry_rows(csv_path):
    """Read a CSV (fetch_fastest_lap.py format) as a list of dicts with float
    time_s, distance, speed [km/h], throttle, brake."""
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "time_s":   float(r["time_s"]),
                    "distance": float(r["distance"]),
                    "speed":    float(r["speed"]),
                    "throttle": float(r.get("throttle", 0) or 0),
                    "brake":    float(r.get("brake", 0) or 0),
                })
            except (ValueError, KeyError):
                continue
    return rows


def extract_peak_decel_g(rows, window_s=DECEL_WINDOW_S):
    """Largest sustained braking deceleration in g, measured as dv over a
    ~window_s time span starting at each braking sample (robust to FastF1
    speed-channel step quantization). Inputs are CSV-row dicts, speed in km/h."""
    g_max = 0.0
    n = len(rows)
    for i in range(n):
        if rows[i]["brake"] <= 50.0:
            continue
        j = i
        while j + 1 < n and rows[j]["time_s"] - rows[i]["time_s"] < window_s:
            j += 1
        dt = rows[j]["time_s"] - rows[i]["time_s"]
        if dt < window_s * 0.5:          # too little span (end of lap)
            continue
        dv_ms = (rows[j]["speed"] - rows[i]["speed"]) / 3.6
        if dv_ms < 0.0:
            g = -dv_ms / dt / 9.81
            if g > g_max:
                g_max = g
    return g_max


def extract_apex_speed_ms(rows):
    """Minimum sustained speed in the lap (in m/s). Sustained = the lowest
    point must be flanked by 5+ samples within 2 m/s of it on both sides,
    to avoid picking a noise dip."""
    v_ms = [r["speed"] / 3.6 for r in rows]
    n = len(v_ms)
    best = float("inf")
    for i in range(5, n - 5):
        v = v_ms[i]
        if v < best and all(abs(v_ms[j] - v) < 2.0 for j in range(i-5, i+6)):
            best = v
    return best if best < float("inf") else min(v_ms)


def detect_clipping_zones(rows, flatline_dvdt_threshold=0.3, min_zone_s=0.5):
    """Find sections where speed flatlines while throttle is pinned. Each
    zone is returned as {start_s, end_s, drop_kmh, duration_s, frac_in_straight}
    where frac_in_straight is the (start - last_corner_exit) / straight_length."""
    # First, identify the *containing* full-throttle straight for each row,
    # so we can compute fraction-into-the-straight for each clipping zone.
    n = len(rows)
    full_throttle = [r["throttle"] >= 99.0 and r["brake"] < 1.0 for r in rows]

    # Find contiguous full-throttle runs
    runs = []
    i = 0
    while i < n:
        if full_throttle[i]:
            j = i
            while j < n and full_throttle[j]:
                j += 1
            if rows[j-1]["time_s"] - rows[i]["time_s"] > 1.5:
                runs.append((i, j - 1))
            i = j
        else:
            i += 1

    zones = []
    for r_start, r_end in runs:
        run_dur = rows[r_end]["time_s"] - rows[r_start]["time_s"]
        # Find sub-segment(s) where dv/dt is near zero (clipping)
        k = r_start
        while k < r_end:
            dt = rows[k+1]["time_s"] - rows[k]["time_s"]
            if dt <= 1e-3:
                k += 1; continue
            dv_ms = (rows[k+1]["speed"] - rows[k]["speed"]) / 3.6
            if abs(dv_ms / dt) < flatline_dvdt_threshold and rows[k]["speed"] > 250.0:
                # Start of a clipping zone; extend while still flat
                cs = k
                while k + 1 <= r_end:
                    dt2 = rows[k+1]["time_s"] - rows[k]["time_s"]
                    if dt2 <= 1e-3: k += 1; continue
                    dv2 = (rows[k+1]["speed"] - rows[k]["speed"]) / 3.6
                    if abs(dv2 / dt2) >= flatline_dvdt_threshold:
                        break
                    k += 1
                ce = k
                zone_dur = rows[ce]["time_s"] - rows[cs]["time_s"]
                if zone_dur >= min_zone_s:
                    drop = rows[cs]["speed"] - min(r["speed"] for r in rows[cs:ce+1])
                    frac = (rows[cs]["time_s"] - rows[r_start]["time_s"]) / max(run_dur, 1e-3)
                    zones.append({
                        "start_s":        rows[cs]["time_s"],
                        "end_s":          rows[ce]["time_s"],
                        "drop_kmh":       float(drop),
                        "duration_s":     float(zone_dur),
                        "frac_in_straight": float(frac),
                    })
            k += 1
    return zones


def calibrate_from_telemetry(canada_2025_csv, china_2026_csv, out_path):
    """Read reference CSVs, extract calibration values, write JSON."""
    canada = _read_telemetry_rows(canada_2025_csv)
    china = _read_telemetry_rows(china_2026_csv)

    mu_long_obs   = extract_peak_decel_g(canada)
    v_apex_obs    = extract_apex_speed_ms(canada)
    clip_zones    = detect_clipping_zones(china)

    # Effective P/m ceiling: peak observed accel measured over a ~window span on
    # sustained-full-throttle sections (windowed for the same FastF1 speed-channel
    # quantization reason as extract_peak_decel_g).
    P_over_m_obs = 0.0
    n_can = len(canada)
    for i in range(n_can):
        if canada[i]["throttle"] < 99.0:
            continue
        j = i
        while j + 1 < n_can and canada[j]["time_s"] - canada[i]["time_s"] < DECEL_WINDOW_S:
            j += 1
        dt = canada[j]["time_s"] - canada[i]["time_s"]
        if dt < DECEL_WINDOW_S * 0.5:
            continue
        dv_ms = (canada[j]["speed"] - canada[i]["speed"]) / 3.6
        if dv_ms > 0.0:
            v_now = canada[i]["speed"] / 3.6
            p_over_m = (dv_ms / dt) * v_now      # W/kg, ignoring drag for ceiling
            if p_over_m > P_over_m_obs:
                P_over_m_obs = p_over_m

    payload = {
        "mu_long_obs":        round(mu_long_obs, 3),
        "P_over_m_obs":       round(P_over_m_obs, 1),
        "v_apex_hairpin_obs": round(v_apex_obs, 2),
        "clipping_zones_china_2026": clip_zones,
        "_source": {
            "canada_2025_csv": canada_2025_csv,
            "china_2026_csv":  china_2026_csv,
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[calibrate] mu_long={mu_long_obs:.2f}g  P/m={P_over_m_obs:.0f} W/kg  "
          f"v_apex={v_apex_obs:.1f} m/s  clipping zones={len(clip_zones)}")
    print(f"[calibrate] wrote {out_path}")
    return payload


# ════════════════════════════════════════════════════════════════════════
# 2026 PHYSICS BLOCK
# ════════════════════════════════════════════════════════════════════════
# Every magnitude below is justified in the spec at
# docs/superpowers/specs/2026-05-19-canada-2026-revamp-design.md §3 / §6.

# Vehicle
MASS_KG               = 768.0          # FIA 2026 min
G                     = 9.81
RHO                   = 1.225

# Power
P_ICE_MAX_W           = 400_000        # 400 kW combustion
P_MGU_DEPLOY_MAX_W    = 350_000        # MGU-K in key-accel zone
P_MGU_NORMAL_CAP_W    = 250_000        # MGU-K elsewhere (pre-Miami 2026)
P_MGU_REGEN_MAX_W     = 350_000        # MGU-K regen ceiling
E_DEPLOY_BUDGET_J     = 9_000_000      # 9 MJ/lap deploy budget
E_BATTERY_CAP_J       = 4_000_000      # 4 MJ usable store

# Aero (effective Cd·A and Cl·A) — derived from -40..-55% drag, -30% DF
CDA_STRAIGHT_M2       = 0.55
CDA_CORNER_M2         = 0.90
CL_STRAIGHT_M2        = 1.40
CL_CORNER_M2          = 2.80

# Tire grip
MU_LONG               = 1.60
MU_LAT                = 1.70

# Mode-switching
KAPPA_CORNER_THRESH   = 0.005          # |κ| > this → Corner Mode
SOC_SUPERCLIP_THRESH  = 0.30
KEY_ACCEL_WINDOW_S    = 5.0

# Initial battery and safety caps
SOC_INIT              = 1.0
V_FLOOR_MS            = 5.0            # never let v drop below this in numerics


def aero_mode(kappa):
    return "CORNER" if abs(kappa) > KAPPA_CORNER_THRESH else "STRAIGHT"


def drag_force(v, mode):
    cda = CDA_CORNER_M2 if mode == "CORNER" else CDA_STRAIGHT_M2
    return 0.5 * RHO * cda * v * v


def downforce(v, mode):
    cl = CL_CORNER_M2 if mode == "CORNER" else CL_STRAIGHT_M2
    return 0.5 * RHO * cl * v * v


def v_grip_static(kappa):
    """Max steady-state cornering speed at a station with curvature κ, using
    the friction circle with active downforce in Corner Mode:
        μ_lat (m·g + 0.5·ρ·Cl·v²) = m·v²·|κ|
        v² = μ_lat g  /  (|κ|  −  μ_lat · 0.5·ρ·Cl / m)
    If denominator ≤ 0 (long radius), v is effectively unbounded → cap large."""
    k = abs(kappa)
    if k < 1e-6:
        return 300.0   # effectively no corner cap; powertrain decides
    denom = k - MU_LAT * 0.5 * RHO * CL_CORNER_M2 / MASS_KG
    if denom <= 0.0:
        return 300.0
    return math.sqrt(MU_LAT * G / denom)


def compute_v_brake_backward(v_grip, kappa, arc, track_length_m, n_iters=3):
    """Backward pass: at each station, the speed must be low enough that the
    car can brake to v_grip(s+ds) by the time it reaches the next station.
    Friction-circle braking with active downforce."""
    n = len(v_grip)
    ds = np.diff(np.concatenate([arc, [track_length_m]]))   # closed loop
    v = v_grip.copy()
    for _ in range(n_iters):
        for i in range(n - 1, -1, -1):
            ip = (i + 1) % n
            # Lateral grip required at station ip
            a_lat_used = abs(kappa[ip]) * v[ip] * v[ip]
            mode_ip = aero_mode(kappa[ip])
            a_lat_max = MU_LAT * (G + 0.5 * RHO *
                                  (CL_CORNER_M2 if mode_ip == "CORNER" else CL_STRAIGHT_M2)
                                  / MASS_KG * v[ip] * v[ip])
            if a_lat_max <= 0.0:
                continue
            ratio_sq = min(1.0, (a_lat_used / a_lat_max) ** 2)
            a_long_grip = MU_LONG * (G + downforce(v[ip], mode_ip) / MASS_KG) * math.sqrt(1.0 - ratio_sq)
            drag_a = drag_force(v[ip], mode_ip) / MASS_KG
            a_decel = a_long_grip + drag_a   # both decelerate (brake + drag)
            v_pred = math.sqrt(max(0.0, v[ip] * v[ip] + 2.0 * a_decel * ds[i]))
            if v_pred < v[i]:
                v[i] = v_pred
    return v


def _pick_mode(soc, lap_deploy_j, dv_target, t_since_corner_exit,
               kappa_here, on_straight_with_room):
    """Return one of DEPLOY / NORMAL / CLIPPING / SUPERCLIP / REGEN."""
    if dv_target < 0.0:
        return "REGEN"
    budget_left = E_DEPLOY_BUDGET_J - lap_deploy_j
    can_deploy = (soc > 1e-4) and (budget_left > 1e3)
    if not can_deploy:
        return "CLIPPING"
    if soc < SOC_SUPERCLIP_THRESH and on_straight_with_room:
        return "SUPERCLIP"
    if t_since_corner_exit < KEY_ACCEL_WINDOW_S:
        return "DEPLOY"
    return "NORMAL"


def _power_for_mode(mode, v):
    """Total propulsion power (W) by mode. Positive = pushing; negative = harvesting."""
    if mode == "DEPLOY":
        return P_ICE_MAX_W + P_MGU_DEPLOY_MAX_W
    if mode == "NORMAL":
        return P_ICE_MAX_W + P_MGU_NORMAL_CAP_W
    if mode == "CLIPPING":
        return P_ICE_MAX_W
    if mode == "SUPERCLIP":
        return P_ICE_MAX_W - P_MGU_NORMAL_CAP_W   # ICE pushes, MGU harvests
    if mode == "REGEN":
        return 0.0   # propulsion zero; regen handled separately
    raise ValueError(mode)


def _battery_delta_for_mode(mode, dt):
    """Joules added (+) or removed (−) from battery this step."""
    if mode == "DEPLOY":
        return -P_MGU_DEPLOY_MAX_W * dt
    if mode == "NORMAL":
        return -P_MGU_NORMAL_CAP_W * dt
    if mode == "SUPERCLIP":
        return +P_MGU_NORMAL_CAP_W * dt
    if mode == "REGEN":
        return +P_MGU_REGEN_MAX_W * dt
    return 0.0


def _deploy_energy_for_mode(mode, dt):
    """Counts toward the per-lap deploy budget."""
    if mode == "DEPLOY":
        return P_MGU_DEPLOY_MAX_W * dt
    if mode == "NORMAL":
        return P_MGU_NORMAL_CAP_W * dt
    return 0.0


def _straight_room_ahead(v_brake, i, n):
    """True iff there's ≥ 3 s of straight ahead before the next braking event.
    A 'braking event' is a station where v_brake drops below the predecessor's
    v_brake by more than 5 m/s. Heuristic but cheap."""
    look_steps = min(200, n // 4)
    drop_threshold = 5.0
    for k in range(1, look_steps):
        j = (i + k) % n
        if v_brake[j] < v_brake[(j - 1) % n] - drop_threshold:
            return False
    return True


def forward_pass_energy_aware(v_grip, v_brake, kappa, arc, track_length_m,
                               v0=None, soc0=SOC_INIT):
    """Walk the lap forward, picking one of 5 modes per step, integrating v
    and battery state. Returns (v, soc, mode, power_kw, t)."""
    n = len(v_grip)
    ds = np.diff(np.concatenate([arc, [track_length_m]]))

    v_init = v0 if v0 is not None else min(v_grip[0], v_brake[0])
    v = np.full(n, v_init)
    soc_arr = np.zeros(n); soc_arr[0] = soc0
    mode_arr = ["NORMAL"] * n
    p_kw_arr = np.zeros(n)
    t_arr = np.zeros(n)

    soc = soc0
    lap_deploy_j = 0.0
    t = 0.0
    t_since_corner_exit = 0.0

    for i in range(n):
        v_cap = min(v_grip[i], v_brake[i])
        if v[i] > v_cap:
            v[i] = v_cap

        # Detect corner exit (κ falls below threshold): reset window
        in_corner = abs(kappa[i]) > KAPPA_CORNER_THRESH
        if not in_corner:
            t_since_corner_exit += 0.0   # accumulated below per step
        else:
            t_since_corner_exit = 0.0    # reset whenever we're in a corner

        mode_here = aero_mode(kappa[i])
        dv_target = v_brake[(i + 1) % n] - v[i]   # if upcoming brake forces a drop

        chosen = _pick_mode(soc, lap_deploy_j, dv_target,
                            t_since_corner_exit, kappa[i],
                            _straight_room_ahead(v_brake, i, n))
        mode_arr[i] = chosen
        soc_arr[i] = soc

        if chosen == "REGEN":
            # Brake to v_cap if needed; no propulsion. Regen energy already in v_brake
            # constraint. Just integrate time and update battery.
            v_next = min(v[(i + 1) % n], v_cap, v_brake[(i + 1) % n])
            v[(i + 1) % n] = v_next
            dt = 2.0 * ds[i] / max(v[i] + v_next, 1e-3)
            soc += _battery_delta_for_mode("REGEN", dt) / E_BATTERY_CAP_J
            soc = min(1.0, max(0.0, soc))
            p_kw_arr[i] = -P_MGU_REGEN_MAX_W / 1000.0
            t += dt
            t_arr[i] = t
            t_since_corner_exit += dt
            continue

        # Propulsion (DEPLOY / NORMAL / CLIPPING / SUPERCLIP)
        P_total = _power_for_mode(chosen, v[i])
        a_lat_used = abs(kappa[i]) * v[i] * v[i]
        a_lat_max = MU_LAT * (G + downforce(v[i], mode_here) / MASS_KG)
        ratio_sq = min(1.0, (a_lat_used / max(a_lat_max, 1e-6)) ** 2)
        a_long_grip = MU_LONG * (G + downforce(v[i], mode_here) / MASS_KG) * math.sqrt(1.0 - ratio_sq)
        a_long_power = P_total / (MASS_KG * max(v[i], V_FLOOR_MS))
        a_drag = drag_force(v[i], mode_here) / MASS_KG
        a_long = min(a_long_grip, a_long_power) - a_drag

        v_next = math.sqrt(max(V_FLOOR_MS ** 2,
                               v[i] * v[i] + 2.0 * a_long * ds[i]))
        v_next = min(v_next, v_grip[(i + 1) % n], v_brake[(i + 1) % n])
        v[(i + 1) % n] = v_next

        dt = 2.0 * ds[i] / max(v[i] + v_next, 1e-3)
        soc += _battery_delta_for_mode(chosen, dt) / E_BATTERY_CAP_J
        soc = min(1.0, max(0.0, soc))
        lap_deploy_j += _deploy_energy_for_mode(chosen, dt)
        p_kw_arr[i] = P_total / 1000.0
        t += dt
        t_arr[i] = t
        t_since_corner_exit += dt

    # final SoC capture
    soc_arr_final = soc_arr.copy()
    return v, soc_arr_final, mode_arr, p_kw_arr, t_arr


def simulate_lap(raceline, arc, kappa, track_length_m, max_iters=8, tol_v=1.0):
    """Forward-backward closure loop until v(end) ≈ v(start)."""
    n = len(raceline)
    v_grip = np.array([v_grip_static(k) for k in kappa])

    v0 = 60.0   # initial guess, refined by closure
    for it in range(max_iters):
        v_brake = compute_v_brake_backward(v_grip, kappa, arc, track_length_m)
        v, soc, mode, p_kw, t_arr = forward_pass_energy_aware(
            v_grip, v_brake, kappa, arc, track_length_m, v0=v0)
        v_end = v[-1]
        v_start = v[0]
        dv_closure = abs(v_end - v_start)
        print(f"  closure iter {it}: v0={v_start:.1f} vN={v_end:.1f} "
              f"d={dv_closure:.2f} T_lap={t_arr[-1]:.3f}s")
        if dv_closure < tol_v and it >= 1:
            print(f"  closure converged at iter {it}")
            break
        v0 = 0.5 * (v_start + v_end)   # damped midpoint update
    return v, soc, mode, p_kw, t_arr


def write_csv(out_path, v, soc, mode, p_kw, t_arr, arc, track_length_m, fps=30):
    """Resample uniformly in time at video fps and write the CSV."""
    T_lap = float(t_arr[-1])
    n_out = max(60, int(math.ceil(T_lap * fps)))
    t_out = np.linspace(0.0, T_lap, n_out, endpoint=False)

    # Make t_arr strictly monotonic (forward pass should already be)
    t_mono = np.maximum.accumulate(t_arr)

    v_out   = np.interp(t_out, t_mono, v)
    soc_out = np.interp(t_out, t_mono, soc)
    p_out   = np.interp(t_out, t_mono, p_kw)
    d_out   = np.interp(t_out, t_mono, arc)
    # categorical mode: nearest neighbour
    idx_for_t = np.searchsorted(t_mono, t_out, side="right") - 1
    idx_for_t = np.clip(idx_for_t, 0, len(mode) - 1)
    mode_out = [mode[i] for i in idx_for_t]

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "frame", "time_s", "distance", "speed",
            "throttle", "brake", "gear", "rpm",
            "soc_pct", "mode", "power_kw",
        ])
        w.writeheader()
        for i in range(n_out):
            v_kmh = v_out[i] * 3.6
            throttle = 100.0 if p_out[i] > 0.0 else 0.0
            brake    = 100.0 if mode_out[i] == "REGEN" else 0.0
            w.writerow({
                "frame":      i,
                "time_s":     round(float(t_out[i]), 4),
                "distance":   round(float(d_out[i]), 3),
                "speed":      round(float(v_kmh), 3),
                "throttle":   round(throttle, 2),
                "brake":      round(brake, 2),
                "gear":       0,
                "rpm":        0,
                "soc_pct":    round(float(soc_out[i] * 100.0), 2),
                "mode":       mode_out[i],
                "power_kw":   round(float(p_out[i]), 2),
            })
    print(f"[sim] wrote {n_out} rows -> {out_path}")


def main():
    # Status lines contain Unicode (α, ×, κ); force UTF-8 stdout so they
    # don't crash on Windows' default cp1252 console codec.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--outline", required=True)
    ap.add_argument("--raceline-out", required=True)
    ap.add_argument("--csv-out", required=True)
    args = ap.parse_args()

    with open(args.outline, encoding="utf-8") as f:
        data = json.load(f)
    outer_raw = np.array(data["outer"], dtype=float)
    inner_raw = np.array(data["inner"], dtype=float)
    print(f"[sim] outline loaded: outer={len(outer_raw)} inner={len(inner_raw)}")

    raceline, arc, kappa, total_len = build_raceline(outer_raw, inner_raw)
    print(f"[sim] raceline: {len(raceline)} pts, {total_len:.0f} m, "
          f"|κ|max={np.abs(kappa).max():.4f}")

    os.makedirs(os.path.dirname(os.path.abspath(args.raceline_out)), exist_ok=True)
    with open(args.raceline_out, "w", encoding="utf-8") as f:
        json.dump({
            "raceline":       raceline.tolist(),
            "arc_length":     arc.tolist(),
            "kappa":          kappa.tolist(),
            "track_length_m": float(total_len),
        }, f)
    print(f"[sim] wrote raceline -> {args.raceline_out}")

    v, soc, mode, p_kw, t_arr = simulate_lap(raceline, arc, kappa, total_len)
    write_csv(args.csv_out, v, soc, mode, p_kw, t_arr, arc, total_len, fps=30)


if __name__ == "__main__":
    main()
