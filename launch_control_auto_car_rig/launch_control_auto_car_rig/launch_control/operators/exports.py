import bpy
import os

from ..utils.functions import get_collection_by_name, link_collection, unlink_collection_all
from ..utils.resources import get_blend_name_clean
from mathutils import Matrix
from math import pi

from ..globals import *
from ..utils.errors.exceptions import RigCollectionNotFound
from ..utils.errors.export_errors import ExportErrorTypes, export_error_messages
from ..utils.validations import validate_lc_object
from ..ui.utils import show_message_box
from ..logger import log_info, log_debug, log_error


def build_filepath(export_path, is_unreal, name, extension):
    if export_path == "//":
        blend_DIR = bpy.path.abspath("//")
        file_path = os.path.join(blend_DIR, name + "_LC" + extension)

        if is_unreal:
            file_path = os.path.join(blend_DIR, '_' + name + "_LC_UE5" + extension)
    else:
        file_path = bpy.path.abspath(export_path)

    if not file_path.endswith(extension):
        file_path = os.path.join(file_path + '_' + name + extension)

    return file_path


def nla_subframes_bake(subframes):
    scene = bpy.context.scene

    revert_frame_map_old = scene.render.frame_map_old
    revert_frame_map_new = scene.render.frame_map_new

    scene.render.frame_map_old = 100
    scene.render.frame_map_new = 100 * subframes

    delta_frames = scene.frame_end - scene.frame_start

    frame_start = scene.frame_start * subframes
    frame_end = frame_start + delta_frames * subframes


    bpy.ops.nla.bake(
        frame_start = frame_start,
        frame_end = frame_end,
        only_selected = True,
        visual_keying = True,
        clear_constraints = True,
        clear_parents = True,
        bake_types = {"OBJECT"},
        channel_types = {'LOCATION', 'ROTATION', 'SCALE', 'BBONE'},
    )


    anim_time_scale = 1/subframes

    for obj in bpy.context.selected_objects:
        if obj.animation_data and obj.animation_data.action:
            action = obj.animation_data.action

            # Iterate through all FCurves
            for fcurve in action.fcurves:
                # Iterate through Keyframes
                for keyframe in fcurve.keyframe_points:
                    # Scale the time
                    keyframe.co.x *= anim_time_scale
                
                fcurve.update()

    scene.render.frame_map_old = revert_frame_map_old
    scene.render.frame_map_new = revert_frame_map_new

    return None




class OBJECT_OT_quick_export(bpy.types.Operator):
    bl_label = "FBX"
    bl_idname = "object.quick_export"
    bl_description = "Quickly export an FBX to Omniverse, Cinema 4D, Maya, Max or another DCC that supports FBX"

    is_unreal: bpy.props.BoolProperty(name="Check For Unreal", default=False)

    def execute(self, context):
        scene = context.scene
        multi_edit = scene.settings.edit_all_mode
        current_car = scene.lc.find_selected()

        cars_to_export = []
        if scene.settings.export_all_cars or multi_edit: 
            cars_to_export.extend(scene.lc.cars)
        else:
            cars_to_export.append(current_car)

        if current_car.settings.export_path == "//" and not bpy.data.is_saved:
            export_error_messages(ExportErrorTypes.NOT_SAVED)
            return {"CANCELLED"}

        # Create undo point
        bpy.ops.ed.undo_push()
        restore_frame = scene.frame_current

        for car in cars_to_export:            
            try: 
                car.get_rig_collection()
            except RigCollectionNotFound as e: 
                e.show_error_message(title="Quick Export")
                return {"CANCELLED"}
            
            car_name = car.collection.name
            rig_object = car.rig_object

            # Make sure something is selected and we are in object mode
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except:
                pass
            bpy.ops.object.select_all(action="DESELECT")

            # Ready to go
            restore_frame = scene.frame_current
            scene.frame_set(0)

            # Apply transforms in activated
            if car.settings.apply_transforms:
                for child in rig_object.children:
                    for sub_child in child.children_recursive:

                        if not validate_lc_object(sub_child):
                            return {"CANCELLED"}
                        
                        sub_child.select_set(True)

                bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
                bpy.ops.object.select_all(action="DESELECT")


            if not validate_lc_object(rig_object):
                return {"CANCELLED"}
            
            rig_object.select_set(True)
            
            objects_not_selectable = []

            if not scene.settings.export_anim_only:
                for child in rig_object.children_recursive:
                    try: child.select_set(True)
                    except: objects_not_selectable.append(child.name)

                if car.settings.include_ground or scene.settings.include_ground_for_all:
                    col = bpy.data.collections["GroundDetection"]
                    for obj in col.objects:
                        try: obj.select_set(True)
                        except: objects_not_selectable.append(obj.name)

                col = bpy.data.collections["ExportObjects"]
                for obj in col.objects:
                    try: obj.select_set(True)
                    except: objects_not_selectable.append(obj.name)
            
            if car.settings.speedometer:
                collection_name = car.collection.name
                speedometer = scene.objects[FILENAME_SPEEDOMETER + ("_" + collection_name)]
                unit = scene.objects[FILENAME_UNIT + ("_" + collection_name)]
                unit_flipped = scene.objects[FILENAME_UNIT_FLIPPED + ("_" + collection_name)]
                speed_calculator = car.speed_calculator
                
                try:
                    speedometer.select_set(False)
                    unit.select_set(False)
                    unit_flipped.select_set(False)
                    speed_calculator.select_set(False)
                except:
                    pass

            file_path = build_filepath(current_car.settings.export_path, self.is_unreal, car_name, ".fbx")

            anim_step = 1/scene.settings.subframes

            try:
                bpy.ops.export_scene.fbx(
                    filepath=file_path,
                    filter_glob="*.fbx",
                    use_selection=True,
                    global_scale = 1,
                    bake_anim=scene.settings.include_anim,
                    add_leaf_bones=False,
                    use_armature_deform_only=True,
                    bake_anim_use_all_bones=True,
                    bake_anim_use_nla_strips=False,
                    bake_anim_use_all_actions=False,
                    bake_anim_step=anim_step,
                    bake_anim_simplify_factor=0,
                )

                if len(objects_not_selectable) > 0:
                    show_message_box(
                        "Animation exported to: " + file_path + " - Some objects could not be selected and exported (see list in console)", "Quick Export", "INFO"
                    )
                    log_info(f"Animation Exported with missing objects: {objects_not_selectable}", "OBJECT_OT_quick_exportUE")

                else:
                    show_message_box(
                        "Animation exported to: " + file_path, "Quick Export", "INFO"
                    )
            except:
                export_error_messages(ExportErrorTypes.NOT_FOUND)
                bpy.ops.object.select_all(action="DESELECT")
                # return {"CANCELLED"}

        scene.frame_set(restore_frame)
        return {"FINISHED"}


class OBJECT_OT_quick_exportUE(bpy.types.Operator):
    bl_label = "FBX for UE5"
    bl_idname = "object.quick_export_ue"
    bl_description = "Quickly export an FBX to Unreal Engine. Please Note: This will always export with frame 0 as 'start frame'"

    def getmat(self, bone, active, context, ignoreparent):
        """Helper function for visual transform copy,
        gets the active transform in bone space
        """
        obj_bone = bone.id_data
        obj_active = active.id_data
        data_bone = obj_bone.data.bones[bone.name]
        # all matrices are in armature space unless commented otherwise
        active_to_selected = obj_bone.matrix_world.inverted() @ obj_active.matrix_world
        active_matrix = active_to_selected @ active.matrix
        otherloc = active_matrix  # final 4x4 mat of target, location.
        bonemat_local = data_bone.matrix_local.copy()  # self rest matrix
        if data_bone.parent:
            parentposemat = obj_bone.pose.bones[data_bone.parent.name].matrix.copy()
            parentbonemat = data_bone.parent.matrix_local.copy()
        else:
            parentposemat = parentbonemat = Matrix()
        if parentbonemat == parentposemat or ignoreparent:
            newmat = bonemat_local.inverted() @ otherloc
        else:
            bonemat = parentbonemat.inverted() @ bonemat_local

            newmat = bonemat.inverted() @ parentposemat.inverted() @ otherloc
        return newmat

    def rotcopy(self, item, mat):
        """Copy rotation to item from matrix mat depending on item.rotation_mode"""
        if item.rotation_mode == 'QUATERNION':
            item.rotation_quaternion = mat.to_3x3().to_quaternion()
        elif item.rotation_mode == 'AXIS_ANGLE':
            rot = mat.to_3x3().to_quaternion().to_axis_angle()    # returns (Vector((x, y, z)), w)
            axis_angle = rot[1], rot[0][0], rot[0][1], rot[0][2]  # convert to w, x, y, z
            item.rotation_axis_angle = axis_angle
        else:
            item.rotation_euler = mat.to_3x3().to_euler(item.rotation_mode)

    def pVisLocExec(self, bone, active, context):
        bone.location = self.getmat(bone, active, context, False).to_translation()

    def pVisRotExec(self, bone, active, context):
        obj_bone = bone.id_data
        self.rotcopy(bone, self.getmat(bone, active,
                            context, not obj_bone.data.bones[bone.name].use_inherit_rotation))

    def nozeros(self, vec, decimal_points = 2 ):
        ''' Returns True if none of the elements in the provided vector vec
            equate to zero when rounded by the provided number of decimal_points
        '''

        return any( round( v, decimal_points ) for v in vec )

    def execute(self, context):
        scene = context.scene
        multi_edit = scene.settings.edit_all_mode
        current_car = scene.lc.find_selected()

        cars_to_export = []
        if scene.settings.export_all_cars or multi_edit: 
            cars_to_export.extend(scene.lc.cars)
        else:
            cars_to_export.append(current_car)

        # Create undo point
        bpy.ops.ed.undo_push()

        for car in cars_to_export:
            try: 
                car.get_rig_collection()
            except RigCollectionNotFound as e: 
                e.show_error_message(title="Quick Export")
                return {"CANCELLED"} 

            car_name = car.collection.name
            rig_object = car.rig_object

            # Export messes up when frame is not 0
            if scene.frame_current != 0:
                log_error("Frame must be 0", "OBJECT_OT_quick_exportUE")
                show_message_box(
                    "Please set 'Current Frame' to 0 and try exporting again (Move playhead to frame 0)",
                    "Unreal Export - Animation Issue",
                    "ERROR",
                )
                return {"CANCELLED"}

            # Set start frame to 0 temporarily
            start_frame_restore = scene.frame_start
            scene.frame_start = 0

            # Fix rotations so they are 0
            decimal_points = 2
            index = 0
            for v in car.driving_path.rotation_euler:
                if round(v, decimal_points) == round(-pi*2, decimal_points) or round(v, decimal_points) == round(pi*2, decimal_points):
                    current_car.driving_path.rotation_euler[index] = 0
                index += 1


            if self.nozeros(car.driving_path.rotation_euler):
                log_error("Driving Path has non-applied rotations.", "OBJECT_OT_quick_exportUE")
                show_message_box(
                    "'DrivingPath' has non-applied rotations. To avoid issues, please select the 'DrivingPath' object and apply rotations using 'Ctrl+A -> Rotation'",
                    "Unreal Export - Driving Path",
                    "ERROR",
                )
                return {"CANCELLED"}


            try:
                bpy.ops.object.quick_export(is_unreal=1)  # Launch normal export
            except:
                export_error_messages(ExportErrorTypes.NOT_FOUND)
                bpy.ops.object.select_all(action="DESELECT")
                # return {"CANCELLED"} # because if multiple let it continue

        
        return {"FINISHED"}

    
class OBJECT_OT_quick_export_blend(bpy.types.Operator):
    bl_label = "Blend Scene File"
    bl_idname = "object.quick_export_blend"
    bl_description = "Export a blend scene file with baked Animations and Physics for rendering on renderfarms. - The 'Launch Control Collection' will not be included in baked file"

    def execute(self, context):
        scene = context.scene
        multi_edit = scene.settings.edit_all_mode
        current_car = scene.lc.find_selected()

        cars_to_export = []
        """if scene.settings.export_all_cars or multi_edit: 
            cars_to_export.extend(scene.lc.cars)
        else:
            cars_to_export.append(current_car)"""
        cars_to_export.extend(scene.lc.cars)

        if current_car.settings.export_path == "//" and not bpy.data.is_saved:
            export_error_messages(ExportErrorTypes.NOT_SAVED)
            return {"CANCELLED"}

        # Create undo point
        bpy.ops.ed.undo_push()

        # Make sure we are in object mode
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except:
            pass
    
        bpy.ops.object.select_all(action="DESELECT")

        objects_not_selectable = []


        for car in cars_to_export:
            try: 
                car.get_rig_collection()
            except RigCollectionNotFound as e: 
                e.show_error_message(title="Quick Export")
                return {"CANCELLED"} 
            
            rig_object = car.rig_object

            if not scene.settings.export_anim_only:
                for child in rig_object.children_recursive:
                    try: child.select_set(True)
                    except: objects_not_selectable.append(child.name)

                if car.settings.include_ground or scene.settings.include_ground_for_all:
                    col = bpy.data.collections["GroundDetection"]
                    for obj in col.objects:
                        try: obj.select_set(True)
                        except: objects_not_selectable.append(obj.name)

                col = bpy.data.collections["ExportObjects"]
                for obj in col.objects:
                    try: obj.select_set(True)
                    except: objects_not_selectable.append(obj.name)
            
            if car.settings.speedometer:
                collection_name = car.collection.name
                speedometer = scene.objects[FILENAME_SPEEDOMETER + ("_" + collection_name)]
                unit = scene.objects[FILENAME_UNIT + ("_" + collection_name)]
                unit_flipped = scene.objects[FILENAME_UNIT_FLIPPED + ("_" + collection_name)]
                speed_calculator = car.speed_calculator
                
                try:
                    speedometer.select_set(False)
                    unit.select_set(False)
                    unit_flipped.select_set(False)
                    speed_calculator.select_set(False)
                except:
                    pass

        file_name = (get_blend_name_clean() + "_baked")
        file_path = build_filepath(current_car.settings.export_path, False, file_name, ".blend")

        # Bake object animation
        try:
            nla_subframes_bake(scene.settings.subframes)

        except:
            show_message_box("Export failed - Could not bake all objects", "Quick Export", "ERROR")
            log_info(f"Could not bake all objects", "OBJECT_OT_quick_blend")
            bpy.ops.object.select_all(action="DESELECT")
            bpy.ops.ed.undo_push()
            bpy.ops.ed.undo()
            return {"CANCELLED"}

        ground_detect_coll = bpy.data.collections["GroundDetection"]
        unlink_collection_all(ground_detect_coll)
        link_collection(ground_detect_coll, scene.collection)

        lc_collection = get_collection_by_name(COLLECTIONNAME_ADDON, scene.collection)
        scene.collection.children.unlink(lc_collection)

        for car in scene.lc.cars:
            if car.rig_collection is not None:
                try: scene.collection.children.unlink(car.rig_collection)
                except: pass
        
        for coll in bpy.data.collections:
            if not coll.users:
                bpy.data.collections.remove(coll)
                    
                    
        try: 
            # Save data to desired path
            bpy.ops.wm.save_as_mainfile(filepath=file_path, copy=True)

            # Undo the scene deletion
            bpy.ops.ed.undo_push()
            bpy.ops.ed.undo()
            if len(objects_not_selectable) > 0:
                show_message_box(
                    "Animation exported to: " + file_path + " - Some objects could not be selected and exported (see list in console)", "Quick Export", "INFO"
                )
                log_info(f"Animation Exported with missing objects: {objects_not_selectable}", "OBJECT_OT_quick_exportUE")

            else:
                show_message_box(
                    "Baked Blender Scene exported to: " + file_path, "Quick Export", "INFO"
                )
        except:
            export_error_messages(ExportErrorTypes.BLEND_NOT_FOUND)
            bpy.ops.object.select_all(action="DESELECT")
            bpy.ops.ed.undo_push()
            bpy.ops.ed.undo()
            return {"CANCELLED"}
            
        return {"FINISHED"}


