import bpy

from . import animation, camera, custom_anim_presets, rig, append, physics, jump, extra, path, exports, speed_segment, lap_from_json, F1_HiFi_Baker_Pro, f1_pipeline
from ..data.properties import is_pro_license

if is_pro_license:
    from ...pro_features import bridge_tool_pro, proxy_model_pro, link_pro, panels_pro
    from ...pro_features.export_datasmith import datasmith

classes_tuple = (
    animation.OBJECT_OT_prepare_animation,
    path.OBJECT_OT_refresh_path_len,
    lap_from_json.OBJECT_OT_apply_lap_from_json,
    extra.OBJECT_OT_fix_spin,
    extra.OBJECT_OT_setup_tire_deform,
    extra.OBJECT_OT_remove_tire_deform,
    exports.OBJECT_OT_quick_export,
    exports.OBJECT_OT_quick_exportUE,
    exports.OBJECT_OT_quick_export_blend,
    extra.OBJECT_OT_reset_props,
    extra.OBJECT_OT_reset_postfx,
    physics.OBJECT_OT_bake_physics,
    physics.OBJECT_OT_execute_physics_bake,
    physics.OBJECT_OT_free_physics,
    physics.OBJECT_OT_disable_physics,
    physics.OBJECT_OT_physics_revert_to_main,
    physics.OBJECT_OT_refresh_physics,
    physics.OBJECT_OT_mute_physics,
    physics.OBJECT_OT_unmute_physics,
    jump.OBJECT_OT_prepare_jump,
    rig.OBJECT_OT_rig_car,
    rig.OBJECT_OT_delete_rig,
    append.OBJECT_OT_append_search_select_file,
    append.OBJECT_OT_append_from_file,
    custom_anim_presets.OBJECT_OT_save_anim_preset,
    custom_anim_presets.OBJECT_OT_remove_anim_preset,
    custom_anim_presets.OBJECT_OT_edit_anim_preset,
    extra.OBJECT_OT_rename_object_operators,
    extra.OBJECT_OT_calculate_wheel_diameter,
    extra.OBJECT_OT_reload_headlight_tex,
    extra.OBJECT_OT_reload_all_headlight_tex,
    extra.OBJECT_OT_unload_headlight_tex,
    extra.OBJECT_OT_bake_skidmarks,
    extra.OBJECT_OT_free_skidmarks,
    extra.OBJECT_OT_find_selected_car,
    extra.OBJECT_OT_pick_selected_path,
    extra.OBJECT_OT_revert_vehicle_add,
    extra.OBJECT_OT_revert_vehicle_edit,
    extra.OBJECT_OT_refresh_speedometer,
    extra.OBJECT_OT_update_vehicle_rig,
    extra.OBJECT_OT_add_ground_colliders,
    extra.OBJECT_OT_remove_ground_colliders,
    extra.OBJECT_OT_remove_all_ground_colliders,
    extra.OBJECT_OT_install_lib,
    extra.OBJECT_OT_select_driving_path,
    extra.OBJECT_OT_refresh_cache_dirs,
    camera.CAMERAS_OT_create_follow_cam,
    camera.CAMERAS_OT_create_mounted_cam,
    speed_segment.OBJECT_OT_speed_segment_tool,
    speed_segment.OBJECT_OT_speed_segment_apply_speed,
    speed_segment.OBJECT_OT_speed_segment_apply_offset_time,
    F1_HiFi_Baker_Pro.F1_OT_InstallDeps,
    f1_pipeline.OBJECT_OT_f1_generate_scene,
    f1_pipeline.OBJECT_OT_f1_add_lap_to_queue,
    f1_pipeline.OBJECT_OT_f1_remove_lap,
    f1_pipeline.OBJECT_OT_f1_clear_queue,
    f1_pipeline.OBJECT_OT_f1_save_alignment,
    f1_pipeline.OBJECT_OT_f1_load_alignment,
    f1_pipeline.OBJECT_OT_f1_reset_alignment,
    f1_pipeline.OBJECT_OT_f1_diagnose_path,
    f1_pipeline.OBJECT_OT_f1_correct_path,
    f1_pipeline.OBJECT_OT_f1_auto_correct_path,
    f1_pipeline.OBJECT_OT_f1_clear_diagnostic,
    f1_pipeline.OBJECT_OT_f1_flatten_z,
    f1_pipeline.OBJECT_OT_f1_snap_z_to_track,


)

classes = list(classes_tuple)


if is_pro_license:
    classes.append(bridge_tool_pro.OBJECT_OT_bridge_usd)
    classes.append(bridge_tool_pro.OBJECT_OT_bridge_abc)
    classes.append(bridge_tool_pro.OBJECT_OT_bridge_blend)
    classes.append(bridge_tool_pro.OBJECT_OT_bridge_glb)
    classes.append(bridge_tool_pro.OBJECT_OT_bridge_gltf)
    classes.append(bridge_tool_pro.OBJECT_OT_bridge_fbx)
    classes.append(bridge_tool_pro.OBJECT_OT_bridge_ue)
    classes.append(bridge_tool_pro.OBJECT_OT_bridge_datasmith)
    classes.append(bridge_tool_pro.OBJECT_OT_bridge_file_info)
    classes.append(bridge_tool_pro.OBJECT_OT_set_bind_pose)
    classes.append(datasmith.OBJECT_OT_export_datasmith)
    classes.append(proxy_model_pro.OBJECT_OT_generate_proxy)
    classes.append(proxy_model_pro.OBJECT_OT_load_proxy)
    classes.append(panels_pro.OBJECT_OT_show_addon_prefs)
    classes.append(link_pro.OBJECT_OT_link_search_select_file)
    classes.append(link_pro.OBJECT_OT_link_from_file) 
    classes.append(link_pro.OBJECT_OT_make_lib_override) 
    classes.append(link_pro.OBJCET_OT_cancel_lib_override) 
    classes.append(link_pro.OBJCET_OT_make_lib_override_path) 
    
    


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    f1_pipeline.register()

def unregister():
    f1_pipeline.unregister()
    for cls in classes:
        bpy.utils.unregister_class(cls)