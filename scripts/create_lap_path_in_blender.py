"""
Create one Blender curve from a JSON file of 3D points.
Smooth path (smooth=true in JSON): AUTO handles for smooth interpolation.
Raw path: VECTOR handles, point-to-point.
No addons. Edit FILEPATH below and run script in Scripting workspace.
"""

import bpy
import json
import os

# Full path to your lap JSON file. Run script with Alt+P.
FILEPATH = r"d:\Work\Blender Projects\HotLap\f1_hot_lap\scripts\lap_path.json"

CURVE_NAME = "LapPath"


def parse_points(data):
    pts = data.get("points") or data.get("path") or []
    if not pts:
        raise ValueError("JSON must contain a 'points' (or 'path') array")
    out = []
    for p in pts:
        if isinstance(p, (list, tuple)):
            out.append((float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0))
        else:
            out.append((float(p["x"]), float(p["y"]), float(p.get("z", 0))))
    return out


def make_curve(points, closed=True, smooth_handles=False, name=CURVE_NAME):
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    if name in bpy.data.curves:
        bpy.data.curves.remove(bpy.data.curves[name], do_unlink=True)

    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("BEZIER")
    n = len(points)
    spline.bezier_points.add(n - 1)

    handle_type = "AUTO" if smooth_handles else "VECTOR"
    for i, (px, py, pz) in enumerate(points):
        bp = spline.bezier_points[i]
        bp.co = (px, py, pz)
        bp.handle_left_type = handle_type
        bp.handle_right_type = handle_type

    spline.use_cyclic_u = bool(closed)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def main():
    path = FILEPATH.strip()
    if not path:
        print("Set FILEPATH at the top of this script to your JSON file path.")
        return
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    points = parse_points(data)
    closed = data.get("closed", True)
    smooth_handles = data.get("smooth", False)
    obj = make_curve(points, closed=closed, smooth_handles=smooth_handles)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    print(f"Created {obj.name} with {len(points)} points (smooth_handles={smooth_handles}).")


if __name__ == "__main__":
    main()
