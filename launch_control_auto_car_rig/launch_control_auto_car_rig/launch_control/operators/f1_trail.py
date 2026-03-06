import bpy
import math
from mathutils import Vector

SAFETY_MARGIN = 1.0
CAR_BONE = "bone_body_FollowPath"


def _get_trail_z_offset(scene):
    try:
        return getattr(scene.f1_pipeline_props, 'trail_z_offset', 0.2)
    except Exception:
        return 0.2


def _get_car_up_vector(rig):
    """Get the car's local Y axis in world space (points up from the car)."""
    bone = rig.pose.bones.get(CAR_BONE)
    if bone:
        mw = rig.matrix_world @ bone.matrix
        up = mw.to_3x3().col[1].normalized()
        if up.length_squared > 0.0001:
            return up
    return Vector((0, 1, 0))


def _raise_along_up(local_co, obj_matrix, up_world, offset):
    """Offset point along the given world-space up direction (negative = down)."""
    v = Vector(local_co)
    is_4d = len(v) == 4
    xyz = Vector((v.x, v.y, v.z)) if is_4d else v
    world = obj_matrix @ xyz
    world += up_world * offset
    local = obj_matrix.inverted() @ world
    if is_4d:
        return (local.x, local.y, local.z, v.w)
    return local


def _bezier_point_at_t(p0, p1, p2, p3, t):
    u = 1.0 - t
    return u*u*u*p0 + 3*u*u*t*p1 + 3*u*t*t*p2 + t*t*t*p3


def _find_car_fraction_on_trail(trail_obj, car_world_pos):
    """Find where the car sits on the trail curve as a 0-1 fraction.
    Samples the Bezier segments and returns the fraction of the closest point."""
    if not trail_obj or trail_obj.type != 'CURVE' or not trail_obj.data.splines:
        return 0.0
    spline = trail_obj.data.splines[0]
    if spline.type != 'BEZIER' or len(spline.bezier_points) < 2:
        return 0.0

    mw = trail_obj.matrix_world
    pts = spline.bezier_points
    n_seg = len(pts) - 1
    if spline.use_cyclic_u:
        n_seg = len(pts)
    if n_seg <= 0:
        return 0.0

    best_f = 0.0
    best_dist_sq = float('inf')
    samples_per_seg = 32

    for seg in range(n_seg):
        i0 = seg
        i1 = (seg + 1) % len(pts)
        p0 = Vector(pts[i0].co)
        p1 = Vector(pts[i0].handle_right)
        p2 = Vector(pts[i1].handle_left)
        p3 = Vector(pts[i1].co)
        for k in range(samples_per_seg + 1):
            t = k / samples_per_seg
            pt_world = mw @ _bezier_point_at_t(p0, p1, p2, p3, t)
            dist_sq = (pt_world - car_world_pos).length_squared
            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_f = min((seg + t) / n_seg, 1.0)

    return best_f


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))

def setup_trail_for_driver(driver_code, constructor_color_hex, rig_object, curve_obj):
    if not curve_obj:
        print(f"[F1Trail] ERROR: No curve passed for {driver_code}")
        return

    scene = bpy.context.scene

    # Use rig name for trail identity so same driver from different sessions gets separate trails
    trail_suffix = rig_object.name
    trail_name = f"LC_Trail_{trail_suffix}"

    # 1. Remove existing trail for THIS rig only (in case of re-run)
    existing = bpy.data.objects.get(trail_name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)

    # 2. Build a FRESH curve data block — don't copy LC's data
    trail_curve_data = bpy.data.curves.new(name=trail_name, type='CURVE')
    trail_curve_data.dimensions = '3D'
    trail_curve_data.bevel_depth = 0.0
    trail_curve_data.extrude = 0.15
    trail_curve_data.fill_mode = 'FULL'
    trail_curve_data.bevel_factor_end = 0.0
    trail_curve_data.bevel_factor_mapping_end = 'RESOLUTION'

    # 3. Copy spline points from source, offset along car's Z axis so trail stays above track
    mw = curve_obj.matrix_world
    up = _get_car_up_vector(rig_object)
    offset = _get_trail_z_offset(scene)
    for src_spline in curve_obj.data.splines:
        if src_spline.type == 'BEZIER':
            new_spline = trail_curve_data.splines.new('BEZIER')
            pts = src_spline.bezier_points
            new_spline.bezier_points.add(len(pts) - 1)
            for i, src_pt in enumerate(pts):
                dst_pt = new_spline.bezier_points[i]
                dst_pt.co = _raise_along_up(src_pt.co, mw, up, offset)
                dst_pt.handle_left = _raise_along_up(src_pt.handle_left, mw, up, offset)
                dst_pt.handle_right = _raise_along_up(src_pt.handle_right, mw, up, offset)
                dst_pt.handle_left_type = src_pt.handle_left_type
                dst_pt.handle_right_type = src_pt.handle_right_type
                dst_pt.tilt = math.radians(90)
            new_spline.use_cyclic_u = False
        elif src_spline.type == 'NURBS':
            new_spline = trail_curve_data.splines.new('NURBS')
            pts = src_spline.points
            new_spline.points.add(len(pts) - 1)
            for i, src_pt in enumerate(pts):
                new_spline.points[i].co = _raise_along_up(src_pt.co, mw, up, offset)
            new_spline.use_cyclic_u = False

    # 4. Create object with fresh data, match transforms
    trail_obj = bpy.data.objects.new(trail_name, trail_curve_data)
    scene.collection.objects.link(trail_obj)
    trail_obj.location = curve_obj.location.copy()
    trail_obj.rotation_euler = curve_obj.rotation_euler.copy()
    trail_obj.scale = curve_obj.scale.copy()

    # 5. Material (unique per rig so same driver in multiple cars gets separate materials)
    mat_name = f"F1Trail_{trail_suffix}"
    mat = bpy.data.materials.get(mat_name)
    if mat:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        rgb = hex_to_rgb(constructor_color_hex)
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.3
        bsdf.inputs["Emission Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 2.0
    mat.diffuse_color = (*hex_to_rgb(constructor_color_hex), 1.0)
    trail_obj.data.materials.append(mat)

    trail_obj["rig_name"] = rig_object.name
    trail_obj["path_name"] = curve_obj.name

    register_trail_handler()
    print(f"[F1Trail] Trail created for {driver_code} ({rig_object.name}) | color: {constructor_color_hex}")


def _get_car_world_pos(rig):
    """Get the car's actual world position from the bone that follows the path."""
    bone = rig.pose.bones.get(CAR_BONE)
    if bone:
        return (rig.matrix_world @ bone.matrix).translation.copy()
    return rig.matrix_world.translation.copy()


def f1_trail_update(scene, depsgraph=None):
    for obj in scene.objects:
        if not obj.name.startswith("LC_Trail_") or obj.type != 'CURVE':
            continue
        rig_name = obj.get("rig_name")
        if not rig_name:
            continue
        rig = scene.objects.get(rig_name)
        if not rig:
            continue
        try:
            car_pos = _get_car_world_pos(rig)
            fraction = _find_car_fraction_on_trail(obj, car_pos)
            obj.data.bevel_factor_end = min(max(fraction * SAFETY_MARGIN, 0.0), 1.0)
        except Exception as e:
            print(f"[F1Trail] Handler error: {e}")


def register_trail_handler():
    handlers = bpy.app.handlers.frame_change_post
    for h in handlers[:]:
        if getattr(h, '__name__', '') == 'f1_trail_update':
            handlers.remove(h)
    handlers.append(f1_trail_update)
    print("[F1Trail] Handler registered")


def sync_trail_geometry_from_path(path_obj, trail_obj, rig_obj=None, scene=None):
    """Copy spline geometry and transform from path to trail, offset along car Z so trail stays above track."""
    if not path_obj or not trail_obj or path_obj.type != 'CURVE' or trail_obj.type != 'CURVE':
        return
    src_data = path_obj.data
    dst_data = trail_obj.data
    if not src_data.splines or not dst_data.splines:
        return
    mw = path_obj.matrix_world
    up = _get_car_up_vector(rig_obj) if rig_obj else Vector((0, 1, 0))
    offset = _get_trail_z_offset(scene) if scene else 0.2

    for si, src_spline in enumerate(src_data.splines):
        if si >= len(dst_data.splines):
            break
        dst_spline = dst_data.splines[si]
        if src_spline.type == 'BEZIER' and dst_spline.type == 'BEZIER':
            src_pts = src_spline.bezier_points
            dst_pts = dst_spline.bezier_points
            need = len(src_pts) - len(dst_pts)
            if need > 0:
                dst_pts.add(need)
            for i, src_pt in enumerate(src_pts):
                if i < len(dst_pts):
                    dst_pt = dst_pts[i]
                    dst_pt.co = _raise_along_up(src_pt.co, mw, up, offset)
                    dst_pt.handle_left = _raise_along_up(src_pt.handle_left, mw, up, offset)
                    dst_pt.handle_right = _raise_along_up(src_pt.handle_right, mw, up, offset)
                    dst_pt.handle_left_type = src_pt.handle_left_type
                    dst_pt.handle_right_type = src_pt.handle_right_type
                    dst_pt.tilt = math.radians(90)
        elif src_spline.type == 'NURBS' and dst_spline.type == 'NURBS':
            src_pts = src_spline.points
            dst_pts = dst_spline.points
            need = len(src_pts) - len(dst_pts)
            if need > 0:
                dst_pts.add(need)
            for i, src_pt in enumerate(src_pts):
                if i < len(dst_pts):
                    dst_pts[i].co = _raise_along_up(src_pt.co, mw, up, offset)

    trail_obj.location = path_obj.location.copy()
    trail_obj.rotation_euler = path_obj.rotation_euler.copy()
    trail_obj.scale = path_obj.scale.copy()
    dst_data.update_tag()


def sync_all_trails_from_paths(scene):
    """Sync all LC_Trail_* geometry and transform from their driving paths."""
    if not hasattr(scene, 'lc') or not scene.lc or not scene.lc.cars:
        return
    for car in scene.lc.cars:
        if not car.driving_path or car.driving_path.type != 'CURVE':
            continue
        path_obj = car.driving_path
        trail = None
        if car.rig_object:
            rig_name = car.rig_object.name
            for obj in scene.objects:
                if obj.name.startswith("LC_Trail_") and obj.type == 'CURVE' and obj.get("rig_name") == rig_name:
                    trail = obj
                    break
        if not trail and path_obj.name.startswith("driving_path_"):
            suffix = path_obj.name.replace("driving_path_", "").split(".")[0]
            trail = scene.objects.get(f"LC_Trail_{suffix}")
        if trail:
            sync_trail_geometry_from_path(path_obj, trail, car.rig_object, scene)


def unregister_trail_handler():
    handlers = bpy.app.handlers.frame_change_post
    for h in handlers[:]:
        if getattr(h, '__name__', '') == 'f1_trail_update':
            handlers.remove(h)
