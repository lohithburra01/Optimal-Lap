import bpy
import math
import mathutils

from .maths import get_rear_axle, get_2Drotation
from ..globals import (
    OBJECT_HIGHBEAM_L,
    OBJECT_HIGHBEAM_R,
    OBJECT_LOWBEAM_L,
    OBJECT_LOWBEAM_R,
    B_SLIDER_BODY_WEIGHT,
    B_BONE_SETUP_WHEEL_BASE_HANDLE_REST_POS,
    B_BONE_SETUP_TRACK_WIDTH_HANDLE_REST_POS,
    B_BONE_SETUP_WHEEL_RADIUS_HANDLE_REST_POS,
    LABELS_LOCATIONS,
)


def find_facing_dir(wheels):
    # Logic for finding the facing direction of the car - RL 0, RR 1, FR 2, FL 3
    rear_diff = mathutils.Vector((wheels.wheel_RL.location - wheels.wheel_RR.location))
    rear_center = (wheels.wheel_RL.location - (rear_diff * 0.5)) * mathutils.Vector(
        (1, 1, 0)
    )

    front_diff = mathutils.Vector((wheels.wheel_FL.location - wheels.wheel_FR.location))
    front_center = (wheels.wheel_FL.location - (front_diff * 0.5)) * mathutils.Vector(
        (1, 1, 0)
    )

    facing_vec = mathutils.Vector((front_center - rear_center))
    facing_dir = mathutils.Vector((facing_vec / facing_vec.length))

    return facing_dir


def all_lower(my_list):
    return [x.lower() for x in my_list]


def rotate_car(wheels, body):
    """
    Rotate car by aligning it with the ground.

    Parameters:
        wheels (list): List of wheel objects.
        body (bpy.types.Object): Body object of the car.

    Returns:
        tuple: A tuple containing the rotation degree of the car and the
        location of the rear axle point on the ground plane.
    """
    # Find rear axle point and relocate + rot
    loc_Raxle_floor, loc_Raxle, loc_Faxle = get_rear_axle(wheels)
    rotation_degree = get_2Drotation(loc_Raxle, loc_Faxle) - math.pi / 2

    # Create a rotation matrix around the Z-axis and apply it to all car parts
    # rot_matrix = mathutils.Matrix.Rotation(rotation_degree, 4, "Z")
    car_parts = wheels.to_list() + [body.body]
    for obj in car_parts:
        # obj.matrix_world @= rot_matrix
        obj.select_set(1)

    bpy.ops.transform.rotate(value=(rotation_degree), orient_axis="Z")

    for i in car_parts:
        i.select_set(0)

    return rotation_degree, loc_Raxle_floor


def save_locaction(wheels):
    loc_Raxle_floor, loc_Raxle, loc_Faxle = get_rear_axle(wheels)

    return loc_Raxle_floor


def save_rotation(wheels):
    loc_Raxle_floor, loc_Raxle, loc_Faxle = get_rear_axle(wheels)

    rotation_degree = get_2Drotation(loc_Raxle, loc_Faxle) - math.pi / 2

    return rotation_degree


def relocate_car(car_rig, armature, body, wheels):
    # Relocate body temporarily to W origin
    # find location AFTER rotation of car

    loc_Raxle_floor, _, _ = get_rear_axle(wheels)

    # do car transforms
    wheels.wheel_RL.location -= loc_Raxle_floor
    wheels.wheel_RR.location -= loc_Raxle_floor
    wheels.wheel_FR.location -= loc_Raxle_floor
    wheels.wheel_FL.location -= loc_Raxle_floor
    body.body.location -= loc_Raxle_floor

    try:
        for bone_coll in armature.collections:
            bone_coll.is_visible = True

    except:
        # Fallback for Blender 3.6
        armature.layers = [i in [16] for i in range(32)]

    rear_axle_loc = (
        wheels.wheel_RL.location - wheels.wheel_RR.location
    ) / 2 + wheels.wheel_RR.location
    # frontAxle_Loc = (wheels.wheel_FL.location - wheels.wheel_FR.location) / 2 + wheels.wheel_FR.location
    car_rig.location = rear_axle_loc
    car_rig.location[2] = 0

    # Switch off weight offset
    car_rig.pose.bones[B_SLIDER_BODY_WEIGHT].location[1] = 0

    wheel_base_handle_space = B_BONE_SETUP_WHEEL_BASE_HANDLE_REST_POS
    wheel_base_handle = car_rig.pose.bones["bone_setup_wheelBaseHandle"]
    wheel_base_handle.location[0] = (
        wheel_base_handle_space[1]
        - (wheels.wheel_FL.location[1] + wheels.wheel_FR.location[1]) / 2
    )

    rig_scale = 1 + (
        wheel_base_handle.location[0] / -wheel_base_handle_space[1]
    )  # From Drift Bone Driver

    track_width_handle_space = (
        B_BONE_SETUP_TRACK_WIDTH_HANDLE_REST_POS[0] * rig_scale,
        B_BONE_SETUP_TRACK_WIDTH_HANDLE_REST_POS[1] * rig_scale,
        B_BONE_SETUP_TRACK_WIDTH_HANDLE_REST_POS[2] * rig_scale,
    )

    track_width_handle = car_rig.pose.bones["bone_setup_trackWidthHandle"]
    track_width_handle.location[2] = (
        -track_width_handle_space[0] + wheels.wheel_RL.location[0]
    ) / rig_scale

    wheel_radius_handle_space = (
        B_BONE_SETUP_WHEEL_RADIUS_HANDLE_REST_POS[0] * rig_scale,
        B_BONE_SETUP_WHEEL_RADIUS_HANDLE_REST_POS[1] * rig_scale,
        B_BONE_SETUP_WHEEL_RADIUS_HANDLE_REST_POS[2] * rig_scale,
    )
    wheel_radius_handle_R = car_rig.pose.bones["bone_setup_wheelRadiusHandle_R"]
    wheel_radius_handle_R.location[0] = (
        -wheel_radius_handle_space[2] + wheels.wheel_RL.location[2]
    ) / rig_scale

    wheelRadiusHandle_F = car_rig.pose.bones["bone_setup_wheelRadiusHandle_F"]
    wheelRadiusHandle_F.location[0] = (
        -wheel_radius_handle_space[2] + wheels.wheel_FL.location[2]
    ) / rig_scale

    return rig_scale


def set_wheels_pivot(scene, wheels):

    for wheel in wheels.to_list():
        bpy.ops.object.select_all(action="DESELECT")

        wheel.select_set(True)

        bpy.ops.object.make_single_user(
            object=True,
            obdata=True,
            material=False,
            animation=False,
            obdata_animation=False,
        )
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        bpy.ops.object.origin_set(type="ORIGIN_CENTER_OF_MASS")

        wheel.select_set(False)

    facing_dir = find_facing_dir(wheels)

    mat_rot_R = mathutils.Matrix.Rotation(math.radians(90.0000), 4, "Z")
    mat_rot_L = mathutils.Matrix.Rotation(math.radians(-90.0000), 4, "Z")

    for wheel in wheels.to_list():
        bpy.ops.object.select_all(action="DESELECT")
        wheel.select_set(True)

        # Find tire side
        loc_left_labels = LABELS_LOCATIONS["Rear Left"] + LABELS_LOCATIONS["Front Left"]
        mat_rot = (
            mat_rot_L
            if any(x in wheel.name.lower() for x in all_lower(loc_left_labels))
            else mat_rot_R
        )

        # Set up Translation Matrix
        index = 0
        for val in wheel.dimensions:
            if val == min(wheel.dimensions):
                break
            index += 1

        delta_amount = (
            wheel.dimensions[index] / 1.8
        )  # Set the steering axis slightly behind the tire
        delta = facing_dir * delta_amount
        delta.rotate(mat_rot)

        scene.cursor.location = wheel.location + delta

        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")

        wheel.select_set(False)

    """for wheel in wheels.to_list():  FAILED EXPERIMENT TO AVOID 3D CURSOR
        # Find tire side
        loc_left_labels = LABELS_LOCATIONS["Rear Left"] + LABELS_LOCATIONS["Front Left"]  
        mat_rot = mat_rot_L if any(x in wheel.name.lower() for x in all_lower(loc_left_labels)) else mat_rot_R

        # Set up Translation Matrix
        index = 0
        for val in wheel.dimensions:
            if val == min(wheel.dimensions):
                break
            index += 1

        delta_amount = (wheel.dimensions[index] / 1.8)  # Set the steering axis slightly behind the tire
        delta = facing_dir*delta_amount
        delta.rotate(mat_rot)

        translation = mathutils.Matrix.Translation(delta)

        # Offset origin (full object)
        wheel.location += delta

        # We use the inverse of the translation to reverse it
        wheel.data.transform(translation.inverted())

        for child in wheel.children:
            child.location -= delta

        brakes[loc_id].location = mathutils.Vector((0,0,0))

        wheel.select_set(False)

        loc_id += 1"""

    return None


def relocate_lights(scene, headlights, wheels, rig_scale):

    facing_dir = find_facing_dir(wheels)
    print("facing_dir",facing_dir)

    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = bpy.context.preferences.addons[addon_root].preferences

    headlight_lamps = [
        scene.objects[OBJECT_LOWBEAM_L],
        scene.objects[OBJECT_LOWBEAM_R],
        scene.objects[OBJECT_HIGHBEAM_L],
        scene.objects[OBJECT_HIGHBEAM_R],
    ]

    if headlights:
        # If they have the same pivot, hide and ignore
        if (headlights.headlight_L.matrix_world.translation == headlights.headlight_R.matrix_world.translation):
            for light in headlight_lamps:
                light.hide_viewport = 1
                light.hide_render = 1

        else:
            headlight_lamps[0].matrix_world.translation = (headlights.headlight_L.matrix_world.translation)
            headlight_lamps[1].matrix_world.translation = (headlights.headlight_R.matrix_world.translation)
            headlight_lamps[2].matrix_world.translation = (headlights.headlight_L.matrix_world.translation)
            headlight_lamps[3].matrix_world.translation = (headlights.headlight_R.matrix_world.translation)


            # Offset lamps a little forward and up to avoid clipping
            for light in headlight_lamps:
                loc = mathutils.Matrix.Translation((0.0, 0.02 * rig_scale, (-0.10 * rig_scale)))
                light.matrix_world @= loc

            # Make sure headlights are facing forward
            for light in headlight_lamps:
                quat = facing_dir.to_track_quat('-Z', 'Y')
                quat = quat.to_matrix().to_4x4()
                light.matrix_world = light.matrix_world @ quat

            vals = [1, 1, 1, 1]
            for i, light in enumerate(headlight_lamps):
                light.hide_viewport = vals[i]
                light.hide_render = vals[i]

    if not headlights or addon_preferences.force_rig_headlights == "OP2":
        for light in headlight_lamps:
            light.hide_viewport = 1
            light.hide_render = 1

        # scene.lightbeam_State = 0
