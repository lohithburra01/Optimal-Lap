import math
import pytest
from svg_to_outline import parse_svg_path_d, sample_cubic_bezier, commands_to_polyline


def test_simple_move_and_close():
    # absolute moveto then close
    cmds = parse_svg_path_d("M 10,20 z")
    assert cmds == [("M", [(10.0, 20.0)]), ("Z", [])]


def test_relative_move_becomes_absolute():
    # relative m starting from origin = same as absolute M for the first pair
    cmds = parse_svg_path_d("m 5,10 z")
    assert cmds[0] == ("M", [(5.0, 10.0)])


def test_relative_cubic_after_move():
    # m 10,20  c 1,2 3,4 5,6  z
    # current = (10,20); cubic control1=(11,22), control2=(13,24), end=(15,26)
    cmds = parse_svg_path_d("m 10,20 c 1,2 3,4 5,6 z")
    assert cmds[0] == ("M", [(10.0, 20.0)])
    assert cmds[1] == ("C", [(11.0, 22.0), (13.0, 24.0), (15.0, 26.0)])
    assert cmds[2] == ("Z", [])


def test_implicit_repeat_cubic():
    # SVG spec: after a 'c', a second triple of pairs is another implicit 'c'.
    cmds = parse_svg_path_d("m 0,0 c 1,0 2,0 3,0 1,0 2,0 3,0 z")
    # Two cubics in a row: ends should be at (3,0) and then (6,0)
    assert len(cmds) == 4  # M, C, C, Z
    assert cmds[1][0] == "C"
    assert cmds[2][0] == "C"
    assert cmds[2][1][2] == (6.0, 0.0)


def test_canada_circuit_path_parses():
    # Smoke check on the actual file
    with open("CANADA CIRCUIT.svg", encoding="utf-8") as f:
        text = f.read()
    # Extract the d="..." attribute (single path in file)
    import re
    m = re.search(r'(?:^|\s)d\s*=\s*"([^"]+)"', text)
    assert m is not None, "no d attribute found in CANADA CIRCUIT.svg"
    cmds = parse_svg_path_d(m.group(1))
    # Must contain a moveto, several cubics, and a closepath
    cmd_kinds = [c[0] for c in cmds]
    assert "M" in cmd_kinds
    assert "C" in cmd_kinds
    assert cmd_kinds[-1] == "Z"
    # Must produce a non-trivial number of cubic segments (Canada path has many)
    assert sum(1 for k in cmd_kinds if k == "C") >= 20


def test_number_after_z_raises():
    with pytest.raises(ValueError, match="after Z"):
        parse_svg_path_d("M 0,0 Z 20,20")


def test_bezier_endpoints():
    p0 = (0.0, 0.0); p1 = (1.0, 2.0); p2 = (3.0, 2.0); p3 = (4.0, 0.0)
    pts = sample_cubic_bezier(p0, p1, p2, p3, n=10)
    # First sample should be p0; last should be p3
    assert pts[0] == pytest.approx(p0)
    assert pts[-1] == pytest.approx(p3)
    assert len(pts) == 10


def test_bezier_midpoint_known():
    # Symmetric control hull -> t=0.5 lies on the perpendicular bisector of p0p3
    p0 = (0.0, 0.0); p1 = (0.0, 1.0); p2 = (1.0, 1.0); p3 = (1.0, 0.0)
    pts = sample_cubic_bezier(p0, p1, p2, p3, n=11)   # odd n -> t=0.5 hit exactly
    mid = pts[5]
    assert mid[0] == pytest.approx(0.5, abs=1e-9)
    assert mid[1] == pytest.approx(0.75, abs=1e-9)   # B(0.5)=0.125*0 + 0.375*1 + 0.375*1 + 0.125*0


def test_commands_to_polyline_simple():
    # Single cubic segment: M (0,0)  C (1,0)(2,0)(3,0)  Z
    cmds = [("M", [(0.0, 0.0)]), ("C", [(1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]), ("Z", [])]
    poly = commands_to_polyline(cmds, n_per_seg=10)
    # Start at (0,0); end at (3,0) before Z snaps back; closure point appended
    assert poly[0] == pytest.approx((0.0, 0.0))
    assert poly[-1] == pytest.approx((0.0, 0.0))   # Z closes back to subpath start


def test_canada_polyline_has_thousands_of_points():
    import re
    with open("CANADA CIRCUIT.svg", encoding="utf-8") as f:
        text = f.read()
    d = re.search(r'(?:^|\s)d\s*=\s*"([^"]+)"', text).group(1)
    cmds = parse_svg_path_d(d)
    poly = commands_to_polyline(cmds, n_per_seg=40)
    # Canada SVG has >=20 cubics x 40 samples ~ 800+ points
    assert len(poly) >= 800
    # Bounding box should match SVG width/height ballpark (1494.5 x 729.5)
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    assert max(xs) - min(xs) > 1000
    assert max(ys) - min(ys) > 350
