"""
BACKUP: Raw path (VECTOR handles, point-to-point). Original create_lap_path_in_blender.py.
Restore with: copy this file over create_lap_path_in_blender.py to get raw behaviour back.
"""

import bpy
import json
import os

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


def make_curve(points, closed=True, name=CURVE_NAME):
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    if name in bpy.data.curves:
        bpy.data.curves.remove(bpy.data.curves[name], do_unlink=True)

    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("BEZIER")
    n = len(points)
    spline.bezier_points.add(n - 1)

    for i, (px, py, pz) in enumerate(points):
        bp = spline.bezier_points[i]
        bp.co = (px, py, pz)
        bp.handle_left_type = "VECTOR"
        bp.handle_right_type = "VECTOR"

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
    obj = make_curve(points, closed=closed)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    print(f"Created {obj.name} with {len(points)} points.")


if __name__ == "__main__":
    main()
