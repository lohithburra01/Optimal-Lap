import bpy

from ..utils.resources import get_resource_path, upload_asset, upload_multi_asset
from ..utils.functions import get_collection_by_name, unlink_collection_all, link_collection, clear_orphans, get_driver_indices_by_expression, get_addon_version
from ..utils.validations import validate_collection_name_availability

from ..ui.utils import show_message_box
from ..logger import log_error, log_debug, log_info

from ..globals import *


appendable_cars = []

def append_lc_car_callback(scene, context):

    items = []

    for car_name in appendable_cars:

        items.append((car_name, car_name, ""))

    return items


class OBJECT_OT_append_search_select_file(bpy.types.Operator):
    bl_label = "Search in file"
    bl_idname = "object.append_select_file"
    bl_description = "Have a LC rigged Vehicle in another file? Locate the file and search for Rigged LC vehicles in it"

    """filepath : bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob : bpy.props.StringProperty(default="*.blend", options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}"""
    

    def search_for_lc_cars(self, filepath):

        # go to "Collection" and add colls with "CarRig_xxx" in name

        lc_car_names = []
        names = []
        CarRig_colls = []

        with bpy.data.libraries.load(filepath) as (data_from, data_to):
            names = [name for name in data_from.collections]

        for name in names:
            if "CarRig_" in name:
                CarRig_colls.append(name)

        # find vehicle mesh coll
        for CarRig_coll in CarRig_colls:
            clean_name = str(CarRig_coll).replace("['", "")
            clean_name_02 = clean_name.replace("']", "")
            clean_name_03 = clean_name_02.replace("CarRig_", "")
            
            for name in names:
                if clean_name_03 == name.lower():
                    lc_car_names.append(name)
                    print("name to append to list", name)

        bpy.context.scene.settings.append_file_path = filepath
        bpy.context.scene.settings.append_path = filepath

        return lc_car_names
    


    def execute(self, context):
        scene = bpy.context.scene
        input_filepath = scene.settings.append_path

        filepath = bpy.path.abspath(input_filepath)
        

        global appendable_cars
        appendable_cars.clear()
        
        if (not filepath.endswith(".blend")):
            
            if filepath == "":
                text = "Please locate a .blend file in the field above"
            else:
                text = "The selected file is not a .blend file"

            show_message_box(title="Unable to use file", message=text, icon="ERROR")
            log_error(text, "OBJECT_OT_append_search_select_file")

            return {'CANCELLED'}   

        lc_cars_in_file = ( self.search_for_lc_cars(filepath) )

        for car in lc_cars_in_file:
            appendable_cars.append(car)

        log_info(f"Found Collections {appendable_cars}", "OBJECT_OT_append_search_select_file")

        text = (f"Found {len(appendable_cars)} Rigged LC Vehicles in the file")

        show_message_box(title="Vehicles ready for append", message=text, icon="INFO")
        log_info(text, "OBJECT_OT_append_search_select_file")

        return {'FINISHED'}   
    

class OBJECT_OT_append_from_file(bpy.types.Operator):
    bl_label = "Append from file"
    bl_idname = "object.append_from_file"
    bl_description = "Ready when you are!"

    def execute(self, context):
        scene = bpy.context.scene

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


        # Setup file reference to addons folder
        file_path = scene.settings.append_file_path

        collection_name = scene.settings.append_lc_car_names
        collection_name_lower = collection_name.lower()
        collection_rig_name = COLLECTIONNAME_CARRIG + "_" + collection_name_lower

        files = []
        list_scenes = []

        for scene in bpy.data.scenes:
            list_scenes.append(scene)

        try:
            with bpy.data.libraries.load(file_path, link=False) as (data_from, data_to):
                for coll_name in data_from.collections:
                    if collection_name_lower in coll_name.lower():
                        files.append({'name': coll_name})

        except:
                text = "Could not access File. Make sure a .blend file is selected above and 'Search' again."
                log_error(text, "OBJECT_OT_rig_car")
                show_message_box(title="Unable to Append Vehicle", message=text, icon="ERROR")
                return {"CANCELLED"}

        print("files", files)

        bpy.ops.ed.undo_push()

        if len(files) >= 5:
            upload_multi_asset(file_path, "Collection", files)
        else:
            text = "The LC data structure in the incoming file is not correct. Please re-rig the vehicle in the incoming file"

            show_message_box(title="Unable to append", message=text, icon="ERROR")
            log_error(text, "OBJECT_OT_append_from_file")

            return {'CANCELLED'}

        """try: 
            sel_obj = context.selected_objects[0]
            obj_collections = sel_obj.users_collection[0]
            collection_vehicle = obj_collections
                    
        except:
            text = "Could not find correct preset collection, will default to name of pre-import collection"
            log_info(text, "OBJECT_OT_append_from_file")"""
        
        target_scene = scene
        source_scene = None
        for scene in bpy.data.scenes:
            if scene not in list_scenes:
                source_scene = scene


        if source_scene is None:
            text = f"Failed to Load Data. Append cancelled."

            show_message_box(title="Rig Append Failed", message=text, icon="ERROR")
            log_error(text, "OBJECT_OT_append_from_file")

            bpy.ops.ed.undo_push()
            bpy.ops.ed.undo()

            return {'CANCELLED'}
        

        for car in source_scene.lc.cars:
            if car.collection.name == collection_name:
                source_car = car


        if source_car is None:
            text = f"Failed to Load Data. Append cancelled."

            show_message_box(title="Rig Append Failed", message=text, icon="ERROR")
            log_error(text, "OBJECT_OT_append_from_file")

            bpy.ops.ed.undo_push()
            bpy.ops.ed.undo()

            return {'CANCELLED'}

        addon_version = get_addon_version()
        source_version = source_car.properties.lc_version

        if addon_version != source_version:
            if target_scene.settings.append_version_control:

                text = f"Incoming file is rigged in LC {source_version}. Installed add-on version is {addon_version}. Append cancelled."

                show_message_box(title="Rig Version Mismatch", message=text, icon="ERROR")
                log_error(text, "OBJECT_OT_append_from_file")

                bpy.ops.ed.undo_push()
                bpy.ops.ed.undo()

                return {'CANCELLED'}

            else:
                text = f"Version mismatch. Please check for compatability issues or Update the Vehicle Rig before proceeding"

                show_message_box(title="Version Control Bypassed", message=text, icon="INFO")
                log_error(text, "OBJECT_OT_append_from_file")

            

        # Define collections
        collection_vehicle = source_car.collection
        collection_rig = source_car.rig_collection
        target_scene.car_collection = collection_vehicle

            
        ### SUCCESFUL APPEND. Now to the setup ###

        try:
            active_car = target_scene.lc.add(collection_vehicle, collection_vehicle.name)

            ### link vehicle data to appended assets ###

            driving_path = target_scene.objects[FILENAME_DRIVINGPATH + "_" + collection_name]
            rig_object = target_scene.objects[FILENAME_CAR_RIG + "_" + collection_name]
            rig_armature = bpy.data.armatures[FILENAME_CARRIG_ARMATURE + "_" + collection_name]
            geo_nodes_skidmarks = bpy.data.node_groups[GEONODE_SKIDMARK + "_" + collection_name]  # a global group
            geo_nodes_sim_body = bpy.data.node_groups[PHYSICS_BODY + "_" + collection_name]
            geo_nodes_sim_wheels = bpy.data.node_groups[PHYSICS_WHEELS + "_" + collection_name]
            sim_body = target_scene.objects[FILENAME_SIM_BODY + "_" + collection_name]
            sim_wheels = target_scene.objects[FILENAME_SIM_WHEELS + "_" + collection_name]
            sim_track_to = target_scene.objects[FILENAME_SIM_TRACK_TO + "_" + collection_name]
            sim_acc_viz = target_scene.objects[FILENAME_SIM_ACC_VIZ + "_" + collection_name]
            sim_vel_viz = target_scene.objects[FILENAME_SIM_VEL_VIZ + "_" + collection_name]
            speed_calculator = target_scene.objects[FILENAME_SPEED_CALCULATOR + "_" + collection_name]
            skidmark_material = bpy.data.materials[M_SKIDMARK_MATERIAL + "_" + collection_name]
            skidmark_collection = get_collection_by_name(
                COLLECTIONNAME_SKIDMARK, target_scene.collection
            )
            ground_local_object = target_scene.objects[FILENAME_GROUND_LOCAL + "_" + collection_name]
            rig_collection = collection_rig

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


            # setup data properties
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
            active_car.properties.lc_version = "0.0.0"

            # append lc data from source car
            if source_car is not None:
                active_car.properties.lc_version = source_car.properties.lc_version

                # rig parts
                active_car.body.body = source_car.body.body

                active_car.wheels.wheel_RL = source_car.wheels.wheel_RL
                active_car.wheels.wheel_RR = source_car.wheels.wheel_RR
                active_car.wheels.wheel_FR = source_car.wheels.wheel_FR
                active_car.wheels.wheel_FL = source_car.wheels.wheel_FL

                # positions
                active_car.body.position.location = source_car.body.position.location
                active_car.body.position.rotation = source_car.body.position.rotation
                active_car.body.position.scale = source_car.body.position.scale

                active_car.wheels.position_wheel_RL.location = source_car.wheels.position_wheel_RL.location
                active_car.wheels.position_wheel_RL.rotation = source_car.wheels.position_wheel_RL.rotation
                active_car.wheels.position_wheel_RL.scale = source_car.wheels.position_wheel_RL.scale
                active_car.wheels.position_wheel_RR.location = source_car.wheels.position_wheel_RR.location
                active_car.wheels.position_wheel_RR.rotation = source_car.wheels.position_wheel_RR.rotation
                active_car.wheels.position_wheel_RR.scale = source_car.wheels.position_wheel_RR.scale
                active_car.wheels.position_wheel_FR.location = source_car.wheels.position_wheel_FR.location
                active_car.wheels.position_wheel_FR.rotation = source_car.wheels.position_wheel_FR.rotation
                active_car.wheels.position_wheel_FR.scale = source_car.wheels.position_wheel_FR.scale
                active_car.wheels.position_wheel_FL.location = source_car.wheels.position_wheel_FL.location
                active_car.wheels.position_wheel_FL.rotation = source_car.wheels.position_wheel_FL.rotation
                active_car.wheels.position_wheel_FL.scale = source_car.wheels.position_wheel_FL.scale


                if active_car.brakes:
                    active_car.brakes.brake_RL = source_car.brakes.brake_RL
                    active_car.brakes.brake_RR = source_car.brakes.brake_RR
                    active_car.brakes.brake_FR = source_car.brakes.brake_FR
                    active_car.brakes.brake_FL = source_car.brakes.brake_FL

                    active_car.brakes.position_brake_RL.location = source_car.brakes.position_brake_RL.location
                    active_car.brakes.position_brake_RL.rotation = source_car.brakes.position_brake_RL.rotation
                    active_car.brakes.position_brake_RL.scale = source_car.brakes.position_brake_RL.scale
                    active_car.brakes.position_brake_RR.location = source_car.brakes.position_brake_RR.location
                    active_car.brakes.position_brake_RR.rotation = source_car.brakes.position_brake_RR.rotation
                    active_car.brakes.position_brake_RR.scale = source_car.brakes.position_brake_RR.scale
                    active_car.brakes.position_brake_FR.location = source_car.brakes.position_brake_FR.location
                    active_car.brakes.position_brake_FR.rotation = source_car.brakes.position_brake_FR.rotation
                    active_car.brakes.position_brake_FR.scale = source_car.brakes.position_brake_FR.scale
                    active_car.brakes.position_brake_FL.location = source_car.brakes.position_brake_FL.location
                    active_car.brakes.position_brake_FL.rotation = source_car.brakes.position_brake_FL.rotation
                    active_car.brakes.position_brake_FL.scale = source_car.brakes.position_brake_FL.scale

                if active_car.wheelcovers:
                    active_car.wheelcovers.wheelcover_FR = source_car.wheelcovers.wheelcover_FR
                    active_car.wheelcovers.wheelcover_FL = source_car.wheelcovers.wheelcover_FL

                    active_car.wheelcovers.position_wheelcover_FR.location = source_car.wheelcovers.position_wheelcover_FR.location
                    active_car.wheelcovers.position_wheelcover_FR.rotation = source_car.wheelcovers.position_wheelcover_FR.rotation
                    active_car.wheelcovers.position_wheelcover_FR.scale = source_car.wheelcovers.position_wheelcover_FR.scale
                    active_car.wheelcovers.position_wheelcover_FL.location = source_car.wheelcovers.position_wheelcover_FL.location
                    active_car.wheelcovers.position_wheelcover_FL.rotation = source_car.wheelcovers.position_wheelcover_FL.rotation
                    active_car.wheelcovers.position_wheelcover_FL.scale = source_car.wheelcovers.position_wheelcover_FL.scale


                if active_car.headlights:
                    active_car.headlights.headlight_R = source_car.headlights.headlight_R
                    active_car.headlights.headlight_L = source_car.headlights.headlight_L

            else:
                text = "Could not retrieve all lc data from incoming file. Some features might be unavailable."

                show_message_box(title="Missing LC data", message=text, icon="INFO")
                log_error(text, "OBJECT_OT_append_from_file")


            # add 'driving path' properties
            active_car.driving_path = driving_path

            active_car.driving_path.modifiers["Shrinkwrap"].target = target_scene.objects[FILENAME_GROUND_GLOBAL]

            # add reference to objects
            active_car.ground_local_object.modifiers[GROUND_DETECT_WRAP_UP].target = target_scene.objects[FILENAME_GROUND_GLOBAL]
            active_car.ground_local_object.modifiers[GROUND_DETECT_WRAP_DOWN].target = target_scene.objects[FILENAME_GROUND_GLOBAL]

            ### Setting up skidmarks
            geo_nodes_skidmarks.animation_data.drivers[0].driver.variables[0].targets[0].id = target_scene  
            geo_nodes_skidmarks.animation_data.drivers[0].driver.variables[0].targets[0].id = target_scene  

            ### Physics
            geo_nodes_sim_body.animation_data.drivers[0].driver.variables[0].targets[0].id = target_scene
            geo_nodes_sim_wheels.animation_data.drivers[0].driver.variables[0].targets[0].id = target_scene

            # set up physics sliders
            vehicle_name = collection_vehicle.name 
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

            text = "Vehicle was succesfully appended"

            show_message_box(title="Append from file", message=text, icon="INFO")
            log_info(text, "OBJECT_OT_append_from_file")

            try:  # removing weird extra scene from import...
                bpy.data.scenes.remove(source_scene)
                clear_orphans()
            except:
                pass

            return {'FINISHED'}   
        
        except:

            text = f"Successfully appended, but LC elements were missing in the data. Please rerig vehicle in the Asset file you are appending from."

            show_message_box(title="Missing LC Data", message=text, icon="ERROR")
            log_error(text, "OBJECT_OT_append_from_file")

            bpy.ops.ed.undo_push()
            bpy.ops.ed.undo()

            return {'CANCELLED'}

