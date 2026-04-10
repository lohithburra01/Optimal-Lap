import bpy
import os

from .. import data
from ..data import commands
from ..ui.utils import show_message_box

from ..utils.functions import find_driver_index, force_update_geo_nodes, get_collection_by_name, enum_members_from_instance
from ..utils.resources import prepare_cache_skidmarks, prepare_cache_physics, validate_cache, unzip_in_location, get_resource_path
from ..utils.validations import validate_lc_object

from ..utils.errors.exceptions import RigCollectionNotFound
from ..logger import log_info, log_debug, log_error

from ..globals import *


class OBJECT_OT_fix_spin(bpy.types.Operator):
    bl_label = "Fix broken Wheel Spin"
    bl_idname = "object.fix_spin"
    bl_description = "Fix all non-spinnig wheels"

    def execute(self, context):
        scene = context.scene

        car = scene.lc.find_selected()
        driving_path = car.driving_path
        rig_object = car.rig_object

        target_data_paths = [
            'pose.bones["bone_wheel_spin.FR"].rotation_euler',
            'pose.bones["bone_wheel_spin.FL"].rotation_euler',
            'pose.bones["bone_wheel_spin.RR"].rotation_euler',
            'pose.bones["bone_wheel_spin.RL"].rotation_euler',
        ]

        # find index of the driver
        target_driver_indexes = []
        drivers = rig_object.animation_data.drivers

        for target_data_path in target_data_paths:
            index = find_driver_index(drivers, target_data_path)
            target_driver_indexes.append(index)

        for index in target_driver_indexes:
            rig_object.animation_data.drivers[index].driver.variables[1].targets[
                0
            ].id = driving_path

        return {"FINISHED"}


class OBJECT_OT_remove_tire_deform(bpy.types.Operator):
    bl_label = "Disable Auto Deform"
    bl_idname = "object.remove_tire_deform"
    bl_description = "Disable automatic deformation of tires - Will improve performance in the viewport"

    def execute(self, context):
        scene = context.scene
        car = scene.lc.find_selected()

        # Check if Car rig exists
        try:
            car.get_rig_collection()
            wheels = car.wheels.to_list()

            # Remove modifiers
            for i in range(4):
                for modifier in wheels[i].modifiers:
                    if modifier.type == "LATTICE":
                        wheels[i].modifiers.remove(modifier)
            return {"FINISHED"}
        
        except RigCollectionNotFound as e:
            e.show_error_message()
            return {"CANCELLED"}


class OBJECT_OT_setup_tire_deform(bpy.types.Operator):
    bl_label = "Enable Auto Deform"
    bl_idname = "object.setup_tire_deform"
    bl_description = "WARNING: Slows down viewport performance significantly! Automatic deformation of tires for when pressure is applied to them either by simulated data, by the weight of the car or by manual body animation"

    def _setup_driver(
        self,
        targetObj,
        targetDriverField,
        targetDriverFieldStr,
        driverFieldName,
        expression,
        *argv,
    ):
        # Base setup
        targetDriverField.driver_add(driverFieldName)

        # Find driver ID created:
        target_data_path = targetDriverFieldStr + "." + driverFieldName
        index = find_driver_index(targetObj.animation_data.drivers, target_data_path)

        if index != -1:
            targetDriver = targetObj.animation_data.drivers[index].driver
            targetDriver.expression = expression

            # First remove all variables
            for var in targetDriver.variables:
                targetDriver.variables.remove(var)

            # Variables
            for i, var in enumerate(argv):
                targetDriver.variables.new()
                targetDriver.variables[i].name = var[0]
                targetDriver.variables[i].type = var[1]
                targetDriver.variables[i].targets[0].id = var[2]
                try:
                    targetDriver.variables[i].targets[0].bone_target = var[3]
                except:
                    pass
                targetDriver.variables[i].targets[0].transform_type = var[4]
                targetDriver.variables[i].targets[0].transform_space = var[5]
        else:
            log_info("Could not add driver to tire deformation.", "Delete Rig")

    def execute(self, context):
        scene = context.scene
        car = scene.lc.find_selected()

        try: 
            car.get_rig_collection()
            rig_object = car.rig_object
            wheels = car.wheels.to_list()

            # Find lattices? UPDATE
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except:
                pass

            bpy.ops.object.select_all(action="DESELECT")
            rig_object.select_set(True)
            bpy.context.view_layer.objects.active = rig_object

            bpy.ops.object.select_all(action="DESELECT")
            try:
                bpy.data.lattices["LaunchLattice_OFF"].name = "LaunchLattice_ON"
            except:
                pass

            cursor = bpy.context.scene.cursor
            savedCursorPos = cursor.location.copy()

            lattices = [
                bpy.context.scene.objects[FILENAME_LATTICE_RR],
                bpy.context.scene.objects[FILENAME_LATTICE_RL],
                bpy.context.scene.objects[FILENAME_LATTICE_FR],
                bpy.context.scene.objects[FILENAME_LATTICE_FL],
            ]

            # Setup modifiers on tire meshes
            i = 0
            while i < 4:
                if i == 1 or i == 3:
                    offsetDir = 1
                else:
                    offsetDir = -1

                bpy.ops.object.select_all(action="DESELECT")
                wheels[i].select_set(True)
                bpy.context.view_layer.objects.active = wheels[i]

                for modifier in wheels[i].modifiers:
                    if modifier.type == "LATTICE":
                        wheels[i].modifiers.remove(modifier)

                bpy.ops.object.modifier_add(type="LATTICE")
                wheels[i].modifiers["Lattice"].object = lattices[i]
                driverField = wheels[i].modifiers["Lattice"].strength

                i = i + 1

            # ADD DRIVER FOR TIRES
            inputVar01 = [
                "wheelCenter",
                "TRANSFORMS",
                rig_object,
                "wheel_camber.FL",
                "LOC_Z",
                "WORLD_SPACE",
            ]
            inputVar02 = [
                "floor",
                "TRANSFORMS",
                rig_object,
                "groundDetectAbs.FL",
                "LOC_Z",
                "WORLD_SPACE",
            ]
            inputVar03 = [
                "wheelHeight",
                "TRANSFORMS",
                rig_object,
                "setup_wheelRadiusHandle_F",
                "LOC_Z",
                "WORLD_SPACE",
            ]
            inputVar04 = [
                "rigBaseZ",
                "TRANSFORMS",
                rig_object,
                "",
                "LOC_Z",
                "WORLD_SPACE",
            ]
            inputVar05 = [
                "userFactor",
                "TRANSFORMS",
                rig_object,
                "Slider_TireDeformFactor",
                "LOC_Y",
                "TRANSFORM_SPACE",
            ]
            expression = "(min(max(    -(wheelCenter-floor    - (wheelHeight-rigBaseZ))*19-.15   , 0), 1.5))* userFactor"

            order = wheels.get_order()
            for i, wheel in enumerate(wheels):
                targetDriverField = wheel.modifiers["Lattice"]
                targetDriverFieldStr = 'modifiers["Lattice"]'
                driverFieldName = "strength"

                inputVar01[3] = "wheel_camber." + order[i]
                inputVar02[3] = "groundDetectAbs." + order[i]
                inputVar03[3] = (
                    "setup_wheelRadiusHandle_" + order[i][0]
                )  # take only first letter

                self._setup_driver(
                    wheel,
                    targetDriverField,
                    targetDriverFieldStr,
                    driverFieldName,
                    expression,
                    inputVar01,
                    inputVar02,
                    inputVar03,
                    inputVar04,
                    inputVar05,
                )

                inputVar_view = [
                    "switch",
                    "TRANSFORMS",
                    rig_object,
                    "Slider_TireDeformFactor",
                    "LOC_Y",
                    "TRANSFORM_SPACE",
                ]
                expression_view = "1 if switch>0.01 else 0"
                driverFieldName_view = "show_viewport"
                self._setup_driver(
                    wheel,
                    targetDriverField,
                    targetDriverFieldStr,
                    driverFieldName_view,
                    expression_view,
                    inputVar_view,
                )

                driverFieldName_render = "show_render"
                self._setup_driver(
                    wheel,
                    targetDriverField,
                    targetDriverFieldStr,
                    driverFieldName_render,
                    expression_view,
                    inputVar_view,
                )

            cursor.location = savedCursorPos
            # Turn on tire Deformation
            rig_object.pose.bones[B_SLIDER_TIRE_DEFORM_FACTOR].location[1] = 1
            return {"FINISHED"}

        except RigCollectionNotFound as e:
            e.show_error_message()
            return {"CANCELLED"}


# THIS ONE NEEDS TO BE CHECKED. UPDATE
class OBJECT_OT_reset_props(bpy.types.Operator):
    bl_label = "Reset all!"
    bl_idname = "object.reset_props"
    bl_description = "Kill the engine and start all over from scratch. Reset all vehicle specific settings to default. Animations are not removed, but all handles are reset."

    def execute(self, context):
        scene = context.scene
        active_car = scene.lc.find_selected()

        # Create undo point
        bpy.ops.ed.undo_push()

        # Car properties:
        car_settings = (
            "show_custom_physics",
            "show_acc_viz",
            "show_vel_viz",
            "export_path",
            "apply_transforms",
            "include_ground",
            "link_beams",
            "low_beam_visibility",
            "high_beam_visibility",
            "ui_view_elements",
            "limit_sliders",
            "show_ground_grid",
            "grid_resolution",
            "show_jump_help",
            "jump_speed",
            "use_rest_pos",
            "enable_skidmarks",
            "speedometer",
            "show_camera_hooks",
            "snap_path",
            "use_true_ground",
            "legacy_ground_detection",
        )

        car_props = (
            "physics_tightness",
            "physics_dampening",
            "physics_softness",
            "physics_multiplier",
            "use_gravity",
            "shake_frequency",
            "low_beam_temperature",
            "low_beam_intensity",
            "low_beam_spread",
            "low_beam_sharpness",
            "high_beam_temperature",
            "high_beam_intensity",
            "high_beam_spread",
            "high_beam_sharpness",
            "overdrive_pitch",
            "overdrive_yaw",
            "overdrive_roll",
            "overdrive_location",
            "overdrive_wheel_location",
            "overdrive_wheel_pressure",
            "skidmarks_mul",
            "skidmarks_var",
        )

        scene_props = (
            "rig_help",
            "export_all_cars",
            #"show_setup_rig",
            "export_anim_only",
            "include_anim",
            "subframes",
        )

        multi_edit = scene.settings.edit_all_mode
        cars = []
        
        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)
        
        
        for prop in scene_props:
            try:
                scene.settings.property_unset(prop)
            except:
                pass

        for active_car in cars:
            for prop in car_props:
                try:
                    active_car.properties.property_unset(prop)
                except:
                    pass

            for prop in car_settings:
                try:
                    active_car.settings.property_unset(prop)
                except:
                    pass

        # Update UI stuffs!
        commands.reveal_speedometer(self, context)
        commands.update_headlight(self, context)
        commands.update_ui_view_elements(self, context)
        commands.reset_handles(self, context)
        #commands.reveal_setup_controls(self, context)
        commands.reveal_acc_viz(self, context)
        commands.reveal_vel_viz(self, context)
        commands.lock_sliders(self, context)
        commands.update_beam_connected(self, context)
        commands.update_beam(self, context)
        commands.update_ground(self, context)
        commands.toggle_ground_grid(self, context)
        commands.reveal_camera_hooks(self, context)
        commands.update_path_snap(self, context)
        commands.update_true_ground(self, context)

        return {"FINISHED"}

class OBJECT_OT_reset_postfx(bpy.types.Operator):
    bl_label = "Reset PostFX"
    bl_idname = "object.reset_postfx"
    bl_description = "Set all the PostFX overdrive sliders back to their default values"

    def execute(self, context):
        scene = context.scene
        active_car = scene.lc.find_selected()

        # Create undo point
        bpy.ops.ed.undo_push()
        car_props = (
            "overdrive_pitch",
            "overdrive_yaw",
            "overdrive_roll",
            "overdrive_location",
            "overdrive_wheel_location",
            "overdrive_wheel_pressure",
        )

        multi_edit = scene.settings.edit_all_mode
        cars = []
        
        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for active_car in cars:
            for prop in car_props:
                active_car.properties.property_unset(prop)

        return {"FINISHED"}

class OBJECT_OT_rename_object_operators(bpy.types.Operator):
    bl_label = "Rename Object to Option"
    bl_idname = "object.rename_to_option"
    bl_description = "Click to tag/rename the selected object. Body can be an Empty or Mesh. Wheel has to be the 'tire mesh'. Brake can be an Empty or Mesh. Headlights need to be left and right headlight meshes split into two separate objects. Wheelcover can be an Empty or Mesh."

    option_name: bpy.props.StringProperty()

    def execute(self, context):
        if context.object:
            context.object.name = self.option_name

        else:
            message = "You need to select an object before trying to rename."
            show_message_box(message, "Invalid Operation")
        return {"FINISHED"}
    

class OBJECT_OT_calculate_wheel_diameter(bpy.types.Operator):
    bl_label = "Calculate Wheel Diameter"
    bl_idname = "object.calculate_wheel_diameter"
    bl_description = "Calculate the Tire Diameter based on the tire data above. You can also input the Tire Diameter manually on the right and not click this button"

    def execute(self, context):
        settings = bpy.context.scene.settings

        if settings.link_tire_settings:
            settings.wheel_size_rear = ((settings.tire_width/1000)*(settings.tire_ratio/100))*2  +  (settings.rim_diameter/39.37)

        else:
            settings.wheel_size_front = ((settings.tire_width_front/1000)*(settings.tire_ratio_front/100))*2  +  (settings.rim_diameter_front/39.37)
            settings.wheel_size_rear = ((settings.tire_width_rear/1000)*(settings.tire_ratio_rear/100))*2  +  (settings.rim_diameter_rear/39.37)

        return {"FINISHED"}

class OBJECT_OT_reload_headlight_tex(bpy.types.Operator):
    bl_label = "Reload Headlight Textures"
    bl_idname = "object.reload_headlight_tex"
    bl_description = "Reload the headlight textures in case they have gone missing (Pink Headlight Beams)"

    def execute(self, context):
        scene = context.scene

        cars = scene.lc.cars
        in_use = []


        unlinked_texs = []

        for car in cars:
            collection_name = car.collection.name

            car.get_rig_collection()
        
            low_beam_L = bpy.data.lights[FILENAME_L_LOWBEAM_L +'_' + collection_name]
            high_beam_L = bpy.data.lights[FILENAME_L_HIGHBEAM_L + '_' +collection_name]
            low_beam_R = bpy.data.lights[FILENAME_L_LOWBEAM_R +'_' + collection_name]
            high_beam_R = bpy.data.lights[FILENAME_L_HIGHBEAM_R + '_' +collection_name]

            beams = [low_beam_L, high_beam_L, low_beam_R, high_beam_R]

            headlight_dir = get_resource_path("headlights")

            for beam in beams:
                for node in beam.node_tree.nodes["Group"].node_tree.nodes:
                    if node.type == "TEX_IMAGE":
                        #if node.image.filepath_raw:  # Check if the image has a file path
                        # Resolve the absolute path
                        abs_path = bpy.path.abspath(node.image.filepath_raw)

                        print("node.image.filepath_raw", node.image.filepath_raw)

                        # Check if the file exists on the disk
                        if not os.path.isfile(abs_path) or node.image.filepath_raw == '':
                            if node.image not in unlinked_texs:
                                unlinked_texs.append(node.image)
                                filename = os.path.basename(bpy.path.abspath(node.image.filepath))
                                relink_path = os.path.join(headlight_dir, filename)
                                node.image.filepath = os.path.join(headlight_dir, filename)
                                log_info(f"Texture {filename} is missing, will relink to {relink_path}", "update_headlight")
            
        relinked_texs = 0
        success = False
        for tex in unlinked_texs:
            if tex.filepath_raw:
                abs_path = bpy.path.abspath(tex.filepath_raw)

                if os.path.isfile(abs_path):
                    relinked_texs += 1
                    success = True

        if len(unlinked_texs) == 0:
            text = "No missing headlight textures detected. You might have to exit 'render preview' for textures to appear." 
        elif success:
            text = f"Reloaded {relinked_texs} missing headlight textures. You might have to exit 'render preview' for textures to appear."
        else:
            text = f"Could not reload all headlight textures. Please relink manually."
        show_message_box(text ,"Reload Headlight Textures", "INFO")
        
        return {"FINISHED"}
    

class OBJECT_OT_reload_all_headlight_tex(bpy.types.Operator):
    bl_label = "Reload All Headlight Textures"
    bl_idname = "object.reload_all_headlight_tex"
    bl_description = "Reload all the headlight textures from the Launch Control Add-on Files"

    def execute(self, context):
        scene = context.scene
        cars = scene.lc.cars

        headlight_preset_names = enum_members_from_instance(cars[0].properties, "headlights_presets")
        headlight_dir = get_resource_path("headlights")

        for image in bpy.data.images:
            if any(x in image.name for x in headlight_preset_names) and (image.file_format == 'TARGA' or image.file_format == 'OPEN_EXR'):
                if image.packed_file is not None:
                    image.unpack(method="USE_LOCAL")

                filename = os.path.basename(bpy.path.abspath(image.filepath))
                relink_path = os.path.join(headlight_dir, filename)
                image.filepath = os.path.join(headlight_dir, filename)
                log_info(f"Will relink Texture {filename} to path {relink_path}", "update_headlight")

                success = False
                if os.path.isfile(relink_path):
                    success = True

        if success:
            text = f"Successfully reloaded all Headlight Textures" 
        else:
            text = f"Could not reload all Headlight Textures"
        show_message_box(text ,"Reload Headlight Textures", "INFO")
        
        return {"FINISHED"}


class OBJECT_OT_unload_headlight_tex(bpy.types.Operator):
    bl_label = "Unload Unused Headlight Textures"
    bl_idname = "object.unload_headlight_tex"
    bl_description = "Unload unused headlight textures to save storage space when packing .blend. Expect Warnings when saving packed file due to the unloaded textures."

    def execute(self, context):
        scene = context.scene

        cars = scene.lc.cars
        in_use = []

        headlight_preset_names = enum_members_from_instance(cars[0].properties, "headlights_presets")

        # Unpack all headlight textures if needed
        for image in bpy.data.images:
            if any(x in image.name for x in headlight_preset_names) and (image.file_format == 'TARGA' or image.file_format == 'OPEN_EXR'):
                if image.packed_file is not None:
                    image.unpack(method="USE_LOCAL")

        for car in cars:
            collection_name = car.collection.name
            collection_name_lower = collection_name.lower()
            car.get_rig_collection()
            
            light_collection = get_collection_by_name(COLLECTIONNAME_LIGHTS + '_' + collection_name_lower, car.rig_collection)

            if light_collection is None:
                message = f"Could not set find headlights for the vehicle named {car.name}. Could not unload."
                show_message_box(message, "Locating Headlight", "ERROR")
                return {"CANCELLED"}  

            for beam in light_collection.objects:
                if not beam.hide_render and not beam.hide_viewport:
                    for node in beam.data.node_tree.nodes["Group"].node_tree.nodes:
                        if node.type == "TEX_IMAGE":
                            if node.image not in in_use:
                                in_use.append(node.image)
        
        data_to_remove = []
        for image in bpy.data.images:
            if any(x in image.name for x in headlight_preset_names) and (image.file_format == 'TARGA' or image.file_format == 'OPEN_EXR'):
                if image not in in_use:
                    abs_path = bpy.path.abspath(image.filepath_raw)
                    if os.path.isfile(abs_path):
                        data_to_remove.append(image)

        for img in data_to_remove:
            img.filepath_raw = (os.path.basename(bpy.path.abspath(img.filepath_raw)))

        if len(data_to_remove) > 0:
            message = f"Unloaded {len(data_to_remove)} Unused Headlight Textures. Use 'Reload All' to reload all textures again."
        else:
            message = f"No Headlight Textures were be unloaded. All are in use."

        show_message_box(message, "Unload Headlight Textures", "INFO")
        return {"FINISHED"}  


            

class OBJECT_OT_bake_skidmarks(bpy.types.Operator):
    bl_label = "Bake Skidmarks"
    bl_idname = "object.bake_skidmarks"
    bl_description = "Bake and freeze the skidmark simulation. Do this before rendering to get consistent rendering results"

    def execute(self, context):
        scene = context.scene
        active_car = scene.lc.find_selected()

        # check if Physics are Live - If they are the physics will break and skidmarks be calculated wrong
        switch = active_car.rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1]
        switch_setup_mode = active_car.rig_object.pose.bones[B_SWITCH_SETUP].location[1]
        baked_physics = active_car.properties.baked_physics

        if switch > 0.5 and not baked_physics:
            message = "Please bake Physics before baking the skidmarks. Alternatively, turn disable the Physics to bake the Skidmarks"
            show_message_box(message, "Skidmark Baking", "INFO")
            return {"CANCELLED"}

        #make sure we have an active object to avoid crash
        bpy.context.view_layer.objects.active = active_car.body.body
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")

        multi_edit = scene.settings.edit_all_mode
        cars = []
        
        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for active_car in cars:
            collection_name = active_car.collection.name

            skidmark_FL = scene.objects[FILENAME_SKIDMARK_ENGINE_FL + ("_" + collection_name)]
            skidmark_FR = scene.objects[FILENAME_SKIDMARK_ENGINE_FR + ("_" + collection_name)]
            skidmark_RL = scene.objects[FILENAME_SKIDMARK_ENGINE_RL + ("_" + collection_name)]
            skidmark_RR = scene.objects[FILENAME_SKIDMARK_ENGINE_RR + ("_" + collection_name)]
            
            skidmarks = [skidmark_FL, skidmark_FR, skidmark_RL, skidmark_RR]

            # prepare cache filepath
            prepare_cache_skidmarks(skidmarks, active_car)

            # bake simulation nodes
            for skidmark in skidmarks:
                skidmark.select_set(True)
            bpy.context.view_layer.objects.active = skidmark_FL

        if len(bpy.context.selected_objects) > 0:
            try: bpy.ops.object.simulation_nodes_cache_delete(selected=True)
            except: log_info("NOPE, Couldn't find cache folder to delete!", "OBJECT_OT_bake_skidmarks")

        try: bpy.ops.object.simulation_nodes_cache_bake(selected=True)
        except: log_info("NOPE, Couldn't bake cache", "OBJECT_OT_bake_skidmarks")

        bpy.ops.object.select_all(action="DESELECT")
        return {"FINISHED"}


class OBJECT_OT_free_skidmarks(bpy.types.Operator):
    bl_label = "Free Skidmarks"
    bl_idname = "object.free_skidmarks"
    bl_description = "Remove the Bake and un-freeze the skidmark simulation. The skidmarks will then update in real-time"
    
    def execute(self, context):
        scene = context.scene
        active_car = scene.lc.find_selected()

        #make sure we have an active object to avoid crash
        bpy.context.view_layer.objects.active = active_car.body.body
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")

        multi_edit = scene.settings.edit_all_mode
        cars = []
        
        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for active_car in cars:
            collection_name = active_car.collection.name

            skidmark_FL = scene.objects[FILENAME_SKIDMARK_ENGINE_FL + ("_" + collection_name)]
            skidmark_FR = scene.objects[FILENAME_SKIDMARK_ENGINE_FR + ("_" + collection_name)]
            skidmark_RL = scene.objects[FILENAME_SKIDMARK_ENGINE_RL + ("_" + collection_name)]
            skidmark_RR = scene.objects[FILENAME_SKIDMARK_ENGINE_RR + ("_" + collection_name)]
            
            skidmarks = [skidmark_FL, skidmark_FR, skidmark_RL, skidmark_RR]

            # free simulation nodes
            for skidmark in skidmarks:
                skidmark.select_set(True)
            bpy.context.view_layer.objects.active = skidmark_FL
            
            # prepare cache filepath
            prepare_cache_skidmarks(skidmarks, active_car)
        
            # validate cache existence
            skidmark_filenames = [FILENAME_SKIDMARK_ENGINE_FL, FILENAME_SKIDMARK_ENGINE_FR, FILENAME_SKIDMARK_ENGINE_RL, FILENAME_SKIDMARK_ENGINE_RR]
            
            for filename in skidmark_filenames:
                if not validate_cache(active_car, filename):

                    for skidmark in skidmarks:
                        skidmark.select_set(False)

                    log_info("No cache to free", "Skidmark Cache")

        if len(bpy.context.selected_objects) > 0:
            try: bpy.ops.object.simulation_nodes_cache_delete(selected=True)
            except: log_info("NOPE, Couldn't find cache folder to delete!", "OBJECT_OT_free_skidmarks")

        bpy.ops.object.select_all(action="DESELECT")
        return {"FINISHED"}
    

class OBJECT_OT_find_selected_car(bpy.types.Operator):
    bl_label = "Set Selected"
    bl_idname = "object.find_selected_car"
    bl_description = "Sets 'Active Vehicle' to the LC Car selected in the viewport"
             
    def execute(self, context):
        scene = context.scene    
        active_object = bpy.context.active_object

        obj_collections = active_object.users_collection

        # auto update active car when selecting another LC rigged car
        for car in bpy.context.scene.lc.cars:
            for coll in obj_collections:
                if coll == car.collection or coll == car.rig_collection:
                    scene.car_collection = car.collection
                    return {"FINISHED"}
                    
        message = "No Rigged Launch Control Car is selected in the viewport"
        show_message_box(message, "Nothing Happened...", "INFO")
        return {"CANCELLED"}  


class OBJECT_OT_pick_selected_path(bpy.types.Operator):
    bl_label = "Pick Selected Path"
    bl_idname = "object.pick_selected_path"
    bl_description = "Picks any selected path in the viewport as the 'User Path' for animation"
             
    def execute(self, context):
        scene = context.scene    
        active_car = scene.lc.find_selected()
        
        try: 
            selected_objects = bpy.context.selected_objects
            for obj in selected_objects:
                if obj.type == 'CURVE':
                    active_car.properties.custom_path = obj

                    return {"FINISHED"}
                    
        except:
            message = "Could not set 'User Path' to selected object"
            show_message_box(message, "Nothing Happened...", "INFO")
            return {"CANCELLED"}  

        message = "Please select the Curve Object you want to use as the new Driving Path"
        show_message_box(message, "Nothing Happened...", "INFO")
        return {"CANCELLED"}  


class OBJECT_OT_revert_vehicle_add(bpy.types.Operator):
    bl_label = "Add new LC Vehicle"
    bl_idname = "object.revert_vehicle_add"
    bl_description = "Show options for adding and rigging more Vehicles"
             
    def execute(self, context):

        if context.scene.car_collection is not None:
            context.scene.car_collection_previous = context.scene.car_collection
            context.scene.car_collection = None
        
        else:
            pass

        return {"FINISHED"}
    

class OBJECT_OT_revert_vehicle_edit(bpy.types.Operator):
    bl_label = "Return to Active Vehicle"
    bl_idname = "object.revert_vehicle_edit"
    bl_description = "Return to edit and animate the most recently selected LC vehicle"
             
    def execute(self, context):

        context.scene.car_collection = context.scene.car_collection_previous
        
        return {"FINISHED"}


class OBJECT_OT_refresh_speedometer(bpy.types.Operator):
    bl_label = "Reset Speedometer"
    bl_idname = "object.refresh_speedometer"
    bl_description = "Resets the speedometer"

    def execute(self, context):
        scene = context.scene

        active_car = scene.lc.find_selected()

        multi_edit = scene.settings.edit_all_mode
        cars = []

        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        for active_car in cars:

            if not validate_lc_object(active_car.speed_calculator):
                return {"CANCELLED"}
            
            active_car.speed_calculator.select_set(True)
            bpy.context.view_layer.objects.active = active_car.rig_object

            # Fix in case the sim nodes broken because of undo
            try: force_update_geo_nodes(active_car)
            except: log_info("Could not 'force update' geo nodes - Not critical", "OBJECT_OT_refresh_speedometer")


            bpy.context.scene.frame_current = bpy.context.scene.frame_current -1

            bpy.ops.object.simulation_nodes_cache_delete(selected=True)

            bpy.context.scene.frame_current = bpy.context.scene.frame_current +1

            #show_message_box("Physics DISABLED", "Physics", "INFO")
            log_info("Speedometer was Refreshed", "OBJECT_OT_refresh_speedometer")

        return {"FINISHED"}
    

class OBJECT_OT_update_vehicle_rig(bpy.types.Operator):
    bl_label = "Update Vehicle Rig"
    bl_idname = "object.update_vehicle_rig"
    bl_description = "Will store rig setup settings, animation data, driving path and ground colliders before unrigging the vehicle and rigging it again with the updated version. The store data will be restored in the new rig if possible. *Some data might not be carried over correctly*"

    def execute(self, context):
        scene = context.scene
        active_car = scene.lc.find_selected()

        # Make sure we are in object mode
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except:
            text = "Please switch to Object Mode and select the LC Armature before Updating the Rig"
            show_message_box(text ,"Updating rig", "INFO")
            log_error("Failed! Could not switch to Object Mode automatically", "Update Rig Failed")
            
            return {"CANCELLED"}

        rig_sliders_changed = False
        
        if active_car and active_car.is_rigged:
            legacy_update = False
        else:
            legacy_update = True

        if legacy_update:
            rig_object = scene.objects["CarRig"]
            bones = rig_object.pose.bones

            restore_car_collection = scene.car_collection
            restore_path = scene.objects["DrivingPath"].data
            restore_path_location = scene.objects["DrivingPath"].location.copy()
            restore_path_rotation_euler = scene.objects["DrivingPath"].rotation_euler.copy()
            restore_path_scale = scene.objects["DrivingPath"].scale.copy()
            restore_action = rig_object.animation_data.action

            for fcurve in restore_action.fcurves:
                if not "bone_" in fcurve.data_path:
                    string = fcurve.data_path
                    fcurve.data_path = string[:12] + 'bone_' + string[12:]
                
                if "Follow_DataFeed" in fcurve.data_path:
                    string = fcurve.data_path
                    fcurve.data_path = string.replace("Follow_DataFeed", "Speed_Rotate")

            col = bpy.data.collections["groundDetection"]
            col_temp = bpy.data.collections.new("Temp_GroundDetection")
            scene.collection.children.link(col_temp)
            for obj in col.objects:
                col_temp.objects.link(obj)
                col.objects.unlink(obj)

            for col in scene.collection.children_recursive:
                if col.name == "CarRig":
                    col.name = col.name + "_lc_rename"
        
            restore_path.use_fake_user = True
            restore_action.use_fake_user = True

            rig_sliders_changed = True

        else:
            rig_object = active_car.rig_object
            bones = rig_object.pose.bones
            
            restore_car_collection = scene.car_collection
            restore_path = active_car.driving_path.data
            restore_path_location = active_car.driving_path.location.copy()
            restore_path_rotation_euler = active_car.driving_path.rotation_euler.copy()
            restore_path_scale = active_car.driving_path.scale.copy()
            restore_action = active_car.rig_object.animation_data.action

            col = bpy.data.collections["GroundDetection"]
            col_temp = bpy.data.collections.new("Temp_GroundDetection")
            scene.collection.children.link(col_temp)
            for obj in col.objects:
                col_temp.objects.link(obj)
                col.objects.unlink(obj)
        
            restore_path.use_fake_user = True
            restore_action.use_fake_user = True

            ### Store Slider Values
            try:
                active_car.settings.restore_settings = (
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

                active_car.settings.restore_settings_02 = (
                    active_car.settings.show_extra_animation_controls,        #00
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
            except:
                rig_sliders_changed = True

            
            ### Store Settings
            restore_setts = []
            restore_setts_value = []

            for setting in active_car.settings.bl_rna.properties:
                id_name = setting.identifier

                if hasattr(setting, "default") and id_name != "name":
                    default_value = setting.default
                    restore_setts.append(id_name)
                    # get value of property. If the value is not yet changed, get the default value
                    restore_setts_value.append(active_car.settings.get(id_name, default_value))
            
            # Store Slider Settings 
            restore_slider_settings = []
            for value in active_car.settings.restore_settings:
                restore_slider_settings.append(value)

            restore_slider_settings_02 = []
            for value in active_car.settings.restore_settings_02:
                restore_slider_settings_02.append(value)


            ### Store Properties
            restore_props = []
            restore_props_value = []

            for prop in active_car.properties.bl_rna.properties:
                id_name = prop.identifier

                if hasattr(prop, "default") and id_name != "name":
                    default_value = prop.default
                    restore_props.append(id_name)
                    # get value of property. If the value is not yet changed, get the default value
                    restore_props_value.append(active_car.properties.get(id_name, default_value))

        
        # Clear bone constraints to avoid carry over
        for bone in bones:
            for c in bone.constraints:
                bone.constraints.remove(c)
                    

        ### Re Rig
        try:
            if legacy_update:
                bpy.data.objects.remove(rig_object)
                bpy.data.collections.remove(bpy.data.collections["CarRigAddon"])
            else:
                bpy.ops.object.delete_rig(do_pop_up=False)
            bpy.ops.object.rig_car()

        except:
            text = "Could not update the Vehicle Rig. Please make sure the entire Vehicle is visible in the scene"
            show_message_box(text ,"Update Rig Failed", "ERROR")
            log_error("Failed! Seems that the new rig did not get uploaded to file", "Update Rig Failed")
            bpy.ops.object.select_all(action="DESELECT")
            bpy.ops.ed.undo_push()
            bpy.ops.ed.undo()
            bpy.ops.ed.undo()
            bpy.ops.ed.undo()
            # undo a 3 times since rig_car also pushes undos
            
            return {"CANCELLED"}


        try:
            scene.car_collection = restore_car_collection
            active_car = scene.lc.find_selected()
            rig_object = active_car.rig_object
            bones = rig_object.pose.bones
        except:
            text = "Could not find all necesarry LC Objects for re-rigging in the file. Update Cancelled"
            show_message_box(text ,"Update Rig Failed", "ERROR")
            log_error(text, "Update Rig Failed")
            bpy.ops.object.select_all(action="DESELECT")
            bpy.ops.ed.undo_push()
            bpy.ops.ed.undo()
            bpy.ops.ed.undo()
            bpy.ops.ed.undo()
            # undo a 3 times since rig_car also pushes undos
            
            return {"CANCELLED"}

        try:
            active_car.driving_path.data = restore_path
        except:
            log_error("Failed! Seems that the new rig did not get uploaded to file", "Update Rig Failed")
            show_message_box("Something went wrong. Please open the console 'Window -> Toggle System Console' to see more details", "Updating Failed!")
            return {"CANCELLED"}
        
        active_car.rig_object.animation_data.action = restore_action
        active_car.driving_path.location = restore_path_location
        active_car.driving_path.rotation_euler = restore_path_rotation_euler
        active_car.driving_path.scale = restore_path_scale

        restore_path.use_fake_user = False
        restore_action.use_fake_user = False

        col = bpy.data.collections["GroundDetection"]
        for obj in col.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        
        for obj in col_temp.objects:
            col.objects.link(obj)
            col_temp.objects.unlink(obj)

            if len(col_temp.objects) == 0:
                bpy.data.collections.remove(col_temp)

        if not legacy_update:
            ### Match Settings with old rig
            i = 0
            for restore_sett in restore_setts:

                match restore_sett:
                    case "show_custom_physics":
                        active_car.settings.show_custom_physics = restore_setts_value[i]

                    case "show_acc_viz":
                        active_car.settings.show_acc_viz = restore_setts_value[i]

                    case "show_vel_viz":
                        active_car.settings.show_vel_viz = restore_setts_value[i]

                    case "export_path":
                        active_car.settings.export_path = restore_setts_value[i]

                    case "apply_transforms":
                        active_car.settings.apply_transforms = restore_setts_value[i]

                    case "include_ground":
                        active_car.settings.include_ground = restore_setts_value[i]

                    case "link_beams":
                        active_car.settings.link_beams = restore_setts_value[i]

                    case "low_beam_visibility":
                        active_car.settings.low_beam_visibility = restore_setts_value[i]

                    case "high_beam_visibility":
                        active_car.settings.high_beam_visibility = restore_setts_value[i]
                    
                    case "show_extra_animation_controls":
                        active_car.settings.show_extra_animation_controls = restore_setts_value[i]
                    
                    case "limit_sliders":
                        active_car.settings.limit_sliders = restore_setts_value[i]

                    case "show_ground_grid":
                        active_car.settings.show_ground_grid = restore_setts_value[i]

                    case "grid_resolution":
                        active_car.settings.grid_resolution = restore_setts_value[i]

                    case "show_jump_help":
                        active_car.settings.show_jump_help = restore_setts_value[i]

                    case "jump_speed":
                        active_car.settings.jump_speed = restore_setts_value[i]

                    case "use_rest_pos":
                        active_car.settings.use_rest_pos = restore_setts_value[i]

                    case "enable_skidmarks":
                        active_car.settings.enable_skidmarks = restore_setts_value[i]

                    case "speedometer":
                        active_car.settings.speedometer = restore_setts_value[i]

                log_info(("Updated Setting:", restore_sett, "to:", restore_setts_value[i]), "Update Rig")
                i = i+1
            
            # Match Slider Settings
            if not rig_sliders_changed:
                try:
                    active_car.settings.restore_settings = restore_slider_settings
                    active_car.settings.restore_settings_02 = restore_slider_settings_02
                except:
                    log_info("Could not update Viewport Sliders!", "Partly Rig Update")


            ### Match Properties with old rig
            i = 0
            for restore_prop in restore_props:

                match restore_prop:
                    case "physics_tightness":
                        active_car.properties.physics_tightness = restore_props_value[i]

                    case "physics_dampening":
                        active_car.properties.physics_dampening = restore_props_value[i]

                    case "physics_softness":
                        active_car.properties.physics_softness = restore_props_value[i]

                    case "physics_multiplier":
                        active_car.properties.physics_multiplier = restore_props_value[i]

                    case "use_gravity":
                        active_car.properties.use_gravity = restore_props_value[i]

                    case "shake_frequency":
                        active_car.properties.shake_frequency = restore_props_value[i]

                    case "low_beam_temperature":
                        active_car.properties.low_beam_temperature = restore_props_value[i]

                    case "low_beam_intensity":
                        active_car.properties.low_beam_intensity = restore_props_value[i]

                    case "low_beam_spread":
                        active_car.properties.low_beam_spread = restore_props_value[i]
                    
                    case "low_beam_sharpness":
                        active_car.properties.low_beam_sharpness = restore_props_value[i]
                    
                    case "high_beam_temperature":
                        active_car.properties.high_beam_temperature = restore_props_value[i]

                    case "high_beam_intensity":
                        active_car.properties.high_beam_intensity = restore_props_value[i]

                    case "high_beam_spread":
                        active_car.properties.high_beam_spread = restore_props_value[i]

                    case "high_beam_sharpness":
                        active_car.properties.high_beam_sharpness = restore_props_value[i]

                    case "overdrive_pitch":
                        active_car.properties.overdrive_pitch = restore_props_value[i]

                    case "overdrive_yaw":
                        active_car.properties.overdrive_yaw = restore_props_value[i]

                    case "overdrive_roll":
                        active_car.properties.overdrive_roll = restore_props_value[i]

                    case "overdrive_location":
                        active_car.properties.overdrive_location = restore_props_value[i]

                    case "overdrive_wheel_location":
                        active_car.properties.overdrive_wheel_location = restore_props_value[i]

                    case "overdrive_wheel_pressure":
                        active_car.properties.overdrive_wheel_pressure = restore_props_value[i]

                    case "skidmarks_mul":
                        active_car.properties.skidmarks_mul = restore_props_value[i]

                    case "skidmarks_var":
                        active_car.properties.skidmarks_var = restore_props_value[i]


                log_info(("Updated Property:", restore_prop, "to:", restore_props_value[i]), "Update Rig")
                i = i+1


        ### Match Sliders with old rig

        if not rig_sliders_changed:
            bones[B_SLIDER_BODY_WEIGHT].location[1] = active_car.settings.restore_settings[0]
            bones[B_SLIDER_WHEEL_CAMBER].location[1] = active_car.settings.restore_settings[1]
            bones[B_SWITCH_SETUP].location[1] = active_car.settings.restore_settings[2]
            bones[B_SWITCH_AIRBOURNE].location[1] = active_car.settings.restore_settings[3]
            bones[B_SWITCH_AIRBOURNE_ROT].location[1] = active_car.settings.restore_settings[4]
            bones[B_SLIDER_PIVOT_POS].location[1] = active_car.settings.restore_settings[6]
            bones[B_SLIDER_WHEEL_WOBBLE].location[1] = active_car.settings.restore_settings[7]
            bones[B_SLIDER_WHEEL_SHAKE].location[1] = active_car.settings.restore_settings[8]
            bones[B_SLIDER_CAMBER_TOE].location[1] = active_car.settings.restore_settings[9]
            bones[B_SLIDER_CAMBER_TOE].location[0] = active_car.settings.restore_settings[30]
            bones[B_SLIDER_MAX_SUSPENSION_FRONT].location[1] = active_car.settings.restore_settings[10]
            bones[B_SWITCH_STEERING_WHEEL].location[1] = active_car.settings.restore_settings[11]
            bones[B_SLIDER_SIMPLE_STEERING].location[1] = active_car.settings.restore_settings[12]
            bones[B_INTERACTIVE_WHEEL_PAIR].location[0] = active_car.settings.restore_settings[13]
            bones[B_CUSTOM_MASS].location[0] = active_car.settings.restore_settings[14]
            bones[B_CUSTOM_MASS].location[1] = active_car.settings.restore_settings[15]
            bones[B_CUSTOM_MASS].location[2] = active_car.settings.restore_settings[16]
            bones[B_BODY_DRIFT].rotation_euler[1] = active_car.settings.restore_settings[17]
            bones[B_WHEEL_CUSTOM_SUSPENSION_FR].location[1] = active_car.settings.restore_settings[18]
            bones[B_WHEEL_CUSTOM_SUSPENSION_FL].location[1] = active_car.settings.restore_settings[19]
            bones[B_WHEEL_CUSTOM_SUSPENSION_RR].location[1] = active_car.settings.restore_settings[20]
            bones[B_WHEEL_CUSTOM_SUSPENSION_RL].location[1] = active_car.settings.restore_settings[21]
            bones[B_WHEEL_CUSTOM_SPIN_FR].rotation_euler[0] = active_car.settings.restore_settings[22]
            bones[B_WHEEL_CUSTOM_SPIN_FL].rotation_euler[0] = active_car.settings.restore_settings[23]
            bones[B_WHEEL_CUSTOM_SPIN_RR].rotation_euler[0] = active_car.settings.restore_settings[24]
            bones[B_WHEEL_CUSTOM_SPIN_RL].rotation_euler[0] = active_car.settings.restore_settings[25]
            bones[B_WHEEL_CUSTOM_TURN_FR].rotation_euler[2] = active_car.settings.restore_settings[26]
            bones[B_WHEEL_CUSTOM_TURN_FL].rotation_euler[2] = active_car.settings.restore_settings[27]
            bones[B_WHEEL_CUSTOM_TURN_RR].rotation_euler[2] = active_car.settings.restore_settings[28]
            bones[B_WHEEL_CUSTOM_TURN_RL].rotation_euler[2] = active_car.settings.restore_settings[29]
            bones[B_WHEEL_CAMBEROFFSET_FR].rotation_euler[1] = active_car.settings.restore_settings_02[1]
            bones[B_WHEEL_CAMBEROFFSET_FL].rotation_euler[1] = active_car.settings.restore_settings_02[2]
            bones[B_WHEEL_CAMBEROFFSET_RR].rotation_euler[1] = active_car.settings.restore_settings_02[3]
            bones[B_WHEEL_CAMBEROFFSET_RL].rotation_euler[1] = active_car.settings.restore_settings_02[4]
            bones[B_WHEEL_CAMBEROFFSET_FR].rotation_euler[2] = active_car.settings.restore_settings_02[5]
            bones[B_WHEEL_CAMBEROFFSET_FL].rotation_euler[2] = active_car.settings.restore_settings_02[6]
            bones[B_WHEEL_CAMBEROFFSET_RR].rotation_euler[2] = active_car.settings.restore_settings_02[7]
            bones[B_WHEEL_CAMBEROFFSET_RL].rotation_euler[2] = active_car.settings.restore_settings_02[8]
            bones[B_WHEEL_ARCH_LIMIT_FR].location[1] = active_car.settings.restore_settings_02[9]
            bones[B_WHEEL_ARCH_LIMIT_FL].location[1] = active_car.settings.restore_settings_02[10]
            bones[B_WHEEL_ARCH_LIMIT_RR].location[1] = active_car.settings.restore_settings_02[11]
            bones[B_WHEEL_ARCH_LIMIT_RL].location[1] = active_car.settings.restore_settings_02[12]
            bones[B_BODY_DRIFT_OFFSET].location[0] = active_car.settings.restore_settings_02[13]
            bones[B_SLIDER_TURN_LIMIT].location[1] = active_car.settings.restore_settings_02[14]
            bones[B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT].location[1] = active_car.settings.restore_settings_02[15]
            bones[B_SWITCH_SINGLE_AXLE_REAR].location[1] = active_car.settings.restore_settings_02[16]
            bones[B_SLIDER_MAX_SUSPENSION_REAR].location[1] = active_car.settings.restore_settings_02[17]
            bones[B_SLIDER_BOTTOM_OUT_HEIGHT_REAR].location[1] = active_car.settings.restore_settings_02[18]
            bones[B_SWITCH_SINGLE_AXLE_FRONT].location[1] = active_car.settings.restore_settings_02[19]
            bones[B_SWITCH_USE_SIMULATION].location[1] = active_car.settings.restore_settings[31]
            
        
        ### Mute slider locks if they are there (LC 1.5.3)
        bones[B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT].constraints["Limit Location"].enabled = False
        bones[B_SLIDER_BOTTOM_OUT_HEIGHT_REAR].constraints["Limit Location"].enabled = False

        if rig_sliders_changed:
            message = "Updated Vehicle Rig version to match add-on version. However, viewport Slider data did not get carried over due to incompatibility!"
            title = "Finished Updating - Viewport Sliders Ignored"
        
        else:
            message = "Updated Vehicle Rig version to match add-on version. Some data might not have been carried over correctly. - Please do a check before proceeding!"
            title = "Finished Updating"

        show_message_box(message, title)
        return {"FINISHED"}
    

class OBJECT_OT_add_ground_colliders(bpy.types.Operator):
    bl_label = "Add Ground Colliders"
    bl_idname = "object.add_ground_colliders"
    bl_description = (
        "Add selected objects as ground colliders to the Ground Detection Collection"
    )

    def execute(self, context):
        scene = context.scene

        if len(bpy.context.selected_objects) < 1:
            text = ("Please select the Object you want to add to the Ground Detection")
            show_message_box(title="No Selected Object", message=text, icon="INFO")
            log_info(text, "OBJECT_OT_add_ground_colliders")
            return {'CANCELLED'}
            
        else:
            lc_collection = get_collection_by_name(COLLECTIONNAME_ADDON, scene.collection)
            ground_detect_collection = get_collection_by_name(COLLECTIONNAME_GROUNDDETECT, scene.collection)

            exclude_colls = lc_collection.children_recursive

            exclude_objs = []

            for coll in exclude_colls:
                for obj in coll.objects:
                    exclude_objs.append(obj)


            for obj in scene.objects:
                if obj.select_get():
                    if obj not in exclude_objs:
                        ground_detect_collection.objects.link(obj)

            return {"FINISHED"}
    

class OBJECT_OT_remove_ground_colliders(bpy.types.Operator):
    bl_label = "Remove Ground Colliders"
    bl_idname = "object.remove_ground_colliders"
    bl_description = (
        "Remove selected objects from ground detection"
    )

    def execute(self, context):
        scene = context.scene

        ground_detect_collection = get_collection_by_name(COLLECTIONNAME_GROUNDDETECT, scene.collection)

        for obj in scene.objects:
            if obj.select_get():
                if ground_detect_collection in obj.users_collection:
                    ground_detect_collection.objects.unlink(obj)
                    if len(obj.users_collection) < 1:
                        scene.collection.objects.link(obj)

        return {"FINISHED"}

class OBJECT_OT_remove_all_ground_colliders(bpy.types.Operator):
    bl_label = "Remove All Ground Colliders"
    bl_idname = "object.remove_all_ground_colliders"
    bl_description = (
        "Remove all objects from ground detection"
    )

    def execute(self, context):
        scene = context.scene

        ground_detect_collection = get_collection_by_name(COLLECTIONNAME_GROUNDDETECT, scene.collection)

        for obj in scene.objects:
            if ground_detect_collection in obj.users_collection:
                ground_detect_collection.objects.unlink(obj)
                if len(obj.users_collection) < 1:
                    scene.collection.objects.link(obj)

        return {"FINISHED"}


class OBJECT_OT_install_lib(bpy.types.Operator):
    bl_label = "Install .lcl"
    bl_idname = "object.install_lib"
    bl_description = ("Install an .lcl file with assets from your system")

    filepath : bpy.props.StringProperty(subtype="FILE_PATH")

    asset_type : bpy.props.StringProperty(options={'HIDDEN'})
    filter_glob : bpy.props.StringProperty(default="*.lcl", options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


    def execute(self, context):
        
        if (not self.filepath.endswith(".lcl")):

            text = "The selected file is not an .lcl asset file"

            show_message_box(title="Unable to install library", message=text, icon="ERROR")
            log_error(text, "OBJECT_OT_install_lib")

            return {'CANCELLED'}   
        
        target_path = None

        if self.asset_type == 'VEHICLE':

            # Setup file reference to "vehicle assets" in addons folder
            target_path = get_resource_path("vehicles")

        
        if target_path is not None:
            try:
                unzip_in_location(self.filepath , target_path)
            except:
                text = (f"Assets could not be installed. Please re-download or contact the creator.")
                show_message_box(title="Installation Failed!", message=text, icon="ERROR")
                self.report({'ERROR'}, text)
                log_info(text, "OBJECT_OT_install_lib")
                return {'CANCELLED'}

            if self.asset_type == 'VEHICLE':
                text = (f"Assets were installed to the Vehicle Gallery")

            else:
                text = "Assets were installed"
            
            #show_message_box(title="Library Installed", message=text, icon="INFO")
            self.report({'INFO'}, text)
            log_info(text, "OBJECT_OT_install_lib")

            # Re-Register "Data" to reload Galleries
            data.unregister()
            data.register()

            return {"FINISHED"}
        
        else:
            text = "Could not determine asset type"

            show_message_box(title="Unable to install library", message=text, icon="ERROR")
            log_error(text, "OBJECT_OT_install_lib")

            return {'CANCELLED'}  



class OBJECT_OT_select_driving_path(bpy.types.Operator):
    bl_label = "Edit Driving Path"
    bl_idname = "object.select_driving_path"
    bl_description = (
        "Select the Driving Path in the viewport which belongs to the selected vehicle"
    )

    def execute(self, context):
        scene = context.scene

        active_car = scene.lc.find_selected()

        multi_edit = scene.settings.edit_all_mode
        cars = []

        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        for active_car in cars:
            driving_path = active_car.driving_path

            try: driving_path.select_set(True)
            except: pass


        if not validate_lc_object(driving_path):
            return {"CANCELLED"}

        bpy.context.view_layer.objects.active = driving_path
        try: bpy.ops.object.mode_set(mode="EDIT")
        except: pass

        return {"FINISHED"}
    

class OBJECT_OT_refresh_cache_dirs(bpy.types.Operator):
    bl_label = "Refresh Cache Directories"
    bl_idname = "object.refresh_cache_dirs"
    bl_description = ("Update all Cache Directories. Useful when exchanging blend files with LC rigs between systems")

    def execute(self, context):
        scene = context.scene
        active_car = scene.lc.find_selected()

        collection_name = active_car.collection.name

        skidmark_FL = scene.objects[FILENAME_SKIDMARK_ENGINE_FL + ("_" + collection_name)]
        skidmark_FR = scene.objects[FILENAME_SKIDMARK_ENGINE_FR + ("_" + collection_name)]
        skidmark_RL = scene.objects[FILENAME_SKIDMARK_ENGINE_RL + ("_" + collection_name)]
        skidmark_RR = scene.objects[FILENAME_SKIDMARK_ENGINE_RR + ("_" + collection_name)]
        
        skidmarks = [skidmark_FL, skidmark_FR, skidmark_RL, skidmark_RR]

        # prepare cache filepath
        prepare_cache_skidmarks(skidmarks, active_car)

        prepare_cache_physics(active_car)

        if bpy.app.version >= (4, 2, 0):
            # reset speed_calculator directory. Cache is not needed here!
            active_car.speed_calculator.modifiers["speed_calculator"].bake_directory = ""
        
        physics_bake_target = None
        has_physics_bake_target = hasattr(bpy.context.scene.settings, "physics_bake_target")
        if has_physics_bake_target:
            physics_bake_target = bpy.context.scene.settings.physics_bake_target

        if bpy.app.version >= (4, 3, 0) and physics_bake_target == "PACKED":
            show_message_box(title="Cache Directories", message="Cache Directories Updated. Caches are being Packed to .blend", icon="INFO")
        else:
            show_message_box(title="Cache Directories", message="Cache Directories Updated so they are relative to the .blend", icon="INFO")

        return {"FINISHED"}

