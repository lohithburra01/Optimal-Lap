import bpy
import math

from mathutils import Vector



from ..logger import log_info, log_error
from ..ui.utils import show_message_box
from ..utils.errors.exceptions import LCException
from enum import Enum

class Options(str, Enum):
    USE = 0
    FORCE = 1
    IGNORE = 2

def validate_collection(collection):
    """Validates that collection is enabled"""

    layer_collections = bpy.context.view_layer.layer_collection.children
    
    for layer_coll in layer_collections:
        if layer_coll.name == collection.name:
            if layer_coll.exclude:
                raise LCException("Validate Collection", "Please activate (Checkbox) the Selected Vehicle Collection in the Outliner")
            
    return True

def validated_collection_content(collection):

    if len(collection.all_objects) < 5:
        raise LCException("Insufficient objects in collection", f"Please make sure the body and wheels of the vehicle you want to rig are inside the selected collection '{collection.name}'")
    
    return True


def validate_name_availability():
    """Validates if object names might be taken already, which would cause import to fail"""

    objs = bpy.context.scene.objects

    check_names = ['car_rig', 'driving_path', 'sim_Body', 'sim_Wheels', 'sim_TrackTo', 'ground_detect_remeshed', ]

    for name in check_names:
        if name in objs:
            try:
                objs[name].select_set(True)
            except:
                pass

            raise LCException("Name Collision Detected", f"Please rename or remove the existing object '{name}' in the scene to continue")

    objs = bpy.data.objects

    for name in check_names:
        if name in objs:
            raise LCException("Name Collision Detected", f"Please rename or remove the existing object '{name}' which is not located in the current scene, but is in the blend file data")
    
def validate_collection_name_availability():
    """Validates if collection names might be taken already, which would cause import to fail"""

    colls = bpy.data.collections

    for coll in colls:
        if "LaunchControl" in coll.name:
            raise LCException("Name Collision Detected", "Please remove any existing collections called 'LaunchControl' along with its content. The Collection might be located in another scene. You might need to 'Purge Unused Data' from 'File -> Clean Up'")

    return True

def validate_version():
    """Validates if the Blender version is too old"""
    if bpy.app.version < (4, 2, 0):
        raise LCException("Validate Blender Version", "This version of Launch Control is not compatible with any version of Blender older than 4.2.0. Please upgrade Blender or install an over version of Launch Control")

    return True

def validate_parent(body, wheels):
    """Validates if parent of any crucial car part is scaled"""

    bpy.ops.object.select_all(action="DESELECT")

    car_parts = wheels
    car_parts.append(body)

    child_parts = []
    child_parts_name = []
    
    for part in car_parts:
        if part.parent:
            child_parts.append(part)
            child_parts_name.append(part.name)


    if len(child_parts) > 0:
        if len(child_parts) == 1:
            msg = (f"The Tagged Part: '{child_parts[0].name}' has a parent object '{child_parts[0].parent.name}'. Please use 'Alt + P  ->  Clear and Keep Transform' on the Tagged Part to avoid issues")

        else:
            msg = (f"The selected Tagged Parts have Parent objects. Please use 'Alt + P  ->  Clear and Keep Transform' to avoid issues. (See console for more info)")
        
        for part in child_parts:
            part.select_set(True)

        log_error((f"Tagged parts have parents. Child Parts affected: '{child_parts_name}'"), "rigging")
        raise LCException("Validate Parent", msg)       
    
    else:
        return True
                
#raise 
    

def validate_car_dimension(wheels):
    """Validates the dimension of the car are between 1 and 10"""

    bpy.ops.object.select_all(action="DESELECT")

    dimension = (wheels[2].location - wheels[1].location).length

    # if dimension = 0 
    # error_message = "The distance between the origin points of the tires seems too be 0. Please select all the tire meshes and do 'Object -> Set Origin -> Origin to Geometry' and try again."

    error_type = int(dimension < 1) + 2 * int(dimension > 10)  # typeof dimension error
    # 0 if dimension is greater than or equal to 0.001 and less than or equal to 10.
    # 1 if dimension is less than 0.001.
    # 2 if dimension is greater than 10.

    if error_type: 
        if error_type == 1:
            if wheels[1].parent:
                wheels[1].parent.select_set(True)
                bpy.context.view_layer.objects.active = wheels[1].parent
                error_message = f"The vehicle seems to be too small to be rigged. Maybe this is caused by the scale of the parent objects of the wheels called '{wheels[1].parent.name}'. Please apply the scale of this object and try again."
            elif dimension < 0.001:
                for wheel in wheels:
                    wheel.select_set(True)
                error_message = f"It seems that the origin of all tires are at the same location. Please go to 'Object -> Set Origin -> Origin to Geometry' to recalculate the tire pivots"
            else:
                error_message = f"The vehicle is too small to be rigged. Please scale up your vehicle, so it is at least 1 'Blender Unit' long. Current length: '{round(dimension, 2)}' Blender Units"

        elif error_type == 2:
            if wheels[1].parent:
                wheels[1].parent.select_set(True)
                bpy.context.view_layer.objects.active = wheels[1].parent
                error_message = f"The vehicle seems to be too big to be rigged. Maybe this is caused by the scale of the parent objects of the wheels called '{wheels[1].parent.name}'. Please apply the scale of this object and try again."
            else:
                error_message = f"The vehicle is too big to be rigged. Please scale down your vehicle, so it is maximum 10 'Blender Unit' long. Current length: '{round(dimension, 2)}' Blender Units"

        raise LCException("Validating car dimention", error_message)
    else:
        return True

def validate_wheel_height(wheels):
    """Validates the axles have the wheels in the same height"""

    a = wheels[2].location[2]
    b = wheels[3].location[2]
    if not math.isclose(a, b, abs_tol=0.01):
        wheels[2].select_set(True)
        wheels[3].select_set(True)
        
        error_message = "The Front Wheels seem to be misaligned. Please make sure they are in the same height before rigging and that the origin of the objects are in the center of the wheels"
        raise LCException("Validating wheel height", error_message)

    a = wheels[0].location[2]
    b = wheels[1].location[2]
    if not math.isclose(a, b, abs_tol=0.01):
        wheels[0].select_set(True)
        wheels[1].select_set(True)

        error_message = "The Rear Wheels seem to be misaligned. Please make sure they are in the same height before rigging and that the origin of the objects are in the center of the wheels"
        raise LCException("Validating wheel height", error_message)
    return True

def validate_rotation_mode(body, wheels, brakes, wheelcovers):
    """Validates that all car parts have Euler rotations so rotations will be store correctly"""

    bpy.ops.object.select_all(action="DESELECT")

    car_parts = wheels
    car_parts.append(body)

    if brakes and None not in brakes:
        for brake in brakes:
            car_parts.append(brake)
    
    if wheelcovers and None not in wheelcovers:
        for wheelcover in wheelcovers:
            car_parts.append(wheelcover)

    failed_car_parts = []

    for part in car_parts:
        if part.rotation_mode == 'QUATERNION' or part.rotation_mode == 'AXIS_ANGLE':
            failed_car_parts.append(part)


    if len(failed_car_parts) > 0:
        for obj in failed_car_parts:
            obj.select_set(True)

        failed_car_parts_name = []
        for failed_part in failed_car_parts:
            failed_car_parts_name.append(failed_part.name)

        error_message = f"The objects: {failed_car_parts_name} have an unsupported Rotation Mode. Please set the rotation mode of these objects to 'XYZ Euler' before rigging"
        raise LCException("Validating Rotation Mode", error_message)
    return True

def validate_viewport_context():
    """Validates if the viewport tools are set correctly. Incorrect settings with make 'high level code' fail"""
    
    scene = bpy.context.scene

    if scene.tool_settings.use_transform_pivot_point_align:
        scene.tool_settings.use_transform_pivot_point_align = False

    if scene.tool_settings.transform_pivot_point != "MEDIAN_POINT":
        scene.tool_settings.transform_pivot_point = "MEDIAN_POINT"

    if scene.tool_settings.use_keyframe_insert_auto:
        scene.tool_settings.use_keyframe_insert_auto = False

    return True

def validate_animation(body, wheels, brakes, wheelcovers):
    """Removes any animation there might be on the wheels, brakes, wheelcovers or body has any animation on it"""

    animated_parts = []

    def check_part(part):
        if hasattr(part, "animation_data"):
            if hasattr(part.animation_data, "action"):
                if hasattr(part.animation_data.action, "fcurves"):
                    if hasattr(part.animation_data.action.fcurves[0], "keyframe_points"):
                        if len(part.animation_data.action.fcurves[0].keyframe_points) > 0:

                            part.animation_data_clear()
                            animated_parts.append(part.name)

    #body_children = body.children_recursive
    #for part in body_children:
    check_part(body)
    
    for wheel in wheels:
        check_part(wheel)
        #wheel_children = wheel.children_recursive
        #for part in wheel_children:
    
    if brakes != None:
        for brake in brakes:
            if brake != None:
                check_part(brake)
                #brake_children = brake.children_recursive
                #for part in brake_children:
    
    if wheelcovers != None:
        for wheelcover in wheelcovers:
            if wheelcover != None:
                check_part(wheelcover)
                #wheelcover_children = wheelcover.children_recursive
                #for part in wheelcover_children:
    
    if len(animated_parts) > 0:
        log_info(f"Removed animation for: {animated_parts}", "OBJECT_OT_rig_car")
        error_message = f"Some tagged parts were animated. Animations were removed. Please rig again. (See list of removed animations in console)"
        raise LCException("Pre Existing Animations", error_message)

    return True


def validate_non_applied_scales(body, wheels, brakes):
    """Validates that no assemblies for CAD setup has a non (1,1,1) scale. It is common for CAD data to have (0.001, 0.001, 0.001)"""
    
    bpy.ops.object.select_all(action="DESELECT")

    needs_rescale = False

    body_children = body.children_recursive
    for part in body_children:
        if part.type == 'EMPTY':
            if part.scale != Vector((1,1,1)):
                part.select_set(True)
                needs_rescale = True
    
    for wheel in wheels:
        wheel_children = wheel.children_recursive
        for part in wheel_children:
            if part.type == 'EMPTY':
                if part.scale != Vector((1,1,1)):
                    part.select_set(True)
                    part = True

    for brake in brakes:
        if brake != None:
            brake_children = brake.children_recursive
            for part in brake_children:
                if part.type == 'EMPTY':
                    if part.scale != Vector((1,1,1)):
                        part.select_set(True)
                        part = True


    if needs_rescale:
        error_message = f"Non-applied scales found. Please apply the scale of the selected assemblies before rigging using: 'Object -> Apply -> Scale'"
        raise LCException("Validating Assembly Scales", error_message)
    
    return True

def validate_library_overrides():
    """Validates that if library overwrites are preset, the user has the "Scene Collection" selected"""
    scene = bpy.context.scene

    if bpy.context.collection != scene.collection:
        for collection in scene.collection.children_recursive:
            if collection.override_library != None:

                error_message = f"Library Override detected. Please select the 'Scene Collection' in the outliner before rigging to make sure all collections get imported correctly"
                raise LCException("Validating Library Overrides", error_message)
    return True
            

def validated_wheel(possible_wheel, name, location):
    """Returns the wheel object if validated, or or raises error"""
    
    location_short = ''.join(ch for ch in location if not ch.islower()).replace(" ", "")
    car_collection = bpy.context.scene.car_collection

    if len(possible_wheel) < 1:
        error_message = f"Please rename the {location} Tire Mesh to: 'wheel.{location_short}' and place it inside the collection '{car_collection.name}'"
        raise LCException("Could not find '{location} Wheel'", error_message)

    elif len(possible_wheel) > 1:
        names = [obj.name for obj in possible_wheel]
        log_info(
            f"Too many {location} wheels detected. - Will try to find the top object to rig - Could be wrong...",
            "find_wheel",
            data={"all_objects": names},
        )

        def get_parent_depth(obj):
            return 0 if obj.parent is None else get_parent_depth(obj.parent) + 1

        parent_depths = [get_parent_depth(obj) for obj in possible_wheel]

        min_depth = min(parent_depths)

        min_index = 0
        for item in parent_depths:
            if item == min_depth:
                break
            min_index = min_index + 1

        # should fail if
        min_depth_amount = parent_depths.count(min_depth)

        if min_depth_amount > 1:
            for name in names:
                bpy.context.scene.objects[name].select_set(True)

            error_message = f"Found multiple objects that could be the {location} Wheel. Please make sure only 1 of these objects is named 'wheel_{location_short}' or similar: {names}"
            raise LCException("Searching for wheel", error_message)

        wheel = possible_wheel[min_index]

    # then there is only one object, and just need to confirm it is a mesh
    elif len(possible_wheel) == 1:
        wheel = possible_wheel[0]
    
    if wheel.type != "MESH":
        wheel.select_set(True)
        error_message = f"'{wheel.name}' is not a 'MESH', but an '{wheel.type}'. Please make sure you have tagged the 4 'Tire Meshes' of your Vehicle as the wheels."
        raise LCException("Searching for wheel", error_message)

    # Check for any delta transforms
    check_delta_list = []
    for deltaVal in wheel.delta_location:
        if deltaVal != 0:
            check_delta_list.append(True)
        else:
            check_delta_list.append(False)

    for deltaVal in wheel.delta_rotation_euler:
        if deltaVal != 0:
            check_delta_list.append(True)
        else:
            check_delta_list.append(False)

    for deltaVal in wheel.delta_scale:
        if deltaVal != 1:
            check_delta_list.append(True)
        else:
            check_delta_list.append(False)

    if any(check_delta_list):
        wheel.select_set(True)

        for index, delta in enumerate(wheel.delta_location):
            wheel.location[index] += delta
            wheel.delta_location[index] = 0

        for index, delta in enumerate(wheel.delta_rotation_euler):
            wheel.rotation_euler[index] += delta
            wheel.delta_rotation_euler[index] = 0

        for index, delta in enumerate(wheel.delta_scale):
            wheel.scale[index] = wheel.scale[index] * delta
            wheel.delta_scale[index] = 1
            

        error_message = f"Found Delta transforms on '{wheel.name}'. These have now been cleared. Please check if all looks correct and Rig Vehicle again."
        raise LCException("Searching for wheel", error_message)

    return wheel

def validated_brake(possible_brake, name, location):
    """Returns the brake object if validated, or and error dictionary to be handled later"""

    location_short = ''.join(ch for ch in location if not ch.islower())
    location_short = location_short.replace(" ", "")
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = bpy.context.preferences.addons[addon_root].preferences
    option = addon_preferences.force_rig_brakes

    if len(possible_brake) < 1:
        if option == 'OP1':
            show_message_box(f"Could not find '{location} Brake Caliper'. Will skip brakes.", "Brake Object Detecion")
            return None
        else:
            error_message = f"Please rename the {location} Brake Caliper to: 'brake.{location_short}' or change the 'Rig Brakes' setting in the add-on preferences to 'If Possible'."
            raise LCException("Could not find '{location} Brake Caliper'", error_message)
            
    elif len(possible_brake) > 1:
        names = [obj.name for obj in possible_brake]
        log_info(
            f"Too many {location} brakes detected. - Will try to find the top object to rig - Could be wrong...",
            "find_brake",
            data={"all_objects": names},
        )

        def get_parent_depth(obj):
            return 0 if obj.parent is None else get_parent_depth(obj.parent) + 1

        parent_depths = [get_parent_depth(obj) for obj in possible_brake]

        min_depth = min(parent_depths)

        min_index = 0
        for item in parent_depths:
            if item == min_depth:
                break
            min_index = min_index + 1

        # should fail if
        min_depth_amount = parent_depths.count(min_depth)

        if min_depth_amount > 1:
            if option == 'OP1':
                show_message_box(f"Found multiple objects that could be the {location} Brake Caliper. Will skip brakes.", "Brake Object Detecion")
                return None
            else:
                for name in names:
                    bpy.context.scene.objects[name].select_set(True)

                error_message = f"Found multiple objects that could be the {location} Brake Caliper. Please make sure only 1 of these objects is named 'brake_{location_short}' or similar: {names}"
                raise LCException("Searching for brake", error_message)

        brake = possible_brake[min_index]

    # then there is only one object - it may be a mesh or an empty
    brake = possible_brake[0]

    return brake

def validated_wheelcover(possible_wheelcover, name, location):
    """Returns the wheelcover object if validated, or and error dictionary to be handled later"""

    location_short = ''.join(ch for ch in location if not ch.islower())
    location_short = location_short.replace(" ", "")
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = bpy.context.preferences.addons[addon_root].preferences
    option = addon_preferences.force_rig_wheelcovers

    if len(possible_wheelcover) < 1:
        if option == 'OP1':
            return None
        else:
            error_message = f"Could not find '{location} Wheelcover'. Please rename the {location} Wheelcover to: 'wheelcover.{location_short}'"
            raise LCException("Searching for wheelcovers", error_message)

    if len(possible_wheelcover) > 1:
        if option == 'OP1':
            return None
        else:
            names = [obj.name for obj in possible_wheelcover]

            for name in names:
                bpy.context.scene.objects[name].select_set(True)

            error_message = f"Found multiple objects that could be the '{location} Wheelcover'. Please make sure only 1 of these objects is named 'wheelcover_{location_short}' or similar: {names}"
            raise LCException("Searching for wheelcovers", error_message)
    
    # then there is only one object, and just need to confirm it is a mesh
    wheelcover = possible_wheelcover[0]

    return wheelcover

def validated_body(possible_body):
    """Returns the body object if validated, or raises error """
    car_collection = bpy.context.scene.car_collection

    if len(possible_body) < 1:
        error_message = f"Please rename the main car body part to 'Body' and place it inside the collection '{car_collection.name}'."
        raise LCException("Could not find Car Body", error_message)
    

    if len(possible_body) > 1:
        # get the deph of the objects to find the most general one
        def get_parent_depth(obj):
            return 0 if obj.parent is None else get_parent_depth(obj.parent) + 1

        parent_depths = [get_parent_depth(obj) for obj in possible_body]

        min_depth = min(parent_depths)

        min_index = 0
        for item in parent_depths:
            if item == min_depth:
                break
            min_index = min_index + 1

        # should fail if
        min_depth_amount = parent_depths.count(min_depth)

        if min_depth_amount > 1:
            obj_names = [obj.name for obj in possible_body]

            context = bpy.context
            for name in obj_names:
                context.scene.objects[name].select_set(True)

            error_message = "Found multiple objects that could be the 'Main Car Body'. Please make sure only 1 of these objects is named 'Body'."
            raise LCException("Searching for body", error_message)
        
        return possible_body[min_index]

    return possible_body[0]


def validate_wheel_naming(wheels, active_car):
    scene = bpy.context.scene

    # check if the wheels names are swaped and warn + select + cancel (Doing it auto messes up)
    """def fix_wheel_locations(wheel_R, wheel_L):
        if wheel_R.location[0] > wheel_L.location[0]:
            log_error("Name labels seem flipped.", "Rig execution")
            aux = wheel_R.name
            wheel_R.name = wheel_L.name
            wheel_L.name = aux

    fix_wheel_locations(wheels.wheel_RR, wheels.wheel_RL)
    fix_wheel_locations(wheels.wheel_FR, wheels.wheel_FL)"""

    wheels_flipped = False

    if wheels.wheel_RR.location[0] > wheels.wheel_RL.location[0]:
        wheels_flipped = True
        wheels.wheel_RR.select_set(True)
        wheels.wheel_RL.select_set(True)
    
    if wheels.wheel_FR.location[0] > wheels.wheel_FL.location[0]:
        wheels_flipped = True
        wheels.wheel_FR.select_set(True)
        wheels.wheel_FL.select_set(True)

    if wheels_flipped:
        log_error("Name labels seem flipped.", "Rig execution")
        scene.lc.remove(active_car)
        error_message = "Naming of selected wheels seems to be wrong. Please look from the Rear of the vehicle and check naming again."
        raise LCException("Validating wheel naming", error_message)


def validate_existing_objects():
    scene = bpy.context.scene
    if scene.objects.get("driving_path"):
        log_info("Found 'driving_path' object in file already. Renamed to 'driving_path.old'.", "Rig execution")
        scene.objects["driving_path"].name = "driving_path.old"


def validate_lc_object(object):

    try:
        object.select_set(True)
        object.select_set(False)

    except:
        message = f"Could not locate '{object.name}' for the active vehicle. Please make sure it's not hidden, disabled or deleted"
        log_error(message, "Missing LC Object")
        show_message_box(message, "Missing LC Object", "ERROR")
        return False
    
    return True