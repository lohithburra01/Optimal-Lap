import bpy
import os
import sys
import site
import subprocess
import tempfile
import csv
import math
import importlib.util
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import (
    StringProperty, EnumProperty, FloatProperty,
    BoolProperty, IntProperty, PointerProperty
)

bl_info = {
    "name": "F1 Track Visualizer",
    "author": "Lohith Burra",
    "version": (3, 2),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > F1 Track Tab",
    "description": "Visualize F1 tracks with centerline, style-based racing line, and Kabsch alignment",
    "category": "3D View",
}

# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCY MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def get_modules_path():
    # Isolated dependencies dir for this addon. Living under modules/ but in
    # our own subfolder lets us install/upgrade/clean without colliding with
    # other addons' deps (or leftover stale wheels from earlier failed runs).
    return bpy.utils.user_resource(
        "SCRIPTS", path="modules/f1_track_visualizer_deps", create=True
    )

def append_modules_to_sys_path(modules_path):
    # Insert at the FRONT so our isolated wheels shadow any stale copies
    # that earlier install attempts left in <user>/modules/.
    if modules_path in sys.path:
        sys.path.remove(modules_path)
    sys.path.insert(0, modules_path)
    site.addsitedir(modules_path)

def check_dependencies():
    # quadprog before trajectory_planning_helpers, and pinned: tph pulls
    # quadprog as a transitive dep, and unpinned latest has no cp311
    # win_amd64 wheel — pip would fall back to a source build that fails
    # against Blender's header-less Python. Pinning >=0.1.12 forces a
    # version with a published wheel.
    required = {
        "fastf1": "fastf1",
        "pandas": "pandas",
        "scipy":  "scipy",
        "quadprog": "quadprog>=0.1.12",
        "trajectory_planning_helpers": "trajectory-planning-helpers",
    }
    missing = []
    for module_name, pip_name in required.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(pip_name)
    return missing

def install_package_to_blender(package, modules_path):
    # --only-binary + --prefer-binary so pip refuses source builds —
    # Blender's bundled Python ships without development headers, so any
    # C extension that has to compile from source will fail.
    # --upgrade is still needed: without it pip skips existing package
    # dirs and we end up with old code paired with new dist-info metadata.
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "--upgrade", "--target", modules_path,
            "--only-binary=:all:", "--prefer-binary",
            package
        ])
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {package}: {e}")
        return False

def dependencies_available():
    return len(check_dependencies()) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# NUMPY UTILITY FUNCTIONS (used by centerline, racing line, alignment)
# ═══════════════════════════════════════════════════════════════════════════════

def _resample_equidistant(coords, n):
    import numpy as np
    from scipy.interpolate import interp1d

    mask = np.ones(len(coords), dtype=bool)
    for i in range(1, len(coords)):
        if np.linalg.norm(coords[i] - coords[i - 1]) < 1e-10:
            mask[i] = False
    coords = coords[mask]

    if len(coords) < 4:
        raise ValueError(f"Too few unique points ({len(coords)}) for resampling")

    closed = np.vstack((coords, coords[0]))
    diffs = closed[1:] - closed[:-1]
    dists = np.linalg.norm(diffs, axis=1)
    cum = np.concatenate(([0], np.cumsum(dists)))
    total = cum[-1]

    if total < 1e-10:
        raise ValueError("Path has zero total length")

    targets = np.linspace(0, total, n, endpoint=False)

    m = len(coords)
    ext_coords = np.vstack((coords, coords, coords))
    ext_cum = np.concatenate((cum[:-1] - total, cum[:-1], cum[:-1] + total))

    fx = interp1d(ext_cum, ext_coords[:, 0], kind='cubic')
    fy = interp1d(ext_cum, ext_coords[:, 1], kind='cubic')

    out = np.zeros((n, 2))
    out[:, 0] = fx(targets)
    out[:, 1] = fy(targets)
    return out


def _resample_equidistant_3d(coords, n):
    import numpy as np
    from scipy.interpolate import interp1d

    mask = np.ones(len(coords), dtype=bool)
    for i in range(1, len(coords)):
        if np.linalg.norm(coords[i] - coords[i - 1]) < 1e-10:
            mask[i] = False
    coords = coords[mask]

    if len(coords) < 4:
        raise ValueError(f"Too few unique points ({len(coords)}) for resampling")

    closed = np.vstack((coords, coords[0]))
    diffs = closed[1:] - closed[:-1]
    dists = np.linalg.norm(diffs, axis=1)
    cum = np.concatenate(([0], np.cumsum(dists)))
    total = cum[-1]

    if total < 1e-10:
        raise ValueError("Path has zero total length")

    targets = np.linspace(0, total, n, endpoint=False)

    m = len(coords)
    ext_coords = np.vstack((coords, coords, coords))
    ext_cum = np.concatenate((cum[:-1] - total, cum[:-1], cum[:-1] + total))

    interps = []
    for axis in range(3):
        interps.append(interp1d(ext_cum, ext_coords[:, axis], kind='cubic'))

    out = np.zeros((n, 3))
    for axis in range(3):
        out[:, axis] = interps[axis](targets)
    return out


def _kabsch_alignment(P, Q):
    import numpy as np

    P = np.asarray(P, dtype=float)
    Q = np.asarray(Q, dtype=float)
    assert P.shape == Q.shape

    centroid_P = P.mean(axis=0)
    centroid_Q = Q.mean(axis=0)

    Pc = P - centroid_P
    Qc = Q - centroid_Q

    H = Pc.T @ Qc
    U, S, Vt = np.linalg.svd(H)

    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T

    t = centroid_Q - R @ centroid_P
    P_aligned = (R @ P.T).T + t
    return R, t, P_aligned


# ═══════════════════════════════════════════════════════════════════════════════
# STYLE LAYER — corner detection + parametric α_style builder
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_corners_on_centerline(coords, kappa_hi_frac=0.25, kappa_lo_frac=0.08, min_corner_len=6):
    """
    Segment a closed 2D centerline into corners with hysteresis on |κ|.

    Returns (corners, corner_id, phase, kappa_sign):
        corners     list of dicts {entry, apex, exit, kappa_sign}
        corner_id   (n,) int  — corner index per station, -1 on straights
        phase       (n,) float — [0,1] along corner (0=entry, 1=exit), 0 on straights
        kappa_sign  (n,) float — +1 inside left corner, -1 inside right corner, 0 straight
    """
    import numpy as np
    from scipy.ndimage import gaussian_filter1d

    n = len(coords)

    tang = np.zeros((n, 2))
    for i in range(n):
        d = coords[(i + 3) % n] - coords[(i - 3) % n]
        nm = np.linalg.norm(d)
        tang[i] = d / nm if nm > 1e-8 else np.array([1.0, 0.0])

    kappa = np.zeros(n)
    for i in range(n):
        t1 = tang[i]
        t2 = tang[(i + 1) % n]
        cross = t1[0] * t2[1] - t1[1] * t2[0]
        dot = float(np.clip(np.dot(t1, t2), -1.0, 1.0))
        kappa[i] = math.copysign(math.acos(dot), cross)

    kappa_s = gaussian_filter1d(np.tile(kappa, 3), sigma=5.0)[n:2 * n]
    kappa_abs = np.abs(kappa_s)
    kappa_max = float(kappa_abs.max())
    if kappa_max < 1e-6:
        return [], np.full(n, -1, dtype=int), np.zeros(n), np.zeros(n)

    kappa_hi = kappa_hi_frac * kappa_max
    kappa_lo = kappa_lo_frac * kappa_max
    above_hi = kappa_abs > kappa_hi
    above_lo = kappa_abs > kappa_lo

    # Roll so index 0 is on a straight (simplifies cyclic corner walks)
    straights = np.where(~above_lo)[0]
    if len(straights) == 0:
        apex = int(np.argmax(kappa_abs))
        corners = [{'entry': 0, 'apex': apex, 'exit': n - 1,
                    'kappa_sign': int(math.copysign(1, kappa_s[apex]))}]
        return (corners,
                np.zeros(n, dtype=int),
                np.linspace(0.0, 1.0, n),
                np.full(n, corners[0]['kappa_sign'], dtype=float))

    roll = int(straights[0])
    above_hi_r = np.roll(above_hi, -roll)
    above_lo_r = np.roll(above_lo, -roll)
    kappa_abs_r = np.roll(kappa_abs, -roll)
    kappa_s_r = np.roll(kappa_s, -roll)

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

            if exit_ - entry + 1 >= min_corner_len:
                apex_local = core_start + int(np.argmax(kappa_abs_r[core_start:core_end + 1]))
                corners.append({
                    '_entry_r': entry,
                    '_apex_r': apex_local,
                    '_exit_r': exit_,
                    'L': exit_ - entry + 1,
                    'kappa_sign': int(math.copysign(1, kappa_s_r[apex_local])),
                })
        else:
            i += 1

    # Build per-station arrays in rolled coords, then unroll
    corner_id_r = np.full(n, -1, dtype=int)
    phase_r = np.zeros(n)
    sign_arr_r = np.zeros(n)
    for ci, c in enumerate(corners):
        entry, exit_ = c['_entry_r'], c['_exit_r']
        L = exit_ - entry + 1
        for k, s in enumerate(range(entry, exit_ + 1)):
            corner_id_r[s] = ci
            phase_r[s] = k / max(L - 1, 1)
            sign_arr_r[s] = c['kappa_sign']

    corner_id = np.roll(corner_id_r, roll)
    phase = np.roll(phase_r, roll)
    sign_arr = np.roll(sign_arr_r, roll)

    for c in corners:
        c['entry'] = (c.pop('_entry_r') + roll) % n
        c['apex']  = (c.pop('_apex_r')  + roll) % n
        c['exit']  = (c.pop('_exit_r')  + roll) % n

    return corners, corner_id, phase, sign_arr


def _compute_alpha_style(corners, corner_id, phase, kappa_sign, wr_safe, wl_safe, params,
                         corner_overrides=None):
    """
    Build lateral-offset warp α_style(s) from style params.

    Convention: positive α = RIGHT (TUMFTM right-normal), negative = LEFT.
    Inside of a left corner (kappa_sign=+1) is LEFT → apex pull is negative α.

    Anti-wobble treatment:
      (A) Entry/exit anchors shift with apex_phase to prevent bump overlap.
      (B) σ adapts to corner length and shrinks near the apex to prevent
          overlap when anchors compress (e.g. late apex → exit anchor near apex).
      (C) Per-station |α_style| capped at 70% of available width before the
          hard clip, so stacked bumps cannot saturate the boundary clipper.

    corner_overrides (optional): list of per-corner dicts in lap order, each
        with apex_phase / apex_tightness / vu_shape. Used when its length
        matches len(corners) — those three params are then per-corner instead
        of lap-wide. Other params (widths, smoothness, lr_asymmetry, master)
        remain global.
    """
    import numpy as np
    from scipy.ndimage import gaussian_filter1d

    n = len(corner_id)
    alpha = np.zeros(n)

    master = float(params['master'])
    if master < 1e-6:
        return alpha

    entry_w = float(params['entry_width'])
    exit_w  = float(params['exit_width'])
    lr_asym = float(params['lr_asymmetry'])

    # Build per-corner derivations. If corner_overrides is consumable, the
    # driver's per-corner apex_phase/apex_tightness/vu_shape replace the
    # global lap-wide values for that corner. Otherwise the globals are
    # broadcast to every corner (legacy behaviour).
    Nc = len(corners)
    use_overrides = (
        isinstance(corner_overrides, list)
        and len(corner_overrides) == Nc
        and Nc > 0
    )

    g_ap = float(params['apex_phase'])
    g_at = float(params['apex_tightness'])
    g_vu = float(params['vu_shape'])

    apex_target_c  = np.zeros(Nc)
    vu_bias_c      = np.zeros(Nc)
    apex_tight_c   = np.zeros(Nc)
    entry_anchor_c = np.zeros(Nc)
    exit_anchor_c  = np.zeros(Nc)
    half_gap_min_c = np.zeros(Nc)

    for ci in range(Nc):
        if use_overrides:
            co = corner_overrides[ci] or {}
            ap = float(co.get('apex_phase',     g_ap))
            at = float(co.get('apex_tightness', g_at))
            vu = float(co.get('vu_shape',       g_vu))
        else:
            ap, at, vu = g_ap, g_at, g_vu

        ap_t = 0.5 + 0.35 * ap                                  # [0.15, 0.85]
        ea   = max(0.05, ap_t - 0.35)                           # (A) anchors follow apex
        xa   = min(0.95, ap_t + 0.35)
        hg   = max(1e-3, min(ap_t - ea, xa - ap_t))

        apex_target_c[ci]  = ap_t
        vu_bias_c[ci]      = (vu + 1.0) * 0.5                   # 0=V, 1=U
        apex_tight_c[ci]   = at
        entry_anchor_c[ci] = ea
        exit_anchor_c[ci]  = xa
        half_gap_min_c[ci] = hg

    for i in range(n):
        cid = int(corner_id[i])
        if cid < 0:
            continue

        phi = float(phase[i])
        ks = float(kappa_sign[i])
        in_dir = -ks
        out_dir = ks

        w_in  = wr_safe[i] if in_dir > 0 else wl_safe[i]
        w_out = wr_safe[i] if out_dir > 0 else wl_safe[i]
        w_sym = min(w_in, w_out)

        apex_target  = float(apex_target_c[cid])
        vu_bias      = float(vu_bias_c[cid])
        apex_tight   = float(apex_tight_c[cid])
        entry_anchor = float(entry_anchor_c[cid])
        exit_anchor  = float(exit_anchor_c[cid])
        half_gap_min = float(half_gap_min_c[cid])

        # (B) Per-corner σ: length-adaptive base, clamped so bumps don't overlap.
        L = int(corners[cid]['L'])
        L_scale = math.sqrt(max(L, 10) / 30.0)            # sqrt so extremes stay tame
        base_apex = max(0.07, min(0.15, 0.10 * L_scale))
        # V-line: narrow apex bump (sharp); U-line: broad apex bump.
        base_apex *= (0.75 + 0.50 * vu_bias)              # V:0.75× … U:1.25×
        sigma_apex = min(base_apex, 0.45 * half_gap_min)  # 2σ < half-gap
        sigma_apex = max(sigma_apex, 0.04)
        sigma_ee = max(0.05, min(0.10, 0.07 * L_scale))

        apex_mag  = apex_tight * 0.80 * w_in  * math.exp(-((phi - apex_target)  ** 2) / (2 * sigma_apex ** 2))
        entry_mag = entry_w    * 0.70 * w_sym * math.exp(-((phi - entry_anchor) ** 2) / (2 * sigma_ee   ** 2))
        exit_mag  = exit_w     * 0.70 * w_sym * math.exp(-((phi - exit_anchor)  ** 2) / (2 * sigma_ee   ** 2))

        a = in_dir * apex_mag + out_dir * entry_mag + out_dir * exit_mag
        a *= (1.0 + lr_asym * ks)
        alpha[i] = a

    # Straight bias — look AHEAD to next corner's outside direction
    straight_b = float(params['straight_bias'])
    if abs(straight_b) > 1e-6:
        next_ks = np.zeros(n)
        last = 0.0
        for i in range(2 * n - 1, -1, -1):
            idx = i % n
            if corner_id[idx] >= 0:
                last = float(kappa_sign[idx])
            next_ks[idx] = last

        for i in range(n):
            if corner_id[i] >= 0:
                continue
            out_dir = 1 if next_ks[i] >= 0 else -1
            w_o = wr_safe[i] if out_dir > 0 else wl_safe[i]
            alpha[i] += straight_b * 0.40 * w_o * out_dir

    alpha *= master

    # (C) Soft cap at 70% of available width BEFORE the hard clip runs.
    # Leaves 30% headroom for smoothness blur without triggering clip kinks.
    alpha = np.clip(alpha, -0.70 * wl_safe, 0.70 * wr_safe)

    sigma = 1.0 + 10.0 * float(params['smoothness'])
    alpha = gaussian_filter1d(np.concatenate([alpha, alpha, alpha]), sigma=sigma)[n:2 * n]

    return alpha


# ═══════════════════════════════════════════════════════════════════════════════
# PROPERTIES
# ═══════════════════════════════════════════════════════════════════════════════

class F1TrackProperties(PropertyGroup):
    # --- Telemetry fetch ---
    season: StringProperty(name="Season", default="2023")
    grand_prix: StringProperty(name="Grand Prix", default="Bahrain")
    session_type: EnumProperty(
        name="Session",
        items=[
            ('R', "Race", ""), ('Q', "Qualifying", ""),
            ('FP1', "FP1", ""), ('FP2', "FP2", ""), ('FP3', "FP3", ""),
        ],
        default='R'
    )
    driver_id: StringProperty(name="Driver", default="VER")
    cache_dir: StringProperty(
        name="Cache Dir",
        default=os.path.join(tempfile.gettempdir(), "fastf1_cache"),
        subtype='DIR_PATH'
    )
    csv_file_path: StringProperty(name="CSV File", default="", subtype='FILE_PATH')

    # --- Track curve creation ---
    scale_factor: FloatProperty(name="Scale", default=10.0, min=0.1, max=100.0)
    curve_type: EnumProperty(
        name="Curve Type",
        items=[('NURBS', "NURBS", ""), ('BEZIER', "Bezier", "")],
        default='NURBS'
    )
    track_thickness: FloatProperty(name="Thickness", default=0.05, min=0.01, max=1.0)
    curve_resolution: FloatProperty(name="Resolution", default=12, min=1, max=64)

    # --- Track mesh (eyedropper) ---
    track_mesh: PointerProperty(
        name="Track Mesh",
        description="Select the track road mesh object",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH'
    )

    # --- Centerline ---
    centerline_iterations: IntProperty(
        name="Iterations", default=5, min=1, max=10,
        description="Number of centerline refinement iterations"
    )
    centerline_ray_step: FloatProperty(
        name="Ray Step", default=0.15, min=0.05, max=1.0,
        description="Step size for edge-detection raycasts (BU)"
    )
    centerline_max_width: FloatProperty(
        name="Max Width", default=30.0, min=5.0, max=100.0,
        description="Maximum half-width to search for track edges (BU)"
    )
    centerline_smooth_sigma: FloatProperty(
        name="Smooth Sigma", default=2.0, min=0.5, max=10.0,
        description="Gaussian sigma for centerline smoothing"
    )

    # --- Racing line constraints ---
    racing_line_inset: FloatProperty(
        name="Base Edge Inset", default=0.3, min=0.0, max=2.0,
        description="Safety inset from track edges (BU)"
    )
    racing_line_kappa_bound: FloatProperty(
        name="Base Max Curvature", default=0.5, min=0.05, max=2.0,
        description="Maximum curvature bound (rad/m)"
    )
    racing_line_veh_width: FloatProperty(
        name="Vehicle Width", default=2.0, min=0.5, max=4.0,
        description="Vehicle width in meters (F1 car ~2.0m)"
    )
    racing_line_stepsize: FloatProperty(
        name="Interp Stepsize", default=2.0, min=0.5, max=10.0,
        description="Interpolation step size in meters for final raceline"
    )

    # --- Style Layer (parametric post-warp on Q_RACING_LINE) ---
    # Designed so per-corner telemetry-driven values can later replace the global sliders.
    style_enabled: BoolProperty(
        name="Enable Style Layer", default=True,
        description="If off, Q_RACING_LINE_STYLED won't be generated"
    )
    style_master: FloatProperty(
        name="Master Strength", default=1.0, min=0.0, max=1.0,
        description="0 = identical to Q_RACING_LINE, 1 = full style effect"
    )
    style_apex_phase: FloatProperty(
        name="Apex Phase", default=0.0, min=-1.0, max=1.0,
        description="-1 early apex (tight-in, wide-out) ↔ +1 late apex (wide-in, tight-out for exit speed)"
    )
    style_apex_tightness: FloatProperty(
        name="Apex Tightness", default=0.5, min=0.0, max=1.0,
        description="0 conservative margin from inside edge ↔ 1 kerb-riding aggressive"
    )
    style_entry_width: FloatProperty(
        name="Entry Width", default=0.0, min=-1.0, max=1.0,
        description="-1 tight entry ↔ +1 wide entry"
    )
    style_exit_width: FloatProperty(
        name="Exit Width", default=0.0, min=-1.0, max=1.0,
        description="-1 tight exit ↔ +1 wide track-out"
    )
    style_vu_shape: FloatProperty(
        name="V ↔ U Shape", default=0.0, min=-1.0, max=1.0,
        description="-1 V-line (sharp apex, late-brake/early-throttle) ↔ +1 U-line (broad arc, momentum)"
    )
    style_straight_bias: FloatProperty(
        name="Straight Bias", default=0.0, min=-1.0, max=1.0,
        description="-1 toward inside of next corner ↔ +1 toward outside (setup position)"
    )
    style_smoothness: FloatProperty(
        name="Smoothness", default=0.3, min=0.0, max=1.0,
        description="Low-pass filter on α_style — higher = smoother transitions"
    )
    style_lr_asymmetry: FloatProperty(
        name="L/R Asymmetry", default=0.0, min=-1.0, max=1.0,
        description="+1 apply style only to left corners, -1 only to right, 0 symmetric"
    )
    style_json_path: StringProperty(
        name="Style JSON", default="", subtype='FILE_PATH',
        description="Path to style params JSON exported by the F1 Race Replay Studio addon"
    )

    # --- Alignment ---
    alignment_target_curve: PointerProperty(
        name="Target Line",
        description="Pick any Q_RACING_LINE* curve in the scene (eyedropper). Used by the single-path Align/Reshape button.",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'CURVE' and obj.name.startswith("Q_RACING_LINE")
    )
    overwrite_source_path: BoolProperty(
        name="Overwrite Source Curve",
        default=True,
        description="Replace the Driving Path's own geometry with the aligned result, so any follow-path rig on that curve picks up the new shape automatically. Turn OFF if you want a preview-only align without modifying the source."
    )
    alignment_samples: IntProperty(
        name="Resample Points", default=500, min=50, max=5000,
        description="Number of equidistant points for alignment resampling"
    )
    alignment_blend: FloatProperty(
        name="Racing Line Blend", default=0.0, min=0.0, max=1.0,
        description="0.0 = Raw Driver Path (Kabsch only). 1.0 = Fully snapped to Q_RACING_LINE"
    )

    # --- Source driving path ---
    driving_path: PointerProperty(
        name="Driving Path",
        description="Select the raw telemetry driving path curve",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'CURVE'
    )


# ═══════════════════════════════════════════════════════════════════════════════
# OPERATORS
# ═══════════════════════════════════════════════════════════════════════════════

class OBJECT_OT_InstallF1Dependencies(Operator):
    bl_idname = "object.install_f1_dependencies"
    bl_label = "Install Dependencies"
    bl_description = "Install fastf1, pandas, scipy"

    def execute(self, context):
        modules_path = get_modules_path()
        append_modules_to_sys_path(modules_path)
        missing = check_dependencies()
        if not missing:
            self.report({'INFO'}, "All dependencies already installed!")
            return {'FINISHED'}

        ok = 0
        for pkg in missing:
            self.report({'INFO'}, f"Installing {pkg}...")
            if install_package_to_blender(pkg, modules_path):
                ok += 1
                self.report({'INFO'}, f"Installed {pkg}")
            else:
                self.report({'ERROR'},
                    f"Failed: {pkg}. If error mentions 'Access is denied' on "
                    f"a .pyd file, close Blender and re-run install from a "
                    f"fresh session before importing the addon's panel.")

        if ok == len(missing):
            self.report({'INFO'}, "All installed! Restart Blender if needed.")
        else:
            self.report({'WARNING'}, f"{ok}/{len(missing)} installed")
        return {'FINISHED'}


class OBJECT_OT_FetchF1Data(Operator):
    bl_idname = "object.fetch_f1_data"
    bl_label = "Fetch Telemetry"
    bl_description = "Fetch FastF1 telemetry → CSV"

    def execute(self, context):
        if not dependencies_available():
            self.report({'ERROR'}, "Install dependencies first")
            return {'CANCELLED'}

        props = context.scene.f1_track_props
        try:
            import fastf1
            import pandas as pd

            os.makedirs(props.cache_dir, exist_ok=True)
            fastf1.Cache.enable_cache(props.cache_dir)

            session = fastf1.get_session(int(props.season), props.grand_prix, props.session_type)
            session.load()

            laps = session.laps.pick_driver(props.driver_id)
            if laps.empty:
                self.report({'ERROR'}, f"No data for {props.driver_id}")
                return {'CANCELLED'}

            fastest = laps.loc[laps['LapTime'].idxmin()]
            telem = fastest.get_telemetry()
            telem['Time'] = telem['Time'].dt.total_seconds()

            if 'X' not in telem.columns or 'Y' not in telem.columns:
                self.report({'ERROR'}, "No X/Y in telemetry")
                return {'CANCELLED'}
            if 'Z' not in telem.columns:
                telem['Z'] = 0

            cols = ['Time', 'X', 'Y', 'Z']
            if 'Speed' in telem.columns:
                cols.append('Speed')

            base = bpy.path.abspath("//")
            if base == "":
                base = tempfile.gettempdir()
            csv_path = os.path.join(base, f"telemetry_{props.driver_id}_{props.grand_prix}_{props.season}.csv")
            telem[cols].to_csv(csv_path, index=False)
            props.csv_file_path = csv_path

            self.report({'INFO'}, f"Saved: {csv_path}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


class OBJECT_OT_CreateTrackFromCSV(Operator):
    bl_idname = "object.create_track_from_csv"
    bl_label = "Create Driving Path"
    bl_description = "Create curve from CSV telemetry data"

    def execute(self, context):
        props = context.scene.f1_track_props
        if not props.csv_file_path:
            self.report({'ERROR'}, "No CSV file set")
            return {'CANCELLED'}

        try:
            coordinates = []
            with open(props.csv_file_path, 'r') as f:
                reader = csv.reader(f)
                header = next(reader)
                idx = {}
                for i, col in enumerate(header):
                    idx[col.upper()] = i

                if 'X' not in idx or 'Y' not in idx:
                    self.report({'ERROR'}, "CSV needs X and Y columns")
                    return {'CANCELLED'}

                for row in reader:
                    x = float(row[idx['X']])
                    y = float(row[idx['Y']])
                    z = float(row[idx.get('Z', idx['X'])]) if 'Z' in idx else 0.0
                    if 'Z' not in idx:
                        z = 0.0
                    coordinates.append((x, y, z))

            # Shift to near origin
            min_x = min(c[0] for c in coordinates)
            min_y = min(c[1] for c in coordinates)
            min_z = min(c[2] for c in coordinates)
            coordinates = [(x - min_x, y - min_y, z - min_z) for x, y, z in coordinates]

            sf = props.scale_factor
            coordinates = [(x * sf, y * sf, z * sf) for x, y, z in coordinates]

            curve_name = f"driving_path_{props.driver_id}_{props.grand_prix}_{props.season}"

            if curve_name in bpy.data.objects:
                old = bpy.data.objects[curve_name]
                bpy.data.objects.remove(old, do_unlink=True)
            if curve_name in bpy.data.curves:
                bpy.data.curves.remove(bpy.data.curves[curve_name])

            curve_data = bpy.data.curves.new(name=curve_name, type='CURVE')
            curve_data.dimensions = '3D'

            if props.curve_type == 'NURBS':
                spline = curve_data.splines.new(type='NURBS')
                spline.points.add(len(coordinates) - 1)
                for i, (x, y, z) in enumerate(coordinates):
                    spline.points[i].co = (x, y, z, 1.0)
                spline.use_endpoint_u = True
                spline.order_u = 4
                spline.resolution_u = int(props.curve_resolution)

                start, end = coordinates[0], coordinates[-1]
                dist = sum((a - b) ** 2 for a, b in zip(start, end)) ** 0.5
                if dist < 10.0:
                    spline.use_cyclic_u = True
            else:
                spline = curve_data.splines.new(type='BEZIER')
                spline.bezier_points.add(len(coordinates) - 1)
                for i, (x, y, z) in enumerate(coordinates):
                    bp = spline.bezier_points[i]
                    bp.co = (x, y, z)
                    bp.handle_left_type = 'AUTO'
                    bp.handle_right_type = 'AUTO'

                start, end = coordinates[0], coordinates[-1]
                dist = sum((a - b) ** 2 for a, b in zip(start, end)) ** 0.5
                if dist < 10.0:
                    spline.use_cyclic_u = True

            curve_data.bevel_depth = props.track_thickness
            curve_data.bevel_resolution = 4

            obj = bpy.data.objects.new(curve_name, curve_data)
            bpy.context.collection.objects.link(obj)

            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj

            props.driving_path = obj

            self.report({'INFO'}, f"Created: {curve_name}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


class OBJECT_OT_GenerateCenterline(Operator):
    bl_idname = "object.generate_centerline"
    bl_label = "Generate Centerline"
    bl_description = "Generate TRACK_CENTER_FIXED purely from track mesh geometry"

    @staticmethod
    def _point_on_track(track, inv, ray_dir, x, y):
        from mathutils import Vector as Vec
        origin = Vec((x, y, 10000.0))
        hit, _, _, _ = track.ray_cast(inv @ origin, ray_dir)
        return hit

    @staticmethod
    def _find_edge_dist(track, inv, ray_dir, pt, direction, coarse_step, max_dist):
        from mathutils import Vector as Vec
        last_hit_d = 0.0
        first_miss_d = -1.0
        steps = int(max_dist / coarse_step)

        for si in range(1, steps + 1):
            d_raw = si * coarse_step
            test = pt + direction * d_raw
            origin = Vec((test[0], test[1], 10000.0))
            hit, _, _, _ = track.ray_cast(inv @ origin, ray_dir)
            if hit:
                last_hit_d = d_raw
            else:
                first_miss_d = d_raw
                break

        if first_miss_d < 0:
            return max_dist

        lo, hi = last_hit_d, first_miss_d
        for _ in range(10):
            mid = (lo + hi) * 0.5
            test = pt + direction * mid
            origin = Vec((test[0], test[1], 10000.0))
            hit, _, _, _ = track.ray_cast(inv @ origin, ray_dir)
            if hit:
                lo = mid
            else:
                hi = mid
        return lo

    @staticmethod
    def _walk_track_centerline(track, inv, ray_dir, start_xy, n_target,
                                coarse_step, max_width, step_size):
        import numpy as np
        from mathutils import Vector as Vec

        find_edge = OBJECT_OT_GenerateCenterline._find_edge_dist
        on_track = OBJECT_OT_GenerateCenterline._point_on_track

        pt = np.array(start_xy, dtype=float)
        best_angle = 0.0
        best_width = float('inf')

        for angle_deg in range(0, 180, 5):
            angle = math.radians(angle_deg)
            direction = np.array([math.cos(angle), math.sin(angle)])
            dl = find_edge(track, inv, ray_dir, pt, direction, coarse_step, max_width)
            dr = find_edge(track, inv, ray_dir, pt, -direction, coarse_step, max_width)
            width = dl + dr
            if 1.0 < width < best_width:
                best_width = width
                best_angle = angle

        width_dir = np.array([math.cos(best_angle), math.sin(best_angle)])
        fwd = np.array([-width_dir[1], width_dir[0]])

        dl = find_edge(track, inv, ray_dir, pt, width_dir, coarse_step, max_width)
        dr = find_edge(track, inv, ray_dir, pt, -width_dir, coarse_step, max_width)
        shift = (dl - dr) * 0.5
        pt = pt + width_dir * shift

        points = [pt.copy()]
        max_points = n_target * 3 

        for step_i in range(1, max_points):
            candidate = pt + fwd * step_size

            if not on_track(track, inv, ray_dir, candidate[0], candidate[1]):
                found = False
                for angle_offset in range(5, 91, 5):
                    for sign in [1, -1]:
                        angle = math.radians(angle_offset * sign)
                        rot_fwd = np.array([
                            fwd[0] * math.cos(angle) - fwd[1] * math.sin(angle),
                            fwd[0] * math.sin(angle) + fwd[1] * math.cos(angle)
                        ])
                        test = pt + rot_fwd * step_size
                        if on_track(track, inv, ray_dir, test[0], test[1]):
                            candidate = test
                            fwd = rot_fwd
                            found = True
                            break
                    if found:
                        break
                if not found:
                    print(f"Walk stopped at step {step_i}: can't find forward direction")
                    break

            pt = candidate
            # Find true width direction by scanning angles around fwd-perpendicular
            base_left = np.array([-fwd[1], fwd[0]])
            best_width_dir = base_left
            best_total_width = float('inf')
            for angle_deg in range(-45, 46, 5):
                angle = math.radians(angle_deg)
                test_dir = np.array([
                    base_left[0] * math.cos(angle) - base_left[1] * math.sin(angle),
                    base_left[0] * math.sin(angle) + base_left[1] * math.cos(angle)
                ])
                tdl = find_edge(track, inv, ray_dir, pt, test_dir, coarse_step, max_width)
                tdr = find_edge(track, inv, ray_dir, pt, -test_dir, coarse_step, max_width)
                total = tdl + tdr
                if 0.5 < total < best_total_width:
                    best_total_width = total
                    best_width_dir = test_dir
            dl = find_edge(track, inv, ray_dir, pt, best_width_dir, coarse_step, max_width)
            dr = find_edge(track, inv, ray_dir, pt, -best_width_dir, coarse_step, max_width)
            shift = (dl - dr) * 0.5
            pt = pt + best_width_dir * shift

            if not on_track(track, inv, ray_dir, pt[0], pt[1]):
                pt = candidate

            if len(points) >= 3:
                recent = np.array(points[-3:])
                new_fwd = pt - recent[0]
                nm = np.linalg.norm(new_fwd)
                if nm > 1e-8:
                    new_fwd = new_fwd / nm
                    fwd = 0.4 * new_fwd + 0.6 * fwd
                    nm = np.linalg.norm(fwd)
                    if nm > 1e-8:
                        fwd = fwd / nm

            points.append(pt.copy())

            if step_i > n_target // 2:
                dist_to_start = np.linalg.norm(pt - points[0])
                if dist_to_start < step_size * 2.0:
                    print(f"Loop closed at step {step_i}")
                    break

        return np.array(points)

    def execute(self, context):
        if not dependencies_available():
            self.report({'ERROR'}, "Install dependencies first")
            return {'CANCELLED'}

        import numpy as np
        from scipy.interpolate import interp1d
        from scipy.ndimage import gaussian_filter1d, median_filter
        from mathutils import Vector

        props = context.scene.f1_track_props
        track = props.track_mesh

        if not track:
            self.report({'ERROR'}, "Select a Track Mesh (eyedropper)")
            return {'CANCELLED'}
        if track.type != 'MESH':
            self.report({'ERROR'}, "Track Mesh must be a mesh object")
            return {'CANCELLED'}

        inv = track.matrix_world.inverted()
        ray_dir = (inv.to_3x3() @ Vector((0, 0, -1))).normalized()

        coarse_step = props.centerline_ray_step
        max_width = props.centerline_max_width
        iterations = props.centerline_iterations
        sigma = props.centerline_smooth_sigma

        bb = [track.matrix_world @ Vector(c) for c in track.bound_box]
        min_x = min(v.x for v in bb)
        max_x = max(v.x for v in bb)
        min_y = min(v.y for v in bb)
        max_y = max(v.y for v in bb)

        start_xy = None
        scan_res = 50
        for ix in range(scan_res):
            for iy in range(scan_res):
                sx = min_x + (max_x - min_x) * (ix + 0.5) / scan_res
                sy = min_y + (max_y - min_y) * (iy + 0.5) / scan_res
                if self._point_on_track(track, inv, ray_dir, sx, sy):
                    start_xy = (sx, sy)
                    break
            if start_xy:
                break

        if not start_xy:
            self.report({'ERROR'}, "Could not find a point on the track mesh. Check mesh normals.")
            return {'CANCELLED'}

        pt0 = np.array(start_xy)
        test_width = 0.0
        for angle_deg in range(0, 180, 10):
            angle = math.radians(angle_deg)
            d = np.array([math.cos(angle), math.sin(angle)])
            dl = self._find_edge_dist(track, inv, ray_dir, pt0, d, coarse_step, max_width)
            dr = self._find_edge_dist(track, inv, ray_dir, pt0, -d, coarse_step, max_width)
            w = dl + dr
            if 1.0 < w < max_width * 1.5:
                test_width = max(test_width, w)

        step_size = max(0.5, test_width * 0.3)
        n_target = 800

        raw_centerline = self._walk_track_centerline(
            track, inv, ray_dir, start_xy, n_target,
            coarse_step, max_width, step_size
        )

        if len(raw_centerline) < 20:
            self.report({'ERROR'}, f"Walk produced only {len(raw_centerline)} points. Track mesh may have issues.")
            return {'CANCELLED'}

        n = min(len(raw_centerline), 1000)
        coords = _resample_equidistant(raw_centerline, n)

        for iteration in range(iterations):
            tangents_fixed = np.zeros((n, 2))
            for i in range(n):
                diff = coords[(i + 3) % n] - coords[(i - 3) % n]
                nm = np.linalg.norm(diff)
                tangents_fixed[i] = diff / nm if nm > 1e-8 else [1, 0]

            curv_mag = np.zeros(n)
            for i in range(n):
                t1 = tangents_fixed[i]
                t2 = tangents_fixed[(i + 1) % n]
                dot = np.clip(np.dot(t1, t2), -1, 1)
                curv_mag[i] = math.acos(dot)

            curv_mag_smooth = gaussian_filter1d(np.concatenate([curv_mag] * 3), sigma=5)[n:2*n]
            curv_max = np.max(curv_mag_smooth)

            tangents = np.zeros((n, 2))
            for i in range(n):
                c_norm = curv_mag_smooth[i] / curv_max if curv_max > 1e-8 else 0.0
                win = max(1, int(5 - 4 * c_norm))
                diff = coords[(i + win) % n] - coords[(i - win) % n]
                nm = np.linalg.norm(diff)
                tangents[i] = diff / nm if nm > 1e-8 else [1, 0]

            arr_dl = np.zeros(n)
            arr_dr = np.zeros(n)
            for i in range(n):
                pt = coords[i]
                left = np.array([-tangents[i][1], tangents[i][0]])
                arr_dl[i] = self._find_edge_dist(track, inv, ray_dir, pt, left, coarse_step, max_width)
                arr_dr[i] = self._find_edge_dist(track, inv, ray_dir, pt, -left, coarse_step, max_width)

            widths = arr_dl + arr_dr
            med_w = np.median(widths)
            valid_mask = (
                (widths > med_w * 0.4) &
                (widths < med_w * 1.6) &
                (arr_dl < max_width - 1.0) &
                (arr_dr < max_width - 1.0)
            )

            if not np.all(valid_mask):
                valid_idx = np.where(valid_mask)[0]
                if len(valid_idx) < 4:
                    continue

                ext_idx = np.concatenate([valid_idx - n, valid_idx, valid_idx + n])
                ext_dl = np.tile(arr_dl[valid_idx], 3)
                ext_dr = np.tile(arr_dr[valid_idx], 3)

                f_dl = interp1d(ext_idx, ext_dl, kind='linear')
                f_dr = interp1d(ext_idx, ext_dr, kind='linear')

                arr_dl = f_dl(np.arange(n))
                arr_dr = f_dr(np.arange(n))

            arr_dl = median_filter(arr_dl, size=7)
            arr_dr = median_filter(arr_dr, size=7)

            new_coords = np.zeros((n, 2))
            for i in range(n):
                pt = coords[i]
                left = np.array([-tangents[i][1], tangents[i][0]])
                shift = (arr_dl[i] - arr_dr[i]) * 0.5
                new_coords[i] = pt + left * shift

            for i in range(n):
                if not self._point_on_track(track, inv, ray_dir, new_coords[i, 0], new_coords[i, 1]):
                    old_pt = coords[i]
                    lo_t, hi_t = 0.0, 1.0
                    for _ in range(10):
                        mid_t = (lo_t + hi_t) * 0.5
                        test_pt = old_pt + mid_t * (new_coords[i] - old_pt)
                        if self._point_on_track(track, inv, ray_dir, test_pt[0], test_pt[1]):
                            lo_t = mid_t
                        else:
                            hi_t = mid_t
                    new_coords[i] = old_pt + lo_t * (new_coords[i] - old_pt)

            coords = _resample_equidistant(new_coords, n)

            t_new = np.zeros((n, 2))
            for i in range(n):
                diff = coords[(i + 2) % n] - coords[(i - 2) % n]
                nm = np.linalg.norm(diff)
                t_new[i] = diff / nm if nm > 1e-8 else [1, 0]

            curv_new = np.zeros(n)
            for i in range(n):
                dot = np.clip(np.dot(t_new[i], t_new[(i + 1) % n]), -1, 1)
                curv_new[i] = math.acos(dot)

            curv_new_smooth = gaussian_filter1d(np.concatenate([curv_new] * 3), sigma=3)[n:2*n]
            curv_new_max = np.max(curv_new_smooth)

            min_sigma = max(0.5, sigma * 0.4)
            sx = gaussian_filter1d(np.concatenate([coords[:, 0]] * 3), sigma=min_sigma)[n:2*n]
            sy = gaussian_filter1d(np.concatenate([coords[:, 1]] * 3), sigma=min_sigma)[n:2*n]

            for i in range(n):
                blend = curv_new_smooth[i] / curv_new_max if curv_new_max > 1e-8 else 0.0
                keep = 0.2 + 0.6 * blend
                coords[i, 0] = coords[i, 0] * keep + sx[i] * (1.0 - keep)
                coords[i, 1] = coords[i, 1] * keep + sy[i] * (1.0 - keep)

            for i in range(n):
                if not self._point_on_track(track, inv, ray_dir, coords[i, 0], coords[i, 1]):
                    for radius in range(1, min(20, n // 2)):
                        for nbr in [(i - radius) % n, (i + radius) % n]:
                            if self._point_on_track(track, inv, ray_dir, coords[nbr, 0], coords[nbr, 1]):
                                lo_t, hi_t = 0.0, 1.0
                                for _ in range(10):
                                    mid_t = (lo_t + hi_t) * 0.5
                                    test = coords[i] * (1 - mid_t) + coords[nbr] * mid_t
                                    if self._point_on_track(track, inv, ray_dir, test[0], test[1]):
                                        hi_t = mid_t
                                    else:
                                        lo_t = mid_t
                                coords[i] = coords[i] * (1 - hi_t) + coords[nbr] * hi_t
                                break
                        else:
                            continue
                        break

        name = "TRACK_CENTER_FIXED"
        for d in [bpy.data.objects, bpy.data.curves]:
            if name in d:
                d.remove(d[name], do_unlink=True)

        curve_data = bpy.data.curves.new(name, 'CURVE')
        curve_data.dimensions = '3D'
        sp = curve_data.splines.new('POLY')
        sp.points.add(n - 1)
        for i in range(n):
            sp.points[i].co = (coords[i, 0], coords[i, 1], 0, 1)
        sp.use_cyclic_u = True

        cl_obj = bpy.data.objects.new(name, curve_data)
        bpy.context.collection.objects.link(cl_obj)

        self.report({'INFO'}, f"TRACK_CENTER_FIXED created: {n} pts")
        return {'FINISHED'}


class OBJECT_OT_GenerateRacingLine(Operator):
    bl_idname = "object.generate_racing_line"
    bl_label = "Generate Racing Line"
    bl_description = (
        "Q_RACING_LINE via IQP — sparse-solve replacement for tph.opt_min_curv, "
        "scipy-1.17 safe, ~10s total"
    )

    @staticmethod
    def _opt_min_curv_sparse(reftrack, normvectors, A, kappa_bound, w_veh):
        """
        Exact reimplementation of tph.opt_min_curv (Heilmeier et al. 2019)
        with np.linalg.inv replaced by scipy sparse solve.
        
        A is the (4n x 4n) square spline system matrix from tph.calc_splines.
        It is ~99.9% zeros (banded structure), so sparse solve is ~9x faster
        than dense inv on n=738 tracks.
        """
        import numpy as np
        import quadprog
        from scipy.sparse import csc_matrix
        from scipy.sparse.linalg import spsolve

        no_points  = reftrack.shape[0]
        no_splines = no_points  # closed track

        # ── Extraction matrices (same as tph source) ──────────────────
        A_ex_b = np.zeros((no_points, no_splines * 4), dtype=float)
        for i in range(no_splines):
            A_ex_b[i, i * 4 + 1] = 1.0

        A_ex_c = np.zeros((no_points, no_splines * 4), dtype=float)
        for i in range(no_splines):
            A_ex_c[i, i * 4 + 2] = 2.0

        # ── SPARSE solve instead of dense inv ─────────────────────────
        # Original: A_inv = np.linalg.inv(A);  T_c = A_ex_c @ A_inv
        # Equivalent: T_c.T = solve(A.T, A_ex_c.T)
        A_sp = csc_matrix(A)
        T_c  = spsolve(A_sp.T, A_ex_c.T).T   # (n, 4n)
        T_b  = spsolve(A_sp.T, A_ex_b.T).T   # (n, 4n)

        # ── M_x, M_y (normal vectors in spline coeff space) ──────────
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

        # ── q_x, q_y (reference coordinates in spline coeff space) ───
        q_x = np.zeros((no_splines * 4, 1))
        q_y = np.zeros((no_splines * 4, 1))
        for i in range(no_splines):
            j = i * 4
            nxt = (i + 1) % no_points
            q_x[j, 0] = reftrack[i,   0];  q_x[j+1, 0] = reftrack[nxt, 0]
            q_y[j, 0] = reftrack[i,   1];  q_y[j+1, 0] = reftrack[nxt, 1]

        # ── Curvature denominator terms ───────────────────────────────
        x_prime = np.eye(no_points) * (T_b @ q_x)
        y_prime = np.eye(no_points) * (T_b @ q_y)
        x_prime_sq      = x_prime ** 2
        y_prime_sq      = y_prime ** 2
        x_prime_y_prime = -2.0 * (x_prime @ y_prime)

        curv_den  = (x_prime_sq + y_prime_sq) ** 1.5
        curv_part = np.divide(1.0, curv_den,
                              out=np.zeros_like(curv_den), where=curv_den != 0)
        curv_part_sq = curv_part ** 2

        P_xx = curv_part_sq @ y_prime_sq
        P_yy = curv_part_sq @ x_prime_sq
        P_xy = curv_part_sq @ x_prime_y_prime

        # ── H and f (QP cost matrices) ────────────────────────────────
        T_nx = T_c @ M_x   # (n, n)
        T_ny = T_c @ M_y   # (n, n)

        H_x  = T_nx.T @ (P_xx @ T_nx)
        H_xy = T_ny.T @ (P_xy @ T_nx)
        H_y  = T_ny.T @ (P_yy @ T_ny)
        H    = H_x + H_xy + H_y
        H    = (H + H.T) * 0.5  # enforce symmetry

        f_x  = 2.0 * (q_x.T @ T_c.T @ P_xx @ T_nx)
        f_xy = (q_x.T @ T_c.T @ P_xy @ T_ny
               + q_y.T @ T_c.T @ P_xy @ T_nx)
        f_y  = 2.0 * (q_y.T @ T_c.T @ P_yy @ T_ny)
        f    = np.squeeze(f_x + f_xy + f_y)

        # ── Kappa constraints ─────────────────────────────────────────
        Q_x = curv_part @ y_prime
        Q_y = curv_part @ x_prime
        E_kappa   = Q_y @ T_ny - Q_x @ T_nx
        k_kappa_ref = (Q_y @ (T_c @ q_y)) - (Q_x @ (T_c @ q_x))
        con_ge    = np.ones((no_points, 1)) * kappa_bound - k_kappa_ref
        con_le    = -(np.ones((no_points, 1)) * (-kappa_bound) - k_kappa_ref)
        con_stack = np.concatenate([con_ge, con_le]).ravel()

        # ── Track boundary constraints ────────────────────────────────
        half_veh     = w_veh / 2.0
        dev_max_right = reftrack[:, 2] - half_veh
        dev_max_left  = reftrack[:, 3] - half_veh

        # Clamp to avoid infeasible problem
        dev_max_right = np.maximum(dev_max_right, 0.05)
        dev_max_left  = np.maximum(dev_max_left,  0.05)

        G = np.vstack([np.eye(no_points), -np.eye(no_points), E_kappa, -E_kappa])
        h = np.concatenate([dev_max_right, dev_max_left, con_stack])

        # ── Solve: quadprog.solve_qp(H, -f, -G.T, -h) ───────────────
        H += np.eye(H.shape[0]) * 1e-8   # small regularization
        try:
            alpha = quadprog.solve_qp(H, -f, -G.T, -h, 0)[0]
        except Exception as e:
            raise RuntimeError(f"quadprog: {e}")

        # ── Curvature error (cheap version — no scipy.spatial) ────────
        q_x_sol = q_x + M_x @ np.expand_dims(alpha, 1)
        q_y_sol = q_y + M_y @ np.expand_dims(alpha, 1)
        x_p_sol = np.eye(no_points) * (T_b @ q_x_sol)
        y_p_sol = np.eye(no_points) * (T_b @ q_y_sol)
        x_pp    = np.squeeze(T_c @ q_x + T_nx @ np.expand_dims(alpha, 1))
        y_pp    = np.squeeze(T_c @ q_y + T_ny @ np.expand_dims(alpha, 1))

        curv_orig = np.zeros(no_points)
        curv_sol  = np.zeros(no_points)
        for i in range(no_points):
            denom_o = (x_prime[i,i]**2 + y_prime[i,i]**2) ** 1.5
            denom_s = (x_p_sol[i,i]**2 + y_p_sol[i,i]**2) ** 1.5
            if denom_o > 1e-12:
                curv_orig[i] = (x_prime[i,i]*y_pp[i] - y_prime[i,i]*x_pp[i]) / denom_o
            if denom_s > 1e-12:
                curv_sol[i]  = (x_p_sol[i,i]*y_pp[i] - y_p_sol[i,i]*x_pp[i]) / denom_s

        curv_error_max = float(np.max(np.abs(curv_sol - curv_orig)))
        return alpha, curv_error_max

    def execute(self, context):
        if not dependencies_available():
            self.report({'ERROR'}, "Install dependencies first")
            return {'CANCELLED'}

        import numpy as np
        from mathutils import Vector
        from scipy.interpolate import splprep, splev
        from scipy.ndimage import gaussian_filter1d, median_filter
        import time

        t_total = time.perf_counter()
        props   = context.scene.f1_track_props
        track   = props.track_mesh

        cl_obj = bpy.data.objects.get("TRACK_CENTER_FIXED")
        if not cl_obj:
            self.report({'ERROR'}, "TRACK_CENTER_FIXED not found.")
            return {'CANCELLED'}
        if not track:
            self.report({'ERROR'}, "Select a Track Mesh")
            return {'CANCELLED'}

        try:
            import trajectory_planning_helpers as tph
            import quadprog
        except ImportError as e:
            self.report({'ERROR'}, f"Missing package: {e}")
            return {'CANCELLED'}

        print("\n" + "="*60)
        print("  [Racing Line] SPARSE IQP (scipy-1.17 safe)")
        print("="*60)

        # ── [1/7] Extract centerline ───────────────────────────────────
        t0 = time.perf_counter()
        sp = cl_obj.data.splines[0]
        n  = len(sp.points)
        cl = np.zeros((n, 2))
        for i in range(n):
            co = cl_obj.matrix_world @ Vector(sp.points[i].co[:3])
            cl[i] = [co.x, co.y]
        seg_lens  = np.linalg.norm(np.diff(np.vstack([cl, cl[0]]), axis=0), axis=1)
        print(f"  [1/7] Centerline: {n} pts, length={seg_lens.sum():.1f} BU "
              f"({time.perf_counter()-t0:.3f}s)")

        # ── [2/7] Roll seam to flattest point ─────────────────────────
        tang = np.zeros((n, 2))
        for i in range(n):
            d = cl[(i+3)%n] - cl[(i-3)%n]
            nm = np.linalg.norm(d)
            tang[i] = d/nm if nm > 1e-8 else [1, 0]
        curv_pre = np.array([math.acos(np.clip(np.dot(tang[i], tang[(i+1)%n]), -1, 1))
                             for i in range(n)])
        seam = int(np.argmin(curv_pre))
        cl = np.roll(cl, -seam, axis=0)
        print(f"  [2/7] Seam rolled by {seam}")

        # ── [3/7] Raycast widths ───────────────────────────────────────
        tang2 = np.zeros((n, 2))
        for i in range(n):
            d = cl[(i+3)%n] - cl[(i-3)%n]
            nm = np.linalg.norm(d)
            tang2[i] = d/nm if nm > 1e-8 else [1, 0]
        normals_raw = np.column_stack([-tang2[:, 1], tang2[:, 0]])

        t0  = time.perf_counter()
        inv = track.matrix_world.inverted()
        ray_dir = (inv.to_3x3() @ Vector((0, 0, -1))).normalized()
        INSET   = props.racing_line_inset
        w_tr_right = np.zeros(n)
        w_tr_left  = np.zeros(n)

        print(f"  [3/7] Raycasting {n} pts...")
        for i in range(n):
            pt   = cl[i]
            bn   = normals_raw[i]
            best_total = float('inf')
            best_dir   = bn

            for ad in range(-45, 46, 5):
                a = math.radians(ad)
                td = np.array([bn[0]*math.cos(a) - bn[1]*math.sin(a),
                               bn[0]*math.sin(a) + bn[1]*math.cos(a)])
                tdl = 10.0
                for s in range(1, 67):
                    d = s*0.15
                    h2, *_ = track.ray_cast(inv @ Vector((*(pt+td*d), 10000.)), ray_dir)
                    if not h2: tdl = d-0.15; break
                tdr = 10.0
                for s in range(1, 67):
                    d = s*0.15
                    h2, *_ = track.ray_cast(inv @ Vector((*(pt-td*d), 10000.)), ray_dir)
                    if not h2: tdr = d-0.15; break
                tot = tdl+tdr
                if 0.5 < tot < best_total and tdl < 9.5 and tdr < 9.5:
                    best_total = tot; best_dir = td

            dl = 30.0
            for s in range(1, 200):
                d = s*0.15
                h2, *_ = track.ray_cast(inv @ Vector((*(pt+best_dir*d), 10000.)), ray_dir)
                if not h2: dl = d-0.15; break
            dr = 30.0
            for s in range(1, 200):
                d = s*0.15
                h2, *_ = track.ray_cast(inv @ Vector((*(pt-best_dir*d), 10000.)), ray_dir)
                if not h2: dr = d-0.15; break

            w_tr_right[i] = max(dr - INSET, 0.01)
            w_tr_left[i]  = max(dl - INSET, 0.01)

        w_tr_right = median_filter(np.tile(w_tr_right, 3), size=9)[n:2*n]
        w_tr_left  = median_filter(np.tile(w_tr_left,  3), size=9)[n:2*n]
        w_veh    = props.racing_line_veh_width
        kappa_bound = props.racing_line_kappa_bound
        min_hw   = w_veh/2.0 + 0.5
        wr_safe  = gaussian_filter1d(np.tile(np.maximum(w_tr_right, min_hw), 3), sigma=3)[n:2*n]
        wl_safe  = gaussian_filter1d(np.tile(np.maximum(w_tr_left,  min_hw), 3), sigma=3)[n:2*n]
        print(f"  [3/7] right=[{wr_safe.min():.2f},{wr_safe.max():.2f}] "
              f"left=[{wl_safe.min():.2f},{wl_safe.max():.2f}] ({time.perf_counter()-t0:.1f}s)")

        # ── [4/7] Strong centerline smoothing ─────────────────────────
        t0 = time.perf_counter()
        try:
            cl_cl = np.vstack([cl, cl[0]])
            el    = np.linalg.norm(np.diff(cl_cl, axis=0), axis=1)
            cum   = np.concatenate([[0], np.cumsum(el)])
            u_n   = cum / cum[-1]
            s_val = max(20.0, n * 0.3)
            tck_s, _ = splprep([cl_cl[:, 0], cl_cl[:, 1]], u=u_n, k=3, s=s_val, per=1)
            cl_qp = np.array(splev(u_n[:-1], tck_s)).T
            dev   = np.linalg.norm(cl_qp - cl, axis=1)
            print(f"  [4/7] Smoothed s={s_val:.0f}: dev mean={dev.mean():.3f} "
                  f"max={dev.max():.3f} BU ({time.perf_counter()-t0:.3f}s)")
        except Exception as e:
            print(f"  [4/7] Smoothing failed: {e}")
            cl_qp = cl.copy()
        n_qp = len(cl_qp)

        # ── [5/7] IQP loop — sparse direct solve ──────────────────────
        t0      = time.perf_counter()
        cur_ref = cl_qp.copy()
        cur_wr  = wr_safe.copy()
        cur_wl  = wl_safe.copy()

        n_iters_max   = 5
        alpha_tol     = 0.10
        safety_margin = 0.15

        print(f"  [5/7] IQP sparse (up to {n_iters_max} iters)...")
        converged = False

        for it in range(n_iters_max):
            t_it = time.perf_counter()

            refpath = np.vstack([cur_ref, cur_ref[0]])
            try:
                coeffs_x, coeffs_y, A_mat, _ = tph.calc_splines.calc_splines(
                    path=refpath, use_dist_scaling=True
                )
            except Exception as e:
                print(f"  iter {it}: calc_splines FAILED: {e}")
                break

            ind_s = np.arange(len(coeffs_x))
            t_s   = np.zeros(len(coeffs_x))
            try:
                psi, kappa = tph.calc_head_curv_an.calc_head_curv_an(
                    coeffs_x=coeffs_x, coeffs_y=coeffs_y,
                    ind_spls=ind_s, t_spls=t_s,
                    calc_curv=True, calc_dcurv=False
                )[:2]
            except Exception as e:
                print(f"  iter {it}: calc_head_curv_an FAILED: {e}")
                break

            normvec = tph.calc_normal_vectors.calc_normal_vectors(psi=psi)

            # Psi seam check
            psi_diff = np.mod(np.diff(np.concatenate([psi, [psi[0]+2*math.pi]])) + math.pi,
                              2*math.pi) - math.pi
            if np.max(np.abs(psi_diff)) > 0.4:
                bad = int(np.argmax(np.abs(psi_diff)))
                print(f"        iter {it}: psi jump {psi_diff[bad]:.3f}rad "
                      f"at station {bad}")

            reftrack_it = np.column_stack([cur_ref, cur_wr, cur_wl])

            try:
                alpha_it, curv_err = self._opt_min_curv_sparse(
                    reftrack_it, normvec, A_mat, kappa_bound, w_veh
                )
            except Exception as e:
                print(f"        iter {it}: QP FAILED: {e}")
                if it == 0:
                    self.report({'ERROR'}, f"QP failed: {e}")
                    return {'CANCELLED'}
                break

            alpha_it = np.clip(alpha_it,
                               -cur_wl + w_veh/2.0 + safety_margin,
                                cur_wr - w_veh/2.0 - safety_margin)

            grad = np.abs(np.diff(np.concatenate([alpha_it, [alpha_it[0]]])))
            print(f"        iter {it}: max|α|={np.max(np.abs(alpha_it)):.3f} "
                  f"mean|α|={np.mean(np.abs(alpha_it)):.3f} "
                  f"max|Δα|={grad.max():.3f} "
                  f"curv_err={curv_err:.4f} "
                  f"({time.perf_counter()-t_it:.2f}s)")

            cur_ref = cur_ref + normvec * alpha_it[:, None]
            cur_wr  = np.maximum(cur_wr - alpha_it, w_veh/2.0 + safety_margin)
            cur_wl  = np.maximum(cur_wl + alpha_it, w_veh/2.0 + safety_margin)

            if np.max(np.abs(alpha_it)) < alpha_tol and it >= 1:
                print(f"  [5/7] Converged at iter {it} ✓")
                converged = True
                break

        print(f"  [5/7] IQP done: {time.perf_counter()-t0:.1f}s converged={converged}")

        # ── [6/7] Final interpolation to user stepsize ─────────────────
        t0 = time.perf_counter()
        stepsize  = props.racing_line_stepsize
        rl_closed = np.vstack([cur_ref, cur_ref[0]])
        arc       = np.concatenate([[0],
                    np.cumsum(np.linalg.norm(np.diff(rl_closed, axis=0), axis=1))])
        total_len = arc[-1]
        n_out     = max(10, int(total_len / stepsize))

        # Light smoothing (s>0) removes residual kinks from IQP reference points
        # without destroying the optimised geometry
        s_out = max(1.0, len(rl_closed) * 0.005)
        try:
            tck, _ = splprep([rl_closed[:, 0], rl_closed[:, 1]],
                             u=arc, s=s_out, per=True)
        except Exception:
            tck, _ = splprep([rl_closed[:, 0], rl_closed[:, 1]],
                             u=arc, s=0, per=True)
        u_new    = np.linspace(0, total_len, n_out, endpoint=False)
        rx, ry   = splev(u_new, tck)
        raceline = np.column_stack([rx, ry])
        print(f"  [6/7] {n_out} pts @ {stepsize}m ({time.perf_counter()-t0:.3f}s)")

        # ── [7/7] Containment check ────────────────────────────────────
        from scipy.spatial import cKDTree
        tree = cKDTree(cl_qp)
        _, nidx = tree.query(raceline, k=1)
        off = 0; worst = 0.0
        for i in range(n_out):
            s = nidx[i]
            d = cl_qp[(s+3)%n_qp] - cl_qp[(s-3)%n_qp]
            nm = np.linalg.norm(d)
            if nm < 1e-8: continue
            nv = np.array([d[1], -d[0]]) / nm  # RIGHT
            offset = np.dot(raceline[i] - cl_qp[s], nv)
            if offset > wr_safe[s] or offset < -wl_safe[s]:
                off += 1
                worst = max(worst, max(offset - wr_safe[s], -wl_safe[s] - offset))
        if off:
            print(f"  [7/7] {off}/{n_out} pts off-track (worst={worst:.2f} BU)")
        else:
            print(f"  [7/7] All {n_out} pts within bounds ✓")

        # ── Write to Blender ───────────────────────────────────────────
        name = "Q_RACING_LINE"
        for d in [bpy.data.objects, bpy.data.curves]:
            if name in d: d.remove(d[name], do_unlink=True)

        cd  = bpy.data.curves.new(name, 'CURVE')
        cd.dimensions = '3D'
        sp2 = cd.splines.new('POLY')
        sp2.points.add(n_out - 1)
        for i in range(n_out):
            sp2.points[i].co = (raceline[i, 0], raceline[i, 1], 0.0, 1.0)
        sp2.use_cyclic_u = True

        obj = bpy.data.objects.new(name, cd)
        bpy.context.collection.objects.link(obj)

        # Stash smoothed centerline and half-widths for the style-layer operator.
        # Avoids re-raycasting (~10-30s) on every slider change.
        obj["_cl_qp_x"]          = cl_qp[:, 0].tolist()
        obj["_cl_qp_y"]          = cl_qp[:, 1].tolist()
        obj["_wr_safe"]          = wr_safe.tolist()
        obj["_wl_safe"]          = wl_safe.tolist()
        obj["_has_style_cache"]  = 1

        t_done = time.perf_counter() - t_total
        print("="*60)
        print(f"  DONE: {n_out} pts, {total_len:.0f}m, {t_done:.1f}s total")
        print("="*60 + "\n")
        self.report({'INFO'},
            f"Q_RACING_LINE: {n_out} pts, {total_len:.0f}m ({t_done:.1f}s)")
        return {'FINISHED'}


# ─── STYLED LINE V2 ─────────────────────────────────────────────────────────
# Detects corners directly on Q_RACING_LINE (not centerline), parameterizes
# phase along arc length, warps and clips in a single basis (raceline normals),
# uses smoothed normals to kill tangent-noise zigzag at corners. Centerline
# is used ONLY as a width lookup table.

def _v2_detect_corners_arclen(coords, kappa_hi_frac=0.25, kappa_lo_frac=0.08, min_len=6):
    """Hysteresis κ-corner detection on a closed 2D curve, with phase
    parameterized by ARC LENGTH within each corner (not station count)."""
    import numpy as np
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

    kappa_s = gaussian_filter1d(np.tile(kappa, 3), sigma=5.0)[n:2 * n]
    kappa_abs = np.abs(kappa_s)
    kmax = float(kappa_abs.max())
    if kmax < 1e-6:
        return [], np.full(n, -1, dtype=int), np.zeros(n), np.zeros(n)

    above_hi = kappa_abs > kappa_hi_frac * kmax
    above_lo = kappa_abs > kappa_lo_frac * kmax

    straights = np.where(~above_lo)[0]
    if len(straights) == 0:
        apex = int(np.argmax(kappa_abs))
        ks = int(math.copysign(1, kappa_s[apex]))
        return ([{'entry': 0, 'apex': apex, 'exit': n - 1, 'L': n,
                  'kappa_sign': ks}],
                np.zeros(n, dtype=int),
                np.linspace(0.0, 1.0, n),
                np.full(n, ks, dtype=float))

    roll = int(straights[0])
    above_hi_r = np.roll(above_hi, -roll)
    above_lo_r = np.roll(above_lo, -roll)
    kappa_abs_r = np.roll(kappa_abs, -roll)
    kappa_s_r = np.roll(kappa_s, -roll)
    coords_r = np.roll(coords, -roll, axis=0)

    seg = np.linalg.norm(np.diff(np.vstack([coords_r, coords_r[0]]), axis=0), axis=1)
    arc_r = np.concatenate([[0.0], np.cumsum(seg)])

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
                apex_local = core_start + int(np.argmax(kappa_abs_r[core_start:core_end + 1]))
                corners.append({
                    '_entry_r': entry,
                    '_apex_r': apex_local,
                    '_exit_r': exit_,
                    'L': L,
                    'kappa_sign': int(math.copysign(1, kappa_s_r[apex_local])),
                })
        else:
            i += 1

    corner_id_r = np.full(n, -1, dtype=int)
    phase_r = np.zeros(n)
    sign_arr_r = np.zeros(n)
    for ci, c in enumerate(corners):
        entry, exit_ = c['_entry_r'], c['_exit_r']
        arc0 = arc_r[entry]
        arc1 = arc_r[exit_ + 1]
        denom = max(arc1 - arc0, 1e-6)
        for s in range(entry, exit_ + 1):
            corner_id_r[s] = ci
            phase_r[s] = (arc_r[s] - arc0) / denom
            sign_arr_r[s] = c['kappa_sign']

    corner_id = np.roll(corner_id_r, roll)
    phase = np.roll(phase_r, roll)
    kappa_sign = np.roll(sign_arr_r, roll)
    for c in corners:
        c['entry'] = (c.pop('_entry_r') + roll) % n
        c['apex']  = (c.pop('_apex_r')  + roll) % n
        c['exit']  = (c.pop('_exit_r')  + roll) % n

    return corners, corner_id, phase, kappa_sign


def _v2_periodic_smooth_xy(coords, sigma=1.5):
    """Light periodic gaussian on a closed XY curve. Sigma kept small so
    real corner geometry isn't flattened."""
    import numpy as np
    from scipy.ndimage import gaussian_filter1d
    n = len(coords)
    sx = gaussian_filter1d(np.tile(coords[:, 0], 3), sigma=sigma)[n:2 * n]
    sy = gaussian_filter1d(np.tile(coords[:, 1], 3), sigma=sigma)[n:2 * n]
    return np.column_stack([sx, sy])


def _v3_find_hifi_path(driver_tag, props):
    """Locate the per-driver baked telemetry path JSON. Tries in order:
       1. <style_json_path>/../../temp_data/{driver}_{N}_hifi_path.json
       2. <blend_dir>/F1_Pipeline_Assets/temp_data/...
       3. <blend_dir>/temp_data/...
    Returns the absolute path string, or None if nothing found."""
    import os, glob
    cands = []
    style_json = str(getattr(props, 'style_json_path', '') or '').strip()
    if style_json:
        style_dir = os.path.dirname(os.path.abspath(style_json))
        cands.append(os.path.join(os.path.dirname(style_dir), 'temp_data'))
    try:
        blend_dir = bpy.path.abspath('//')
    except Exception:
        blend_dir = ''
    if blend_dir:
        cands.append(os.path.join(blend_dir, 'F1_Pipeline_Assets', 'temp_data'))
        cands.append(os.path.join(blend_dir, 'temp_data'))

    for d in cands:
        if not d or not os.path.isdir(d):
            continue
        c0 = os.path.join(d, f"{driver_tag}_0_hifi_path.json")
        if os.path.isfile(c0):
            return c0
        c1 = os.path.join(d, f"{driver_tag}_hifi_path.json")
        if os.path.isfile(c1):
            return c1
        matches = glob.glob(os.path.join(d, f"{driver_tag}_*_hifi_path.json"))
        if matches:
            return sorted(matches)[0]
    return None


def _v3_load_hifi_xy(path):
    """Read hifi_path JSON → (N, 2) XY numpy array. Returns None on parse error."""
    import json
    import numpy as np
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        pts = data.get('points') or []
        if len(pts) < 50:
            return None
        xs = np.array([float(p.get('x', 0.0)) for p in pts], dtype=float)
        ys = np.array([float(p.get('y', 0.0)) for p in pts], dtype=float)
        return np.column_stack([xs, ys])
    except Exception:
        return None


def _v3_lap_fractions(corners, coords):
    """For each corner, return apex's lap fraction (arc-length to apex / total lap
    arc-length, in [0, 1)). Coord-frame independent."""
    import numpy as np
    n = len(coords)
    d = np.diff(np.vstack([coords, coords[0:1]]), axis=0)
    seg = np.linalg.norm(d, axis=1)
    total = float(seg.sum())
    if total < 1e-6:
        return np.zeros(len(corners))
    cumarc = np.concatenate([[0.0], np.cumsum(seg)])
    return np.array([cumarc[int(c['apex'])] / total for c in corners])


def _v3_match_corners_lap_fraction(q_corners, q_coords, sai_corners, sai_coords,
                                   max_diff=0.06):
    """Greedy one-to-one match by lap-fraction position of each apex. Q's coord
    frame and SAI's coord frame can differ — only relative arc-length within each
    path matters. Picks a global rotation offset that maximises matched pairs,
    then assigns greedily. Returns list of length len(q_corners) with matched SAI
    index or None for unmatched."""
    import numpy as np
    Nq = len(q_corners)
    Ns = len(sai_corners) if sai_corners else 0
    if Nq == 0 or Ns == 0:
        return [None] * Nq

    qf = _v3_lap_fractions(q_corners, q_coords)
    sf = _v3_lap_fractions(sai_corners, sai_coords)

    def _circ(a, b):
        d = abs(float(a) - float(b))
        return min(d, 1.0 - d)

    # Search a small set of global offsets (Q lap-fraction may start at a
    # different physical track position than SAI lap-fraction). Pick the offset
    # that maximises matched pairs under max_diff, ties broken by total error.
    best = None
    for off in np.linspace(0.0, 1.0, 41, endpoint=False):
        sf_shift = (sf + off) % 1.0
        used_s = set()
        n_match = 0
        total_err = 0.0
        for qi in range(Nq):
            best_sj = None
            best_d = max_diff + 1.0
            for sj in range(Ns):
                if sj in used_s:
                    continue
                d = _circ(qf[qi], sf_shift[sj])
                if d < best_d:
                    best_d = d
                    best_sj = sj
            if best_sj is not None and best_d <= max_diff:
                used_s.add(best_sj)
                n_match += 1
                total_err += best_d
        if best is None or n_match > best[0] or (n_match == best[0] and total_err < best[1]):
            best = (n_match, total_err, off)

    off = best[2] if best is not None else 0.0
    sf_shift = (sf + off) % 1.0

    pairs = []
    for qi in range(Nq):
        for sj in range(Ns):
            pairs.append((_circ(qf[qi], sf_shift[sj]), qi, sj))
    pairs.sort(key=lambda t: t[0])
    matched = [None] * Nq
    q_taken = set()
    s_taken = set()
    for d, qi, sj in pairs:
        if d > max_diff:
            break
        if qi in q_taken or sj in s_taken:
            continue
        matched[qi] = sj
        q_taken.add(qi)
        s_taken.add(sj)
    return matched


def _find_style_params_dir(props):
    """Locate the project's style_params/ directory. Tries:
       1. Sibling of props.style_json_path (most reliable when user has loaded one)
       2. <blend_dir>/F1_Pipeline_Assets/style_params/
       3. <blend_dir>/style_params/
    Returns absolute path, or None."""
    import os
    cands = []
    style_json = str(getattr(props, 'style_json_path', '') or '').strip()
    if style_json:
        cands.append(os.path.dirname(bpy.path.abspath(style_json)))
    try:
        blend_dir = bpy.path.abspath('//')
    except Exception:
        blend_dir = ''
    if blend_dir:
        cands.append(os.path.join(blend_dir, 'F1_Pipeline_Assets', 'style_params'))
        cands.append(os.path.join(blend_dir, 'style_params'))
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return None


def _q_right_normals(raceline):
    """Per-station right-normals for Q (chord-based), used for projecting the
    driver's lateral offset and for re-applying it as displacement."""
    import numpy as np
    n_r = len(raceline)
    rn = np.zeros((n_r, 2))
    for i in range(n_r):
        d = raceline[(i + 3) % n_r] - raceline[(i - 3) % n_r]
        nm = np.linalg.norm(d)
        if nm < 1e-8:
            rn[i] = np.array([0.0, -1.0])
        else:
            t = d / nm
            rn[i] = np.array([t[1], -t[0]])
    return rn


def _extract_offset_profile(raceline, q_corners, right_normals, driver_path_xy,
                            smooth_sigma=3.0, taper_frac=0.15, max_clip=5.0):
    """Returns a per-station signed lateral offset profile (n_r,) extracted from
    the driver's path: closest-point projection onto Q's right-normals, masked
    to corner stations only, cosine-tapered at corner boundaries, lightly
    smoothed, and hard-clipped to ±max_clip metres. NOT scaled by master and
    NOT applied to coords yet — pure signal extraction."""
    import numpy as np
    from scipy.spatial import cKDTree
    from scipy.ndimage import gaussian_filter1d

    n_r = len(raceline)
    if driver_path_xy is None or len(driver_path_xy) < 50:
        return np.zeros(n_r)

    tree = cKDTree(driver_path_xy)
    _, nn = tree.query(raceline)
    raw = np.einsum('ij,ij->i', driver_path_xy[nn] - raceline, right_normals)
    raw = np.clip(raw, -max_clip, max_clip)

    out = np.zeros(n_r)
    for c in q_corners:
        idx = _v3_corner_indices(c, n_r)
        L = len(idx)
        if L < 4:
            continue
        taper_len = max(2, int(L * taper_frac))
        taper = np.ones(L)
        for k in range(taper_len):
            phase = k / max(taper_len - 1, 1)
            w = 0.5 * (1.0 - np.cos(np.pi * phase))
            taper[k] = w
            taper[L - 1 - k] = w
        out[idx] = raw[idx] * taper

    if smooth_sigma > 0.0:
        out = gaussian_filter1d(np.tile(out, 3), sigma=smooth_sigma)[n_r:2 * n_r]

    in_corner = np.zeros(n_r, dtype=bool)
    for c in q_corners:
        idx = _v3_corner_indices(c, n_r)
        in_corner[idx] = True
    out[~in_corner] = 0.0
    return out


def _styled_line_from_driver_path(raceline, q_corners, driver_path_xy, master,
                                   smooth_sigma=3.0, taper_frac=0.15, max_offset_clip=5.0,
                                   driver_tag=""):
    """Build the styled racing line by extracting the driver's actual lateral
    offset from Q (using their hifi-path / driving_path curve) and applying it
    as a deformation to Q.

    Process:
      1. For each Q station, compute Q's right-normal from a 7-point chord.
      2. cKDTree-find the closest point on the driver's path to each Q point.
      3. Project the (driver_pt - Q_pt) vector onto Q's right-normal → signed
         lateral offset per station, in metres.
      4. Mask: stations not inside any detected corner → offset = 0 (straights
         keep the line exactly on Q).
      5. Cosine-taper the first/last `taper_frac` of each corner so offset goes
         smoothly 0 → raw → 0 across the corner.
      6. Light gaussian smooth (sigma ≈ 3 stations, periodic) to remove
         telemetry sampling noise.
      7. Re-mask after smoothing as a paranoia guard against small bleed.
      8. Hard-clip per-station |offset| to max_offset_clip metres.
      9. Output: styled = Q + (offset × master) × Q_right_normal.

    Driver-style identity comes from the SHAPE of the offset profile within each
    corner, which is unique to each driver's actual driving. Q's straights are
    untouched. No JSON params — the data from FastF1 (the driving path itself)
    IS the parameter."""
    import numpy as np
    from scipy.spatial import cKDTree
    from scipy.ndimage import gaussian_filter1d

    n_r = len(raceline)
    if driver_path_xy is None or len(driver_path_xy) < 50:
        return raceline.copy(), 0, len(q_corners)

    right_normals = np.zeros((n_r, 2))
    for i in range(n_r):
        d = raceline[(i + 3) % n_r] - raceline[(i - 3) % n_r]
        nm = np.linalg.norm(d)
        if nm < 1e-8:
            right_normals[i] = np.array([0.0, -1.0])
        else:
            t = d / nm
            right_normals[i] = np.array([t[1], -t[0]])

    tree = cKDTree(driver_path_xy)
    _, nn = tree.query(raceline)
    delta = driver_path_xy[nn] - raceline                     # (n, 2)
    raw_offsets = np.einsum('ij,ij->i', delta, right_normals) # (n,)
    raw_offsets = np.clip(raw_offsets, -max_offset_clip, max_offset_clip)

    in_corner = np.zeros(n_r, dtype=bool)
    for c in q_corners:
        idx = _v3_corner_indices(c, n_r)
        in_corner[idx] = True

    final_offsets = np.zeros(n_r)
    for c in q_corners:
        idx = _v3_corner_indices(c, n_r)
        L = len(idx)
        if L < 4:
            continue
        taper_len = max(2, int(L * taper_frac))
        taper = np.ones(L)
        for k in range(taper_len):
            phase = k / max(taper_len - 1, 1)
            w = 0.5 * (1.0 - np.cos(np.pi * phase))
            taper[k] = w
            taper[L - 1 - k] = w
        final_offsets[idx] = raw_offsets[idx] * taper

    if smooth_sigma > 0.0:
        final_offsets = gaussian_filter1d(
            np.tile(final_offsets, 3), sigma=smooth_sigma,
        )[n_r:2 * n_r]

    # Re-mask hard zero outside corners (smoothing can bleed a few stations).
    final_offsets[~in_corner] = 0.0

    final_offsets *= float(master)

    # Per-corner peak-magnitude debug.
    if driver_tag:
        print(f"[STYLE-OFFSET] {driver_tag}: per-corner peak |offset| (m):", flush=True)
        for ci, c in enumerate(q_corners):
            idx = _v3_corner_indices(c, n_r)
            seg = final_offsets[idx]
            if len(seg) > 0:
                peak = float(np.abs(seg).max())
                signed_at_apex = float(final_offsets[int(c['apex'])])
                print(
                    f"  c{ci:02d} L={c['L']:3d} ks={c['kappa_sign']:+d} "
                    f"peak={peak:+.2f}m  apex_offset={signed_at_apex:+.2f}m",
                    flush=True,
                )
        max_d = float(np.abs(final_offsets).max())
        print(f"[STYLE-OFFSET] {driver_tag}: max |offset| over lap = {max_d:.2f} m", flush=True)

    styled = raceline + final_offsets[:, None] * right_normals
    return styled, n_r, len(q_corners)


def _styled_line_for_driver_legacy(raceline, q_corners, outside_budget,
                            json_corners, json_params, sai_xy, master,
                            max_drift=2.0, max_loose=0.6):
    """[Legacy — replaced by _styled_line_from_driver_path] Periodic cubic spline
    through anchor points derived from the 8-param JSON. Kept here in case the
    JSON-based fallback is needed."""
    import numpy as np
    from scipy.interpolate import CubicSpline
    n_r = len(raceline)

    # 1. Match Q's corners to SAI's per-corner JSON entries via lap-fraction.
    per_corner_data = [None] * len(q_corners)
    if sai_xy is not None and json_corners:
        sai_corners_det, _, _, _ = _v2_detect_corners_arclen(sai_xy)
        if sai_corners_det:
            matched = _v3_match_corners_lap_fraction(
                q_corners, raceline, sai_corners_det, sai_xy, max_diff=0.06,
            )
            for qi, sj in enumerate(matched):
                if sj is not None and 0 <= sj < len(json_corners):
                    per_corner_data[qi] = json_corners[sj]

    g_ap = float(json_params.get('apex_phase', 0.0))
    g_at = float(json_params.get('apex_tightness', 0.5))

    # 2. Per-station cumulative arc length and lap-fraction.
    d = np.diff(np.vstack([raceline, raceline[0:1]]), axis=0)
    seg_len = np.linalg.norm(d, axis=1)
    total_arc = float(seg_len.sum())
    if total_arc < 1e-6:
        return raceline.copy(), 0, len(q_corners)
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])[:-1]      # (n_r,)
    arc_frac = cum / total_arc                                    # in [0, 1)

    # 3. Build anchor list (arc_frac, dev_x, dev_y).
    arcs = []
    dxs = []
    dys = []

    n_corners = len(q_corners)
    for ci, c in enumerate(q_corners):
        data = per_corner_data[ci]
        if data is not None:
            ap = float(data.get('apex_phase', g_ap))
            at = float(data.get('apex_tightness', g_at))
        else:
            ap, at = g_ap, g_at

        ap_eff = ap * master
        at_eff = 0.5 + (at - 0.5) * master

        drift_mag = abs(ap_eff) * float(max_drift)
        drift_mag += max(0.0, 0.5 - at_eff) * float(max_loose)
        budget = float(outside_budget.get(ci, 100.0))
        drift_mag = min(drift_mag, budget)

        apex_idx = int(c['apex'])
        p_back = max(0, apex_idx - 3)
        p_fwd = min(n_r - 1, apex_idx + 3)
        chord = raceline[p_fwd] - raceline[p_back]
        cn = float(np.linalg.norm(chord))
        if cn < 1e-6:
            continue
        chord /= cn
        right_normal = np.array([chord[1], -chord[0]])
        outside_dir = +float(c['kappa_sign']) * right_normal

        arcs.append(float(arc_frac[int(c['entry'])])); dxs.append(0.0); dys.append(0.0)
        arcs.append(float(arc_frac[apex_idx]));        dxs.append(drift_mag * outside_dir[0]); dys.append(drift_mag * outside_dir[1])
        arcs.append(float(arc_frac[int(c['exit'])]));  dxs.append(0.0); dys.append(0.0)

    # 4. Mid-straight rest anchors (zero deviation).
    for ci in range(n_corners):
        c1 = q_corners[ci]
        c2 = q_corners[(ci + 1) % n_corners]
        a_exit = float(arc_frac[int(c1['exit'])])
        a_entry = float(arc_frac[int(c2['entry'])])
        if a_entry > a_exit:
            mid = 0.5 * (a_exit + a_entry)
        else:
            mid = (0.5 * (a_exit + a_entry + 1.0)) % 1.0
        arcs.append(mid); dxs.append(0.0); dys.append(0.0)

    # 5. Sort, deduplicate, wrap for periodic.
    arr = sorted(zip(arcs, dxs, dys), key=lambda t: t[0])
    out_arcs, out_dxs, out_dys = [], [], []
    for a, x, y in arr:
        if out_arcs and abs(a - out_arcs[-1]) < 1e-6:
            continue
        out_arcs.append(a)
        out_dxs.append(x)
        out_dys.append(y)
    out_arcs.append(out_arcs[0] + 1.0)
    out_dxs.append(out_dxs[0])
    out_dys.append(out_dys[0])

    if len(out_arcs) < 4:
        return raceline.copy(), sum(1 for d in per_corner_data if d is not None), n_corners

    # 6. Periodic cubic splines for x and y deviation components.
    spl_x = CubicSpline(out_arcs, out_dxs, bc_type='periodic')
    spl_y = CubicSpline(out_arcs, out_dys, bc_type='periodic')

    dev_x = spl_x(arc_frac)
    dev_y = spl_y(arc_frac)

    styled = raceline.copy()
    styled[:, 0] += dev_x
    styled[:, 1] += dev_y

    # Debug — corner positions, anchor count, max deviation.
    print("[STYLE-CUBIC] corners (entry/apex/exit station, apex lap-frac, kappa_sign):", flush=True)
    for ci, c in enumerate(q_corners):
        print(
            f"  c{ci:02d}  entry={c['entry']:4d}  apex={c['apex']:4d}  exit={c['exit']:4d}  "
            f"apex_frac={arc_frac[int(c['apex'])]*100:.1f}%  ks={c['kappa_sign']:+d}",
            flush=True,
        )
    max_dev_total = float(np.linalg.norm(np.column_stack([dev_x, dev_y]), axis=1).max())
    print(f"[STYLE-CUBIC] {len(out_arcs)-1} anchors used | max styled-vs-Q deviation = {max_dev_total:.2f} m", flush=True)

    n_matched = sum(1 for d in per_corner_data if d is not None)
    return styled, n_matched, n_corners


def _curve_world_xy(obj):
    """Read a curve object's spline points in world XY (handles BEZIER + POLY/NURBS)."""
    import numpy as np
    from mathutils import Vector
    if obj is None or obj.type != 'CURVE' or not obj.data.splines:
        return None
    sp = obj.data.splines[0]
    if sp.type == 'BEZIER':
        pts = [obj.matrix_world @ bp.co for bp in sp.bezier_points]
    else:
        pts = [obj.matrix_world @ Vector(pt.co[:3]) for pt in sp.points]
    if len(pts) < 4:
        return None
    return np.array([[float(p.x), float(p.y)] for p in pts], dtype=float)


def _resolve_driving_path_obj(driver_code, scene):
    """Find the driving_path_* curve in scene that corresponds to this driver code.
    Two-step: direct name match, else trail-name back-lookup. Returns Object or None."""
    du = driver_code.upper()
    driving_paths = [
        o for o in scene.objects
        if o.type == 'CURVE' and o.name.startswith("driving_path_")
    ]
    for p in driving_paths:
        if du in p.name.upper():
            return p
    trails = [
        o for o in scene.objects
        if o.type == 'CURVE' and o.name.startswith("LC_Trail_")
    ]
    for t in trails:
        if du not in t.name.upper():
            continue
        suffix = t.name
        for prefix in ("LC_Trail_car_rig_", "LC_Trail_"):
            if suffix.startswith(prefix):
                suffix = suffix[len(prefix):]
                break
        parts = suffix.split("_")
        for i in range(len(parts), 0, -1):
            cand_name = "driving_path_" + "_".join(parts[:i])
            obj = scene.objects.get(cand_name)
            if obj is not None and obj.type == 'CURVE':
                return obj
    return None


def _v3_corner_indices(c, n):
    """Inclusive index array entry..exit, wrap-aware."""
    import numpy as np
    entry, exit_ = c['entry'], c['exit']
    if exit_ >= entry:
        return np.arange(entry, exit_ + 1)
    return np.concatenate([np.arange(entry, n), np.arange(0, exit_ + 1)])


def _v3_apex_local_index(c, n, L):
    """Where the κ-peak sits within the corner's local index range [0..L-1]."""
    import numpy as np
    entry, exit_ = int(c['entry']), int(c['exit'])
    apex_abs = int(c['apex'])
    if exit_ >= entry:
        A = apex_abs - entry
    else:
        A = (apex_abs - entry) % n
    return int(np.clip(A, 1, L - 2))


def _v3_asymmetric_bell(L, peak_phase, sharpness=1.0):
    """Smooth bump shape across L stations with peak at peak_phase ∈ (0, 1).
    Value AND slope are exactly zero at both endpoints — this is critical for
    a kink-free transition from the corner into the surrounding straight. The
    peak is placed via a power warp on a cosine bell, which keeps the function
    smooth everywhere (no piecewise discontinuity at the peak)."""
    import numpy as np
    if L < 4:
        return np.zeros(L)
    pp = float(np.clip(peak_phase, 0.05, 0.95))
    if abs(math.log(pp)) < 1e-3:
        power = 1.0
    else:
        power = math.log(0.5) / math.log(pp)
    phase = np.arange(L, dtype=float) / float(L - 1)
    warped = phase ** power
    bell = 0.5 * (1.0 - np.cos(2.0 * np.pi * warped))
    if sharpness != 1.0:
        bell = bell ** float(sharpness)
    return bell


def _v3_reshape_corner(coords, c, ap_phase, tight, vu,
                       outside_budget_at_apex=None,
                       max_drift=3.5, max_loose=1.5,
                       _dbg=False, _dbg_tag=""):
    """Apply a smooth, bounded OUTSIDE drift to one corner. The bump shape is a
    power-warped cosine bell — zero value AND zero slope at the corner's entry
    and exit, peak slid to (0.5 − 0.4·apex_phase) of the corner. Result: smooth
    tangent transition between corner and straight (no boundary kink), no
    deviation propagating into the straights."""
    import numpy as np

    n = len(coords)
    idx = _v3_corner_indices(c, n)
    L = len(idx)
    if L < 4:
        return idx, coords[idx].copy()

    seg = coords[idx].copy()
    A_0 = _v3_apex_local_index(c, n, L)

    # Outside direction = +kappa_sign × right_normal (away from apex inside).
    iA = A_0
    p_back = max(0, iA - 3)
    p_fwd = min(L - 1, iA + 3)
    chord = seg[p_fwd] - seg[p_back]
    cn = float(np.linalg.norm(chord))
    if cn < 1e-6:
        return idx, seg
    chord /= cn
    right_normal = np.array([chord[1], -chord[0]])
    outside_dir = +float(c['kappa_sign']) * right_normal

    # Bump peak phase: late apex (ap>0) → entry side; early apex (ap<0) → exit side.
    bump_phase = 0.5 - 0.4 * float(ap_phase)               # ap=+1 → 0.1, ap=-1 → 0.9
    drift_mag = abs(float(ap_phase)) * float(max_drift)

    # vu_shape: -1 → sharp (peakier), +1 → broad (rounder). Maps to bell exponent.
    sharpness = float(np.clip(1.0 - 0.4 * float(vu), 0.5, 1.6))

    w_drift = _v3_asymmetric_bell(L, bump_phase, sharpness=sharpness)

    # Loose-driver kicker: a centered, symmetric bell at the natural apex.
    loose_mag = max(0.0, 0.5 - float(tight)) * float(max_loose)
    apex_phase_norm = float(A_0) / float(L - 1)
    w_loose = _v3_asymmetric_bell(L, apex_phase_norm, sharpness=1.4)

    outward = w_drift * drift_mag + w_loose * loose_mag    # (L,)

    # Track-width clip against the outside budget at apex (the conservative point
    # — outside budget is largest near apex on Q's IQP line, smallest near
    # entry/exit; using apex value keeps the bump inside the kerb at its peak,
    # and the gaussian decays toward entry/exit so we never push closer to the
    # outside kerb than the apex value).
    clipped = False
    if outside_budget_at_apex is not None:
        max_allowed = float(max(0.0, outside_budget_at_apex))
        peak = float(outward.max())
        if peak > max_allowed and peak > 1e-6:
            outward *= max_allowed / peak
            clipped = True

    new_seg = seg + outward[:, None] * outside_dir[None, :]

    if _dbg:
        max_dev = float(np.linalg.norm(new_seg - seg, axis=1).max())
        clip_tag = " *TRACK-CLIP*" if clipped else ""
        print(
            f"[V3-DBG]   {_dbg_tag} L={L} A_0={A_0} bump_idx={bump_center_idx:.1f} "
            f"ap={ap_phase:+.3f} tight={tight:.3f} vu={vu:+.3f} "
            f"drift_mag={drift_mag:.2f}m loose_mag={loose_mag:.2f}m{clip_tag} "
            f"sigma_bump={sigma_bump:.1f} max_dev={max_dev:.3f}m",
            flush=True,
        )

    return idx, new_seg


class OBJECT_OT_GenerateAllStyledRacingLines(Operator):
    bl_idname = "object.generate_all_styled_racing_lines"
    bl_label = "Generate Styled Racing Lines"
    bl_description = (
        "Auto-discover every per-driver style JSON under "
        "<project>/F1_Pipeline_Assets/style_params/ that matches the currently "
        "loaded JSON's grand_prix + season (or all of them if none is loaded), "
        "and create one Q_RACING_LINE_STYLED_{driver} curve per driver. "
        "Pulls each driver's hifi-path JSON for lap-fraction corner matching."
    )

    def execute(self, context):
        if not dependencies_available():
            self.report({'ERROR'}, "Install dependencies first")
            return {'CANCELLED'}

        import numpy as np
        from mathutils import Vector
        from scipy.spatial import cKDTree as _cKDTree
        import json as _json
        import os, glob

        props = context.scene.f1_track_props
        if not props.style_enabled:
            self.report({'INFO'}, "Style layer disabled")
            return {'CANCELLED'}

        q_obj = bpy.data.objects.get("Q_RACING_LINE")
        if not q_obj:
            self.report({'ERROR'}, "Q_RACING_LINE not found — run 'Generate Racing Line' first")
            return {'CANCELLED'}
        if "_has_style_cache" not in q_obj:
            self.report({'ERROR'}, "Style cache missing on Q_RACING_LINE — regenerate it first")
            return {'CANCELLED'}

        sp_q = q_obj.data.splines[0]
        n_r = len(sp_q.points)
        raceline = np.zeros((n_r, 2))
        for i in range(n_r):
            co = q_obj.matrix_world @ Vector(sp_q.points[i].co[:3])
            raceline[i] = [co.x, co.y]

        corners_r, _, _, _ = _v2_detect_corners_arclen(raceline)
        if not corners_r:
            self.report({'WARNING'}, "No corners detected on Q_RACING_LINE")
            return {'CANCELLED'}

        cl_qp = np.column_stack([
            np.array(q_obj["_cl_qp_x"], dtype=float),
            np.array(q_obj["_cl_qp_y"], dtype=float),
        ])
        wr_safe_cl = np.array(q_obj["_wr_safe"], dtype=float)
        wl_safe_cl = np.array(q_obj["_wl_safe"], dtype=float)
        n_cl = len(cl_qp)
        nv_cl_all = np.zeros((n_cl, 2))
        for s in range(n_cl):
            d = cl_qp[(s + 3) % n_cl] - cl_qp[(s - 3) % n_cl]
            nm = np.linalg.norm(d)
            if nm < 1e-8:
                nv_cl_all[s] = np.array([0.0, -1.0])
            else:
                t = d / nm
                nv_cl_all[s] = np.array([t[1], -t[0]])
        nn = _cKDTree(cl_qp).query(raceline)[1]
        nv_cl_r = nv_cl_all[nn]
        off_raceline = np.einsum('ij,ij->i', raceline - cl_qp[nn], nv_cl_r)
        veh_half = float(props.racing_line_veh_width) * 0.5
        safety = 0.15
        outside_budget = {}
        for ci, c in enumerate(corners_r):
            a = int(c['apex'])
            if c['kappa_sign'] < 0:
                b = float(wl_safe_cl[nn[a]] + off_raceline[a] - veh_half - safety)
            else:
                b = float(wr_safe_cl[nn[a]] - off_raceline[a] - veh_half - safety)
            outside_budget[ci] = max(0.0, b)

        master = float(props.style_master)

        style_dir = _find_style_params_dir(props)
        if not style_dir:
            self.report({'ERROR'},
                "style_params/ folder not found — set Style JSON path or place "
                "the .blend in <project_root>/F1_Pipeline_Assets/...")
            return {'CANCELLED'}

        json_files = sorted(glob.glob(os.path.join(style_dir, "*.json")))
        if not json_files:
            self.report({'ERROR'}, f"No style JSONs in {style_dir}")
            return {'CANCELLED'}

        # Filter by GP+year if a JSON is currently loaded (to avoid making lines
        # for drivers from a different track sitting in the same folder).
        filter_gp = None
        filter_yr = None
        if props.style_json_path:
            try:
                with open(bpy.path.abspath(props.style_json_path), 'r', encoding='utf-8') as fp:
                    p = _json.load(fp)
                src = p.get('source', {})
                filter_gp = str(src.get('grand_prix', '')).strip().lower() or None
                filter_yr = str(src.get('season', '')).strip() or None
            except Exception:
                pass

        print("\n========== STYLED RACING LINES — BATCH ==========", flush=True)
        print(f"[BATCH] style_dir={style_dir}", flush=True)
        print(f"[BATCH] {len(json_files)} JSON(s) | filter_gp={filter_gp!r} filter_yr={filter_yr!r}", flush=True)
        print(f"[BATCH] Q corners={len(corners_r)} | master={master:.3f}", flush=True)

        # Per-Q-station right-normals (computed once, used for both extraction
        # and re-application).
        right_normals = _q_right_normals(raceline)

        # Pass 1 — gather raw lateral-offset profiles per driver.
        profiles = {}            # driver -> np.ndarray(n_r,)
        sources  = {}            # driver -> dp_obj.name
        skipped  = []
        for jf in json_files:
            try:
                with open(jf, 'r', encoding='utf-8') as fp:
                    payload = _json.load(fp)
            except Exception:
                skipped.append(f"{os.path.basename(jf)}: parse")
                continue

            src = payload.get('source', {})
            driver = str(src.get('driver', '')).strip()
            gp = str(src.get('grand_prix', '')).strip().lower()
            yr = str(src.get('season', '')).strip()
            if not driver:
                skipped.append(f"{os.path.basename(jf)}: no driver")
                continue
            if filter_gp and gp != filter_gp:
                continue
            if filter_yr and yr != filter_yr:
                continue

            dp_obj = _resolve_driving_path_obj(driver, context.scene)
            if dp_obj is None:
                skipped.append(f"{driver}: no driving_path_* in scene")
                print(f"[BATCH] {driver}: NO driving_path FOUND — skipping", flush=True)
                continue
            driver_path_xy = _curve_world_xy(dp_obj)
            if driver_path_xy is None:
                skipped.append(f"{driver}: driving_path malformed")
                continue

            try:
                profile = _extract_offset_profile(
                    raceline, corners_r, right_normals, driver_path_xy,
                    smooth_sigma=3.0, taper_frac=0.15, max_clip=5.0,
                )
            except Exception as e:
                skipped.append(f"{driver}: extract {e}")
                continue

            profiles[driver] = profile
            sources[driver] = (dp_obj.name, len(driver_path_xy))

        if not profiles:
            print("[BATCH] no profiles gathered", flush=True)
            print("========== BATCH END ==========\n", flush=True)
            self.report({'WARNING'}, f"Generated 0; skipped {len(skipped)}: {'; '.join(skipped)[:160]}")
            return {'CANCELLED'}

        # Average across drivers — the lap-wide common deviation.
        all_profiles = np.array(list(profiles.values()))    # (n_drivers, n_r)
        avg_profile = all_profiles.mean(axis=0)             # (n_r,)
        n_drivers = len(profiles)

        # Amplification: highlight what makes each driver UNIQUE among the
        # queued set. With 1 driver, unique=0 → falls back to raw profile.
        amp = 2.5 if n_drivers >= 2 else 1.0

        print(
            f"[BATCH] gathered {n_drivers} driver profile(s); "
            f"applying avg + amp×unique  (amp={amp:.1f})",
            flush=True,
        )
        print(
            f"[BATCH] avg-profile peak |offset| = {float(np.abs(avg_profile).max()):.2f} m  "
            f"(common driver-vs-Q deviation, applied at master strength)",
            flush=True,
        )

        # Pass 2 — for each driver, build styled = Q + (avg + amp×unique) × master × right_normal.
        written = []
        for driver, profile in profiles.items():
            unique = profile - avg_profile
            final = master * (avg_profile + amp * unique)
            final = np.clip(final, -6.0, 6.0)
            styled = raceline + final[:, None] * right_normals

            curve_name = f"Q_RACING_LINE_STYLED_{driver}"
            for d in [bpy.data.objects, bpy.data.curves]:
                if curve_name in d:
                    d.remove(d[curve_name], do_unlink=True)
            cd = bpy.data.curves.new(curve_name, 'CURVE')
            cd.dimensions = '3D'
            sp_s = cd.splines.new('POLY')
            sp_s.points.add(n_r - 1)
            for i in range(n_r):
                sp_s.points[i].co = (styled[i, 0], styled[i, 1], 0.0, 1.0)
            sp_s.use_cyclic_u = True
            obj_s = bpy.data.objects.new(curve_name, cd)
            bpy.context.collection.objects.link(obj_s)

            delta_total = float(np.linalg.norm(styled - raceline, axis=1).max())
            unique_peak = float(np.abs(unique).max())
            src_name, src_pts = sources[driver]
            print(
                f"[BATCH] {driver}: source={src_name} ({src_pts} pts) | "
                f"unique_peak={unique_peak:.2f}m | total_delta={delta_total:.2f}m | "
                f"wrote {curve_name}",
                flush=True,
            )
            print(f"[STYLE-DRIVER] {driver}: per-corner UNIQUE offset (driver - avg):", flush=True)
            for ci, c in enumerate(corners_r):
                u_at_apex = float(unique[int(c['apex'])])
                f_at_apex = float(final[int(c['apex'])])
                print(
                    f"  c{ci:02d} L={c['L']:3d} ks={c['kappa_sign']:+d}  "
                    f"unique@apex={u_at_apex:+.2f}m  final@apex={f_at_apex:+.2f}m",
                    flush=True,
                )
            written.append(driver)

        print(f"[BATCH] Done: {len(written)} written, {len(skipped)} skipped", flush=True)
        print("========== BATCH END ==========\n", flush=True)

        if written:
            self.report({'INFO'}, f"Generated {len(written)} styled racing lines: {', '.join(written)}")
            return {'FINISHED'}
        self.report({'WARNING'}, f"Generated 0; skipped {len(skipped)}: {'; '.join(skipped)[:160]}")
        return {'CANCELLED'}


class OBJECT_OT_LoadStyleFromJson(Operator):
    bl_idname = "object.load_style_from_json"
    bl_label = "Load Style from JSON"
    bl_description = "Read style params JSON (from F1 Race Replay Studio addon) and populate the sliders"

    def execute(self, context):
        import json
        props = context.scene.f1_track_props

        path = bpy.path.abspath(props.style_json_path) if props.style_json_path else ""
        if not path or not os.path.isfile(path):
            self.report({'ERROR'}, "Set Style JSON to a valid file path")
            return {'CANCELLED'}

        try:
            with open(path, "r", encoding="utf-8") as fp:
                payload = json.load(fp)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to parse JSON: {e}")
            return {'CANCELLED'}

        sp = payload.get("style_params")
        if not isinstance(sp, dict):
            self.report({'ERROR'}, "JSON missing 'style_params' object")
            return {'CANCELLED'}

        mapping = {
            "apex_phase":     "style_apex_phase",
            "apex_tightness": "style_apex_tightness",
            "entry_width":    "style_entry_width",
            "exit_width":     "style_exit_width",
            "vu_shape":       "style_vu_shape",
            "straight_bias":  "style_straight_bias",
            "smoothness":     "style_smoothness",
            "lr_asymmetry":   "style_lr_asymmetry",
        }
        loaded = []
        for json_key, prop_name in mapping.items():
            if json_key in sp:
                try:
                    setattr(props, prop_name, float(sp[json_key]))
                    loaded.append(json_key)
                except Exception:
                    pass

        src = payload.get("source", {})
        driver = str(src.get("driver", "")).strip() or "DRIVER"
        context.scene["_style_driver"] = driver

        corners_in = payload.get("corners")
        if isinstance(corners_in, list) and corners_in:
            context.scene["_style_corners"] = json.dumps(corners_in)
            corner_msg = f", {len(corners_in)} per-corner entries"
        else:
            if "_style_corners" in context.scene:
                del context.scene["_style_corners"]
            corner_msg = " (no per-corner data — JSON v1)"

        tag = f"{driver}/{src.get('grand_prix','?')}/{src.get('season','?')}"
        self.report({'INFO'}, f"Loaded {len(loaded)}/8 params from {tag}{corner_msg}")
        return {'FINISHED'}


class OBJECT_OT_AlignPathToRacingLine(Operator):
    bl_idname = "object.align_path_to_racing_line"
    bl_label = "Align / Reshape Path"
    bl_description = "Kabsch-align the Driving Path to Q_RACING_LINE or Q_RACING_LINE_STYLED (optionally overwrite source geometry)"

    def execute(self, context):
        if not dependencies_available():
            self.report({'ERROR'}, "Install dependencies first")
            return {'CANCELLED'}

        import numpy as np
        from mathutils import Vector

        props = context.scene.f1_track_props
        path = props.driving_path
        q_obj = props.alignment_target_curve
        target_name = q_obj.name if q_obj else "(none)"

        if not path:
            self.report({'ERROR'}, "Select a Driving Path")
            return {'CANCELLED'}
        if not q_obj:
            self.report({'ERROR'}, "Pick a Target Line via the eyedropper")
            return {'CANCELLED'}

        N = props.alignment_samples
        blend_ratio = props.alignment_blend

        spline_p = path.data.splines[0]
        if spline_p.type == 'BEZIER':
            n_p = len(spline_p.bezier_points)
            P_raw = np.zeros((n_p, 3))
            for i, bp in enumerate(spline_p.bezier_points):
                co = path.matrix_world @ bp.co
                P_raw[i] = [co.x, co.y, co.z]
        else:
            n_p = len(spline_p.points)
            P_raw = np.zeros((n_p, 3))
            for i, pt in enumerate(spline_p.points):
                co = path.matrix_world @ Vector(pt.co[:3])
                P_raw[i] = [co.x, co.y, co.z]

        spline_q = q_obj.data.splines[0]
        n_q = len(spline_q.points)
        Q_raw = np.zeros((n_q, 3))
        for i, pt in enumerate(spline_q.points):
            co = q_obj.matrix_world @ Vector(pt.co[:3])
            Q_raw[i] = [co.x, co.y, co.z]

        P_resampled = _resample_equidistant_3d(P_raw, N)
        Q_resampled = _resample_equidistant_3d(Q_raw, N)

        test_shifts = min(N, 100)
        shift_step = max(1, N // test_shifts)
        best_rms = float('inf')
        best_shift = 0

        for s in range(0, N, shift_step):
            Q_shifted = np.roll(Q_resampled, -s, axis=0)
            _, _, P_al = _kabsch_alignment(P_resampled, Q_shifted)
            rms = np.sqrt(((P_al - Q_shifted) ** 2).mean())
            if rms < best_rms:
                best_rms = rms
                best_shift = s

        for s in range(max(0, best_shift - shift_step), min(N, best_shift + shift_step + 1)):
            Q_shifted = np.roll(Q_resampled, -s, axis=0)
            _, _, P_al = _kabsch_alignment(P_resampled, Q_shifted)
            rms = np.sqrt(((P_al - Q_shifted) ** 2).mean())
            if rms < best_rms:
                best_rms = rms
                best_shift = s

        Q_final = np.roll(Q_resampled, -best_shift, axis=0)
        R, t, _ = _kabsch_alignment(P_resampled, Q_final)

        P_full_aligned = (R @ P_raw.T).T + t

        if blend_ratio > 0.0:
            M = len(P_full_aligned)
            K_len = len(Q_raw)
            shift_ratio = best_shift / N
            
            A = Q_raw
            B = np.roll(Q_raw, -1, axis=0)
            AB = B - A
            AB_len_sq = np.sum(AB**2, axis=1)
            AB_len_sq[AB_len_sq < 1e-12] = 1e-12
            
            P_projected = np.zeros((M, 3))
            window = max(20, int(K_len * 0.15)) 
            
            for i in range(M):
                pt = P_full_aligned[i]
                expected_k = int(((i / M) + shift_ratio) * K_len) % K_len
                idx = np.arange(expected_k - window, expected_k + window + 1) % K_len
                
                A_win = A[idx]
                AB_win = AB[idx]
                len_sq_win = AB_len_sq[idx]
                
                AP = pt - A_win
                dot_val = np.sum(AP * AB_win, axis=1)
                t_param = np.clip(dot_val / len_sq_win, 0.0, 1.0)
                
                proj = A_win + t_param[:, np.newaxis] * AB_win
                dists_sq = np.sum((pt - proj)**2, axis=1)
                best = np.argmin(dists_sq)
                P_projected[i] = proj[best]
            
            P_out = P_full_aligned * (1.0 - blend_ratio) + P_projected * blend_ratio
        else:
            P_out = P_full_aligned.copy()

        P_out[:, 2] = 0.0
        label = "ALIGNED_PATH_BLENDED"

        # Always clear any stale preview curve from previous runs so the scene
        # stays clean regardless of which mode we end up in.
        for d in [bpy.data.objects, bpy.data.curves]:
            if label in d:
                d.remove(d[label], do_unlink=True)

        # Preview mode: create ALIGNED_PATH_BLENDED as a separate curve.
        # Skipped when overwriting the source in place — that'd leave a
        # redundant second curve in the scene.
        if not props.overwrite_source_path:
            curve_data = bpy.data.curves.new(label, 'CURVE')
            curve_data.dimensions = '3D'
            sp_out = curve_data.splines.new('POLY')
            sp_out.points.add(len(P_out) - 1)
            for i in range(len(P_out)):
                sp_out.points[i].co = (P_out[i, 0], P_out[i, 1], P_out[i, 2], 1)
            sp_out.use_cyclic_u = True
            aligned_obj = bpy.data.objects.new(label, curve_data)
            bpy.context.collection.objects.link(aligned_obj)

        # Optional: overwrite the source curve's geometry in place, so any
        # follow-path rig targeting that curve automatically picks up the new shape.
        # Only spline points are touched — curve/object custom properties,
        # constraints, modifiers, drivers, and animation data are untouched.
        # Preserves original spline type (BEZIER / NURBS / POLY) so the rig's
        # expectations aren't broken.
        if props.overwrite_source_path:
            src_curve = path.data
            if src_curve.splines:
                orig_type = src_curve.splines[0].type
                orig_cyclic = bool(src_curve.splines[0].use_cyclic_u)
                orig_resolution = int(getattr(src_curve.splines[0], 'resolution_u', 12))
                orig_order = int(getattr(src_curve.splines[0], 'order_u', 4))
                orig_endpoint = bool(getattr(src_curve.splines[0], 'use_endpoint_u', True))
            else:
                orig_type, orig_cyclic = 'POLY', True
                orig_resolution, orig_order, orig_endpoint = 12, 4, True

            src_curve.splines.clear()
            new_sp = src_curve.splines.new(orig_type)
            inv = path.matrix_world.inverted()

            if orig_type == 'BEZIER':
                new_sp.bezier_points.add(len(P_out) - 1)
                for i in range(len(P_out)):
                    world_co = Vector((P_out[i, 0], P_out[i, 1], P_out[i, 2]))
                    local = inv @ world_co
                    bp = new_sp.bezier_points[i]
                    bp.co = (local.x, local.y, local.z)
                    bp.handle_left_type = 'AUTO'
                    bp.handle_right_type = 'AUTO'
            else:
                new_sp.points.add(len(P_out) - 1)
                for i in range(len(P_out)):
                    world_co = Vector((P_out[i, 0], P_out[i, 1], P_out[i, 2]))
                    local = inv @ world_co
                    new_sp.points[i].co = (local.x, local.y, local.z, 1)
                if orig_type == 'NURBS':
                    new_sp.order_u = orig_order
                    new_sp.resolution_u = orig_resolution
                    new_sp.use_endpoint_u = orig_endpoint

            new_sp.use_cyclic_u = orig_cyclic

        if props.overwrite_source_path:
            self.report({'INFO'},
                f"Reshaped '{path.name}' in place ({len(P_out)} pts, "
                f"target={target_name}, blend={blend_ratio:.2f})")
        else:
            self.report({'INFO'},
                f"{label} (preview-only, {len(P_out)} pts, "
                f"target={target_name}, blend={blend_ratio:.2f})")
        return {'FINISHED'}


class OBJECT_OT_AlignAllDriverPaths(Operator):
    bl_idname = "object.align_all_driver_paths"
    bl_label = "Align All Driver Paths"
    bl_description = (
        "For every Q_RACING_LINE_STYLED_{driver} in the scene, find the matching "
        "F1_Path_*{driver}* curve and Kabsch-align it. Uses the same alignment_blend "
        "/ alignment_samples / overwrite_source_path settings as the single-path button."
    )

    def execute(self, context):
        scene = context.scene
        props = scene.f1_track_props

        styled_lines = [
            o for o in scene.objects
            if o.type == 'CURVE' and o.name.startswith("Q_RACING_LINE_STYLED_")
            and o.name not in ("Q_RACING_LINE_STYLED",)
        ]
        if not styled_lines:
            self.report({'ERROR'},
                "No Q_RACING_LINE_STYLED_{driver} curves in scene — run 'Generate Styled Racing Lines' first")
            return {'CANCELLED'}

        # Driving paths: ONLY curves named driving_path_* (those are the rig-followed
        # curves that the launch_control pipeline creates; LC_Trail_* are mesh trails
        # and not what the cars follow).
        driving_paths = [
            o for o in scene.objects
            if o.type == 'CURVE' and o.name.startswith("driving_path_")
        ]
        # Trails are kept as a SECONDARY index: their names always carry the rig
        # suffix (incl. driver code), which lets us back-map a driver to a
        # team-only-named driving_path (e.g. driving_path_Mclaren ← Norris).
        trails = [
            o for o in scene.objects
            if o.type == 'CURVE' and o.name.startswith("LC_Trail_")
        ]

        print("\n========== ALIGN ALL — DEBUG ==========", flush=True)
        print(f"[ALIGN] styled lines in scene: {[o.name for o in styled_lines]}", flush=True)
        print(f"[ALIGN] driving paths in scene: {[o.name for o in driving_paths]}", flush=True)
        print(f"[ALIGN] trails in scene       : {[o.name for o in trails]}", flush=True)

        if not driving_paths:
            print("[ALIGN] *** no driving_path_* curves found ***", flush=True)
            print("========== ALIGN ALL — END ==========\n", flush=True)
            self.report({'ERROR'},
                "No driving_path_* curves in scene")
            return {'CANCELLED'}

        def _resolve_driving_path(driver_code):
            du = driver_code.upper()
            # 1. Direct: driving_path whose name itself carries the driver code.
            for p in driving_paths:
                if du in p.name.upper():
                    return p, "direct-name"
            # 2. Indirect via trail: find a trail with driver code, extract its
            #    rig suffix, then look up driving_path_<suffix> or progressively
            #    shorter prefixes of the suffix.
            for t in trails:
                if du not in t.name.upper():
                    continue
                suffix = t.name
                for prefix in ("LC_Trail_car_rig_", "LC_Trail_"):
                    if suffix.startswith(prefix):
                        suffix = suffix[len(prefix):]
                        break
                parts = suffix.split("_")
                for i in range(len(parts), 0, -1):
                    candidate_name = "driving_path_" + "_".join(parts[:i])
                    p = scene.objects.get(candidate_name)
                    if p is not None and p.type == 'CURVE' and p in driving_paths:
                        return p, f"trail→suffix({'_'.join(parts[:i])})"
            return None, None

        old_path = props.driving_path
        old_target = props.alignment_target_curve
        aligned, skipped = [], []
        for line in styled_lines:
            driver = line.name.rsplit("_", 1)[-1]
            cand, how = _resolve_driving_path(driver)
            if cand is None:
                skipped.append(f"{driver}: no driving_path_*{driver}* found (direct or via trail)")
                print(f"[ALIGN] {driver}: NO MATCH", flush=True)
                continue
            try:
                props.driving_path = cand
                props.alignment_target_curve = line
                bpy.ops.object.align_path_to_racing_line()
                aligned.append(f"{cand.name} → {line.name}")
                print(f"[ALIGN] {driver} ({how}): {cand.name} → {line.name} OK", flush=True)
            except Exception as e:
                skipped.append(f"{driver}: {e}")
                print(f"[ALIGN] {driver}: FAILED — {e}", flush=True)

        props.driving_path = old_path
        props.alignment_target_curve = old_target

        # Refresh trails so they re-bake from the modified driving paths
        # (launch_control's trail meshes reference the path geometry; without
        # this, trails stay on the old shape).
        try:
            bpy.ops.f1.refresh_trails()
            print("[ALIGN] f1.refresh_trails() OK — trails re-synced from updated paths", flush=True)
        except Exception as e:
            print(f"[ALIGN] f1.refresh_trails() skipped: {e}", flush=True)

        print(f"[ALIGN] Done: {len(aligned)} aligned, {len(skipped)} skipped", flush=True)
        print("========== ALIGN ALL — END ==========\n", flush=True)

        if aligned:
            msg = f"Aligned {len(aligned)} path(s)"
            if skipped:
                msg += f", skipped {len(skipped)}: {'; '.join(skipped)[:120]}"
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        self.report({'WARNING'}, f"Aligned 0; skipped {len(skipped)}: {'; '.join(skipped)[:160]}")
        return {'CANCELLED'}


# ═══════════════════════════════════════════════════════════════════════════════
# UI PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class VIEW3D_PT_F1TrackPanel(Panel):
    bl_label = "F1 Track Visualizer"
    bl_idname = "VIEW3D_PT_f1_track_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'F1 Track'

    def draw(self, context):
        layout = self.layout
        props = context.scene.f1_track_props
        missing = check_dependencies()

        box = layout.box()
        if missing:
            box.label(text="Missing packages:", icon='ERROR')
            for pkg in missing:
                box.label(text=f"  • {pkg}")
            box.operator("object.install_f1_dependencies", icon='IMPORT')
        else:
            box.label(text="Dependencies OK", icon='CHECKMARK')

        deps_ok = not bool(missing)

        box = layout.box()
        box.label(text="1. Fetch Telemetry", icon='IMPORT')
        col = box.column(align=True)
        col.prop(props, "season")
        col.prop(props, "grand_prix")
        col.prop(props, "session_type")
        col.prop(props, "driver_id")
        col.prop(props, "cache_dir")
        row = box.row()
        row.enabled = deps_ok
        row.operator("object.fetch_f1_data", icon='URL')

        box = layout.box()
        box.label(text="2. Create Driving Path", icon='CURVE_DATA')
        col = box.column(align=True)
        col.prop(props, "csv_file_path")
        col.prop(props, "scale_factor")
        col.prop(props, "curve_type")
        col.prop(props, "track_thickness")
        col.prop(props, "curve_resolution")
        box.operator("object.create_track_from_csv", icon='MOD_CURVE')

        box = layout.box()
        box.label(text="3. Centerline Generation", icon='SNAP_MIDPOINT')
        col = box.column(align=True)
        col.prop(props, "track_mesh", icon='MESH_PLANE')
        col.separator()
        col.prop(props, "centerline_iterations")
        col.prop(props, "centerline_ray_step")
        col.prop(props, "centerline_max_width")
        col.prop(props, "centerline_smooth_sigma")
        row = box.row()
        row.enabled = deps_ok
        row.operator("object.generate_centerline", icon='SNAP_MIDPOINT')

        box = layout.box()
        box.label(text="4. Racing Line (Min-Curvature)", icon='GP_MULTIFRAME_EDITING')
        col = box.column(align=True)
        col.prop(props, "racing_line_inset")
        col.prop(props, "racing_line_kappa_bound")
        col.prop(props, "racing_line_veh_width")
        col.prop(props, "racing_line_stepsize")
        row = box.row()
        row.enabled = deps_ok
        row.operator("object.generate_racing_line", icon='GP_MULTIFRAME_EDITING')

        box = layout.box()
        box.label(text="5. Style Layer", icon='MOD_CURVE')
        col = box.column(align=True)
        col.prop(props, "style_enabled")
        col.prop(props, "style_master", slider=True)
        col.separator()
        col.label(text="Corner Shape:")
        col.prop(props, "style_apex_phase", slider=True)
        col.prop(props, "style_apex_tightness", slider=True)
        col.prop(props, "style_vu_shape", slider=True)
        col.separator()
        col.label(text="Lateral Position:")
        col.prop(props, "style_entry_width", slider=True)
        col.prop(props, "style_exit_width", slider=True)
        col.prop(props, "style_straight_bias", slider=True)
        col.separator()
        col.label(text="Character:")
        col.prop(props, "style_smoothness", slider=True)
        col.prop(props, "style_lr_asymmetry", slider=True)
        col.separator()
        col.label(text="Style JSON folder (auto-discovered):")
        col.prop(props, "style_json_path")
        row = box.row()
        row.enabled = deps_ok
        row.scale_y = 1.4
        row.operator("object.generate_all_styled_racing_lines", icon='MOD_CURVE')

        box = layout.box()
        box.label(text="6. Path Alignment / Reshape", icon='CON_ROTLIKE')
        col = box.column(align=True)
        col.prop(props, "alignment_samples")
        col.prop(props, "alignment_blend", slider=True)
        col.prop(props, "overwrite_source_path")
        col.separator()
        row = box.row()
        row.enabled = deps_ok
        row.scale_y = 1.4
        row.operator("object.align_all_driver_paths", icon='CON_ROTLIKE')
        col.separator()
        col.label(text="Single-path manual mode:")
        col.prop(props, "driving_path", icon='CURVE_BEZCURVE')
        col.prop(props, "alignment_target_curve", icon='OUTLINER_OB_CURVE')
        row = box.row()
        row.enabled = deps_ok
        row.operator("object.align_path_to_racing_line", icon='CON_ROTLIKE')


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

classes = (
    F1TrackProperties,
    OBJECT_OT_InstallF1Dependencies,
    OBJECT_OT_FetchF1Data,
    OBJECT_OT_CreateTrackFromCSV,
    OBJECT_OT_GenerateCenterline,
    OBJECT_OT_GenerateRacingLine,
    OBJECT_OT_GenerateAllStyledRacingLines,
    OBJECT_OT_LoadStyleFromJson,
    OBJECT_OT_AlignPathToRacingLine,
    OBJECT_OT_AlignAllDriverPaths,
    VIEW3D_PT_F1TrackPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.f1_track_props = bpy.props.PointerProperty(type=F1TrackProperties)
    modules_path = get_modules_path()
    append_modules_to_sys_path(modules_path)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.f1_track_props

if __name__ == "__main__":
    register()
