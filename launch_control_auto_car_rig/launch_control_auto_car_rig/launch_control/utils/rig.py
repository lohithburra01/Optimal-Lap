import bpy
import math
import numpy as np

from ..globals import LABELS_OBJECTS, LABELS_LOCATIONS
from .validations import validated_wheel, validated_brake, validated_body, validated_wheelcover
from .functions import cad_align_to_ground
from .errors.exceptions import LCException

# Enums
from enum import Enum

class RigOptions(Enum):
    USE = 0
    FORCE = 1
    IGNORE = 2

class WheelLocation(Enum):
    RL = "Rear Left"
    RR = "Rear Right"
    FR = "Front Right"
    FL = "Front Left"

class LightsLocation(Enum):
    R = "Right"
    L = "Left"

# utils
def contains_any(s, substrs):
    return any(x.lower() in s.lower() for x in substrs)

def transform_str(s, substrs):
    for substring in substrs:
        s = s.replace(substring, "")
    return s

### ------------------------------------------------ FIND CAR PARTS ------------------------------------------------ ###
def find_car_parts(collection):
    scene = bpy.context.scene

    if scene.settings.cad_setup:
        try: 
            wheel_RL = scene.anim_rot_rl_assembly
            wheel_RR = scene.anim_rot_rr_assembly
            wheel_FR = scene.anim_rot_fr_assembly
            wheel_FL = scene.anim_rot_fl_assembly
            wheels = [wheel_RL, wheel_RR, wheel_FR, wheel_FL]

            body = scene.body_assembly

            brake_RL = scene.no_rot_rl_assembly
            brake_RR = scene.no_rot_rr_assembly
            brake_FR = scene.no_rot_fr_assembly
            brake_FL = scene.no_rot_fl_assembly

            brakes = [brake_RL, brake_RR, brake_FR, brake_FL]
            # not_found = [brake for brake in all_brakes if brake is None]

            if None in wheels:
                error_message = f"Could not find CAD assemblies for wheels. Please make sure the assembly empties are dropped into the corrosponding fields"
                raise LCException("Searching for wheel", error_message)

            if body == None:
                error_message = f"Could not find CAD assemblies for body. Please make sure the assembly empty is dropped into the corrosponding field"
                raise LCException("Searching for body", error_message)
            

            # If two different wheel sizes are used
            if not scene.settings.link_tire_settings:
                
                cad_align_to_ground(body, wheel_RL, wheel_RR, wheel_FL, wheel_FR, brake_RL, brake_RR, brake_FL, brake_FR)

            return wheels, body, brakes, None, None
            
        except LCException as e:
            raise LCException(e.method, e.message)

    else:
        try: 
            wheels = find_wheels(collection)
            # Find body
            body = find_body(collection)

            # Find brakes
            addon_root = ".".join(__package__.split(".")[:-2])
            addon_preferences = bpy.context.preferences.addons[addon_root].preferences
            prop = addon_preferences.force_rig_brakes
            option = RigOptions.USE if prop == "OP1" else (RigOptions.FORCE if prop == "OP2" else RigOptions.IGNORE)

            brakes = find_brakes(collection, option=option)

            # Find headlights
            option = RigOptions.USE if addon_preferences.force_rig_headlights == "OP1" else RigOptions.IGNORE
            headlights = find_headlights(collection, wheels[2], wheels[3], option=option)

            # Find wheelcovers
            prop = addon_preferences.force_rig_wheelcovers
            option = RigOptions.USE if prop == "OP1" else (RigOptions.FORCE if prop == "OP2" else RigOptions.IGNORE)
            wheelcovers = find_wheelcovers(collection, option=option)
            return wheels, body, brakes, headlights, wheelcovers
        
        except LCException as e:
            raise LCException(e.method, e.message)

# ---------------------------- WHEELS ---------------------------------
# def find_wheels(collection, option = RigOptions.FORCE):
def find_wheels(collection):
    """
    Finds wheel objects in the collection.

    Parameters:
        collection (bpy.types.collection): Blender collection.

    Returns:
        list[bpy.types.Object]: The found wheel objects.

    Raises:
        ValueError: If force=True and, the wheel object cannot be found or there are multiple possible matches.
    """

    try: 
        wheel_RL = _find_wheel(collection, WheelLocation.RL)
        wheel_RR = _find_wheel(collection, WheelLocation.RR)
        wheel_FR = _find_wheel(collection, WheelLocation.FR)
        wheel_FL = _find_wheel(collection, WheelLocation.FL)

        all_wheels = [wheel_RL, wheel_RR, wheel_FR, wheel_FL]
        # not_found = [wheel for wheel in all_wheels if wheel is None]

        # check if the wheels names are swaped and fix
        """def fix_wheel_locations(wheel_R, wheel_L):
            if wheel_R.location[0] > wheel_L.location[0]:
                aux = wheel_R.name
                wheel_R.name = wheel_L.name
                wheel_L.name = aux

        fix_wheel_locations(wheel_RR, wheel_RL)
        fix_wheel_locations(wheel_FR, wheel_FL)"""

        return all_wheels
    
    except LCException as e:
        raise LCException("Searching for wheels", e.message)

def _find_wheel(collection, location: WheelLocation):
    """Find wheel in the collection given the location"""

    # labels
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = bpy.context.preferences.addons[addon_root].preferences
    if addon_preferences.use_custom_tags:
        wheel_labels = [addon_preferences.custom_tire]
        brake_labels = [addon_preferences.custom_brake]
        wheelcover_labels = LABELS_OBJECTS["wheelcover"]

        custom_locations = {
            "Rear Left": [addon_preferences.custom_RL],
            "Rear Right": [addon_preferences.custom_RR],
            "Front Right":  [addon_preferences.custom_FR],
            "Front Left":  [addon_preferences.custom_FL],
            "Right": ["R", "right"],
            "Left": ["L", "left"]
        }
        
        loc_labels = custom_locations[location.value]

    else:
        wheel_labels = LABELS_OBJECTS["wheel"]
        brake_labels = LABELS_OBJECTS["brake"]
        wheelcover_labels = LABELS_OBJECTS["wheelcover"]
        loc_labels = LABELS_LOCATIONS[location.value]

    # filter by condition
    is_wheel = (
        lambda x: contains_any(x, wheel_labels)
        and contains_any(x, loc_labels)
        and not contains_any(x, brake_labels)
        and not contains_any(x, wheelcover_labels)
    )

    possible_wheel_objects = [ob for ob in collection.all_objects if is_wheel(ob.name)]

    name = f"{wheel_labels[0]}_{loc_labels[0]}"

    return validated_wheel(possible_wheel_objects, name, location.value)

# ---------------------------- BRAKES ---------------------------------
def find_brakes(collection, option = RigOptions.USE):
    """
    Finds brake objects in the collection.

    Parameters:
        collection (bpy.types.collection): Blender collection.

    Returns:
        list[bpy.types.Object]: The found brake objects.

    Raises:
        ValueError: If force=True and, the brake object cannot be found or there are multiple possible matches.
    """
    if option == RigOptions.IGNORE:
        return None

    try: 
        brake_RL = _find_brake(collection, WheelLocation.RL)
        brake_RR = _find_brake(collection, WheelLocation.RR)
        brake_FR = _find_brake(collection, WheelLocation.FR)
        brake_FL = _find_brake(collection, WheelLocation.FL)

        all_brakes = [brake_RL, brake_RR, brake_FR, brake_FL]
        # not_found = [brake for brake in all_brakes if brake is None]

        return all_brakes
    
    except LCException as e:
        if option == RigOptions.FORCE:
            raise LCException("Searching for brakes", "Not able to find all 4 Brake Callipers. " + e.message)

def _find_brake(collection, location: WheelLocation):
    """Find brake in the collection given the location."""

    # labels
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = bpy.context.preferences.addons[addon_root].preferences

    if addon_preferences.use_custom_tags:
        brake_labels = [addon_preferences.custom_brake]

        custom_locations = {
            "Rear Left": [addon_preferences.custom_RL],
            "Rear Right": [addon_preferences.custom_RR],
            "Front Right": [addon_preferences.custom_FR],
            "Front Left": [addon_preferences.custom_FL],
            "Right": ["R", "right"],
            "Left": ["L", "left"]
                }
        
        loc_labels = custom_locations[location.value]

    else:
        brake_labels = LABELS_OBJECTS["brake"]
        loc_labels = LABELS_LOCATIONS[location.value]


    # filter by condition
    is_brake = (
        lambda x: contains_any(x, brake_labels) 
        and contains_any(x, loc_labels)
    )

    possible_brake_objects = [ob for ob in collection.all_objects if is_brake(ob.name)]

    name = f"{brake_labels[0]}_{loc_labels[0]}"
    return validated_brake(possible_brake_objects, name, location.value)


# ---------------------------- WHEELCOVERS ---------------------------------
def find_wheelcovers(collection, option: RigOptions.USE):
    """
    Finds wheelcover objects in the collection.

    Parameters:
        collection (bpy.types.collection): Blender collection.

    Returns:
        list[bpy.types.Object]: The found wheelcover objects.

    Raises:
        ValueError: If force=True and, the wheelcover object cannot be found or there are multiple possible matches.
    """
    if option == RigOptions.IGNORE:
        return None

    try:
        wheelcover_FR = _find_wheelcover(collection, WheelLocation.FR)
        wheelcover_FL = _find_wheelcover(collection, WheelLocation.FL)

        all_wheelcovers = [wheelcover_FR, wheelcover_FL]
        #not_found = [wheelcover for wheelcover in all_wheelcovers if type(wheelcover) is dict]

        return all_wheelcovers

    except LCException as e:
        #rig_error_messages(1, not_found)
        if option == RigOptions.FORCE:
            raise LCException("Searching for wheelcovers", "Not able to find 2 wheelcovers. " + e.message)


def _find_wheelcover(collection, location: WheelLocation):
    """Find covers in the collection given the location."""

    # labels
    scene = bpy.context.scene
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = bpy.context.preferences.addons[addon_root].preferences

    if addon_preferences.use_custom_tags:
        wheelcover_labels = [addon_preferences.custom_covers]

        custom_locations = {
            "Front Right": [addon_preferences.custom_FR],
            "Front Left": [addon_preferences.custom_FL],
                }
        
        loc_labels = custom_locations[location.value]

    else:
        wheelcover_labels = LABELS_OBJECTS["wheelcover"]
        loc_labels = LABELS_LOCATIONS[location.value]


    # filter by condition
    is_wheelcover = (
        lambda x: contains_any(x, wheelcover_labels) 
        and contains_any(x, loc_labels)
    )

    possible_wheelcover_objects = [ob for ob in collection.all_objects if is_wheelcover(ob.name)]

    name = f"{wheelcover_labels[0]}_{loc_labels[0]}"
    return validated_wheelcover(possible_wheelcover_objects, name, location.value)


# ---------------------------- LIGHTS ---------------------------------
def find_headlights(collection, wheel_FR, wheel_FL, option = RigOptions.USE):
    """
    Finds all the headlights around the `reference_object`.

    Parameters:
        collection (bpy.types.collection): The current Blender collection.
        ref_wheels (bpy.types.Object): The objecta around which to search for lights.

    Returns:
        list[bpy.types.Object]: The closest objects that has a light material.

    Raises:
        ValueError: If force=True and, the light object cannot be found or there are multiple possible matches.
    """
    if option == RigOptions.IGNORE:
        return None

    try:
        light_R = _find_headlight(collection, wheel_FR, LightsLocation.R)
        light_L = _find_headlight(collection, wheel_FL, LightsLocation.L)

        all_lights = [light_R, light_L]
        # not_found = [light for light in all_lights if light is None]
        return all_lights
    except LCException as e:
        if option == RigOptions.FORCE:
            raise LCException("Searching for headlights", "Not able to find headlights. " + e.message)

def _find_headlight(collection, ref_wheel, location: LightsLocation):
    """Find light in the collection given the location"""
    headlight_labels = LABELS_OBJECTS["headlight"]

    # Get the list of materials that contain any of the keywords
    light_materials = [
        material
        for material in bpy.data.materials
        if contains_any(material.name, headlight_labels)
    ]

    # Get the list of objects that have a material slot that uses any of the light materials
    is_light = lambda x: any(
        slot.material in light_materials for slot in x.material_slots
    )
    possible_light_objects = [obj for obj in collection.all_objects if is_light(obj)]

    # Add any objects that have a name containing any of the keywords
    light_objects = [
        ob for ob in collection.all_objects if contains_any(ob.name, headlight_labels)
    ]
    possible_light_objects.extend(light_objects)

    # If no objects were found, return error payload
    if not possible_light_objects:
        raise LCException()

    # Calculate the distance between the reference object and each object in the list
    dist_list = [
        math.dist(ref_wheel.matrix_world.translation, obj.matrix_world.translation)
        for obj in possible_light_objects
    ]
    min_index = np.argmin(dist_list)

    return possible_light_objects[min_index]

# ----------------------------  BODY  ---------------------------------
def find_body(collection):
    """
    Finds the body of the car.

    Parameters:
        collection (bpy.types.collection): The current Blender collection.

    Returns:
        bpy.types.Object: The body.

    Raises:
        ValueError: If force=True and, the body object cannot be found or there are multiple possible matches.
    """
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = bpy.context.preferences.addons[addon_root].preferences
    if addon_preferences .use_custom_tags:
        body_labels = [addon_preferences.custom_body]
    else:
        body_labels = LABELS_OBJECTS["body"]
    
    # filter by condition
    is_body = lambda x: contains_any(x, body_labels)
    possible_body_objects = [ob for ob in collection.all_objects if is_body(ob.name)]

    try:
        body = validated_body(possible_body_objects)
        return body
    
    except LCException as e:
        raise LCException("Searching for body", e.message)

