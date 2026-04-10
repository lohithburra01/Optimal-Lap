import bpy

from ..data.commands import reveal_camera_hooks
from .low_level import set_parent_bone_keep_transform
from ..utils.functions import find_area
from ..utils.validations import validate_lc_object
from ..ui.utils import show_message_box
from ..logger import log_info, log_debug, log_error

from ..globals import (
    B_BODY_DEFORM,
    B_HOOK_CAM_FOLLOW,
    B_HOOK_CAM_MOUNTED,
)

def add_camera_from_view(context, name):
    area = find_area('VIEW_3D')
    if area is None:
        self.report({"WARNING"},"VIEW_3D not found.")
        return
    
    space3d = context.area.spaces.active
    
    r3d = context.area.spaces.active.region_3d
    view_matrix = r3d.view_matrix.inverted()
    loc = view_matrix.to_translation()
    rot = view_matrix.to_euler()
    focal_length = context.space_data.lens
    context.space_data.lock_camera = True

    # Get or create camera data
    camera_data = bpy.data.cameras.get(name)
    if not camera_data:
        camera_data = bpy.data.cameras.new(name=name)

    # Get or create camera object
    camera_object = bpy.data.objects.get(name)

    # Remove camera if it exists to avoid matrix issues due to parenting
    if camera_object:
        bpy.data.objects.remove(camera_object, do_unlink=True)
        camera_object = None

    camera_object = bpy.data.objects.new(name, camera_data)
    context.scene.collection.objects.link(camera_object)

    # Set camera properties
    camera_object.location = loc
    camera_object.rotation_euler = rot
    camera_object.data.lens = focal_length
    camera_object.data.shift_x = r3d.view_camera_offset[0]
    camera_object.data.shift_y = r3d.view_camera_offset[1]

    return camera_object


class CAMERAS_OT_create_follow_cam(bpy.types.Operator):
    bl_idname = "object.create_follow_cam"
    bl_label = "Create Follow Camera"
    bl_description = "Create a camera from view which is following the general position of the Vehicle, but not being affected by the physics on the vehicle"


    def execute(self, context):  
        scene = context.scene
        active_car = scene.lc.find_selected()

        if not validate_lc_object(active_car.rig_object):
            return {"CANCELLED"}

        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        rig_object = active_car.rig_object

        #VALIDATE IF RIG COLLECTION IS HERE
        
        context.view_layer.objects.active = rig_object

        # Enable specific layers for the CarRig
        try:
            rig_object.data.collections["Camera Hooks"].is_visible = True
        except:
            #Fallback for LC 1.5
            rig_object.data.collections["Layer 19"].is_visible = True

        follow_rig_bone = rig_object.data.bones.get(B_HOOK_CAM_FOLLOW)
        mounted_bone = rig_object.data.bones.get(B_HOOK_CAM_MOUNTED)

        if not follow_rig_bone or not mounted_bone:
            show_message_box(f"Could not find camera hook bones. Rig the car again to generate these bones","Camera FX","ERROR",)
            log_error("Camera hook bones removed!", "Create Cameras")
            return{'CANCELLED'}

        # Add cameras
        collection_name = active_car.collection.name
        follow_rig_cam = add_camera_from_view(context, f"Follow Cam {collection_name}")

        prev_mode = context.active_object.mode

        # Parent cameras to bones
        set_parent_bone_keep_transform(follow_rig_cam, follow_rig_bone, rig_object)

        context.scene.camera = follow_rig_cam

        bpy.ops.object.mode_set(mode=prev_mode)
        context.view_layer.objects.active = follow_rig_cam

        # Set 3D view to camera perspective
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces[0].region_3d.view_perspective = 'CAMERA'
                break

        body_deform = rig_object.pose.bones.get(B_BODY_DEFORM)
        rig_object.data.bones.active = body_deform.bone
        bpy.ops.view3d.view_selected(use_all_regions=False)

        active_car.settings.show_camera_hooks = True

        show_message_box(f"Follow Cam added to '{active_car.collection.name}'.","Camera FX","INFO",)

        context.space_data.lock_camera = False 
        return {'FINISHED'}

class CAMERAS_OT_create_mounted_cam(bpy.types.Operator):
    bl_idname = "object.create_mounted_cam"
    bl_label = "Create Mounted Camera"
    bl_description = "Create a camera from view which is mounted on the Vehicle. Similar to a 'GoPro' angle or a child-of constraint in Blender"


    def execute(self, context):  
        scene = context.scene
        active_car = scene.lc.find_selected()

        if not validate_lc_object(active_car.rig_object):
            return {"CANCELLED"}

        for obj in bpy.context.selected_objects:
            obj.select_set(False)

        rig_object = active_car.rig_object

        #VALIDATE IF RIG COLLECTION IS HERE
        
        context.view_layer.objects.active = rig_object

        # Enable specific layers for the CarRig
        try:
            rig_object.data.collections["Camera Hooks"].is_visible = True
        except:
            #Fallback for LC 1.5
            rig_object.data.collections["Layer 19"].is_visible = True

        follow_rig_bone = rig_object.data.bones.get(B_HOOK_CAM_FOLLOW)
        mounted_bone = rig_object.data.bones.get(B_HOOK_CAM_MOUNTED)

        if not follow_rig_bone or not mounted_bone:
            show_message_box(f"Could not find camera hook bones. Rig the car again to generate these bones","Camera FX","ERROR",)
            log_error("Camera hook bones removed!", "Create Cameras")
            return{'CANCELLED'}

        # Add cameras
        collection_name = active_car.collection.name
        mounted_cam = add_camera_from_view(context, f"Mounted Cam {collection_name}")

        prev_mode = context.active_object.mode

        # Parent cameras to bones
        set_parent_bone_keep_transform(mounted_cam, mounted_bone, rig_object)

        context.scene.camera = mounted_cam

        bpy.ops.object.mode_set(mode=prev_mode)
        context.view_layer.objects.active = mounted_cam

        # Set 3D view to camera perspective
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces[0].region_3d.view_perspective = 'CAMERA'
                break

        body_deform = rig_object.pose.bones.get(B_BODY_DEFORM)
        rig_object.data.bones.active = body_deform.bone
        bpy.ops.view3d.view_selected(use_all_regions=False)

        active_car.settings.show_camera_hooks = True

        show_message_box(f"Mounted Cam added to '{active_car.collection.name}'.","Camera FX","INFO",)

        context.space_data.lock_camera = False 
        return {'FINISHED'}



