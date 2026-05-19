import pytest
from svg_to_outline import parse_svg_path_d


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
