import bpy

from .panels import (
        PANEL_PT_interface,
        PANEL_PT_PostFX,
        PANEL_PT_QuickFBX,
        PANEL_PT_BridgeTool,
        PANEL_PT_ProxyTool,
        PANEL_PT_Advanced,
        PANEL_PT_View,
        PANEL_PT_RigSettings,
        PANEL_PT_AdvancedHeadlights,
        PANEL_PT_Skidmarks,
        PANEL_PT_AdvancedPath,
        PANEL_PT_AdvancedCamera,
        PANEL_PT_RigInfo,
        PANEL_PT_Data,
        ADDONPREFERENCES_UserPref,
)
from . import f1_studio_panel
# from .menus import MT_Export     
from .dialogs import(
        WM_OT_delete_rig_dialog,
        WM_OT_delete_anim_preset_confirm,
        WM_OT_overwrite_anim_preset_confirm,
        WM_OT_bridge_ue_confirm,
)

from ..data.properties import is_pro_license


classes_tuple = (
    # MT_Advanced,
    # MT_Export,
    PANEL_PT_interface,
    PANEL_PT_PostFX,
    PANEL_PT_Advanced,
    PANEL_PT_View,
    PANEL_PT_RigSettings,
    PANEL_PT_QuickFBX,
    PANEL_PT_BridgeTool,
    PANEL_PT_ProxyTool,
    PANEL_PT_AdvancedHeadlights,
    PANEL_PT_Skidmarks,
    PANEL_PT_AdvancedPath,
    PANEL_PT_AdvancedCamera,
    PANEL_PT_RigInfo,
    PANEL_PT_Data,
    ADDONPREFERENCES_UserPref,
    f1_studio_panel.PANEL_PT_F1_Studio,
    WM_OT_delete_rig_dialog,
    WM_OT_delete_anim_preset_confirm,
    WM_OT_overwrite_anim_preset_confirm,
    WM_OT_bridge_ue_confirm,
)

classes = list(classes_tuple)

if is_pro_license:
    classes.remove(PANEL_PT_QuickFBX)
else:
    classes.remove(PANEL_PT_BridgeTool)
    classes.remove(PANEL_PT_ProxyTool)
    


def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            try:
                bpy.utils.unregister_class(cls)
                bpy.utils.register_class(cls)
            except Exception as e:
                print(f"Warning: Could not register {cls.__name__}: {e}")

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
