import bpy
import math

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))

def setup_trail_for_driver(driver_code, constructor_color_hex, rig_object, curve_obj):
    if not curve_obj:
        print(f"[F1Trail] ERROR: No curve passed for {driver_code}")
        return

    scene = bpy.context.scene

    # 1. Remove existing trail
    trail_name = f"LC_Trail_{driver_code}"
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

    # 3. Copy spline points manually from source curve
    for src_spline in curve_obj.data.splines:
        if src_spline.type == 'BEZIER':
            new_spline = trail_curve_data.splines.new('BEZIER')
            pts = src_spline.bezier_points
            new_spline.bezier_points.add(len(pts) - 1)  # add() adds ON TOP of the 1 that exists
            for i, src_pt in enumerate(pts):
                dst_pt = new_spline.bezier_points[i]
                dst_pt.co = src_pt.co.copy()
                dst_pt.handle_left = src_pt.handle_left.copy()
                dst_pt.handle_right = src_pt.handle_right.copy()
                dst_pt.handle_left_type = src_pt.handle_left_type
                dst_pt.handle_right_type = src_pt.handle_right_type
                dst_pt.tilt = math.radians(90)
            new_spline.use_cyclic_u = False
        elif src_spline.type == 'NURBS':
            new_spline = trail_curve_data.splines.new('NURBS')
            pts = src_spline.points
            new_spline.points.add(len(pts) - 1)
            for i, src_pt in enumerate(pts):
                new_spline.points[i].co = src_pt.co.copy()
            new_spline.use_cyclic_u = False

    # 4. Create object with fresh data, match transforms
    trail_obj = bpy.data.objects.new(trail_name, trail_curve_data)
    scene.collection.objects.link(trail_obj)
    trail_obj.location = curve_obj.location.copy()
    trail_obj.rotation_euler = curve_obj.rotation_euler.copy()
    trail_obj.scale = curve_obj.scale.copy()

    # 5. Material
    mat_name = f"F1Trail_{driver_code}"
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

    # 6. Store rig reference for handler
    trail_obj["rig_name"] = rig_object.name
    trail_obj["max_speed_val"] = 523.5621948242188

    register_trail_handler()
    print(f"[F1Trail] Trail created for {driver_code} | color: {constructor_color_hex}")


def f1_trail_update(scene, depsgraph=None):
    for obj in scene.objects:
        if not obj.name.startswith("LC_Trail_") or obj.type != 'CURVE':
            continue
        rig_name = obj.get("rig_name")
        max_val = obj.get("max_speed_val", 523.56)
        if not rig_name:
            continue
        rig = scene.objects.get(rig_name)
        if not rig:
            continue
        try:
            bone = rig.pose.bones.get("bone_Speed_Rotate")
            if not bone:
                continue
            speed_val = bone.rotation_euler[2]
            progress = min(max(speed_val / max_val, 0.0), 1.0)
            obj.data.bevel_factor_end = progress
        except Exception as e:
            print(f"[F1Trail] Handler error: {e}")


def register_trail_handler():
    handlers = bpy.app.handlers.frame_change_post
    for h in handlers[:]:
        if getattr(h, '__name__', '') == 'f1_trail_update':
            handlers.remove(h)
    handlers.append(f1_trail_update)
    print("[F1Trail] Handler registered")


def unregister_trail_handler():
    handlers = bpy.app.handlers.frame_change_post
    for h in handlers[:]:
        if getattr(h, '__name__', '') == 'f1_trail_update':
            handlers.remove(h)