import bpy

from ..globals import B_SWITCH_USE_SIMULATION, FILENAME_SIM_BODY, FILENAME_SIM_WHEELS, GEONODE_SKIDMARK, PHYSICS_BODY, PHYSICS_WHEELS, SPEED_CALC
from ..utils.resources import prepare_cache_physics, validate_cache

from ..utils.functions import force_update_geo_nodes
from ..utils.validations import validate_lc_object

from ..utils.errors.exceptions import RigCollectionNotFound
from ..logger import log_info
from ..ui.utils import show_message_box


class OBJECT_OT_bake_physics(bpy.types.Operator):
    bl_label = "Bake Physics!"
    bl_idname = "object.bake_physics"
    bl_description = "Lock the Physics to prepare them for rendering"

    def execute(self, context):
        scene = context.scene
        scene.frame_current = scene.frame_start

        active_car = scene.lc.find_selected()

        if not validate_lc_object(active_car.rig_object):
            return {"CANCELLED"}
        
        bpy.context.view_layer.objects.active = active_car.sim_body

        multi_edit = scene.settings.edit_all_mode
        cars = []
        
        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        for active_car in cars:
            # Check for car rig in scene
            if not validate_lc_object(active_car.rig_object):
                return {"CANCELLED"}

            rig_object = active_car.rig_object
            rig_object.pose.bones["bone_Switch_Setup"].location[1] = 1.8
            rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1] = 1

            # save properties into a "baked" value, so we can compare if they changed
            active_car.properties.physics_baked_tightness = active_car.properties.physics_tightness
            active_car.properties.physics_baked_dampening = active_car.properties.physics_dampening 
            active_car.properties.physics_baked_softness = active_car.properties.physics_softness
            active_car.properties.physics_baked_multiplier = active_car.properties.physics_multiplier
            active_car.properties.baked_use_gravity = active_car.properties.use_gravity
            active_car.properties.baked_auto_level = active_car.properties.auto_level
            active_car.properties.baked_spring_offset = active_car.properties.spring_offset
            active_car.properties.baked_mass = active_car.properties.mass

            # mute PostFX to avoid jumpy car when clicking "Bake Physics" 
            rig_object.pose.bones["bone_body_simCTRL"].constraints["PITCH"].enabled = False
            rig_object.pose.bones["bone_body_simCTRL"].constraints["YAW"].enabled = False
            rig_object.pose.bones["bone_body_simCTRL"].constraints["ROLL"].enabled = False

            # prepare file paths
            prepare_cache_physics(active_car)

            # bake simulation nodes
            active_car.sim_wheels.select_set(True)
            active_car.sim_body.select_set(True)
            
            #active_car.sim_wheels.use_simulation_cache = True
            #active_car.sim_body.use_simulation_cache = True

            active_car.path_changed = False
            active_car.properties.mute_physics = False   
            active_car.properties.baked_physics = True
        
        if len(bpy.context.selected_objects) > 0:
            try: bpy.ops.object.simulation_nodes_cache_delete(selected=True)
            except: print("NOPE, Couldn't find cache folder to delete!")
        

        bpy.context.scene.use_preview_range = True
        scene.frame_preview_start = scene.frame_start
        scene.frame_preview_end = scene.frame_end

        scene.settings.physics_restore_start_frame = scene.frame_start
        scene.settings.physics_restore_end_frame = scene.frame_end
        scene.frame_start = scene.frame_start - scene.settings.physics_warm_up_frames

        scene.settings.confirm_bake_state = True

        return {"FINISHED"}
    
    
class OBJECT_OT_execute_physics_bake(bpy.types.Operator):
    bl_label = "Confirm Bake!"
    bl_idname = "object.execute_physics_bake"
    bl_description = "Physics Prepared, click to Bake"
    
            
    def execute(self, context):
        scene = context.scene

        if not bpy.data.is_saved:
            log_info("File not saved.", "OBJECT_OT_execute_physics_bake")
            show_message_box(f"Please save the blend file before baking the Physics.","File not saved","ERROR",)
            return {"CANCELLED"}
        
        active_car = scene.lc.find_selected()

        if not validate_lc_object(active_car.rig_object):
            return {"CANCELLED"}
        
        bpy.context.view_layer.objects.active = active_car.sim_body

        multi_edit = scene.settings.edit_all_mode
        cars = []
        
        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        try: 
            bpy.ops.object.mode_set(mode="OBJECT")
        except:
            pass


        # Set the baking frame range with Warmup frames
        active_car.properties.baked_frame_start = scene.frame_preview_start
        active_car.properties.baked_frame_end = scene.frame_preview_end

        scene.frame_start = scene.frame_preview_start - scene.settings.physics_warm_up_frames
        scene.frame_end = scene.frame_preview_end


        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        
        for active_car in cars:

            if not validate_lc_object(active_car.rig_object):
                return {"CANCELLED"}
            
            # prepare file paths (in case it needs to be updated after user changed settings)
            prepare_cache_physics(active_car)
        
            active_car.sim_wheels.select_set(True)
            active_car.sim_body.select_set(True)
            
            rig_object = active_car.rig_object

            # unmute PostFX to avoid jumpy car when clicking "Bake Physics" 
            rig_object.pose.bones["bone_body_simCTRL"].constraints["PITCH"].enabled = True
            rig_object.pose.bones["bone_body_simCTRL"].constraints["YAW"].enabled = True
            rig_object.pose.bones["bone_body_simCTRL"].constraints["ROLL"].enabled = True

            if not active_car.sim_wheels.select_get() or not active_car.sim_body.select_get():
                log_info(f"Physics could not be Baked. Could not select: {active_car.sim_wheels.name} and/or {active_car.sim_body.name}. Please make sure these are NOT hidden in the outliner and that their parent collections are not disabled or hidden", "OBJECT_OT_execute_physics_bake")
                show_message_box(f"Physics not be baked! Could not select the physics objects for {active_car.collection.name}. More info in the 'System Console'","Baking Failed","ERROR",)        
                return {"CANCELLED"}
            
        try: 
            bpy.ops.object.simulation_nodes_cache_bake(selected=True)

        except: 
            log_info("Physics could not be Baked.", "OBJECT_OT_execute_physics_bake")
            show_message_box(f"Physics Could not be baked! Please select the vehicle, make sure the 'Launch Control' collection is visible and try again.","Baking Failed","ERROR",)        
            return {"CANCELLED"}
        
        log_info("Physics Baked.", "OBJECT_OT_execute_physics_bake")
        #scene.settings.bake_running = True


        bpy.context.scene.use_preview_range = False
        scene.frame_start = scene.settings.physics_restore_start_frame
        scene.frame_end = scene.settings.physics_restore_end_frame
        scene.settings.confirm_bake_state = False
        scene.settings.bake_running = False
        
        show_message_box("Bake Complete! - Ready for rendering", "Physics Baking", "INFO")

        return {"FINISHED"}
 

class OBJECT_OT_physics_revert_to_main(bpy.types.Operator):
    bl_label = "Revert to Physics Menu"
    bl_idname = "object.physics_revert_to_main"
    bl_description = "Physics baking, click to revert to Physics Menu when it finishes"

    def execute(self, context):
        scene = context.scene

        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except:
            pass

        bpy.ops.object.select_all(action="DESELECT")

        bpy.context.scene.use_preview_range = False
        scene.frame_start = scene.settings.physics_restore_start_frame
        scene.frame_end = scene.settings.physics_restore_end_frame
        scene.settings.confirm_bake_state = False
        scene.settings.bake_running = False

        return {"FINISHED"}

class OBJECT_OT_free_physics(bpy.types.Operator):
    bl_label = "Free Physics"
    bl_idname = "object.free_physics"
    bl_description = "Use Live Physics"

    def execute(self, context):
        scene = context.scene

        active_car = scene.lc.find_selected()

        if not validate_lc_object(active_car.rig_object):
            return {"CANCELLED"}
        
        bpy.context.view_layer.objects.active = active_car.sim_body
        
        multi_edit = scene.settings.edit_all_mode
        cars = []

        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        for active_car in cars:
            rig_object = active_car.rig_object

            if not validate_lc_object(rig_object):
                return {"CANCELLED"}

            # remove bake of simulation nodes
            active_car.sim_wheels.select_set(True)
            active_car.sim_body.select_set(True)

            if not active_car.sim_wheels.select_get() or not active_car.sim_body.select_get():
                log_info(f"Physics could not be set to Free. Could not select: '{active_car.sim_wheels.name}' and/or '{active_car.sim_body.name}'. Please make sure these are not hidden in the outliner and that their parent collections are not disabled or hidden", "OBJECT_OT_execute_physics_bake")
                show_message_box(f"Free Physics were not enabled! Could not select the physics objects for {active_car.collection.name}. More info in the 'System Console'","Physics Change Failed","ERROR",)        
                return {"CANCELLED"}

            switch = rig_object.pose.bones[B_SWITCH_USE_SIMULATION]

            # enable G-Force Debug if it's the first time the user turns on Physics
            if switch.location[1] < 0.5:
                auto_enable_acc_viz = True

            rig_object.pose.bones["bone_Switch_Setup"].location[1] = 1.8
            switch.location[1] = 1
            
            active_car.properties.baked_physics = False
            active_car.properties.mute_physics = False 

            # unmute PostFX to avoid jumpy car when clicking "Bake Physics" 
            rig_object.pose.bones["bone_body_simCTRL"].constraints["PITCH"].enabled = True
            rig_object.pose.bones["bone_body_simCTRL"].constraints["YAW"].enabled = True
            rig_object.pose.bones["bone_body_simCTRL"].constraints["ROLL"].enabled = True

            # prepare file paths
            prepare_cache_physics(active_car)

            # validate cache existence
            physics_filenames = [FILENAME_SIM_BODY, FILENAME_SIM_WHEELS]
            
            for filename in physics_filenames:
                if not validate_cache(active_car, filename):
                    log_info("No cache to free", "Physics Cache")
                    
                    # deselect objects to avoid baking them
                    active_car.sim_wheels.select_set(False)
                    active_car.sim_body.select_set(False)

            #show_message_box("Physics are now LIVE", "Physics", "INFO")
            log_info("Physics were freed. Now using real-time physics.", "OBJECT_OT_free_physics")
        
        if len(bpy.context.selected_objects) > 0:
            try: bpy.ops.object.simulation_nodes_cache_delete(selected=True)
            except: log_info("NOPE, Couldn't find cache folder to delete!", "OBJECT_OT_free_physics")

        bpy.ops.object.select_all(action="DESELECT")
        
        try: active_car.settings.show_acc_viz = auto_enable_acc_viz
        except: pass

        if scene.settings.confirm_bake_state:

            bpy.context.scene.use_preview_range = False
            scene.frame_start = scene.settings.physics_restore_start_frame
            scene.frame_end = scene.settings.physics_restore_end_frame
            scene.settings.confirm_bake_state = False
            scene.settings.bake_running = False
        
        return {"FINISHED"}
    

class OBJECT_OT_disable_physics(bpy.types.Operator):
    bl_label = "Disable Physics"
    bl_idname = "object.disable_physics"
    bl_description = "Remove all physics - Show only the animation"

    def execute(self, context):
        scene = context.scene

        active_car = scene.lc.find_selected()

        if not validate_lc_object(active_car.rig_object):
            return {"CANCELLED"}
        
        bpy.context.view_layer.objects.active = active_car.sim_body

        multi_edit = scene.settings.edit_all_mode
        cars = []

        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        for active_car in cars:
            rig_object = active_car.rig_object

            if not validate_lc_object(rig_object):
                return {"CANCELLED"}

            # remove bake of simulation nodes
            active_car.sim_wheels.select_set(True)
            active_car.sim_body.select_set(True)

            #active_car.sim_wheels.use_simulation_cache = True
            #active_car.sim_body.use_simulation_cache = True

            rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1] = 0

            active_car.properties.baked_physics = False

            # prepare file paths
            prepare_cache_physics(active_car)

            # validate cache existence
            physics_filenames = [FILENAME_SIM_BODY, FILENAME_SIM_WHEELS]
            
            for filename in physics_filenames:
                if not validate_cache(active_car, filename):
                    log_info("No cache to free", "Physics Cache")
                    
                    # deselect objects to avoid baking them
                    active_car.sim_wheels.select_set(False)
                    active_car.sim_body.select_set(False)
            
            log_info("Physics were Disabled", "OBJECT_OT_disable_physics")

        if len(bpy.context.selected_objects) > 0:
            try: bpy.ops.object.simulation_nodes_cache_delete(selected=True)
            except: log_info("NOPE, Couldn't find cache folder to delete!", "OBJECT_OT_disable_physics")

        bpy.ops.object.select_all(action="DESELECT")
        active_car.settings.show_acc_viz = False
        return {"FINISHED"}
    

class OBJECT_OT_mute_physics(bpy.types.Operator):
    bl_label = "Mute Physics"
    bl_idname = "object.mute_physics"
    bl_description = "Mute baked physics temporarily - Show only the animation, but keep the cache"

    def execute(self, context):
        scene = context.scene

        active_car = scene.lc.find_selected()

        if not validate_lc_object(active_car.rig_object):
            return {"CANCELLED"}
        
        bpy.context.view_layer.objects.active = active_car.sim_body

        multi_edit = scene.settings.edit_all_mode
        cars = []

        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        for active_car in cars:
            rig_object = active_car.rig_object
            if not validate_lc_object(rig_object):
                return {"CANCELLED"}

            rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1] = 0    

            active_car.properties.mute_physics = True  
            active_car.settings.show_acc_viz_override = False

            #show_message_box("Physics DISABLED", "Physics", "INFO")
            log_info("Physics were Muted", "OBJECT_OT_mute_physics")

        return {"FINISHED"}
    

class OBJECT_OT_unmute_physics(bpy.types.Operator):
    bl_label = "Unmute Physics"
    bl_idname = "object.unmute_physics"
    bl_description = "Unmute baked physics - Show the cached physics again"

    def execute(self, context):
        scene = context.scene

        active_car = scene.lc.find_selected()

        if not validate_lc_object(active_car.rig_object):
            return {"CANCELLED"}
        
        bpy.context.view_layer.objects.active = active_car.sim_body

        multi_edit = scene.settings.edit_all_mode
        cars = []

        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        for active_car in cars:
            rig_object = active_car.rig_object

            if not validate_lc_object(rig_object):
                return {"CANCELLED"}

            rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1] = 1     

            active_car.properties.mute_physics = False       
            active_car.settings.show_acc_viz_override = True

            #show_message_box("Physics DISABLED", "Physics", "INFO")
            log_info("Physics were Unmuted", "OBJECT_OT_unmute_physics")

        bpy.ops.object.select_all(action="DESELECT")
        return {"FINISHED"}
    

class OBJECT_OT_refresh_physics(bpy.types.Operator):
    bl_label = "Refresh Physics"
    bl_idname = "object.refresh_physics"
    bl_description = "Clears the cache of the Physics to allow a fresh calculation from the current frame forward"

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
            rig_object = active_car.rig_object

            if not validate_lc_object(rig_object):
                return {"CANCELLED"}

            active_car.sim_wheels.select_set(True)
            active_car.sim_body.select_set(True)

            # Fix in case the physics broken because of undo
            try: force_update_geo_nodes(active_car)
            except: log_info("Could not 'force update' geo nodes - Not critical", "OBJECT_OT_refresh_physics")
            
            rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1] = 1
            
            log_info("Physics were Refreshed", "OBJECT_OT_refresh_physics")

        if len(bpy.context.selected_objects) > 0:
            try: bpy.ops.object.simulation_nodes_cache_delete(selected=True)
            except: log_info("NOPE, Couldn't find cache folder to delete!", "OBJECT_OT_refresh_physics")

        active_car.sim_wheels.select_set(False)
        active_car.sim_body.select_set(False)
        
        return {"FINISHED"}