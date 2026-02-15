import bpy

from ..operators.custom_anim_presets import delete_anim_preset, overwrite_anim_preset
from ..operators.rig import unrig_vehicle
from .. data.commands import update_filter_anim_preset
from .. import data
from ..globals import *
 

class WM_OT_delete_anim_preset_confirm(bpy.types.Operator):
    bl_idname = "wm.delete_anim_preset_confirm"
    bl_label = "Delete Animation Preset?"
    #bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):

        delete_anim_preset()

        self.report({'INFO'}, "Deleted Custom Animation Preset")

        # Re-Register "Data" to reload Galleries
        data.unregister()
        data.register()

        update_filter_anim_preset(self, context)

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
    


class WM_OT_overwrite_anim_preset_confirm(bpy.types.Operator):
    bl_idname = "wm.overwrite_anim_preset_confirm"
    bl_label = "Overwrite Animation Preset?"
    #bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):

        overwrite_anim_preset()

        self.report({'INFO'}, "Custom Animation Preset has been Updated")

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
    

class WM_OT_delete_rig_dialog(bpy.types.Operator):
    bl_idname = "wm.delete_rig_dialog"
    bl_label = "Unrig and Delete active Vehicle Rig?"
    #bl_options = {'REGISTER', 'INTERNAL'}

    no_delete_car: bpy.props.BoolProperty(name="Keep Vehicle Model", description="Remove Vehicle Rig, but keep Vehicle Meshes", default=True)
    no_delete_proxy: bpy.props.BoolProperty(name="Keep Vehicle Proxy", description="Remove Vehicle Rig, but keep Vehicle Proxy Meshes", default=False)
    no_delete_path: bpy.props.BoolProperty(name="Keep Driving Path", description="Remove Vehicle Rig, but keep the Driving Path", default=False)
    no_delete_ground: bpy.props.BoolProperty(name="Keep Ground Colliders", description="Remove Vehicle Rig, but keep Ground Colliders", default=False)
    revert_transforms: bpy.props.BoolProperty(name="Revert Transforms", description="Unrig and revert Transforms of the Vehicle to the original transforms before rigging", default=True)


    def execute(self, context):

        unrig_vehicle(no_delete_path = self.no_delete_path, no_delete_ground = self.no_delete_ground, no_delete_car = self.no_delete_car, no_delete_proxy = self.no_delete_proxy, revert_transforms = self.revert_transforms)

        return {'FINISHED'}

    def invoke(self, context, event=None):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        active_car = scene.lc.find_selected()

        layout.prop(self, "no_delete_path")
        if len(context.scene.lc.cars) == 1:
            layout.prop(self, "no_delete_ground")

        layout.separator(factor=0.8)
        
        if not active_car.properties.has_lib_override:
            layout.prop(self, "no_delete_car")

            """coll_name = active_car.name + " Proxy"
            proxy_coll_exists = False
            for coll in scene.collection.children_recursive:
                if coll.name == coll_name:
                    proxy_coll_exists = True
            
            if proxy_coll_exists:
                layout.prop(self, "no_delete_proxy")"""
            
            if self.no_delete_car:
                box = layout.box()
                box.prop(self, "revert_transforms")
        

class WM_OT_bridge_ue_confirm(bpy.types.Operator):
    bl_idname = "wm.bridge_ue_confirm"
    bl_label = "Confirm Bind Pose"

    def execute(self, context):

        bpy.ops.object.bridge_ue()
        
        return {'FINISHED'}

    def invoke(self, context, event=None):
        return context.window_manager.invoke_props_dialog(self)
    
    def cancel(self, context):

        # Revert Garage mode to prepare for animation export
        bpy.context.scene.settings.mode = 'race_mode'

        scene = context.scene
        current_car = scene.lc.find_selected()

        deform_bones = [
            current_car.rig_object.pose.bones[B_BRAKE_DEFORM_RL],
            current_car.rig_object.pose.bones[B_BRAKE_DEFORM_RR],
            current_car.rig_object.pose.bones[B_BRAKE_DEFORM_FL],
            current_car.rig_object.pose.bones[B_BRAKE_DEFORM_FR],
            current_car.rig_object.pose.bones[B_WHEEL_DEFORM_RL],
            current_car.rig_object.pose.bones[B_WHEEL_DEFORM_RR],
            current_car.rig_object.pose.bones[B_WHEEL_DEFORM_FL],
            current_car.rig_object.pose.bones[B_WHEEL_DEFORM_FR],
            current_car.rig_object.pose.bones[B_BODY_DEFORM],
            current_car.rig_object.pose.bones[B_STEERING_DEFORM]
        ]

        for index in range(len(deform_bones)):
            deform_bones[index].constraints["set_bind_pose"].enabled = False

        return {'FINISHED'}
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Current Transform will be the Bind Pose inside UE")
        layout.label(text="Continue Export?")
        
    