"""svg_to_outline.py

Parse an Inkscape SVG centerline of a race track and build an outline JSON
(outer + inner road edges) in the schema raceline_video.py already consumes.

Spec: docs/superpowers/specs/2026-05-19-canada-2026-revamp-design.md
"""
import re

import numpy as np
from scipy.interpolate import splprep, splev

# === Constants (see spec §5) ============================================
TRACK_LENGTH_M          = 4361.0
ROAD_WIDTH_M            = 13.0
HAIRPIN_NARROW_M        = 10.5
HAIRPIN_HALF_RANGE_M    = 60.0
N_OUTPUT_POINTS         = 2000
BEZIER_SAMPLES_PER_SEG  = 40
SF_LINE_KAPPA_THRESH    = 0.001
SCALE_SANITY_MIN        = 0.5
SCALE_SANITY_MAX        = 50.0


# === SVG path parser ====================================================

_NUM_RE = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")

# How many coordinate pairs each command consumes per "instance"
_PAIRS_PER_CMD = {
    "M": 1, "L": 1, "T": 1,
    "H": 0, "V": 0,           # special: single number, not pair (not used by Inkscape export here)
    "C": 3,
    "S": 2, "Q": 2,
    "A": 0,                   # arc — not handled (Inkscape Canada export uses only M/m, C/c, Z/z)
    "Z": 0,
}


def parse_svg_path_d(d_str):
    """Tokenise an SVG path `d` attribute into a list of (CMD, [(x,y), ...]) tuples
    with all coordinates expanded to absolute. Supports M/m, L/l, C/c, Z/z —
    which is all the Canada Inkscape export uses.

    NOTE for callers extracting `d=` from raw SVG text via regex: use the pattern
    r'(?:^|\\s)d\\s*=\\s*"([^"]+)"' (d preceded by whitespace or start-of-string),
    NOT the bare r'd\\s*=\\s*"([^"]+)"'. The bare pattern matches the substring
    `d="..."` inside Inkscape id attributes (e.g. id="svg3151") before it ever
    reaches the actual <path d="..."> attribute.
    """
    tokens = re.findall(r"[MmLlCcZz]|" + _NUM_RE.pattern, d_str)

    out = []
    cx, cy = 0.0, 0.0          # current point
    sx, sy = 0.0, 0.0          # start of current subpath (for Z)
    i = 0
    last_cmd = None
    while i < len(tokens):
        tok = tokens[i]
        if tok in "MmLlCcZz":
            cmd = tok
            i += 1
        else:
            # Number with no preceding letter → implicit repeat of previous command.
            # SVG rule: after an M/m, the implicit repeat is L/l, not M/m.
            if last_cmd is None:
                raise ValueError(f"Number {tok!r} with no preceding command")
            if last_cmd in ("Z", "z"):
                raise ValueError(f"Number {tok!r} after Z is invalid SVG (Z must be followed by M)")
            if last_cmd == "M":
                cmd = "L"
            elif last_cmd == "m":
                cmd = "l"
            else:
                cmd = last_cmd

        upper = cmd.upper()
        rel = cmd.islower()

        if upper == "Z":
            out.append(("Z", []))
            cx, cy = sx, sy
            last_cmd = cmd
            continue

        n_pairs = _PAIRS_PER_CMD[upper]
        coords = []
        for _ in range(n_pairs):
            x = float(tokens[i]); y = float(tokens[i + 1]); i += 2
            if rel:
                x += cx; y += cy
            coords.append((x, y))

        # update current point
        cx, cy = coords[-1]
        if upper == "M":
            sx, sy = cx, cy

        out.append((upper, coords))
        last_cmd = cmd

    return out


# === Bezier sampling & polyline expansion ==============================

def sample_cubic_bezier(p0, p1, p2, p3, n):
    """Sample n points (inclusive of endpoints) along a cubic Bezier curve."""
    out = []
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0.0
        u = 1.0 - t
        b0 = u * u * u
        b1 = 3.0 * u * u * t
        b2 = 3.0 * u * t * t
        b3 = t * t * t
        x = b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0]
        y = b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]
        out.append((x, y))
    return out


def commands_to_polyline(cmds, n_per_seg=BEZIER_SAMPLES_PER_SEG):
    """Expand a parsed command list into a dense polyline. Skips the start of
    each segment after the first to avoid duplicate points at joins.
    Supports M, L, C, Z."""
    pts = []
    cur = None
    subpath_start = None
    for kind, coords in cmds:
        if kind == "M":
            cur = coords[0]
            subpath_start = cur
            pts.append(cur)
        elif kind == "L":
            for tgt in coords:
                pts.append(tgt)
                cur = tgt
        elif kind == "C":
            # SVG cubic: control1, control2, end
            c1, c2, end = coords
            sample = sample_cubic_bezier(cur, c1, c2, end, n_per_seg)
            pts.extend(sample[1:])   # drop the duplicate start
            cur = end
        elif kind == "Z":
            if subpath_start is not None and cur != subpath_start:
                pts.append(subpath_start)
                cur = subpath_start
    return pts


# === Geometry helpers (flip, scale, recentre, resample) ================

def y_flip(pts):
    """Negate the y coordinate so SVG-down becomes math-up."""
    pts = np.asarray(pts, dtype=float).copy()
    pts[:, 1] = -pts[:, 1]
    return pts


def scale_to_length(pts, target_arc_m):
    """Uniform-scale a closed polyline so its perimeter == target_arc_m.
    Returns (scaled_pts, scale_factor)."""
    pts = np.asarray(pts, dtype=float)
    seg = np.linalg.norm(np.diff(np.vstack([pts, pts[0]]), axis=0), axis=1)
    raw_arc = float(seg.sum())
    if raw_arc <= 0.0:
        raise ValueError("scale_to_length: zero-length polyline")
    scale = target_arc_m / raw_arc
    return pts * scale, scale


def recentre(pts):
    """Subtract the centroid so the loop is centred on origin."""
    pts = np.asarray(pts, dtype=float)
    return pts - pts.mean(axis=0, keepdims=True)


def smooth_resample_loop(poly, n_out, smooth_s):
    """Periodic cubic-spline smooth + uniform arc-length resample.

    `smooth_s` is `splprep`'s sum-of-squared-residuals bound, in the SAME
    UNITS² as `poly`. It scales with the polyline's size: production uses
    s≈10–30 on a ~4361 m track (raceline_video.py:54-55), which corresponds
    to s≈0.01–0.05 on a unit-radius circle.

    Same pattern as raceline_video.py:113 (kept consistent for readability)."""
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


# === Edge generation (outer/inner from centerline) =====================

def compute_left_normals(pts):
    """3-point tangent → left-normal at each station of a closed polyline.

    Expects CCW (math-convention) input. For CW input the returned normals
    still point left of the tangent — they just point outward from the loop
    instead of inward. The ±3 stencil (vs ±1 central difference) is
    deliberate noise rejection: a 2000-station resampled track has small
    per-station jitter from the spline that a 1-step difference amplifies.
    """
    pts = np.asarray(pts, dtype=float)
    n = len(pts)
    tang = np.zeros_like(pts)
    for i in range(n):
        d = pts[(i + 3) % n] - pts[(i - 3) % n]
        nm = np.linalg.norm(d)
        tang[i] = d / nm if nm > 1e-8 else np.array([1.0, 0.0])
    # Left-normal of tangent (tx, ty) = (-ty, tx)
    return np.column_stack([-tang[:, 1], tang[:, 0]])


def generate_edges_constant_width(centerline, width_m):
    """Offset the centerline by ±W/2 along the left-normal to get outer/inner.

    PRECONDITION: `centerline` must be CCW in math coordinates. For a CCW
    loop, the left-normal points INWARD → inner = centerline + W/2·n_left,
    outer = centerline - W/2·n_left. CW input produces inner/outer SWAPPED
    (no error). Task 7's main() is responsible for enforcing orientation
    (signed-area check) before calling this helper.
    """
    nrm = compute_left_normals(centerline)
    half = width_m / 2.0
    inner = centerline + half * nrm
    outer = centerline - half * nrm
    return outer, inner


# === Curvature, hairpin narrowing, start/finish detection ==============

def compute_curvature(pts):
    """Discrete signed curvature κ at each station of a closed polyline."""
    pts = np.asarray(pts, dtype=float)
    n = len(pts)
    kappa = np.zeros(n)
    for i in range(n):
        a = pts[(i - 1) % n]
        b = pts[i]
        c = pts[(i + 1) % n]
        ab = b - a; bc = c - b
        cross = ab[0] * bc[1] - ab[1] * bc[0]
        denom = np.linalg.norm(ab) * np.linalg.norm(bc) * np.linalg.norm(c - a)
        kappa[i] = 0.0 if denom < 1e-9 else 2.0 * cross / denom
    return kappa


def apply_hairpin_narrowing(widths, kappa, arc_per_step, half_range_m,
                             narrowed_width):
    """In-place: narrow `widths` to `narrowed_width` within ±half_range_m
    (in arc length) of the global |κ| peak. Linear taper at the edges."""
    n = len(widths)
    peak = int(np.argmax(np.abs(kappa)))
    half_range_steps = int(half_range_m / arc_per_step)
    if half_range_steps == 0:
        widths[peak] = narrowed_width
        return
    for offset in range(-half_range_steps, half_range_steps + 1):
        idx = (peak + offset) % n
        # Linear taper: 0 at edge, 1 at peak
        t = 1.0 - abs(offset) / float(half_range_steps)
        w_target = widths[idx] * (1.0 - t) + narrowed_width * t
        if w_target < widths[idx]:    # only narrow, never widen
            widths[idx] = w_target


def find_start_finish_index(kappa, low_thresh=SF_LINE_KAPPA_THRESH):
    """Return the index that is the midpoint of the longest contiguous run
    of |κ| < low_thresh on a closed loop. Used to place s=0 at the longest
    straight (proxy for the start/finish line)."""
    n = len(kappa)
    is_straight = np.abs(kappa) < low_thresh
    if not is_straight.any():
        return 0
    # Walk the loop twice to find the longest run accounting for wrap-around
    doubled = np.concatenate([is_straight, is_straight])
    best_len, best_start = 0, 0
    i = 0
    while i < 2 * n:
        if doubled[i]:
            j = i
            while j < 2 * n and doubled[j]:
                j += 1
            run_len = j - i
            if run_len > best_len and run_len <= n:
                best_len, best_start = run_len, i
            i = j
        else:
            i += 1
    mid = (best_start + best_len // 2) % n
    return mid
