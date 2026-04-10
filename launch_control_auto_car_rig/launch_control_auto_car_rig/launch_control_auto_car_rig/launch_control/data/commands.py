import bpy
import math
import mathutils
import os
import shutil

from .. import data

from ..ui.utils import show_message_box
from ..utils.errors.exceptions import RigCollectionNotFound
from ..logger import log_error, log_info
from ..utils.functions import get_active_curve_length, setup_driver, find_driver_index, get_addon_path
from ..utils.validations import validate_lc_object

from ..globals import *

# PHYSICS
def update_physics_presets(self, context):
    scene = context.scene

    car = scene.lc.find_selected()
    preset = car.properties.physics_presets

    try: 
        car.get_rig_collection()

        values = PHYSICS.get(preset, PHYSICS_DEFAULT_VALUES)
        (
            car.properties.physics_tightness,
            car.properties.physics_dampening,
            car.properties.physics_softness,
            #car.properties.physics_multiplier,
            #car.properties.use_gravity,
            car.properties.mass,
            car.properties.spring_offset,
        ) = values

    except RigCollectionNotFound as e: 
        e.show_error_message(title="Updating Physics Presets")


# not used anymore as this is handled by drivers!
def update_postFX(self, context):
    scene = context.scene

    car = scene.lc.find_selected()
    rig_object = car.rig_object
    bones = rig_object.pose.bones

    # values
    overdrive_impact = car.properties.overdrive_wheel_impact / 100
    overdrive_pitch = car.properties.overdrive_pitch / (100*5)
    overdrive_yaw = car.properties.overdrive_yaw / (100*5)
    overdrive_roll = car.properties.overdrive_roll / (100*2.5)
    overdrive_location = car.properties.overdrive_location / 100
    overdrive_wheel = car.properties.overdrive_wheel_location / 100

    bones[B_BODY_WHEEL_IMPACT].constraints["PITCH"].influence = overdrive_impact
    bones[B_BODY_WHEEL_IMPACT].constraints["YAW"].influence = overdrive_impact
    bones[B_BODY_WHEEL_IMPACT].constraints["ROLL"].influence = overdrive_impact

    bones[B_BODY_SIM_WIGGLE].constraints["PITCH"].influence = overdrive_pitch
    bones[B_BODY_SIM_WIGGLE].constraints["YAW"].influence = overdrive_yaw
    bones[B_BODY_SIM_WIGGLE].constraints["ROLL"].influence = overdrive_roll

    bones[B_BODY_SIM_MASS].constraints["Copy Location"].influence = overdrive_location

    bones[B_WHEEL_SIM_FR].constraints["Sim"].influence = overdrive_wheel
    bones[B_WHEEL_SIM_FL].constraints["Sim"].influence = overdrive_wheel
    bones[B_WHEEL_SIM_RR].constraints["Sim"].influence = overdrive_wheel
    bones[B_WHEEL_SIM_RL].constraints["Sim"].influence = overdrive_wheel


def reveal_acc_viz(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()
    ui_show_acc_viz = active_car.settings.show_acc_viz
    ui_show_acc_viz_override = active_car.settings.show_acc_viz_override

    multi_edit = scene.settings.edit_all_mode
    cars = []
    
    if multi_edit: cars = scene.lc.cars
    else: cars.append(active_car)

    for active_car in cars:
        rig_object = active_car.rig_object

        simulation_state = rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1]

        if ui_show_acc_viz and ui_show_acc_viz_override:
            if simulation_state > 0.5:
                active_car.sim_acc_viz.hide_viewport = False
            else:
                active_car.sim_acc_viz.hide_viewport = True
                show_message_box("Please 'Enable Physics' before visualizing the acceleration", "Acceleration Visualizer", "INFO")
                
        else:
            active_car.sim_acc_viz.hide_viewport = True
        

def reveal_vel_viz(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()
    ui_show_vel_viz = active_car.settings.show_vel_viz

    multi_edit = scene.settings.edit_all_mode
    cars = []
    
    if multi_edit: cars = scene.lc.cars
    else: cars.append(active_car)

    for active_car in cars:
        rig_object = active_car.rig_object

        simulation_state = rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1]
        
        if ui_show_vel_viz:
            if simulation_state > 0.5:
                active_car.sim_vel_viz.hide_viewport = False
            else:
                active_car.sim_vel_viz.hide_viewport = True
                show_message_box("Please 'Enable Physics' before visualizing the velocity", "Velocity Visualizer", "INFO")
                
        else:
            active_car.sim_vel_viz.hide_viewport = True
        
     
# HEADLIGHTS
def update_headlights_presets(self, context):
    scene = context.scene

    active_car = scene.lc.find_selected()

    # Check for car rig in scene
    try: 
        active_car.get_rig_collection()

        ui_preset = active_car.properties.headlights_presets

        cars = []
        if scene.settings.edit_all_mode: 
            cars = scene.lc.cars
        else: 
            cars.append(active_car)

        for active_car in cars:
            preset = ui_preset
            collection_name = active_car.collection.name
            images = bpy.data.images
            low_beam_L = bpy.data.lights[FILENAME_L_LOWBEAM_L +'_' + collection_name]
            light_group = low_beam_L.node_tree.nodes["Group"].node_tree

            preset_image = images[preset]
            preset_image_blur01 = images[(str(preset) + "_Blur01")]
            preset_image_blur02 = images[(str(preset) + "_Blur02")]

            light_group.nodes["Image"].image = preset_image
            light_group.nodes["Image_Blur01"].image = preset_image_blur01
            light_group.nodes["Image_Blur02"].image = preset_image_blur02

            temperature = HEADLIGHTS.get(preset, None)

            if temperature:
                active_car.properties.low_beam_temperature = temperature
                active_car.properties.high_beam_temperature = temperature

    except RigCollectionNotFound as e: 
        e.show_error_message()

    except:
        log_error("something went wrong", "update_headlights_presets")


def update_headlight(self, context):
    scene = context.scene

    active_car = scene.lc.find_selected()
    settings = active_car.settings
    props = active_car.properties
    ui_link_beams = settings.link_beams
    ui_low_beam_spread = props.low_beam_spread
    ui_low_beam_intensity = props.low_beam_intensity
    ui_low_beam_temperature = props.low_beam_temperature
    ui_low_beam_sharpness = props.low_beam_sharpness
    ui_high_beam_spread = props.high_beam_spread
    ui_high_beam_intensity = props.high_beam_intensity
    ui_high_beam_temperature = props.high_beam_temperature
    ui_high_beam_sharpnesss = props.high_beam_sharpness

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        collection_name = active_car.collection.name
        settings = active_car.settings

        try: 
            active_car.get_rig_collection()

            low_beam_L = bpy.data.lights[FILENAME_L_LOWBEAM_L +'_' + collection_name]
            high_beam_L = bpy.data.lights[FILENAME_L_HIGHBEAM_L + '_' +collection_name]
            low_beam_R = bpy.data.lights[FILENAME_L_LOWBEAM_R +'_' + collection_name]
            high_beam_R = bpy.data.lights[FILENAME_L_HIGHBEAM_R + '_' +collection_name]

            # low_beam
            low1, low2 = 1.75, 45 * (math.pi / 180)
            high1, high2 = 0.5, 115 * (math.pi / 180)
            input_spread = ui_low_beam_spread
            output_spread = input_spread
            
            low_beam_L.energy = ui_low_beam_intensity / 341.4967 * 1000
            low_beam_R.energy = ui_low_beam_intensity / 341.4967 * 1000
            low_beam_L.node_tree.nodes["Group"].inputs[0].default_value = (ui_low_beam_temperature * 1000)
            low_beam_R.node_tree.nodes["Group"].inputs[0].default_value = (ui_low_beam_temperature * 1000)
            low_beam_L.node_tree.nodes["Group"].inputs[1].default_value = ui_low_beam_sharpness
            low_beam_R.node_tree.nodes["Group"].inputs[1].default_value = ui_low_beam_sharpness
            low_beam_L.spot_size = output_spread
            low_beam_R.spot_size = output_spread

            if ui_link_beams:
                high_beam_L.energy = ui_low_beam_intensity / 341.4967 * 1000 * 3
                high_beam_R.energy = ui_low_beam_intensity / 341.4967 * 1000 * 3
                high_beam_L.node_tree.nodes["Group"].inputs[0].default_value = (ui_low_beam_temperature * 1000)
                high_beam_R.node_tree.nodes["Group"].inputs[0].default_value = (ui_low_beam_temperature * 1000)
                high_beam_L.node_tree.nodes["Group"].inputs[1].default_value = (ui_low_beam_sharpness * 0.75)
                high_beam_R.node_tree.nodes["Group"].inputs[1].default_value = (ui_low_beam_sharpness * 0.75)
                high_beam_L.spot_size = output_spread
                high_beam_R.spot_size = output_spread

            else:
                # Remap spread:
                low1, low2 = 1.75, 45 * (math.pi / 180)
                high1, high2 = 0.5, 115 * (math.pi / 180)
                input_spread = ui_high_beam_spread
                output_spread = input_spread

                high_beam_L.energy = ui_high_beam_intensity / 341.4967 * 1000
                high_beam_R.energy = ui_high_beam_intensity / 341.4967 * 1000
                high_beam_L.node_tree.nodes["Group"].inputs[0].default_value = (ui_high_beam_temperature * 1000)
                high_beam_R.node_tree.nodes["Group"].inputs[0].default_value = (ui_high_beam_temperature * 1000)
                high_beam_L.node_tree.nodes["Group"].inputs[1].default_value = ui_high_beam_sharpnesss
                high_beam_R.node_tree.nodes["Group"].inputs[1].default_value = ui_high_beam_sharpnesss
                high_beam_L.spot_size = output_spread
                high_beam_R.spot_size = output_spread

        except RigCollectionNotFound as e: 
            e.show_error_message(title="Updating headlight")

        except: 
            log_error("something went wrong", "update_headlight")


def update_beam_connected(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()
    ui_low_beam_temperature = active_car.properties.low_beam_temperature
    ui_low_beam_intensity = active_car.properties.low_beam_intensity
    ui_low_beam_spread = active_car.properties.low_beam_spread
    ui_low_beam_sharpness = active_car.properties.low_beam_sharpness

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        props = active_car.properties

        props.high_beam_temperature = ui_low_beam_temperature
        props.high_beam_intensity = ui_low_beam_intensity
        props.high_beam_spread = ui_low_beam_spread
        props.high_beam_sharpness = ui_low_beam_sharpness


def update_beam(self, context):
    scene = context.scene
    
    active_car = scene.lc.find_selected()
    ui_low_beam_visibility = active_car.settings.low_beam_visibility
    ui_high_beam_visibility = active_car.settings.high_beam_visibility

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        collection_name = active_car.collection.name
        setting = active_car.settings

        high_beam_left = bpy.context.scene.objects[OBJECT_HIGHBEAM_L + '_' + collection_name]
        high_beam_right = bpy.context.scene.objects[OBJECT_HIGHBEAM_R + '_' + collection_name]
        low_beam_left = bpy.context.scene.objects[OBJECT_LOWBEAM_L + '_' + collection_name]
        low_beam_right = bpy.context.scene.objects[OBJECT_LOWBEAM_R + '_' + collection_name]

        if ui_high_beam_visibility:
            high_beam_left.hide_viewport = 0
            high_beam_right.hide_viewport = 0
            high_beam_left.hide_render = 0
            high_beam_right.hide_render = 0
        else:
            high_beam_left.hide_viewport = 1
            high_beam_right.hide_viewport = 1
            high_beam_left.hide_render = 1
            high_beam_right.hide_render = 1

        if ui_low_beam_visibility:
            low_beam_left.hide_viewport = 0
            low_beam_right.hide_viewport = 0
            low_beam_left.hide_render = 0
            low_beam_right.hide_render = 0
        else:
            low_beam_left.hide_viewport = 1
            low_beam_right.hide_viewport = 1
            low_beam_left.hide_render = 1
            low_beam_right.hide_render = 1

        if not (ui_high_beam_visibility or ui_low_beam_visibility):
            low_beam_left.hide_viewport = 1
            low_beam_right.hide_viewport = 1
            low_beam_left.hide_render = 1
            low_beam_right.hide_render = 1
            high_beam_left.hide_viewport = 1
            high_beam_right.hide_viewport = 1
            high_beam_left.hide_render = 1
            high_beam_right.hide_render = 1


# ANIMATIONS
def update_ui_view_elements(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()
    #ui_show_extra_animation_controls = active_car.settings.show_extra_animation_controls
    ui_ui_view_elements = active_car.settings.ui_view_elements

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        rig_object = active_car.rig_object
        bones = rig_object.pose.bones
        try: 
            active_car.get_rig_collection()

            if ui_ui_view_elements == 'OP1':
               bones[B_SLIDER_INTERNAL_MUTE].scale[1] = 0
               bones[B_SLIDER_INTERNAL_MUTE].scale[0] = 0

            elif ui_ui_view_elements == 'OP2':
               bones[B_SLIDER_INTERNAL_MUTE].scale[1] = 0
               bones[B_SLIDER_INTERNAL_MUTE].scale[0] = 1

            elif ui_ui_view_elements == 'OP3':
               bones[B_SLIDER_INTERNAL_MUTE].scale[1] = 1
               bones[B_SLIDER_INTERNAL_MUTE].scale[0] = 1

        except RigCollectionNotFound as e: 
            e.show_error_message(title="Revealing Extra Animation Controls...")
        

def reveal_camera_hooks(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()
    ui_show_camera_hooks = active_car.settings.show_camera_hooks

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        rig_armature = active_car.rig_armature

        try: 
            active_car.get_rig_collection()
            try:
                rig_armature.collections["Camera Hooks"].is_visible = ui_show_camera_hooks
            except:
                #Fallback for LC 1.5
                rig_armature.collections["Layer 19"].is_visible = ui_show_camera_hooks

        except RigCollectionNotFound as e: 
            e.show_error_message(title="Revealing Extra Animation Controls...")
        

def update_path_snap(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()
    ui_snap_path = active_car.settings.snap_path

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        active_car.driving_path.modifiers["Shrinkwrap"].show_viewport = ui_snap_path
        active_car.driving_path.modifiers["Shrinkwrap"].show_render = ui_snap_path
        active_car.driving_path.modifiers["Shrinkwrap"].use_apply_on_spline = ui_snap_path


def reveal_speedometer(self, context):
    scene = context.scene

    active_car = scene.lc.find_selected()
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = context.preferences.addons[addon_root].preferences

    ui_speedometer = active_car.settings.speedometer

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        settings = active_car.settings
        collection_name = active_car.collection.name
        if active_car.properties.has_lib_override:
            collection_name = collection_name.replace(" Linked","")
        speedometer = scene.objects[FILENAME_SPEEDOMETER + ("_" + collection_name)]
        unit = scene.objects[FILENAME_UNIT + ("_" + collection_name)]
        unit_flipped = scene.objects[FILENAME_UNIT_FLIPPED + ("_" + collection_name)]
        speed_calculator = active_car.speed_calculator
        
        speedometer_meshes = [speedometer, unit, unit_flipped]

        if ui_speedometer:
            speed_calculator.modifiers["speed_calculator"].show_viewport = True
            speed_calculator.modifiers["speed_calculator"].show_render = True

            for mesh in speedometer_meshes:
                mesh.hide_viewport = False
        
        else:
            speed_calculator.modifiers["speed_calculator"].show_viewport = False
            speed_calculator.modifiers["speed_calculator"].show_render = False

            for mesh in speedometer_meshes:
                mesh.hide_viewport = True
        
        # copied from "reveal_imperial"
        unit_obj = scene.objects[FILENAME_UNIT + ("_" + collection_name)]

        unit_to_use = "mph" if addon_preferences.use_imperial else "km/h"
        unit_obj.data.body = unit_to_use

        scene.settings.use_imperial_copy = addon_preferences.use_imperial
        

def reveal_imperial(self, context):
    scene = context.scene
    car = scene.lc.find_selected()
    collection_name = car.collection.name
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = context.preferences.addons[addon_root].preferences

    unit_obj = scene.objects[FILENAME_UNIT + ("_" + collection_name)]

    unit_to_use = "mph" if addon_preferences.use_imperial else "km/h"
    unit_obj.data.body = unit_to_use

    scene.settings.use_imperial_copy = addon_preferences.use_imperial


def lock_sliders(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()
    ui_limit_sliders = active_car.settings.limit_sliders

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        key_words = ["Slider", "Switch"]
        for bone in active_car.rig_object.pose.bones:
            if any(word in bone.name for word in key_words):
                for constraint in bone.constraints:
                    if constraint.name in ["Limit Location", "Limit Location.001"]:
                        constraint.enabled = ui_limit_sliders


def update_shaking_frequency(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()
    ui_shake_frequency = active_car.properties.shake_frequency

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        bones = active_car.rig_object.pose.bones

        wheel_bones = [
            bones[B_WHEEL_SHAKE_RR],
            bones[B_WHEEL_SHAKE_RL],
            bones[B_WHEEL_SHAKE_FL],
            bones[B_WHEEL_SHAKE_FR],
        ]

        action_groups =  active_car.rig_object.animation_data.action.groups

        for bone in wheel_bones:
            group = action_groups.get(bone.name)
            for channel in group.channels:
                if channel.modifiers[0].type == "FNGENERATOR":
                    channel.modifiers[0].phase_multiplier = ui_shake_frequency


# PATH
def toggle_ground_grid(self, context):
    scene = context.scene

    active_car = scene.lc.find_selected()
    ui_show_ground_grid = active_car.settings.show_ground_grid

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        try: 
            active_car.get_rig_collection()
            grid_visualizer = active_car.ground_local_object
            grid_visualizer.hide_viewport = not ui_show_ground_grid

        except RigCollectionNotFound as e: 
            e.show_error_message()

        except:
            log_error("something went wrong", "update_headlights_presets")
        

def update_ground(self, context):
    scene = context.scene

    active_car = scene.lc.find_selected()
    ui_grid_resolution = active_car.settings.grid_resolution

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        try:
            grid_visualizer = active_car.ground_local_object
            modifier = grid_visualizer.modifiers[
                "Ground Detect RESOLUTION"
            ]
            modifier.levels = ui_grid_resolution
            modifier.render_levels = ui_grid_resolution
        except:
            message = "Could not find 'ground_detect_remeshed'. Please rig vehicle again."
            log_error(message, "Show Groung Grid")
            show_message_box(message, "Visualize Ground Detection", "ERROR")

def update_true_ground(self, context):
    scene = context.scene

    active_car = scene.lc.find_selected()
    ui_use_true_ground = active_car.settings.use_true_ground

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        try: 
            active_car.get_rig_collection()
            active_car.ground_local_object.modifiers[GROUND_DETECT_TRUE_GROUND]['Input_3'] = scene.objects[FILENAME_GROUND_GLOBAL]

            active_car.ground_local_object.modifiers[GROUND_DETECT_TRUE_GROUND].show_render = ui_use_true_ground
            active_car.ground_local_object.modifiers[GROUND_DETECT_TRUE_GROUND].show_viewport = ui_use_true_ground
            active_car.ground_local_object.modifiers[GROUND_DETECT_WRAP_UP].show_render = not ui_use_true_ground
            active_car.ground_local_object.modifiers[GROUND_DETECT_WRAP_UP].show_viewport = not ui_use_true_ground
            active_car.ground_local_object.modifiers[GROUND_DETECT_WRAP_DOWN].show_render = not ui_use_true_ground
            active_car.ground_local_object.modifiers[GROUND_DETECT_WRAP_DOWN].show_viewport = not ui_use_true_ground
            active_car.ground_local_object.modifiers["Ground Detect RESOLUTION"].show_render = not ui_use_true_ground
            active_car.ground_local_object.modifiers["Ground Detect RESOLUTION"].show_viewport = not ui_use_true_ground
        
        except RigCollectionNotFound as e: 
            e.show_error_message()

        except:
            log_error("something went wrong", "update_headlights_presets")

def update_legacy_ground_detection(self, context):
    scene = context.scene

    active_car = scene.lc.find_selected()
    ui_legacy_ground_detection = active_car.settings.legacy_ground_detection

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        rig_object = active_car.rig_object

        try: 
            rig_object.pose.bones["bone_find_up_dir"].constraints["Wrap_Upwards"].enabled = ui_legacy_ground_detection
            rig_object.pose.bones["bone_find_up_dir"].constraints["Wrap_Downwards"].enabled = ui_legacy_ground_detection

            rig_object.pose.bones["bone_dampers_LOC"].constraints["Copy Location"].use_x = not ui_legacy_ground_detection
            rig_object.pose.bones["bone_dampers_LOC"].constraints["Copy Location"].use_y = not ui_legacy_ground_detection
            rig_object.pose.bones["bone_dampers_LOC"].constraints["Damped Track"].enabled = ui_legacy_ground_detection

            if ui_legacy_ground_detection:
                scale = 0.24
                
            else:
                scale = 0.08
            
            rig_object.pose.bones["bone_Slider_bottomOutHeight_Front"].custom_shape_scale_xyz[0] = scale
            rig_object.pose.bones["bone_Slider_bottomOutHeight_Front"].custom_shape_scale_xyz[1] = scale
            rig_object.pose.bones["bone_Slider_bottomOutHeight_Front"].custom_shape_scale_xyz[2] = scale

            rig_object.pose.bones["bone_Slider_bottomOutHeight_Front"].constraints["Copy Location"].enabled = not ui_legacy_ground_detection
            
            
            # Handle Driver for auto bottomOutHeight_Front
            target_data_path = 'pose.bones["bone_Slider_bottomOutHeight_Front"].location'
            driver_field_index = 1
            expression = "bottomOutHeight_Rear"

            if not ui_legacy_ground_detection:

                var01 = [
                    "bottomOutHeight_Rear",
                    "TRANSFORMS",
                    rig_object,
                    "bone_Slider_bottomOutHeight_Rear",
                    "LOC_Y",
                    "LOCAL_SPACE",
                ]

                setup_driver(
                    rig_object,
                    target_data_path,
                    driver_field_index,
                    expression,
                    var01,
                )

            else: 
                drivers = rig_object.animation_data.drivers

                driver_index = -1
                driver_index = find_driver_index(drivers, target_data_path)

                if driver_index != -1 and driver_index < len(rig_object.animation_data.drivers):
                    # Remove the driver based on the index
                    driver = rig_object.animation_data.drivers[driver_index]
                    rig_object.animation_data.drivers.remove(driver)


        except:
            message = "Could not change the ground detection type!"
            log_error(message, "legacy_ground_detection")
            show_message_box(message, "Nothing happened...", "ERROR")



def driving_path_poll(self, object):
    if object.type == 'CURVE' and object.users > 0:
        if object.name != "DrivingPath":
            return True
        
    return False


# OTHERS
def get_postFX_from_rig(self, context):
    scene = bpy.context.scene

    car = scene.lc.find_selected()
    rig_object = car.rig_object
    props = car.properties

    # scene.overdrive_impactPitch = rig_object.pose.bones[B_BODY_WHEEL_IMPACT].constraints["PITCH"].influence*100
    # scene.overdrive_impactYaw = rig_object.pose.bones[B_BODY_WHEEL_IMPACT].constraints["YAW"].influence*100
    # scene.overdrive_impactRoll = rig_object.pose.bones[B_BODY_WHEEL_IMPACT].constraints["ROLL"].influence*100
    props.overdrive_wheel_impact = (
        rig_object
        .pose.bones[B_BODY_WHEEL_IMPACT]
        .constraints["ROLL"]
        .influence
        * 200
    )

    props.overdrive_pitch = (
        rig_object
        .pose.bones[B_BODY_SIM_WIGGLE]
        .constraints["PITCH"]
        .influence
        * (100/5)
    )
    props.overdrive_yaw = (
        rig_object
        .pose.bones[B_BODY_SIM_WIGGLE]
        .constraints["YAW"]
        .influence
        * (100/5)
    )
    props.overdrive_roll = (
        rig_object
        .pose.bones[B_BODY_SIM_WIGGLE]
        .constraints["ROLL"]
        .influence
        * (100/2.5)
    )

    props.overdrive_location = (
        rig_object
        .pose.bones[B_BODY_SIM_MASS]
        .constraints["Copy Location"]
        .influence
        * 100
    )
    props.overdrive_wheel_location = (
        rig_object
        .pose.bones[B_WHEEL_SIM_FR]
        .constraints["Sim"]
        .influence
        * 100
    )


def switch_mode(self, context):
    scene = bpy.context.scene
    settings = scene.settings

    if settings.mode == 'garage_mode':
        settings.show_setup_rig = True

    else:
        settings.show_setup_rig = False


def reveal_setup_controls(self, context):
    scene = bpy.context.scene
    settings = scene.settings

    car = scene.lc.find_selected()
    rig_object = car.rig_object
    rig_armature = car.rig_armature
    bones = rig_object.pose.bones
    ground_local_object = car.ground_local_object

    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = context.preferences.addons[addon_root].preferences

    if settings.show_setup_rig:
        log_info("Showing Setup Rig (Garage mode) - Storing Handles", "reveal_setup_controls")
        try:
            rig_armature.collections["Rig Setup Mode"].is_visible = True
        except:
            #Fallback for LC 1.5
            rig_armature.collections["Layer 17"].is_visible = True

        car.settings.restore_settings = (
            bones[B_SLIDER_BODY_WEIGHT].location[1],    #00
            bones[B_SLIDER_WHEEL_CAMBER].location[1],   #01
            bones[B_SWITCH_SETUP].location[1],          #02
            bones[B_SWITCH_AIRBOURNE].location[1],      #03
            bones[B_SWITCH_AIRBOURNE_ROT].location[1],  #04
            bones[B_SWITCH_AIRBOURNE_ROT].location[1],  #05
            bones[B_SLIDER_PIVOT_POS].location[1],      #06
            bones[B_SLIDER_WHEEL_WOBBLE].location[1],   #07
            bones[B_SLIDER_WHEEL_SHAKE].location[1],    #08
            bones[B_SLIDER_CAMBER_TOE].location[1],     #09
            bones[B_SLIDER_MAX_SUSPENSION_FRONT].location[1], #10
            bones[B_SWITCH_STEERING_WHEEL].location[1], #11
            bones[B_SLIDER_SIMPLE_STEERING].location[1],#12
            bones[B_INTERACTIVE_WHEEL_PAIR].location[0],#13
            bones[B_CUSTOM_MASS].location[0],           #14
            bones[B_CUSTOM_MASS].location[1],           #15
            bones[B_CUSTOM_MASS].location[2],           #16
            bones[B_BODY_DRIFT].rotation_euler[1],      #17
            bones[B_WHEEL_CUSTOM_SUSPENSION_FR].location[1],  #18
            bones[B_WHEEL_CUSTOM_SUSPENSION_FL].location[1],  #19
            bones[B_WHEEL_CUSTOM_SUSPENSION_RR].location[1],  #20
            bones[B_WHEEL_CUSTOM_SUSPENSION_RL].location[1],  #21
            bones[B_WHEEL_CUSTOM_SPIN_FR].rotation_euler[0],  #22
            bones[B_WHEEL_CUSTOM_SPIN_FL].rotation_euler[0],  #23
            bones[B_WHEEL_CUSTOM_SPIN_RR].rotation_euler[0],  #24
            bones[B_WHEEL_CUSTOM_SPIN_RL].rotation_euler[0],  #25
            bones[B_WHEEL_CUSTOM_TURN_FR].rotation_euler[2],  #26
            bones[B_WHEEL_CUSTOM_TURN_FL].rotation_euler[2],  #27
            bones[B_WHEEL_CUSTOM_TURN_RR].rotation_euler[2],  #28
            bones[B_WHEEL_CUSTOM_TURN_RL].rotation_euler[2],  #29
            bones[B_SLIDER_CAMBER_TOE].location[0],           #30
            bones[B_SWITCH_USE_SIMULATION].location[1],       #31
        )

        car.settings.restore_settings_02 = (
            car.settings.show_extra_animation_controls,        #00
            bones[B_WHEEL_CAMBEROFFSET_FR].rotation_euler[1],  #01
            bones[B_WHEEL_CAMBEROFFSET_FL].rotation_euler[1],  #02
            bones[B_WHEEL_CAMBEROFFSET_RR].rotation_euler[1],  #03
            bones[B_WHEEL_CAMBEROFFSET_RL].rotation_euler[1],  #04
            bones[B_WHEEL_CAMBEROFFSET_FR].rotation_euler[2],  #05
            bones[B_WHEEL_CAMBEROFFSET_FL].rotation_euler[2],  #06
            bones[B_WHEEL_CAMBEROFFSET_RR].rotation_euler[2],  #07
            bones[B_WHEEL_CAMBEROFFSET_RL].rotation_euler[2],  #08
            bones[B_WHEEL_ARCH_LIMIT_FR].location[1],          #09
            bones[B_WHEEL_ARCH_LIMIT_FL].location[1],          #10
            bones[B_WHEEL_ARCH_LIMIT_RR].location[1],          #11
            bones[B_WHEEL_ARCH_LIMIT_RL].location[1],          #12
            bones[B_BODY_DRIFT_OFFSET].location[0],            #13
            bones[B_SLIDER_TURN_LIMIT].location[1],            #14
            bones[B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT].location[1], #15
            bones[B_SWITCH_SINGLE_AXLE_REAR].location[1],      #16
            bones[B_SLIDER_MAX_SUSPENSION_REAR].location[1],   #17
            bones[B_SLIDER_BOTTOM_OUT_HEIGHT_REAR].location[1], #18
            bones[B_SWITCH_SINGLE_AXLE_FRONT].location[1],      #19
        )

        car.settings.show_extra_animation_controls = False

        # Switch OFF UI visibility settings
        bones[B_SLIDER_INTERNAL_MUTE].scale[0] = 0
        bones[B_SLIDER_INTERNAL_MUTE].scale[1] = 0

        # Switch OFF weight offset
        bones[B_SLIDER_BODY_WEIGHT].location[1] = 0
        bones[B_SLIDER_WHEEL_CAMBER].location[1] = 0

        # Switch OFF Animation Mode
        bones[B_SWITCH_SETUP].location[1] = 0

        # Airbourne mode ON to avoid ground detection
        bones[B_SWITCH_AIRBOURNE].location[1] = 0
        bones[B_SWITCH_AIRBOURNE_ROT].location[1] = 0

        # Steering wheel OFF
        #bones[B_SLIDER_STEERING_FACTOR].location[1] = 0

        # Drift offset OFF
        bones[B_SLIDER_PIVOT_POS].location[1] = 0

        # Wheel FX OFF
        bones[B_SLIDER_WHEEL_WOBBLE].location[1] = 0
        bones[B_SLIDER_WHEEL_SHAKE].location[1] = 0

        bones[B_SLIDER_CAMBER_TOE].location[1] = 0
        bones[B_SLIDER_CAMBER_TOE].location[0] = 0
        bones[B_SLIDER_MAX_SUSPENSION_FRONT].location[1] = 0.298176
        bones[B_SLIDER_MAX_SUSPENSION_REAR].location[1] = 0.298176
        bones[B_SWITCH_STEERING_WHEEL].location[1] = 0
        bones[B_SLIDER_SIMPLE_STEERING].location[1] = 0

        # Handles
        bones[B_INTERACTIVE_WHEEL_PAIR].location[0] = 0
        bones[B_CUSTOM_MASS].location[0] = 0
        bones[B_CUSTOM_MASS].location[1] = 0
        bones[B_CUSTOM_MASS].location[2] = 0
        bones[B_BODY_DRIFT].rotation_euler[1] = 0
        bones[B_WHEEL_CUSTOM_SUSPENSION_FR].location[1] = 0
        bones[B_WHEEL_CUSTOM_SUSPENSION_FL].location[1] = 0
        bones[B_WHEEL_CUSTOM_SUSPENSION_RR].location[1] = 0
        bones[B_WHEEL_CUSTOM_SUSPENSION_RL].location[1] = 0
        bones[B_WHEEL_CUSTOM_SPIN_FR].rotation_euler[0] = 0
        bones[B_WHEEL_CUSTOM_SPIN_FL].rotation_euler[0] = 0
        bones[B_WHEEL_CUSTOM_SPIN_RR].rotation_euler[0] = 0
        bones[B_WHEEL_CUSTOM_SPIN_RL].rotation_euler[0] = 0
        bones[B_WHEEL_CUSTOM_TURN_FR].rotation_euler[2] = 0
        bones[B_WHEEL_CUSTOM_TURN_FL].rotation_euler[2] = 0
        bones[B_WHEEL_CUSTOM_TURN_RR].rotation_euler[2] = 0
        bones[B_WHEEL_CUSTOM_TURN_RL].rotation_euler[2] = 0

        bones[B_WHEEL_CAMBEROFFSET_FR].rotation_euler[1] = 0
        bones[B_WHEEL_CAMBEROFFSET_FL].rotation_euler[1] = 0
        bones[B_WHEEL_CAMBEROFFSET_RR].rotation_euler[1] = 0
        bones[B_WHEEL_CAMBEROFFSET_RL].rotation_euler[1] = 0
        bones[B_WHEEL_CAMBEROFFSET_FR].rotation_euler[2] = 0
        bones[B_WHEEL_CAMBEROFFSET_FL].rotation_euler[2] = 0
        bones[B_WHEEL_CAMBEROFFSET_RR].rotation_euler[2] = 0
        bones[B_WHEEL_CAMBEROFFSET_RL].rotation_euler[2] = 0
        bones[B_WHEEL_ARCH_LIMIT_FR].location[1]         = 0
        bones[B_WHEEL_ARCH_LIMIT_FL].location[1]         = 0
        bones[B_WHEEL_ARCH_LIMIT_RR].location[1]         = 0
        bones[B_WHEEL_ARCH_LIMIT_RL].location[1]         = 0
        bones[B_BODY_DRIFT_OFFSET].location[0]           = 0
        bones[B_SLIDER_TURN_LIMIT].location[1]           = 0
        bones[B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT].location[1] = 0
        bones[B_SLIDER_BOTTOM_OUT_HEIGHT_REAR].location[1] = 0
        bones[B_SWITCH_SINGLE_AXLE_REAR].location[1]     = 0
        bones[B_SWITCH_SINGLE_AXLE_FRONT].location[1]   = 0

        # Switch Simulation Data
        bones[B_SWITCH_USE_SIMULATION].location[1] = 0

        # Switch OFF Constraints
        bones[B_BONE_FIND_UP_DIR].constraints["Follow Path"].enabled = 0
        bones[B_WHEEL_STEERING_SIMPLE_FR].constraints["Copy Rotation"].enabled = 0
        bones[B_WHEEL_STEERING_SIMPLE_FL].constraints["Copy Rotation"].enabled = 0
        bones[B_WHEEL_CAL_AUTO_FR].constraints["Copy Rotation"].enabled = 0
        bones[B_WHEEL_CAL_AUTO_FL].constraints["Copy Rotation"].enabled = 0
        bones[B_WHEEL_CAL_AUTO_RR].constraints["Copy Rotation"].enabled = 0
        bones[B_WHEEL_CAL_AUTO_RL].constraints["Copy Rotation"].enabled = 0   

        # Mute Animated Handles
        for bone in bones:
            if len(bone.constraints) > 0:
                for const in bone.constraints:
                    if const.name == "mute":
                        const.enabled = True

        # Mute spin (Inverted value as it's a factor)
        bones[B_SLIDER_INTERNAL_MUTE].location[1] = 0

        # Update Extra Animation Handles
        car.settings.show_extra_animation_controls = False

        # Move local ground to center of scene and turn off all input data
        ground_rig_setup = scene.objects[FILENAME_GROUND_RIG_SETUP]

        ground_local_object.constraints["Child Of"].enabled = 0
        ground_local_object.modifiers["Wrap_Upwards"].target = ground_rig_setup
        ground_local_object.modifiers["Wrap_Downwards"].target = ground_rig_setup


        # Offset Garage Mode loc to "Unrigged State" from "Rig Origin"
        garage_is_unrigged_state = False

        if hasattr(car.properties, "garage_mode_loc") and hasattr(car.properties, "garage_mode_rot_z") and addon_preferences.garage_mode_transforms == "unrigged":

            # Locate internal collection
            col = bpy.data.collections.get('InternalCar_' + car.name.lower())
            if col is not None:
                
                old_ob = bpy.data.collections.get("garage_mode_transforms_" + car.name)
                if old_ob:
                    bpy.data.objects.remove(old_ob, do_unlink=True)

                ob = bpy.data.objects.new( "garage_mode_transform_" + car.name, None )
                col.objects.link(ob)
                ob.empty_display_size = 0
                
                garage_is_unrigged_state = True
                ob.location = car.properties.garage_mode_loc
                ob.rotation_euler = mathutils.Vector((math.pi/2, 0, car.properties.garage_mode_rot_z))
                ground_rig_setup.location = car.properties.garage_mode_loc
                bones[B_BONE_FIND_UP_DIR].constraints["Garage_Mode_Loc"].target = ob
                bones[B_BONE_FIND_UP_DIR].constraints["Garage_Mode_Rot"].target = ob
                bones[B_BONE_SETUP_LENGTH].constraints["Garage_Mode_Loc"].target = ob
                bones[B_BONE_SETUP_LENGTH].constraints["Garage_Mode_Rot"].target = ob
                bones[B_BONE_SETUP_REST].constraints["Garage_Mode_Loc"].target = ob
                bones[B_BONE_SETUP_REST].constraints["Garage_Mode_Rot"].target = ob
                bones[B_BONE_UI].constraints["Garage_Mode_Loc"].target = ob
                bones[B_BONE_UI].constraints["Garage_Mode_Rot"].target = ob
        

        bones[B_BONE_FIND_UP_DIR].constraints["Garage_Mode_Loc"].enabled = garage_is_unrigged_state
        bones[B_BONE_FIND_UP_DIR].constraints["Garage_Mode_Rot"].enabled = garage_is_unrigged_state
        bones[B_BONE_SETUP_LENGTH].constraints["Garage_Mode_Loc"].enabled = garage_is_unrigged_state
        bones[B_BONE_SETUP_LENGTH].constraints["Garage_Mode_Rot"].enabled = garage_is_unrigged_state
        bones[B_BONE_SETUP_REST].constraints["Garage_Mode_Loc"].enabled = garage_is_unrigged_state
        bones[B_BONE_SETUP_REST].constraints["Garage_Mode_Rot"].enabled = garage_is_unrigged_state
        bones[B_BONE_UI].constraints["Garage_Mode_Loc"].enabled = garage_is_unrigged_state
        bones[B_BONE_UI].constraints["Garage_Mode_Rot"].enabled = garage_is_unrigged_state
            
        ground_local_object.constraints["Garage_Mode_Loc"].enabled = garage_is_unrigged_state
        ground_local_object.constraints["Garage_Mode_Rot"].enabled = garage_is_unrigged_state

        # Warnig and UI
        rig_object.show_in_front = True

    else:
        log_info("Hiding Setup Rig (Race mode) - Loading Handle Values", "reveal_setup_controls")
        try:
            rig_armature.collections["Rig Setup Mode"].is_visible = False
        except:
            #Fallback for LC 1.5
            rig_armature.collections["Layer 17"].is_visible = False

        # Switch Revert weight offset
        bones[B_SLIDER_BODY_WEIGHT].location[1] = car.settings.restore_settings[0]
        bones[B_SLIDER_WHEEL_CAMBER].location[1] = car.settings.restore_settings[1]
        
        # UN-mute Animated Handles
        for bone in bones:
            if len(bone.constraints) > 0:
                for const in bone.constraints:
                    if const.name == "mute":
                        const.enabled = False

        # Switch Revert Animation Mode
        bones[B_SWITCH_SETUP].location[1] = car.settings.restore_settings[2]

        # Airbourne mode Revert to avoid ground detection
        bones[B_SWITCH_AIRBOURNE].location[1] = car.settings.restore_settings[3]
        bones[B_SWITCH_AIRBOURNE_ROT].location[1] = car.settings.restore_settings[4]

        # Drift offset Revert
        bones[B_SLIDER_PIVOT_POS].location[1] = car.settings.restore_settings[6]

        # Wheel FX Revert
        bones[B_SLIDER_WHEEL_WOBBLE].location[1] = car.settings.restore_settings[7]
        bones[B_SLIDER_WHEEL_SHAKE].location[1] = car.settings.restore_settings[8]

        bones[B_SLIDER_CAMBER_TOE].location[1] = car.settings.restore_settings[9]
        bones[B_SLIDER_CAMBER_TOE].location[0] = car.settings.restore_settings[30]
        bones[B_SLIDER_MAX_SUSPENSION_FRONT].location[1] = car.settings.restore_settings[10]
        bones[B_SWITCH_STEERING_WHEEL].location[1] = car.settings.restore_settings[11]
        bones[B_SLIDER_SIMPLE_STEERING].location[1] = car.settings.restore_settings[12]

        # Handles
        bones[B_INTERACTIVE_WHEEL_PAIR].location[0] = car.settings.restore_settings[13]
        bones[B_CUSTOM_MASS].location[0] = car.settings.restore_settings[14]
        bones[B_CUSTOM_MASS].location[1] = car.settings.restore_settings[15]
        bones[B_CUSTOM_MASS].location[2] = car.settings.restore_settings[16]
        bones[B_BODY_DRIFT].rotation_euler[1] = car.settings.restore_settings[17]
        bones[B_WHEEL_CUSTOM_SUSPENSION_FR].location[1] = car.settings.restore_settings[18]
        bones[B_WHEEL_CUSTOM_SUSPENSION_FL].location[1] = car.settings.restore_settings[19]
        bones[B_WHEEL_CUSTOM_SUSPENSION_RR].location[1] = car.settings.restore_settings[20]
        bones[B_WHEEL_CUSTOM_SUSPENSION_RL].location[1] = car.settings.restore_settings[21]
        bones[B_WHEEL_CUSTOM_SPIN_FR].rotation_euler[0] = car.settings.restore_settings[22]
        bones[B_WHEEL_CUSTOM_SPIN_FL].rotation_euler[0] = car.settings.restore_settings[23]
        bones[B_WHEEL_CUSTOM_SPIN_RR].rotation_euler[0] = car.settings.restore_settings[24]
        bones[B_WHEEL_CUSTOM_SPIN_RL].rotation_euler[0] = car.settings.restore_settings[25]
        bones[B_WHEEL_CUSTOM_TURN_FR].rotation_euler[2] = car.settings.restore_settings[26]
        bones[B_WHEEL_CUSTOM_TURN_FL].rotation_euler[2] = car.settings.restore_settings[27]
        bones[B_WHEEL_CUSTOM_TURN_RR].rotation_euler[2] = car.settings.restore_settings[28]
        bones[B_WHEEL_CUSTOM_TURN_RL].rotation_euler[2] = car.settings.restore_settings[29]

        bones[B_WHEEL_CAMBEROFFSET_FR].rotation_euler[1] = car.settings.restore_settings_02[1]
        bones[B_WHEEL_CAMBEROFFSET_FL].rotation_euler[1] = car.settings.restore_settings_02[2]
        bones[B_WHEEL_CAMBEROFFSET_RR].rotation_euler[1] = car.settings.restore_settings_02[3]
        bones[B_WHEEL_CAMBEROFFSET_RL].rotation_euler[1] = car.settings.restore_settings_02[4]
        bones[B_WHEEL_CAMBEROFFSET_FR].rotation_euler[2] = car.settings.restore_settings_02[5]
        bones[B_WHEEL_CAMBEROFFSET_FL].rotation_euler[2] = car.settings.restore_settings_02[6]
        bones[B_WHEEL_CAMBEROFFSET_RR].rotation_euler[2] = car.settings.restore_settings_02[7]
        bones[B_WHEEL_CAMBEROFFSET_RL].rotation_euler[2] = car.settings.restore_settings_02[8]
        bones[B_WHEEL_ARCH_LIMIT_FR].location[1] = car.settings.restore_settings_02[9]
        bones[B_WHEEL_ARCH_LIMIT_FL].location[1] = car.settings.restore_settings_02[10]
        bones[B_WHEEL_ARCH_LIMIT_RR].location[1] = car.settings.restore_settings_02[11]
        bones[B_WHEEL_ARCH_LIMIT_RL].location[1] = car.settings.restore_settings_02[12]
        bones[B_BODY_DRIFT_OFFSET].location[0] = car.settings.restore_settings_02[13]
        bones[B_SLIDER_TURN_LIMIT].location[1] = car.settings.restore_settings_02[14]
        bones[B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT].location[1] = car.settings.restore_settings_02[15]
        bones[B_SWITCH_SINGLE_AXLE_REAR].location[1] = car.settings.restore_settings_02[16]
        bones[B_SLIDER_MAX_SUSPENSION_REAR].location[1] = car.settings.restore_settings_02[17]
        bones[B_SLIDER_BOTTOM_OUT_HEIGHT_REAR].location[1] = car.settings.restore_settings_02[18]
        bones[B_SWITCH_SINGLE_AXLE_FRONT].location[1] = car.settings.restore_settings_02[19]
        
        
        # Switch Simulation Data
        bones[B_SWITCH_USE_SIMULATION].location[1] = car.settings.restore_settings[31]

        # Switch ON Constraints
        bones[B_BONE_FIND_UP_DIR].constraints["Follow Path"].enabled = 1
        bones[B_WHEEL_STEERING_SIMPLE_FR].constraints["Copy Rotation"].enabled = 1
        bones[B_WHEEL_STEERING_SIMPLE_FL].constraints["Copy Rotation"].enabled = 1
        bones[B_WHEEL_CAL_AUTO_FR].constraints["Copy Rotation"].enabled = 1
        bones[B_WHEEL_CAL_AUTO_FL].constraints["Copy Rotation"].enabled = 1
        bones[B_WHEEL_CAL_AUTO_RR].constraints["Copy Rotation"].enabled = 1
        bones[B_WHEEL_CAL_AUTO_RL].constraints["Copy Rotation"].enabled = 1


        if hasattr(car.properties, "garage_mode_loc") and hasattr(car.properties, "garage_mode_rot_z"):
            garage_is_unrigged_state = True
        else:
            garage_is_unrigged_state = False
        

        bones[B_BONE_FIND_UP_DIR].constraints["Garage_Mode_Loc"].enabled = False
        bones[B_BONE_FIND_UP_DIR].constraints["Garage_Mode_Rot"].enabled = False
        bones[B_BONE_SETUP_LENGTH].constraints["Garage_Mode_Loc"].enabled = False
        bones[B_BONE_SETUP_LENGTH].constraints["Garage_Mode_Rot"].enabled = False
        bones[B_BONE_SETUP_REST].constraints["Garage_Mode_Loc"].enabled = False
        bones[B_BONE_SETUP_REST].constraints["Garage_Mode_Rot"].enabled = False
        bones[B_BONE_UI].constraints["Garage_Mode_Loc"].enabled = False
        bones[B_BONE_UI].constraints["Garage_Mode_Rot"].enabled = False
            
        ground_local_object.constraints["Garage_Mode_Loc"].enabled = False
        ground_local_object.constraints["Garage_Mode_Rot"].enabled = False

        # unmute spin (VALUE INVERTED as it's a factor
        bones[B_SLIDER_INTERNAL_MUTE].location[1] = 1

        # Update Handles Sliders UI
        update_ui_view_elements(self, context)

        # Restore ground detection
        ground_combined = scene.objects[FILENAME_GROUND_GLOBAL]

        ground_local_object.constraints["Child Of"].enabled = 1
        ground_local_object.modifiers["Wrap_Upwards"].target = ground_combined
        ground_local_object.modifiers["Wrap_Downwards"].target = ground_combined

        # Warnig and UI
        rig_object.show_in_front = False


    # Try to frame the vehicle    
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active

                # check to make sure local view is disabled when entering Rig Setup Mode
                if settings.show_setup_rig and space.local_view:
                    bpy.ops.view3d.localview(frame_selected=False)

                # Check to skip if user already exited local view
                if not settings.show_setup_rig and not space.local_view:
                    break
                

                if settings.show_setup_rig:
                    bpy.ops.object.select_all(action="DESELECT")

                    rig_object.select_set(True)

                    for child in rig_object.children_recursive:
                        child.select_set(True)            

                    bpy.ops.view3d.localview(frame_selected=False)


                elif not settings.show_setup_rig:
                    bpy.ops.view3d.localview(frame_selected=False)

                    bpy.ops.object.select_all(action="DESELECT")

                    rig_object.select_set(True)

                    for child in rig_object.children_recursive:
                        child.select_set(True)            

                rig_object.hide_viewport = True

                with context.temp_override(area = area , region = area.regions[-1]):
                    bpy.ops.view3d.view_selected()

                break
    
        rig_object.hide_viewport = False

        bpy.ops.object.select_all(action="DESELECT")
        rig_object.select_set(True)

    except:
        log_info(f"Could not focus on vehicle in Rig Setup Mode - Not critical", "Rig Setup Mode")

# not used - Drivers are used instead
def update_tire_pressure(self, context):
    scene = bpy.context.scene

    car = scene.lc.find_selected()
    rig_object = car.rig_object
    bones = rig_object.pose.bones

    val = car.settings.overdrive_wheel_pressure / 100

    bones[B_WHEEL_FLOOR_FR].constraints["Floor"].influence = val
    bones[B_WHEEL_FLOOR_FL].constraints["Floor"].influence = val
    bones[B_WHEEL_FLOOR_RR].constraints["Floor"].influence = val
    bones[B_WHEEL_FLOOR_RL].constraints["Floor"].influence = val


def update_deform_factor(self, context):
    scene = bpy.context.scene
    car = scene.lc.find_selected()
    rig_object = car.rig_object
    bones = rig_object.pose.bones

    val = car.settings.deform_factor / 100

    bones[B_SLIDER_TIRE_DEFORM_FACTOR].location[1] = val


def swap_pos(self, context):
    scene = bpy.context.scene
    car = scene.lc.find_selected()

    val = "REST" if car.settings.use_rest_pos else "POSE"

    bpy.data.armatures[FILENAME_CARRIG_ARMATURE].pose_position = val


def update_labels(self, context):
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = context.preferences.addons[addon_root].preferences
    scene = bpy.context.scene
    lc_cars = scene.lc.cars

    for car in lc_cars:
        if addon_preferences.show_slider_labels:
            try:
                car.rig_armature.collections["Slider Labels"].is_visible = True
            except:
                #Fallback for LC 1.5
                car.rig_armature.collections["Layer 24"].is_visible = True

        else:
            try:
                car.rig_armature.collections["Slider Labels"].is_visible = False
            except:
                #Fallback for LC 1.5
                car.rig_armature.collections["Layer 24"].is_visible = False


def update_skidmarks(self, context):
    scene = bpy.context.scene
    active_car = scene.lc.find_selected()
    ui_skidmarks_mul = active_car.properties.skidmarks_mul
    ui_skidmarks_var = active_car.properties.skidmarks_var

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        skidmark_mat = active_car.skidmark_material

        mul = skidmark_mat.node_tree.nodes["Bright/Contrast"].inputs[1]
        var = skidmark_mat.node_tree.nodes["Bright/Contrast"].inputs[2]

        mul.default_value = 6*(ui_skidmarks_mul)
        var.default_value = 15*(ui_skidmarks_var)


def toggle_skidmarks(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()
    ui_enable_skidmarks = active_car.settings.enable_skidmarks

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        
        collection_name = active_car.collection.name
        skidmark_coll = active_car.skidmark_collection

        skidmark_FL = scene.objects[FILENAME_SKIDMARK_ENGINE_FL + ("_" + collection_name)]
        skidmark_FR = scene.objects[FILENAME_SKIDMARK_ENGINE_FR + ("_" + collection_name)]
        skidmark_RL = scene.objects[FILENAME_SKIDMARK_ENGINE_RL + ("_" + collection_name)]
        skidmark_RR = scene.objects[FILENAME_SKIDMARK_ENGINE_RR + ("_" + collection_name)]
        
        skidmarks = [skidmark_FL, skidmark_FR, skidmark_RL, skidmark_RR]

        if ui_enable_skidmarks:

            if validate_lc_object(skidmark_FL):
                skidmark_coll.hide_viewport = 0
                skidmark_coll.hide_render = 0

                for skidmark in skidmarks:
                    skidmark.modifiers["Shrinkwrap"].target = scene.objects[FILENAME_GROUND_GLOBAL]

                    for modifier in skidmark.modifiers:
                        modifier.show_viewport = True
                        modifier.show_render = True
            
            

        else:
            skidmark_coll.hide_viewport = 1
            skidmark_coll.hide_render = 1

            for skidmark in skidmarks:
                for modifier in skidmark.modifiers:
                    modifier.show_viewport = False
                    modifier.show_render = False

    

    if ui_enable_skidmarks:
        bpy.ops.object.free_skidmarks()


def toggle_edit_all_mode(self, context):
    scene = context.scene
    multi_edit = scene.settings.edit_all_mode

    if not multi_edit:
        cars = scene.lc.cars

        for car in cars:
            settings = car.settings
            props = car.properties
            # skidmarks
            try:
                if car.skidmark_collection is not None:
                    settings.enable_skidmarks = not car.skidmark_collection.hide_viewport

                if car.skidmark_material is not None:
                    mul = car.skidmark_material.node_tree.nodes["Bright/Contrast"].inputs[1]
                    var = car.skidmark_material.node_tree.nodes["Bright/Contrast"].inputs[2]

                    props.skidmarks_mul = mul.default_value/6
                    props.skidmarks_var = var.default_value/15
            except Exception as e:
                print(f"[LC] toggle_edit_all_mode skidmark error for {car.name}: {e}")


            # speedometer


            # view panel
            try:
                if car.rig_armature is None:
                    print(f"[LC] toggle_edit_all_mode: rig_armature is None for {car.name}, skipping")
                else:
                    settings.show_extra_animation_controls = car.rig_armature.collections["Extra Controls"].is_visible
            except:
                try:
                    #Fallback for LC 1.5
                    settings.show_extra_animation_controls = car.rig_armature.collections["Layer 3"].is_visible
                except:
                    print(f"[LC] toggle_edit_all_mode: could not read bone collections for {car.name}")

            settings.show_ground_grid = not car.ground_local_object.hide_viewport
            settings.grid_resolution = car.ground_local_object.modifiers["Ground Detect RESOLUTION"].levels


            # vehicle settings panel            
            settings.limit_sliders = car.rig_object.pose.bones[B_SLIDER_WHEEL_WOBBLE].constraints["Limit Location"].enabled

            action_groups = car.rig_object.animation_data.action.groups
            bone = car.rig_object.pose.bones[B_WHEEL_SHAKE_RR]
            group = action_groups.get(bone.name)
            for channel in group.channels:
                if channel.modifiers[0].type == "FNGENERATOR":
                        val = channel.modifiers[0].phase_multiplier
            props.shake_frequency = val


            # visualizers
            settings.show_acc_viz = not car.sim_acc_viz.hide_viewport
            settings.show_vel_viz = not car.sim_vel_viz.hide_viewport

            
            # headlights
            collection_name = car.collection.name
            high_beam = bpy.context.scene.objects[OBJECT_HIGHBEAM_R + '_' + collection_name]
            low_beam = bpy.context.scene.objects[OBJECT_LOWBEAM_R + '_' + collection_name]

            settings.low_beam_visibility = not low_beam.hide_viewport
            settings.high_beam_visibility = not high_beam.hide_viewport

            high_beam = bpy.data.lights[FILENAME_L_HIGHBEAM_R +'_' + collection_name]
            low_beam = bpy.data.lights[FILENAME_L_LOWBEAM_R +'_' + collection_name]

            props.low_beam_temperature = low_beam.node_tree.nodes["Group"].inputs[0].default_value/1000
            props.low_beam_intensity = (low_beam.energy * 341.4967) / 100
            props.low_beam_sharpness = low_beam.node_tree.nodes["Group"].inputs[1].default_value

            props.high_beam_temperature = high_beam.node_tree.nodes["Group"].inputs[0].default_value/1000
            props.high_beam_intensity = (high_beam.energy * 341.4967) / 100           
            props.high_beam_sharpness = high_beam.node_tree.nodes["Group"].inputs[1].default_value/0.75


def update_live_physics(self, context):
    scene = bpy.context.scene
    active_car = scene.lc.find_selected()
    props = active_car.properties

    switch = active_car.rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1]
    switch_setup_mode = active_car.rig_object.pose.bones["bone_Switch_Setup"].location[1]

    if switch > 0.5 and not props.baked_physics:
        bpy.ops.object.refresh_physics()


def update_anim_export(self, context):
    scene = bpy.context.scene
    
    if scene.settings.include_anim == False:
        scene.settings.export_anim_only = False


def update_warm_up(self, context):
    scene = bpy.context.scene

    scene.frame_start = scene.frame_preview_start - scene.settings.physics_warm_up_frames

    if (scene.frame_preview_start - scene.settings.physics_warm_up_frames) < 1:
        scene.settings.physics_warm_up_frames = scene.frame_preview_start


def update_user_path(self, context):
    scene = bpy.context.scene
    active_car = scene.lc.find_selected()
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = context.preferences.addons[addon_root].preferences

    path = active_car.properties.custom_path

    if path is not None     and     addon_preferences.override_anim_on_path_change:
        path.data.use_path = True
        path_len = get_active_curve_length(path)

        if path_len == -1: #If it failed
            path.data.path_duration = 1

        path.data.path_duration = int(path_len)

        #scene.use_preview_range = True
    
    else:
        #scene.use_preview_range = False
        pass


def update_user_path_range(self, context):
    scene = bpy.context.scene
    active_car = scene.lc.find_selected()
    props = active_car.properties

    if props.frame_custom_path_start < 0:
        props.frame_custom_path_start = 0
        
    if props.frame_custom_path_end < 0:
        props.frame_custom_path_end = 0

    if props.frame_custom_path_start > props.frame_custom_path_end:
        props.frame_custom_path_end = props.frame_custom_path_start

    if props.frame_custom_path_end < props.frame_custom_path_start:
        props.frame_custom_path_start = props.frame_custom_path_end

    return None
        



        

def update_speed_segment_state(self, context):
    scene = bpy.context.scene
    settings = scene.settings

    #settings.speed_segments_kill = False
    settings.speed_segments_running = False

    try:
        bpy.ops.object.mode_set(mode='OBJECT')
    except:
        pass


# Not yet implemented - Problematic to run a Modal all the time to force update the panel
def ui_update_timer(self, context):
    for region in context.area.regions:
        if region.type == "UI":
            region.tag_redraw()
    return None


def reset_handles(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()

    cars = []
    if scene.settings.edit_all_mode: 
        cars = scene.lc.cars
    else: 
        cars.append(active_car)

    for active_car in cars:
        rig_object = active_car.rig_object
        bones = rig_object.pose.bones

        for bone in bones:
            if "bone_Slider" in bone.name or "bone_Switch" in bone.name:
                bone.location[1] = 0


        # Unique bone value defaults
        bones[B_SWITCH_SETUP].location[1] = B_SWITCH_SETUP_DEFAULT_VALUE
        bones[B_SLIDER_INTERNAL_MUTE].location[1] = B_SLIDER_INTERNAL_MUTE_DEFAULT_VALUE
        bones[B_SLIDER_WHEEL_CAMBER].location[1] = B_SLIDER_WHEEL_CAMBER_DEFAULT_VALUE
        bones[B_SLIDER_STEERINGACCURACY].location[1] = B_SLIDER_STEERINGACCURAC_DEFAULT_VALUE
        bones[B_SLIDER_BODY_WEIGHT].location[1] = B_SLIDER_BODY_WEIGHT_DEFAULT_VALUE
        bones[B_SLIDER_MAX_SUSPENSION_FRONT].location[1] = B_SLIDER_MAX_SUSPENSION_FRONT_DEFAULT_VALUE
        bones[B_SLIDER_MAX_SUSPENSION_REAR].location[1] = B_SLIDER_MAX_SUSPENSION_REAR_DEFAULT_VALUE
        bones[B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT].location[1] = B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT_DEFAULT_VALUE
        bones[B_SLIDER_BOTTOM_OUT_HEIGHT_REAR].location[1] = B_SLIDER_BOTTOM_OUT_HEIGHT_REAR_DEFAULT_VALUE

        # Reset animation handles
        bones[B_INTERACTIVE_WHEEL_PAIR].location[0] = 0
        bones[B_CUSTOM_MASS].location[0] = 0
        bones[B_CUSTOM_MASS].location[1] = 0
        bones[B_CUSTOM_MASS].location[2] = 0
        bones[B_BODY_DRIFT].rotation_euler[1] = 0
        bones[B_WHEEL_CUSTOM_SUSPENSION_FR].location[1] = 0
        bones[B_WHEEL_CUSTOM_SUSPENSION_FL].location[1] = 0
        bones[B_WHEEL_CUSTOM_SUSPENSION_RR].location[1] = 0
        bones[B_WHEEL_CUSTOM_SUSPENSION_RL].location[1] = 0
        bones[B_WHEEL_CUSTOM_SPIN_FR].rotation_euler[0] = 0
        bones[B_WHEEL_CUSTOM_SPIN_FL].rotation_euler[0] = 0
        bones[B_WHEEL_CUSTOM_SPIN_RR].rotation_euler[0] = 0
        bones[B_WHEEL_CUSTOM_SPIN_RL].rotation_euler[0] = 0
        bones[B_WHEEL_CUSTOM_TURN_FR].rotation_euler[2] = 0
        bones[B_WHEEL_CUSTOM_TURN_FL].rotation_euler[2] = 0
        bones[B_WHEEL_CUSTOM_TURN_RR].rotation_euler[2] = 0
        bones[B_WHEEL_CUSTOM_TURN_RL].rotation_euler[2] = 0

        bones[B_WHEEL_CAMBEROFFSET_FR].rotation_euler[1] = 0
        bones[B_WHEEL_CAMBEROFFSET_FL].rotation_euler[1] = 0
        bones[B_WHEEL_CAMBEROFFSET_RR].rotation_euler[1] = 0
        bones[B_WHEEL_CAMBEROFFSET_RL].rotation_euler[1] = 0
        bones[B_WHEEL_CAMBEROFFSET_FR].rotation_euler[2] = 0
        bones[B_WHEEL_CAMBEROFFSET_FL].rotation_euler[2] = 0
        bones[B_WHEEL_CAMBEROFFSET_RR].rotation_euler[2] = 0
        bones[B_WHEEL_CAMBEROFFSET_RL].rotation_euler[2] = 0
        bones[B_WHEEL_ARCH_LIMIT_FR].location[1]         = 0
        bones[B_WHEEL_ARCH_LIMIT_FL].location[1]         = 0
        bones[B_WHEEL_ARCH_LIMIT_RR].location[1]         = 0
        bones[B_WHEEL_ARCH_LIMIT_RL].location[1]         = 0
        bones[B_BODY_DRIFT_OFFSET].location[0]           = 0
        bones[B_SLIDER_TURN_LIMIT].location[1]           = 0
        bones[B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT].location[1] = 0
        bones[B_SLIDER_BOTTOM_OUT_HEIGHT_REAR].location[1] = 0
        bones[B_SWITCH_SINGLE_AXLE_REAR].location[1]     = 0
        bones[B_SWITCH_SINGLE_AXLE_FRONT].location[1]   = 0

    
    return None



def update_link_tire(self, context):
    scene = context.scene

    if scene.settings.link_tire_settings:
        scene.settings.tire_width = scene.settings.tire_width_front
        scene.settings.tire_ratio = scene.settings.tire_ratio_front
        scene.settings.rim_diameter = scene.settings.rim_diameter_front

    else:
        scene.settings.tire_width_front = scene.settings.tire_width
        scene.settings.tire_ratio_front = scene.settings.tire_ratio
        scene.settings.rim_diameter_front = scene.settings.rim_diameter

        scene.settings.tire_width_rear = scene.settings.tire_width
        scene.settings.tire_ratio_rear = scene.settings.tire_ratio
        scene.settings.rim_diameter_rear = scene.settings.rim_diameter

    return None


def update_proxy(self, context):
    scene = context.scene
    active_car = scene.lc.find_selected()

    coll_name = active_car.name + " Proxy"

    if not active_car.properties.has_lib_override:
        
        if active_car.properties.model_quality == "proxy":
            for coll in scene.collection.children_recursive:
                if coll.name == coll_name:
                    coll.hide_viewport = False

                    for obj in coll.objects:
                        obj.display_type = "TEXTURED"
            
            scene.car_collection.hide_viewport = True


        elif active_car.properties.model_quality == "full":
            for coll in scene.collection.children_recursive:
                if coll.name == coll_name:
                    coll.hide_viewport = True
            
            scene.car_collection.hide_viewport = False


        elif active_car.properties.model_quality == "overlay":
            for coll in scene.collection.children_recursive:
                if coll.name == coll_name:
                    coll.hide_viewport = False

                    for obj in coll.objects:
                        obj.display_type = "WIRE"
            
            scene.car_collection.hide_viewport = False
    
    else:
        car_name_clean = active_car.name.replace(" Linked","")

        car_full = scene.objects.get(car_name_clean)
        car_proxy = scene.objects.get(car_name_clean + " Proxy")

        if car_full and car_proxy:

            if active_car.properties.model_quality == "proxy":
                car_full.hide_viewport = True
                car_proxy.hide_viewport = False

            elif active_car.properties.model_quality == "full":
                car_full.hide_viewport = False
                car_proxy.hide_viewport = True

            elif active_car.properties.model_quality == "overlay":
                car_full.hide_viewport = False
                car_proxy.hide_viewport = False


    return None



def update_filter_anim_preset(self, context):
    
    scene = context.scene

    addons_path = get_addon_path()   

    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = context.preferences.addons[addon_root].preferences


    if scene.settings.filter_anim_presets == "custom":
        destination_folder = os.path.join(addons_path, "assets", "images", "custom_presets")
    elif scene.settings.filter_anim_presets == "library":
        destination_folder = addon_preferences.anim_preset_lib_path
    else:
        destination_folder = os.path.join(addons_path, "assets", "images")

    n = 0
    
    for n in range(10):
        item_1 = os.listdir(destination_folder)[n]

        if os.path.splitext(item_1)[1] == ".png":
            break

        n = n+1

    image_1 = item_1

    bpy.data.window_managers["WinMan"].animation_presets = image_1

    return None


def update_custom_anim_path(self, context):

    addons_path = get_addon_path()

    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = context.preferences.addons[addon_root].preferences
    

    src = os.path.join(addons_path, "assets", "images", "custom_presets", "一 Create 一.png")
    dst = os.path.join(addon_preferences.anim_preset_lib_path, "一 Create 一.png")
    
    shutil.copyfile(src, dst)

    return None
