import bpy

from ..ui.utils import show_message_box
from ..globals import FILENAME_DRIVINGPATH, B_SWITCH_USE_SIMULATION
from ..utils.errors.path_errors import path_error_messages, PathErrorTypes
from ..utils.functions import get_active_curve_length
from ..utils.validations import validate_lc_object
from ..logger import log_error, log_debug

class OBJECT_OT_refresh_path_len(bpy.types.Operator):
    bl_label = "Update Driving Path"
    bl_idname = "object.refresh_path_len"
    bl_description = (
        "Let Blender calculate the new length of the path to be used in the rig"
    )

    def execute(self, context):
        scene = context.scene
        
        active_car = scene.lc.find_selected()
        multi_edit = scene.settings.edit_all_mode
        cars = []

        if not validate_lc_object(active_car.driving_path):
            return {"CANCELLED"}

        # make sure there is an active object in the scene otherwise bpy.ops will fail
        if bpy.context.active_object == None:
            active_car.driving_path.select_set(True)
            bpy.context.view_layer.objects.active = active_car.driving_path
        
        if multi_edit: cars = scene.lc.cars
        else: cars.append(active_car)

        for active_car in cars:
            rig_object = active_car.rig_object
            driving_path = active_car.driving_path

            if not validate_lc_object(active_car.driving_path):
                return {"CANCELLED"}
            
            # Create undo point
            bpy.ops.ed.undo_push()
            
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
                driving_path_len = get_active_curve_length(driving_path)

                if driving_path_len == -1: #If it failed
                    path_error_messages(PathErrorTypes.CALCULATE_PATH_LENGTH)
                    return {"CANCELLED"}

                driving_path.data.path_duration = int(driving_path_len)

                if (rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1] > 0.5 and active_car.properties.baked_physics):
                    show_message_box(
                        "The length of the driving path was updated. Physics bake is outdated.",
                        "Car Rig", "INFO",
                    )

                if driving_path.data.path_duration < 10:
                    """Short path"""
                    log_debug("Short path! - Will change expressions", "OBJECT_OT_refresh_path_len")
                    active_car.rig_object.data.animation_data.drivers[63].driver.expression = '1*mute    if  (dist < 2.3 and dist > 1.7   or   airbourne > 0.5   or drifting >0.5) and dist_02 > 0.001       else 0'
                    active_car.rig_object.data.animation_data.drivers[65].driver.expression = '1*mute    if  (dist < 2.3 and dist > 1.7   or   airbourne > 0.5   or drifting >0.5) and dist_02 > 0.001       else 0'
                    active_car.rig_object.data.animation_data.drivers[66].driver.expression = '0    if  dist < 2.3 and dist > 1.7   or   airbourne > 0.5   or drifting >0.5       else 1'
                    show_message_box(
                        "Driving Path is very short. LC works best with longer paths.",
                        "Uncommon Driving Path", "INFO",
                    )

                active_car.path_changed = True
            except:
                log_debug("Didn't successfully update driving path!", "OBJECT_OT_refresh_path_len")
                show_message_box(
                        "Couldn't update driving path. Make sure the Driving Path is not hidden or deleted",
                        "Driving Path issue", "INFO",
                    )
                return {"CANCELLED"}

        return {"FINISHED"}



