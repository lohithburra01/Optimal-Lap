import bpy
import math
import os

from ..operators.low_level import clear_parent_keep_transform
from ..utils.resources import (
    get_resource_path,
    upload_asset,
    rename_rig_objects,
)
from ..utils.functions import get_addon_version, get_blender_min_version, get_collection_by_name, clear_orphans, unlink_collection_all, link_collection, get_children_list, get_driver_indices_by_expression
from ..utils.validations import validate_collection, validated_collection_content, validate_collection_name_availability, validate_library_overrides, validate_name_availability, validate_non_applied_scales, validate_parent, validate_car_dimension, validate_rotation_mode, validate_version, validate_viewport_context, validate_wheel_height, validate_wheel_naming, validate_existing_objects, validate_animation
from ..utils.relocation import (
    rotate_car,
    relocate_car,
    set_wheels_pivot,
    relocate_lights,
    save_locaction,
    save_rotation,
)

from ..utils.maths import create_matrix

from ..globals import *

from ..utils.errors.exceptions import LCException

from ..ui.utils import show_message_box
from ..utils.rig import find_car_parts
from ..logger import log_error, log_debug, log_info


class OBJECT_OT_rig_car(bpy.types.Operator):
    bl_label = "Rig Vehicle!"
    bl_idname = "object.rig_car"
    bl_description = "Just rev the engine and get ready for Take-Off"
    bl_options = {"UNDO"}

    def collapse_imported_collections(self, context):
       
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN', iterations=1)
            area = next(a for a in bpy.context.screen.areas if a.type == "OUTLINER")
            region = next(r for r in area.regions if r.type == "WINDOW")
            with bpy.context.temp_override(area=area, region=region):
                bpy.ops.outliner.show_hierarchy("INVOKE_DEFAULT")
                for i in range(2):
                    bpy.ops.outliner.expanded_toggle()
            area.tag_redraw()

        except:
            log_error("Could not collapse collections. Not critical.", "OBJECT_OT_rig_car")

        return True
    

    def _import_preset_vehicle(self, file_path, COLLECTION):
        scene = bpy.context.scene

        upload_asset(file_path, "Collection", COLLECTION)

        preset_collection = get_collection_by_name(
            COLLECTION, scene.collection
        )

        """print("File Path", file_path)
        print("COLLECTION name", COLLECTION)
        print("Coll item", preset_collection)"""

        unlink_collection_all(preset_collection)
        link_collection(preset_collection, scene.collection)

        return preset_collection



    def execute(self, context):
        scene = context.scene

        # Validate before attempting to upload any data
        try:
            validate_library_overrides()
        except LCException as e:
            e.show_error_message()
            return {"CANCELLED"}
        
        # Create undo point
        bpy.ops.ed.undo_push()

        try:
            # STEP 1: FIND ADDON COLLECTION ----------------------------------------------------------

            # if LaunchControl collection not in scene then upload it
            lc_collection = get_collection_by_name(
                COLLECTIONNAME_ADDON, scene.collection
            )

            if not lc_collection:
                validate_collection_name_availability()
                file_path = get_resource_path(FILENAME_BLEND)

                if file_path is None:
                    text = "Could not access Add-on. Please re-install."
                    log_error(text, "OBJECT_OT_rig_car")
                    show_message_box(title="Unable to rig car", message=text, icon="ERROR")
                    return {"CANCELLED"}
                
                upload_asset(file_path, "Collection", COLLECTIONNAME_ADDON)

                lc_collection = bpy.data.collections[COLLECTIONNAME_ADDON]

                unlink_collection_all(lc_collection)
                link_collection(lc_collection, scene.collection)

                try:
                    for area in bpy.context.screen.areas:
                        if area.type == 'VIEW_3D':
                            for space in area.spaces:
                                if space.type == 'VIEW_3D':
                                    space.overlay.show_relationship_lines = False
                                    break
                except:
                    log_error("Could not disable relationship lines. Not critical.", "OBJECT_OT_rig_car")
  

            # STEP 2: RIG VEHICLE --------------------------------------------------------------------
            # save current frame and move to frame 0 to avoid animation issues
            restore_frame = context.scene.frame_current
            context.scene.frame_set(0)
            
            multi_edit = scene.settings.edit_all_mode
            search_collections = []

            selected_collection = scene.car_collection

            # If User Vehicle
            if selected_collection:
                if multi_edit: 
                    for collection in scene.collection.children:
                        if collection != bpy.data.collections['LaunchControl']:
                            search_collections.append(collection)
                else: search_collections.append(selected_collection)
            
            # If Preset Vehicle
            else:

                # Get Vehicle Preset Name
                vehicle_preset_name = os.path.splitext(bpy.data.window_managers["WinMan"].vehicle_presets)[0]
                blend_name = str(vehicle_preset_name) + ".blend"

                # Setup file reference to addons folder
                file_dir = get_resource_path("vehicles")
                file_path = os.path.join(file_dir, blend_name)

                if file_path is None:
                    text = "Could not access Add-on. Please re-install."
                    log_error(text, "OBJECT_OT_rig_car")
                    show_message_box(title="Unable to Rig Preset Vehicle", message=text, icon="ERROR")
                    return {"CANCELLED"}

                # Import preset vehicle
                try:
                    preset_collection = self._import_preset_vehicle(file_path, vehicle_preset_name)
                except:
                    text = (f"Model could not be added. Please re-install the vehicle pack or contact the creator.")
                    show_message_box(title="Failed to load Model", message=text, icon="ERROR")
                    self.report({'ERROR'}, text)
                    log_info(text, "OBJECT_OT_install_lib")

                scene = context.scene
                
                try: 
                    sel_obj = context.selected_objects[0]
                    obj_collections = sel_obj.users_collection[0]
                    preset_collection = obj_collections
                            
                except:
                    text = "Could not find correct preset collection, will default to name of pre-import collection"
                    log_info(text, "OBJECT_OT_rig_car")
                
                  
                scene.car_collection = preset_collection

                # Try to collapse all outliner collections
                self.collapse_imported_collections(context)

                return {"FINISHED"}


            for active_collection in search_collections:

                validated_collection_content(active_collection)

                # find car parts
                wheels, body, brakes, headlights, wheelcovers = find_car_parts(active_collection)

                ### Validation before rigging ####
                validate_collection(active_collection)
                validate_name_availability()
                validate_version()
                if not scene.settings.cad_setup:
                    validate_parent(body, wheels)
                validate_car_dimension(wheels)
                validate_wheel_height(wheels)
                validate_rotation_mode(body, wheels, brakes, wheelcovers)
                validate_viewport_context()
                validate_animation(body, wheels, brakes, wheelcovers)

                #if scene.settings.cad_setup:
                    #validate_non_applied_scales(body, wheels, brakes)


                # STEP 3: ADD CAR TO GLOBAL LC_CARS ------------------------------------------------------
                # add 'scene and collection' properties
                active_car = scene.lc.add(active_collection, active_collection.name)
                addon_root = ".".join(__package__.split(".")[:-2])
                addon_preferences = context.preferences.addons[addon_root].preferences

                # add 'body parts' properties
                active_car.body.body = body

                active_car.wheels.wheel_RL = wheels[0]
                active_car.wheels.wheel_RR = wheels[1]
                active_car.wheels.wheel_FR = wheels[2]
                active_car.wheels.wheel_FL = wheels[3]

                # set automatic tire pivot unless user disabled this
                if addon_preferences.auto_pivot and not scene.settings.cad_setup:
                    set_wheels_pivot(active_car.scene, active_car.wheels)
                    
                # positions
                active_car.body.position.location = body.location
                active_car.body.position.rotation = body.rotation_euler
                active_car.body.position.scale = body.scale

                active_car.wheels.position_wheel_RL.location = wheels[0].location
                active_car.wheels.position_wheel_RL.rotation = wheels[0].rotation_euler
                active_car.wheels.position_wheel_RL.scale = wheels[0].scale
                active_car.wheels.position_wheel_RR.location = wheels[1].location
                active_car.wheels.position_wheel_RR.rotation = wheels[1].rotation_euler
                active_car.wheels.position_wheel_RR.scale = wheels[1].scale
                active_car.wheels.position_wheel_FR.location = wheels[2].location
                active_car.wheels.position_wheel_FR.rotation = wheels[2].rotation_euler
                active_car.wheels.position_wheel_FR.scale = wheels[2].scale
                active_car.wheels.position_wheel_FL.location = wheels[3].location
                active_car.wheels.position_wheel_FL.rotation = wheels[3].rotation_euler
                active_car.wheels.position_wheel_FL.scale = wheels[3].scale

                ### Clear and set parents ###
                active_car.body.clear_parents()
                active_car.wheels.clear_parents()

                if brakes and None not in brakes:
                    # if not ignore, or if all brakes were found
                    active_car.brakes.brake_RL = brakes[0]
                    active_car.brakes.brake_RR = brakes[1]
                    active_car.brakes.brake_FR = brakes[2]
                    active_car.brakes.brake_FL = brakes[3]

                    active_car.brakes.position_brake_RL.location = brakes[0].location
                    active_car.brakes.position_brake_RL.rotation = brakes[0].rotation_euler
                    active_car.brakes.position_brake_RL.scale = brakes[0].scale
                    active_car.brakes.position_brake_RR.location = brakes[1].location
                    active_car.brakes.position_brake_RR.rotation = brakes[1].rotation_euler
                    active_car.brakes.position_brake_RR.scale = brakes[1].scale
                    active_car.brakes.position_brake_FR.location = brakes[2].location
                    active_car.brakes.position_brake_FR.rotation = brakes[2].rotation_euler
                    active_car.brakes.position_brake_FR.scale = brakes[2].scale
                    active_car.brakes.position_brake_FL.location = brakes[3].location
                    active_car.brakes.position_brake_FL.rotation = brakes[3].rotation_euler
                    active_car.brakes.position_brake_FL.scale = brakes[3].scale

                    active_car.brakes.link_to_wheels(active_car.wheels)

                if wheelcovers and None not in wheelcovers:
                    active_car.wheelcovers.wheelcover_FR = wheelcovers[0]
                    active_car.wheelcovers.wheelcover_FL = wheelcovers[1]

                    active_car.wheelcovers.position_wheelcover_FR.location = wheelcovers[0].location
                    active_car.wheelcovers.position_wheelcover_FR.rotation = wheelcovers[0].rotation_euler
                    active_car.wheelcovers.position_wheelcover_FR.scale = wheelcovers[0].scale
                    active_car.wheelcovers.position_wheelcover_FL.location = wheelcovers[1].location
                    active_car.wheelcovers.position_wheelcover_FL.rotation = wheelcovers[1].rotation_euler
                    active_car.wheelcovers.position_wheelcover_FL.scale = wheelcovers[1].scale

                    active_car.wheelcovers.link_to_wheels(active_car.wheels)


                if headlights:
                    active_car.headlights.headlight_R = headlights[0]
                    active_car.headlights.headlight_L = headlights[1]


                # Write the custom wheel size into car data in case of empties as wheels
                if scene.settings.cad_setup:
                    if scene.settings.link_tire_settings:
                        active_car.properties.cad_wheel_size_front = scene.settings.wheel_size_rear
                        active_car.properties.cad_wheel_size_rear = scene.settings.wheel_size_rear
                    else:
                        active_car.properties.cad_wheel_size_front = scene.settings.wheel_size_front
                        active_car.properties.cad_wheel_size_rear = scene.settings.wheel_size_rear

                # STEP 4: RELOCATE VEHICLE ------------------------------------------------------
                ### Rotation and Relocation ###
                restore_locaton = save_locaction(active_car.wheels)
                restore_rotation = save_rotation(active_car.wheels)

                active_car.properties.garage_mode_loc = restore_locaton
                active_car.properties.garage_mode_rot_z = restore_rotation
                

                rotate_car(active_car.wheels, active_car.body)

                ### Check if labels are correct ###
                validate_wheel_naming(active_car.wheels, active_car)

                ### Check if certain objects already exist in the scene ###
                validate_existing_objects()
                
                # STEP 5: IMPORT ASSETS ------------------------------------------------------
                file_path = get_resource_path(FILENAME_BLEND)
                upload_asset(file_path, "Collection", COLLECTIONNAME_CARRIG)

                ### Rename Assets ###
                driving_path = scene.objects[FILENAME_DRIVINGPATH]
                rig_object = scene.objects[FILENAME_CAR_RIG]
                rig_armature = bpy.data.armatures[FILENAME_CARRIG_ARMATURE]
                geo_nodes_skidmarks = bpy.data.node_groups[GEONODE_SKIDMARK]  # a global group
                geo_nodes_sim_body = bpy.data.node_groups[PHYSICS_BODY]
                geo_nodes_sim_wheels = bpy.data.node_groups[PHYSICS_WHEELS]
                sim_body = scene.objects[FILENAME_SIM_BODY]
                sim_wheels = scene.objects[FILENAME_SIM_WHEELS]
                sim_track_to = scene.objects[FILENAME_SIM_TRACK_TO]
                sim_acc_viz = scene.objects[FILENAME_SIM_ACC_VIZ]
                sim_vel_viz = scene.objects[FILENAME_SIM_VEL_VIZ]
                speed_calculator = scene.objects[FILENAME_SPEED_CALCULATOR]
                skidmark_material = bpy.data.materials[M_SKIDMARK_MATERIAL]
                skidmark_collection = get_collection_by_name(
                    COLLECTIONNAME_SKIDMARK, scene.collection
                )
                ground_local_object = scene.objects[FILENAME_GROUND_LOCAL]
                rig_collection = get_collection_by_name(
                    COLLECTIONNAME_CARRIG, scene.collection
                )

                ### Moving rig collection inside addon collection ###
                unlink_collection_all(rig_collection)
                link_collection(rig_collection, lc_collection)


                ### Set up Ground Detection ###
                # add reference to bones in the rig
                ground_detect_bones_names = [
                    B_BONE_FIND_UP_DIR,
                    B_BONE_GROUND_DETECT_RL,
                    B_BONE_GROUND_DETECT_RR,
                    B_BONE_GROUND_DETECT_FL,
                    B_BONE_GROUND_DETECT_FR,
                    B_BONE_GROUND_DETECT_ABS_RL,
                    B_BONE_GROUND_DETECT_ABS_RR,
                    B_BONE_GROUND_DETECT_ABS_FL,
                    B_BONE_GROUND_DETECT_ABS_FR
                ]

                for bone_name in ground_detect_bones_names:
                    rig_object.pose.bones[bone_name].constraints[GROUND_DETECT_WRAP_DOWN].target = ground_local_object
                    rig_object.pose.bones[bone_name].constraints[GROUND_DETECT_WRAP_UP].target = ground_local_object
            
                ### Rotation and Relocation ###
                rig_scale = relocate_car(
                    rig_object, rig_armature, active_car.body, active_car.wheels
                )

                ### Connect meshes to bones ###
                bpy.context.view_layer.objects.active = rig_object
                bpy.ops.object.mode_set(mode="POSE")
                bpy.ops.object.mode_set(mode="OBJECT")
                
                active_car.wheels.attach_bone(rig_object)
                active_car.body.attach_bone(rig_object)
                if brakes and None not in brakes:
                    active_car.brakes.attach_bone(rig_object)
                if wheelcovers and None not in wheelcovers:
                    active_car.wheelcovers.attach_bone(rig_object)
                if headlights:
                    active_car.headlights.attach_bone(scene, rig_object)
                
                ### Set lattice ###
                #active_car.wheels.set_lattice(scene, rig_scale)

                ### Relocate lights ###
                if headlights:
                    relocate_lights(scene, active_car.headlights, active_car.wheels, rig_scale)

                ### Rename assets for multi-car support ###
                rename_rig_objects(scene, active_collection.name)

                try:
                    for bone_coll in rig_armature.collections:
                        bone_coll.is_visible = False

                    rig_armature.collections["Main Controls"].is_visible = True
                    rig_armature.collections["UI"].is_visible = True

                except:
                    #Fallback for Blender 3.6
                    rig_armature.layers = [i in [0, 1] for i in range(32)]

                if not multi_edit:
                    scene.frame_set(restore_frame)

                try:  # removing weird extra scene from import...
                    bpy.data.scenes.remove(bpy.data.scenes[FILENAME_TEMP_CAR_RIG])
                    clear_orphans()
                except:
                    pass

                # STEP 6: FILL REST OF CAR DATA SCTRUCTURE ------------------------------------------------------
                # add 'rig' properties
                active_car.is_rigged = True
                active_car.rig_object = rig_object
                active_car.rig_armature = rig_armature
                active_car.rig_collection = rig_collection
                active_car.lc_collection = lc_collection
                active_car.skidmark_collection = skidmark_collection
                active_car.skidmark_material = skidmark_material
                active_car.ground_local_object = ground_local_object
                active_car.sim_body = sim_body
                active_car.sim_wheels = sim_wheels
                active_car.sim_track_to = sim_track_to
                active_car.sim_acc_viz = sim_acc_viz
                active_car.sim_vel_viz = sim_vel_viz
                active_car.speed_calculator = speed_calculator
                active_car.properties.lc_version = get_addon_version()

                # add 'driving path' properties
                active_car.driving_path = driving_path
                
                active_car.driving_path.location = restore_locaton
                active_car.driving_path.rotation_euler[2] = restore_rotation

                active_car.driving_path.modifiers["Shrinkwrap"].target = scene.objects[FILENAME_GROUND_GLOBAL]

                # add reference to objects
                active_car.ground_local_object.modifiers[GROUND_DETECT_WRAP_UP].target = scene.objects[FILENAME_GROUND_GLOBAL]
                active_car.ground_local_object.modifiers[GROUND_DETECT_WRAP_DOWN].target = scene.objects[FILENAME_GROUND_GLOBAL]

                # 'properties and settings' are by default

                ### Setting up sliders as needed for animation
                if scene.settings.cad_setup:
                    active_car.rig_object.pose.bones[B_SLIDER_BODY_WEIGHT].location[1] = scene.settings.emulated_body_weight*20
                    active_car.rig_object.pose.bones[B_SLIDER_CAMBER_TOE].location = [0, ((scene.settings.wheel_camber*180)/math.pi)*0.005, 0]
                else:
                    active_car.rig_object.pose.bones[B_SLIDER_BODY_WEIGHT].location[1] = B_SLIDER_BODY_WEIGHT_DEFAULT_VALUE
                    active_car.rig_object.pose.bones[B_SLIDER_CAMBER_TOE].location = B_SLIDER_CAMBER_TOE_DEFAULT_VALUE

                active_car.rig_object.pose.bones[B_SLIDER_WHEEL_CAMBER].location[1] = B_SLIDER_WHEEL_CAMBER_DEFAULT_VALUE
                active_car.rig_object.pose.bones[B_SWITCH_SETUP].location[1] = B_SWITCH_SETUP_DEFAULT_VALUE
                active_car.rig_object.pose.bones[B_SLIDER_MAX_SUSPENSION_FRONT].location[1] = B_SLIDER_MAX_SUSPENSION_FRONT_DEFAULT_VALUE
                active_car.rig_object.pose.bones[B_SLIDER_MAX_SUSPENSION_REAR].location[1] = B_SLIDER_MAX_SUSPENSION_REAR_DEFAULT_VALUE

                ### Set bottom out height automatically
                rig_scale = active_car.rig_object.pose.bones[B_BONE_FIND_UP_DIR].scale[0]
                wheel_radius_handle_space = (
                    B_BONE_SETUP_WHEEL_RADIUS_HANDLE_REST_POS[0],
                    B_BONE_SETUP_WHEEL_RADIUS_HANDLE_REST_POS[1],
                    B_BONE_SETUP_WHEEL_RADIUS_HANDLE_REST_POS[2],
                )

                
                """wheelRadiusHandle_R = active_car.rig_object.pose.bones["bone_setup_wheelRadiusHandle_R"]       
                wheelRadiusHandle_F = active_car.rig_object.pose.bones["bone_setup_wheelRadiusHandle_F"]
                wheelRadius_F = (wheel_radius_handle_space[2] + wheelRadiusHandle_F.location[0]) 
                wheelRadius_R = (wheel_radius_handle_space[2] + wheelRadiusHandle_R.location[0])

                bottom_out_offset_constant = -0.20
                active_car.rig_object.pose.bones[B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT].location[1] = (wheelRadius_F*2 + bottom_out_offset_constant)   
                active_car.rig_object.pose.bones[B_SLIDER_BOTTOM_OUT_HEIGHT_REAR].location[1] = (wheelRadius_R*2 + bottom_out_offset_constant)"""
                active_car.rig_object.pose.bones[B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT].location[1] = B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT_DEFAULT_VALUE
                active_car.rig_object.pose.bones[B_SLIDER_BOTTOM_OUT_HEIGHT_REAR].location[1] = B_SLIDER_BOTTOM_OUT_HEIGHT_REAR_DEFAULT_VALUE

                ### Set layer visibility
                try:
                    for bone_coll in rig_armature.collections:
                        bone_coll.is_visible = False
                    
                    active_car.rig_object.pose.bones[B_SLIDER_INTERNAL_MUTE].scale[0] = 1
                    active_car.rig_object.pose.bones[B_SLIDER_INTERNAL_MUTE].scale[1] = 0

                except:
                    #Fallback for Blender 3.6
                    active_car.rig_armature.layers = LAYER_VISIBILITY_DEFAULT

                addon_root = ".".join(__package__.split(".")[:-2])
                addon_preferences = context.preferences.addons[addon_root].preferences

                if addon_preferences.show_slider_labels:
                    try:
                        rig_armature.collections["Slider Labels"].is_visible = True
                    except:
                        #Fallback for Blender 3.6
                        active_car.rig_armature.layers[23] = True
                else:
                    try:
                        rig_armature.collections["Slider Labels"].is_visible = False
                    except:
                        #Fallback for Blender 3.6
                        active_car.rig_armature.layers[23] = False

                ### Setting up skidmarks
                geo_nodes_skidmarks.animation_data.drivers[0].driver.variables[0].targets[0].id = scene  
                geo_nodes_skidmarks.animation_data.drivers[0].driver.variables[0].targets[0].id = scene  


                ### Physics
                geo_nodes_sim_body.animation_data.drivers[0].driver.variables[0].targets[0].id = scene
                geo_nodes_sim_wheels.animation_data.drivers[0].driver.variables[0].targets[0].id = scene

                # set up physics sliders 
                vehicle_name = active_collection.name 
                sim_body.animation_data.drivers[2].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.physics_dampening'
                sim_body.animation_data.drivers[3].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.physics_tightness'
                sim_body.animation_data.drivers[4].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.physics_softness'
                sim_body.animation_data.drivers[5].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.physics_multiplier'
                sim_wheels.animation_data.drivers[0].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.physics_dampening'
                sim_wheels.animation_data.drivers[1].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.physics_tightness'
                sim_wheels.animation_data.drivers[2].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.physics_softness'
                sim_wheels.animation_data.drivers[3].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.use_gravity'
                sim_wheels.animation_data.drivers[4].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.auto_level'
                sim_wheels.animation_data.drivers[7].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.spring_offset'
                sim_wheels.animation_data.drivers[8].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.mass'


                # set up postFX sliders 
                expression = 'postFX/100'
                postFX_wheel_location = get_driver_indices_by_expression(rig_object.animation_data.drivers, expression)

                expression = 'postFX/(100*10)'
                postFX_body_pitch_yaw = get_driver_indices_by_expression(rig_object.animation_data.drivers, expression)

                expression = 'postFX/(100*5)'
                postFX_body_roll = get_driver_indices_by_expression(rig_object.animation_data.drivers, expression)               

                expression = '(postFX*0.1)/(100*3.33)'
                postFX_body_location = get_driver_indices_by_expression(rig_object.animation_data.drivers, expression)

                expression = 'shake*0.25 * factor * (postFX/100)'
                wheel_shake_drivers = get_driver_indices_by_expression(rig_object.animation_data.drivers, expression)


                #driver_id = postFX_wheel_location + postFX_driver_indices_02 + postFX_driver_indices_03 + extra_drivers + wheel_shake_drivers

                rig_object.animation_data.drivers[postFX_wheel_location[0]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'
                rig_object.animation_data.drivers[postFX_wheel_location[1]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'
                rig_object.animation_data.drivers[postFX_wheel_location[2]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'
                rig_object.animation_data.drivers[postFX_wheel_location[3]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'

                rig_object.animation_data.drivers[postFX_body_pitch_yaw[0]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_pitch'
                rig_object.animation_data.drivers[postFX_body_pitch_yaw[1]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_yaw'
                rig_object.animation_data.drivers[postFX_body_roll[0]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_roll'

                rig_object.animation_data.drivers[postFX_wheel_location[4]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'
                rig_object.animation_data.drivers[postFX_wheel_location[5]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'
                rig_object.animation_data.drivers[postFX_wheel_location[6]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'
                rig_object.animation_data.drivers[postFX_wheel_location[7]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'

                rig_object.animation_data.drivers[postFX_wheel_location[8]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_pressure'
                rig_object.animation_data.drivers[postFX_wheel_location[9]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_pressure'
                rig_object.animation_data.drivers[postFX_wheel_location[10]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_pressure'
                rig_object.animation_data.drivers[postFX_wheel_location[11]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_pressure'

                rig_object.animation_data.drivers[postFX_body_location[0]].driver.variables[0].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_location'
                
                rig_object.animation_data.drivers[wheel_shake_drivers[0]].driver.variables[2].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'
                rig_object.animation_data.drivers[wheel_shake_drivers[1]].driver.variables[2].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'
                rig_object.animation_data.drivers[wheel_shake_drivers[2]].driver.variables[2].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'
                rig_object.animation_data.drivers[wheel_shake_drivers[3]].driver.variables[2].targets[0].data_path = f'lc.cars["{vehicle_name}"].properties.overdrive_wheel_location'

                # Move collider to the car
                if len(scene.lc.cars) == 1:
                    collider = (DEFAULT_GROUNDS[0] + "_" + active_collection.name)
                    scene.objects[collider].location = driving_path.location
                    scene.objects[collider].rotation_euler = driving_path.rotation_euler

                # make sure animation starts right away on playback
                if scene.frame_start < 25:
                    scene.frame_start = 25

                # set up colors
                color = active_collection.color_tag

                active_car.properties.color_tag = color

                active_car.rig_collection.color_tag = color
                children = get_children_list(active_car.rig_collection)

                for child in children:
                    child.color_tag = color

                if addon_preferences.apply_path_color:
                    white = [0.8,0.8,0.8,1]
                    red = [0.745,0.114,0.105,1]
                    orange = [0.863,0.361,0.089,1]
                    yellow = [0.871,0.708,0.091,1]
                    green = [0.195,0.597,0.195,1]
                    blue = [0.109,0.462,0.815,1]
                    purple = [0.262,0.100,0.694,1]
                    pink = [0.558,0.168,0.474,1]
                    brown = [0.191,0.089,0.053,1]

                    driving_path = active_car.driving_path

                    match color:
                        case 'COLOR_01': 
                            color_rgb = red
                        
                        case 'COLOR_02': 
                            color_rgb = orange

                        case 'COLOR_03': 
                            color_rgb = yellow

                        case 'COLOR_04': 
                            color_rgb = green

                        case 'COLOR_05': 
                            color_rgb = blue

                        case 'COLOR_06': 
                            color_rgb = purple

                        case 'COLOR_07': 
                            color_rgb = pink

                        case 'COLOR_08': 
                            color_rgb = brown

                        case _:
                            color_rgb = white
                    
                    mat_name = (f"driving_path_{active_car.rig_collection.name}")
                    mat = bpy.data.materials.get(mat_name)

                    if mat is None:
                        mat = bpy.data.materials.new(name=mat_name)

                    if driving_path.data.materials:
                        driving_path.data.materials[0] = mat
                    else:
                        driving_path.data.materials.append(mat)

                    driving_path.material_slots[0].material.diffuse_color = color_rgb
                    driving_path.display_type = 'TEXTURED'
            
        except LCException as e:
            e.show_error_message()

            # Try to collapse all outliner collections
            self.collapse_imported_collections(context)

            return {"CANCELLED"}
    
        
        # Deselect all
        bpy.ops.object.select_all(action="DESELECT")
        
        # Try to collapse all outliner collections
        self.collapse_imported_collections(context)

        # Create undo point
        bpy.ops.ed.undo_push()

        return {"FINISHED"}


class OBJECT_OT_delete_rig(bpy.types.Operator):
    bl_label = "Unrig Vehicle"
    bl_idname = "object.delete_rig"
    bl_description = "Remove the Launch Control rig from the Vehicle"

    do_pop_up: bpy.props.BoolProperty(name="do_pop_up", default=True)
    


    def execute(self, context):

        # Create undo point
        bpy.ops.ed.undo_push()

        if self.do_pop_up:
            bpy.ops.wm.delete_rig_dialog('INVOKE_DEFAULT')
        else:
            unrig_vehicle(no_delete_path = False, no_delete_ground = False, no_delete_car = True, no_delete_proxy = False, revert_transforms = True)


        # Create undo point
        bpy.ops.ed.undo_push()
        return {"FINISHED"}



def unrig_vehicle(no_delete_path, no_delete_ground, no_delete_car, no_delete_proxy, revert_transforms):
    scene = bpy.context.scene
    active_car = scene.lc.find_selected()

    settings = scene.settings
    ground_collection = bpy.data.collections.get("GroundDetection")
    lc_collection = get_collection_by_name(COLLECTIONNAME_ADDON, scene.collection)

    if settings.show_setup_rig:
        log_error(
            "Rig Setup Mode is on!", "unrig", {"car": active_car.collection}
        )
        show_message_box(title="Unable to unrig car", message="Please switch to 'Race Mode' before unrigging. (Manual Gearbox -> Race Mode)", icon="ERROR")
        return {"CANCELLED"}
    
    
    missing_objects = False
    if not active_car.properties.has_lib_override:
        if scene.objects.get(f"car_rig_{scene.car_collection.name}"):   #TODO: Why not just reference the LC data instead of searching for the name??!
            missing_objects = False
        else:
            log_error(
                "Cannot find rig object!", "unrig", {"car": active_car.collection}
            )
            show_message_box(title="Locating Rig Armature", message="Could not find the Rig Armature for selected vehicle - The rig might have been altered. Will try to remove LC Data anyway. Expect left over objects and collections!", icon="INFO")
            bpy.ops.object.unrig_confirm()   #does not work :'(
            missing_objects = True

    try:
        # active_car.unrig()
        car_parts = [active_car.body.body] + active_car.wheels.to_list()
        if not active_car.brakes.ignore():
            car_parts += active_car.brakes.to_list()

        # remove the parents of those objects  (Keep parents to reset back to scene center)
        for part in car_parts:
            clear_parent_keep_transform(part)
        
        if revert_transforms:
            # restore all body parts to initial position
            # real body object location   = initial location 
            active_car.body.body.location = active_car.body.position.location
            active_car.body.body.rotation_euler = active_car.body.position.rotation
            active_car.body.body.scale = active_car.body.position.scale

            active_car.wheels.wheel_RL.location = active_car.wheels.position_wheel_RL.location
            active_car.wheels.wheel_RL.rotation_euler = active_car.wheels.position_wheel_RL.rotation
            active_car.wheels.wheel_RL.scale = active_car.wheels.position_wheel_RL.scale
            active_car.wheels.wheel_RR.location = active_car.wheels.position_wheel_RR.location
            active_car.wheels.wheel_RR.rotation_euler = active_car.wheels.position_wheel_RR.rotation
            active_car.wheels.wheel_RR.scale = active_car.wheels.position_wheel_RR.scale
            active_car.wheels.wheel_FR.location = active_car.wheels.position_wheel_FR.location
            active_car.wheels.wheel_FR.rotation_euler = active_car.wheels.position_wheel_FR.rotation
            active_car.wheels.wheel_FR.scale = active_car.wheels.position_wheel_FR.scale
            active_car.wheels.wheel_FL.location = active_car.wheels.position_wheel_FL.location
            active_car.wheels.wheel_FL.rotation_euler = active_car.wheels.position_wheel_FL.rotation
            active_car.wheels.wheel_FL.scale = active_car.wheels.position_wheel_FL.scale


            # try brakes
            try: 
                active_car.brakes.brake_RL.location = active_car.brakes.position_brake_RL.location
                active_car.brakes.brake_RL.rotation_euler = active_car.brakes.position_brake_RL.rotation
                active_car.brakes.brake_RL.scale = active_car.brakes.position_brake_RL.scale
                active_car.brakes.brake_RR.location = active_car.brakes.position_brake_RR.location
                active_car.brakes.brake_RR.rotation_euler = active_car.brakes.position_brake_RR.rotation
                active_car.brakes.brake_RR.scale = active_car.brakes.position_brake_RR.scale
                active_car.brakes.brake_FR.location = active_car.brakes.position_brake_FR.location
                active_car.brakes.brake_FR.rotation_euler = active_car.brakes.position_brake_FR.rotation
                active_car.brakes.brake_FR.scale = active_car.brakes.position_brake_FR.scale
                active_car.brakes.brake_FL.location = active_car.brakes.position_brake_FL.location
                active_car.brakes.brake_FL.rotation_euler = active_car.brakes.position_brake_FL.rotation
                active_car.brakes.brake_FL.scale = active_car.brakes.position_brake_FL.scale
            except:
                pass

            # try wheelcovers
            try: 
                active_car.wheelcovers.wheelcover_FR.location = active_car.wheelcovers.position_wheelcover_FR.location
                active_car.wheelcovers.wheelcover_FR.rotation_euler = active_car.wheelcovers.position_wheelcover_FR.rotation
                active_car.wheelcovers.wheelcover_FR.scale = active_car.wheelcovers.position_wheelcover_FR.scale
                active_car.wheelcovers.wheelcover_FL.location = active_car.wheelcovers.position_wheelcover_FL.location
                active_car.wheelcovers.wheelcover_FL.rotation_euler = active_car.wheelcovers.position_wheelcover_FL.rotation
                active_car.wheelcovers.wheelcover_FL.scale = active_car.wheelcovers.position_wheelcover_FL.scale
            except:
                pass
        
        # Save Ground Colliders
        if len(scene.lc.cars) == 1 and no_delete_ground:
            for ground in ground_collection.objects:
                if scene.collection not in ground.users_collection:
                    scene.collection.objects.link(ground)


        # Save Vehicle Model
        if not no_delete_car or active_car.properties.has_lib_override:
            for obj in active_car.collection.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
                
            bpy.data.collections.remove(active_car.collection)

        # Save Proxy Vehicle Model
        coll_name = active_car.name + " Proxy"
        proxy_coll_exists = False
        for coll in scene.collection.children_recursive:
            if coll.name == coll_name:
                proxy_coll_exists = True
                proxy_coll = coll

        if proxy_coll_exists:
            if no_delete_proxy:
                scene.collection.children.link(proxy_coll)
                lc_collection.children.unlink(proxy_coll)

                if revert_transforms:
                    # restore all body parts to initial position
                    # real body object location   = initial location 
                    active_car.body.body.location = active_car.body.position.location
                    active_car.body.body.rotation_euler = active_car.body.position.rotation
                    active_car.body.body.scale = active_car.body.position.scale

                    active_car.wheels.wheel_RL.location = active_car.wheels.position_wheel_RL.location
                    active_car.wheels.wheel_RL.rotation_euler = active_car.wheels.position_wheel_RL.rotation
                    active_car.wheels.wheel_RL.scale = active_car.wheels.position_wheel_RL.scale
                    active_car.wheels.wheel_RR.location = active_car.wheels.position_wheel_RR.location
                    active_car.wheels.wheel_RR.rotation_euler = active_car.wheels.position_wheel_RR.rotation
                    active_car.wheels.wheel_RR.scale = active_car.wheels.position_wheel_RR.scale
                    active_car.wheels.wheel_FR.location = active_car.wheels.position_wheel_FR.location
                    active_car.wheels.wheel_FR.rotation_euler = active_car.wheels.position_wheel_FR.rotation
                    active_car.wheels.wheel_FR.scale = active_car.wheels.position_wheel_FR.scale
                    active_car.wheels.wheel_FL.location = active_car.wheels.position_wheel_FL.location
                    active_car.wheels.wheel_FL.rotation_euler = active_car.wheels.position_wheel_FL.rotation
                    active_car.wheels.wheel_FL.scale = active_car.wheels.position_wheel_FL.scale


                    # try brakes
                    try: 
                        active_car.brakes.brake_RL.location = active_car.brakes.position_brake_RL.location
                        active_car.brakes.brake_RL.rotation_euler = active_car.brakes.position_brake_RL.rotation
                        active_car.brakes.brake_RL.scale = active_car.brakes.position_brake_RL.scale
                        active_car.brakes.brake_RR.location = active_car.brakes.position_brake_RR.location
                        active_car.brakes.brake_RR.rotation_euler = active_car.brakes.position_brake_RR.rotation
                        active_car.brakes.brake_RR.scale = active_car.brakes.position_brake_RR.scale
                        active_car.brakes.brake_FR.location = active_car.brakes.position_brake_FR.location
                        active_car.brakes.brake_FR.rotation_euler = active_car.brakes.position_brake_FR.rotation
                        active_car.brakes.brake_FR.scale = active_car.brakes.position_brake_FR.scale
                        active_car.brakes.brake_FL.location = active_car.brakes.position_brake_FL.location
                        active_car.brakes.brake_FL.rotation_euler = active_car.brakes.position_brake_FL.rotation
                        active_car.brakes.brake_FL.scale = active_car.brakes.position_brake_FL.scale
                    except:
                        pass

                    # try wheelcovers
                    try: 
                        active_car.wheelcovers.wheelcover_FR.location = active_car.wheelcovers.position_wheelcover_FR.location
                        active_car.wheelcovers.wheelcover_FR.rotation_euler = active_car.wheelcovers.position_wheelcover_FR.rotation
                        active_car.wheelcovers.wheelcover_FR.scale = active_car.wheelcovers.position_wheelcover_FR.scale
                        active_car.wheelcovers.wheelcover_FL.location = active_car.wheelcovers.position_wheelcover_FL.location
                        active_car.wheelcovers.wheelcover_FL.rotation_euler = active_car.wheelcovers.position_wheelcover_FL.rotation
                        active_car.wheelcovers.wheelcover_FL.scale = active_car.wheelcovers.position_wheelcover_FL.scale
                    except:
                        pass
                
        

        # remove ground detection meshes
        if len(scene.lc.cars) == 1 and not missing_objects:
            for ground in ground_collection.objects:
                if any(x in ground.name for x in DEFAULT_GROUNDS):
                    log_debug("Default ground mesh found - will Delete", "OBJECT_OT_delete_rig",)
                else:
                    log_debug("Custom ground mesh found - will back up", "OBJECT_OT_delete_rig",)
                    if scene.collection not in ground.users_collection:
                        scene.collection.objects.link(ground)
                    ground_collection.objects.unlink(ground)


        # Save Driving Path if user selected this
        if no_delete_path:
            scene.collection.objects.link(active_car.driving_path)

        # remove the objects inside the car rig collection & clean orphans
        if active_car.rig_collection and not missing_objects:
            bpy.data.collections.remove(active_car.rig_collection)

        active_car.is_rigged = False  # not really necesary
        scene.lc.remove(active_car)

        if len(scene.lc.cars) == 0:
            bpy.data.collections.remove(lc_collection)

            scene.settings.show_rigged_coll_only = False
        
        clear_orphans()

    except LCException as e:
        log_error(
            "Unable to unrig the car", "unrig", {"car": active_car.collection}
        )
        show_message_box(title="Unable to unrig car", message=e, icon="ERROR")