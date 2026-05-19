"""svg_to_outline.py

Parse an Inkscape SVG centerline of a race track and build an outline JSON
(outer + inner road edges) in the schema raceline_video.py already consumes.

Spec: docs/superpowers/specs/2026-05-19-canada-2026-revamp-design.md
"""
import re

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
