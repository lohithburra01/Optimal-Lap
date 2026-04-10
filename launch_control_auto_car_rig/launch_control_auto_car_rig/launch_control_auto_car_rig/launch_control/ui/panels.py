import bpy
import numpy as np

from ..operators.physics import * 
from ..operators.rig import *
from ..operators.append import *
from ..operators.extra import *
from ..operators.animation import *
from ..operators.jump import *
from ..operators.physics import *
from ..operators.path import *
from ..operators.exports import *
from ..operators.camera import *
from ..operators.speed_segment import *
from ..operators import f1_bridge
from ..operators.lap_from_json import OBJECT_OT_apply_lap_from_json
from ..operators.append import appendable_cars
from ..operators.custom_anim_presets import OBJECT_OT_save_anim_preset, OBJECT_OT_remove_anim_preset, OBJECT_OT_edit_anim_preset
from ..data.properties import is_pro_license

if is_pro_license:
    from ...pro_features.panels_pro import OBJECT_OT_show_addon_prefs, show_cad_setup, show_bridge_tool, show_proxy_tool, show_link_from_file, add_anim_preset_lib_path
    from ...pro_features.link_pro import OBJECT_OT_make_lib_override, OBJCET_OT_make_lib_override_path


from .utils import label_multiline

SMALL = 0.2
MEDIUM = 0.4
LARGE = 0.8

class PANEL_PT_interface(bpy.types.Panel):
    bl_label = "Launch Control (Lap from JSON)"
    bl_idname = "PANEL_PT_interface"
    bl_category = "Launch Control (Lap from JSON)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def cubic_bezier(self, t, p0, p1, p2, p3):
        return (1-t)**3 * p0 + 3*(1-t)**2*t * p1 + 3*(1-t)*t**2 * p2 + t**3 * p3
    

    def get_slope(self, p1, p2):
            
            try: slope = (p2[1]-p1[1]) / (p2[0]-p1[0])
            except: slope = 0
            
            return slope
        
    def get_speed(self, slope):
        
        fps = bpy.context.scene.render.fps
        
        m_per_frame = slope
        m_per_sec = (m_per_frame*fps)
        kmh = m_per_sec*3.6
        
        return kmh

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        multi_edit = scene.settings.edit_all_mode
        speed_segments_running = scene.settings.speed_segments_running
        garage_mode = False
        if scene.settings.mode == "garage_mode":
            garage_mode = True

        addon_root = ".".join(__package__.split(".")[:-2])
        addon_preferences = context.preferences.addons[addon_root].preferences

        selected_collection = scene.car_collection
        vehicle_source = scene.settings.vehicle_source

        # Title 1: VEHICLE SELECTION & RIG
        layout = self.layout
        split = layout.split(factor=0.70)
        col_1 = split.column()
        col_2 = split.column()

        col_1.label(text="Select Vehicle", icon="AUTO")

        if not selected_collection and addon_preferences.show_vehicle_gallery:

            if scene.car_collection_previous is not None:
                col_2.operator(OBJECT_OT_revert_vehicle_edit.bl_idname, text="", icon="LOOP_BACK")

            row = layout.row()
            row.prop(scene.settings, "vehicle_source", expand=True)
            row.enabled = not scene.settings.file_linking_state  # disable if linking is in progress

            
            if vehicle_source == 'gallery':

                row = layout.row()
                row.template_icon_view(
                    context.window_manager,
                    "vehicle_presets",
                    show_labels=True,
                    scale=8,
                )

                vehicle_preset_name = os.path.splitext(bpy.data.window_managers["WinMan"].vehicle_presets)[0]
                
                if "Add More" in vehicle_preset_name:
                    row = layout.row()
                    op = row.operator(OBJECT_OT_install_lib.bl_idname, text='Install .lcl', icon='IMPORT')
                    op.asset_type = "VEHICLE"

                    row = layout.row()
                    op = row.operator('wm.url_open', text='Get Packs', icon='URL')
                    op.url = 'https://launch-control.org/product-category/asset-packs/'

                    

                else:
                    #row = layout.row(align=True)
                    #row.prop(scene, "car_collection", text="User Vehicle")

                    if "LC Porsche" in vehicle_preset_name or "LC Ford Mustang" in vehicle_preset_name:
                        row = layout.row(align=True)
                        layout = self.layout
                        split = layout.split(factor=0.65)
                        sponsor_col_1 = split.column()
                        sponsor_col_2 = split.column()
                        sponsor_col_1.label(text="Model by Sven Giera", icon="FUND")
                        op = sponsor_col_2.operator('wm.url_open', text='More Info')
                        op.url = 'https://www.behance.net/svengiera'

                    row = layout.row(align=True)
                    row.operator(OBJECT_OT_rig_car.bl_idname, text='Add Model', icon="PLUS")
                    op = row.operator('wm.url_open', text='', icon='HELP')
                    op.url = 'https://launch-control-documentation.readthedocs.io/en/latest/launch-control-core.html#gallery-vehicle'
            

            elif vehicle_source == 'append':

                row = layout.row()
                row.label(text="Append Rigged Vehicle into this file")

                row = layout.row()
                row.prop(scene.settings, "append_path", text="")

                row = layout.row()
                row.operator(OBJECT_OT_append_search_select_file.bl_idname, text='Search in Blend File', icon="ZOOM_ALL")
                op = row.operator('wm.url_open', text='', icon='HELP')
                op.url = 'https://launch-control-documentation.readthedocs.io/en/latest/launch-control-core.html#append-vehicle'


                if len(appendable_cars) > 0:
                    box = layout.box()
                    box.use_property_split = True
                    col = box.column()
                    row = col.row()

                    file_name = os.path.splitext(os.path.basename(scene.settings.append_file_path))[0]
                    text = ("File: " + file_name)
                    box.label(text = text)

                    row = box.row()
                    row = box.row()

                    box.prop(scene.settings, "append_lc_car_names", text='LC Vehicles in file:')

                    if scene.settings.append_version_control:
                        ico = 'FAKE_USER_ON'
                    else:
                        ico = 'FAKE_USER_OFF'
                    box.prop(scene.settings, "append_version_control", icon=ico)

                    row = box.row()
                    row = box.row()

                    box.use_property_split = False

                    name_collision = False
                    for coll in bpy.data.collections:
                        if coll.name == scene.settings.append_lc_car_names:
                            name_collision = True
                    
                    row.operator(OBJECT_OT_append_from_file.bl_idname, text="Append Vehicle", icon="APPEND_BLEND")
                    row.enabled = not name_collision

                    if name_collision:
                        box.label(text = "Vehicle Name exists in current file already", icon="INFO")
                        box.label(text = "Please select another vehicle to append")
            

            elif vehicle_source == 'link' and is_pro_license:
                
                row = layout.row()
                row.label(text="Link Rigged Vehicle into this file")

                show_link_from_file(context, scene, layout)


            elif vehicle_source == 'local':

                row = layout.row(align=True)
                row.prop(scene, "car_collection")
                op = row.operator('wm.url_open', text='', icon='HELP')
                op.url = 'https://launch-control-documentation.readthedocs.io/en/latest/launch-control-core.html#local-vehicle'
                row.enabled = (not multi_edit) and (not garage_mode) and (not speed_segments_running)

                if len(scene.lc.cars) > 0:
                    row.prop(scene.settings, "show_rigged_coll_only", text="", icon="FILTER")



        else:
            if selected_collection:
                active_car = scene.lc.find_selected()

                if addon_preferences.show_vehicle_gallery and (active_car and active_car.is_rigged):
                    col_2.operator(OBJECT_OT_revert_vehicle_add.bl_idname, text="", icon="PLUS")
                    col_2.enabled = (not multi_edit) and (not garage_mode) and (not speed_segments_running)

            row = layout.row(align=True)
            row.prop(scene, "car_collection")
            row.enabled = (not multi_edit) and (not garage_mode) and (not speed_segments_running)

            if len(scene.lc.cars) > 1:
                row.operator(OBJECT_OT_find_selected_car.bl_idname, text="", icon="RESTRICT_SELECT_OFF")

            if len(scene.lc.cars) > 0:
                row.prop(scene.settings, "show_rigged_coll_only", text="", icon="FILTER")

        if multi_edit:
            row = layout.row(align=True)
            row.prop(scene.settings, "edit_all_mode", text="Disable Multi-Edit", icon="OUTLINER_OB_POINTCLOUD")
            

        if selected_collection:
            
            active_car = scene.lc.find_selected()

            if (active_car and active_car.is_rigged) and not (len(scene.lc.cars) == 0 and multi_edit):
                props = active_car.properties
                settings = active_car.settings

                if len(scene.lc.cars) > 1 and not multi_edit:
                    if active_car.properties.has_lib_override:
                        pass
                    else:
                        row.prop(scene.settings, "edit_all_mode", text="", icon="OUTLINER_OB_POINTCLOUD")

                row = layout.row()
                row.operator(OBJECT_OT_delete_rig.bl_idname, icon="X")
                row.enabled = (not multi_edit) and (not garage_mode) and (not speed_segments_running)

                layout.separator(factor=LARGE)
                layout.separator(factor=LARGE)

                # Title 2: ANIMATIONS
                split = layout.split(factor=0.70)
                col_1 = split.column()
                col_2 = split.column()

                col_1.label(text="Select Animations", icon="IPO_BEZIER")
                col_2.prop(scene.settings, "filter_anim_presets", text="")

                if addon_preferences.show_animation_gallery:
                    animation_preset_name = os.path.splitext(bpy.data.window_managers["WinMan"].animation_presets)[0]
                    if scene.settings.filter_anim_presets == "custom":

                        row = layout.row(align=True)
                        box = row.box()
                        row = box.row(align=True)
                        row.template_icon_view(
                            context.window_manager,
                            "animation_presets",
                            show_labels=True,
                            scale=8,
                        )
                        row.enabled = not props.custom_path and (not garage_mode)
                        
                        row = layout.row(align=True)

                        if "Create" in animation_preset_name:
                            
                            row = box.row(align=True)
                            row.prop(scene.settings, "anim_preset_name", text="")
                            row.operator(OBJECT_OT_save_anim_preset.bl_idname, text="", icon="FILE_TICK")

                        else:
                            row = box.row(align=True)
                            row.label(text=animation_preset_name)
                            row.operator(OBJECT_OT_edit_anim_preset.bl_idname, text="", icon="GREASEPENCIL")
                            row.operator(OBJECT_OT_remove_anim_preset.bl_idname, text="", icon="TRASH")
                    
                        layout.separator(factor=LARGE)

                    elif scene.settings.filter_anim_presets == "library":

                        row = layout.row(align=True)
                        box = row.box()
                        #row = box.row(align=True)
                        #row.label(text="Library Path:")
                        row = box.row(align=True)
                        path_text = addon_preferences.anim_preset_lib_path
                        if path_text == "":
                            path_text = "Input Library Path in Preferences"

                        row.label(text=path_text)
                        row.operator(OBJECT_OT_show_addon_prefs.bl_idname, text="", icon="FOLDER_REDIRECT")
                        row = box.row(align=True)
                        row.template_icon_view(
                            context.window_manager,
                            "animation_presets",
                            show_labels=True,
                            scale=8,
                        )
                        row.enabled = not props.custom_path and (not garage_mode)
                        
                        row = layout.row(align=True)

                        if "Create" in animation_preset_name:
                            
                            row = box.row(align=True)
                            row.prop(scene.settings, "anim_preset_name", text="")
                            row.operator(OBJECT_OT_save_anim_preset.bl_idname, text="", icon="FILE_TICK")

                        else:
                            row = box.row(align=True)
                            row.label(text=animation_preset_name)
                            row.operator(OBJECT_OT_edit_anim_preset.bl_idname, text="", icon="GREASEPENCIL")
                            row.operator(OBJECT_OT_remove_anim_preset.bl_idname, text="", icon="TRASH")
                    
                        layout.separator(factor=LARGE)
                    
                    else:
                        row = layout.row()
                        row.template_icon_view(
                            context.window_manager,
                            "animation_presets",
                            show_labels=True,
                            scale=8,
                        )
                        row.enabled = not props.custom_path and (not garage_mode)
                
                row = layout.row(align=True)
                row.prop(props, "custom_path", text="User Path")
                row.operator(OBJECT_OT_pick_selected_path.bl_idname, text="", icon="RESTRICT_SELECT_OFF")
                row.enabled = (not garage_mode)

                if active_car.properties.custom_path is not None    and    addon_preferences.override_anim_on_path_change and (not garage_mode):
                    box = layout.box()
                    col = box.column(align=True)

                    row = col.row(align=True)
                    row.prop(active_car.properties, "frame_custom_path_start", text="Start")
                    row.prop(active_car.properties, "frame_custom_path_end", text="End")
                    row.prop(active_car.properties, "path_anim_intpl", text="")

                    row = col.row(align=True)
                    duration = (props.frame_custom_path_end-props.frame_custom_path_start)/scene.render.fps
                    row.label(text=f"Length: {round(duration, 1)} Sec")

                    unit = "mph" if addon_preferences.use_imperial else "km/h"

                    if active_car.properties.custom_path.data.use_path == True:
                        path_len = active_car.properties.custom_path.data.path_duration  # in m
                        if path_len > 1 and duration > 0:

                            if active_car.properties.path_anim_intpl == 'VECTOR':
                                max_speed = (path_len/duration)*3.6
                                label = "Speed:"

                            else:
                                start = props.frame_custom_path_start
                                end = props.frame_custom_path_end

                                offset = (props.frame_custom_path_end - props.frame_custom_path_start)/3

                                t = 0.49
                                p0 = np.array([start, 0])
                                p1 = np.array([start + offset, 0])
                                p2 = np.array([end, path_len])
                                p3 = np.array([end - offset, path_len])

                                mid_p0 = self.cubic_bezier(t, p0, p1, p2, p3,)
                                t = 0.51
                                mid_p1 = self.cubic_bezier(t, p0, p1, p2, p3,)

                                max_speed = self.get_speed(  self.get_slope(mid_p0, mid_p1)  )

                                label = "Max Speed:"

                            if unit == 'mph':
                                max_speed = max_speed*0.6213
                            row.label(text=f"{label} {round(max_speed, 0)} {unit}")
                        else:
                            row.label(text=f"Max Speed: -- {unit}")
                    else:
                        row.label(text=f"Max Speed: -- {unit}")
                        

                row = layout.row(align=True)
                row.operator(OBJECT_OT_apply_lap_from_json.bl_idname, text="Lap from JSON", icon="FILE_NEW")
                row.enabled = (not garage_mode)
                row = layout.row(align=True)
                row.operator(OBJECT_OT_prepare_animation.bl_idname)
                op = row.operator(OBJECT_OT_select_driving_path.bl_idname, text='', icon='CURVE_DATA')
                op = row.operator('wm.url_open', text='', icon='HELP')
                op.url = 'https://launch-control-documentation.readthedocs.io/en/latest/launch-control-core.html#animation'

                row.enabled = (not garage_mode)

                try:
                    layer_visible_state = active_car.rig_armature.collections["internal_warning_path"].is_visible
                except:
                    #Fallback for LC 1.5
                    layer_visible_state = active_car.rig_armature.collections["Layer 8"].is_visible

                if layer_visible_state:
                    layout.operator(OBJECT_OT_refresh_path_len.bl_idname)


                # Make Library Override on Driving Path if needed ----- Does not work...
                #if active_car.driving_path.override_library is not None:
                    #layout.operator(OBJCET_OT_make_lib_override_path.bl_idname)
                

                # If no Ground Detection is found
                ground_detect_collection = get_collection_by_name(COLLECTIONNAME_GROUNDDETECT, scene.collection)

                if ground_detect_collection is not None:  # Avoid breaking pre LC 1.6
                    if len(ground_detect_collection.objects) < 1:

                        layout.separator(factor=LARGE)
                        layout.separator(factor=LARGE)

                        b = layout.box()
                        lisr = b.row()
                        lisr.label(text="No Objects in Ground Detection", icon="ERROR")

                        lisr = b.row(align=True)
                        lisr.operator(OBJECT_OT_add_ground_colliders.bl_idname, text="Add Ground", icon="ADD")

                        layout.separator(factor=LARGE)
                    
                    else:
                        """layout.separator(factor=LARGE)
                        layout.separator(factor=LARGE)
                
                        flow = layout.column_flow(columns=2)

                        row = flow.row(align=True)
                        
                        row.operator(OBJECT_OT_add_ground_colliders.bl_idname, text="Add Ground", icon="ADD")
                        row.operator(OBJECT_OT_remove_ground_colliders.bl_idname, text="", icon="REMOVE")"""
                        pass

                else:
                    pass
                    #log_info(f"Could not find 'ground_detection_collection' reference inside the LC data. Will not draw UI element. Remove all LC vehicles and rig them again to fix this.", "LC - missing data")


                layout.separator(factor=SMALL)


                if speed_segments_running:

                    flow = layout.column_flow(columns=2)
                    flow.prop(scene.settings, "speed_segments_kill", icon="QUIT")

                    flow.prop(props, "settings_speed_segments")

                    if props.settings_speed_segments:
                        box = layout.box()
                        box.use_property_split = True
                        col = box.column()
                        row = col.row()

                        row.label(text="Graph:", icon="RNDCURVE")
                        row = col.row()

                        if props.graph_enable:
                            row.prop(props, "graph_enable", icon="HIDE_OFF")
                            row = col.row()
                            row.prop(props, "speed_graph_resolution", text="Resolution")
                            row = col.row()
                            row.prop(props, "graph_scale", text="Scale")
                            row = col.row()
                            row.prop(props, "graph_color")
                            row = col.row()
                        else:
                            row.prop(props, "graph_enable", icon="HIDE_ON")

                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()

                        row.label(text="Units:", icon="DRIVER_DISTANCE")
                        row = col.row()
                        row.prop(props, "timecode_type")
                        row = col.row()
                        row.prop(props, "units_type")
                        row.enabled = False
                        
                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()

                        row.label(text="Type Input:", icon="GREASEPENCIL")
                        row = box.row()

                        
                        unit = "mph" if addon_preferences.use_imperial else "km/h"
                        row.prop(props, "type_speed", text="Speed")
                        row.operator(OBJECT_OT_speed_segment_apply_speed.bl_idname, text=f"{unit} Set")
                        
                        
                        if props.interpolation_mode != "auto":
                            row = box.row()
                            timecode = "F" if props.timecode_type == 'FRAME' else "Sec"
                            if props.timecode_type == 'FRAME':
                                row.prop(props, "type_offset_time_frame", text="Offset Time")
                            else:
                                row.prop(props, "type_offset_time_sec", text="Offset Time")
                            row.operator(OBJECT_OT_speed_segment_apply_offset_time.bl_idname, text=f"{timecode} Set")
                        
                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()

                        row.label(text="Expert Settings:", icon="COMMUNITY")

                        row = col.row()
                        row.prop(props, "auto_fit_frame_range", text="Auto-fit Range", icon='ACTION')

                        row = col.row()

                        row.prop(props, "interpolation_mode")
                        
                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()
                        col = box.column()
                        row = col.row()

                        row.label(text="Auto-save blocked while tool is active", icon="INFO")


                else:
                    flow = layout.column_flow(columns=2)
                    flow.operator(OBJECT_OT_speed_segment_tool.bl_idname, text="Speed Segments", icon="PARTICLE_POINT")

                flow.enabled = (not garage_mode) and (not bpy.context.screen.is_animation_playing) and (not multi_edit)

                flow = layout.column_flow(columns=2)
                flow.prop(settings, "speedometer", text="Speedometer", icon="MOD_TIME")

                if settings.speedometer:
                    flow.operator(OBJECT_OT_refresh_speedometer.bl_idname, text="Refresh Speed", icon="FILE_REFRESH")

                flow.enabled = (not garage_mode)

                if settings.speedometer and not multi_edit:
                    dgraph_Evaluated = context.evaluated_depsgraph_get()
                    object_eval = active_car.speed_calculator.evaluated_get(dgraph_Evaluated)

                    try: current_kmh = object_eval.data.attributes["vel_attribute"].data[0].value
                    except: current_kmh = 0

                    current_speed = current_kmh*0.6214 if addon_preferences.use_imperial else current_kmh
                    
                    unit = "mph" if addon_preferences.use_imperial else "km/h"

                    label = (f"{(round(current_speed, 2))} {unit}")

                    layout.label(text=label, icon="PREVIEW_RANGE")
                    
                
                if settings.speedometer and multi_edit:
                    flow.label(text="Unavailable", icon="PREVIEW_RANGE")

                    
                layout.separator(factor=LARGE)
                layout.separator(factor=LARGE)

                # TITLE 2.5: F1 TELEMETRY
                # layout.label(text="F1 Telemetry Bridge", icon="WORLD_DATA")
                
                # box = layout.box()
                # box.operator("object.apply_lap_from_json", icon="IMPORT", text="Lap from JSON")
                
                layout.separator(factor=LARGE)
                layout.separator(factor=LARGE)

                # TITLE 3: PHYSICS
                layout.label(text="Select Physics", icon="PHYSICS")

                # Warnings and Settings
                switch = active_car.rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1]
                switch_setup_mode = active_car.rig_object.pose.bones["bone_Switch_Setup"].location[1]
                outdated_physics = physics_outdated(scene, active_car)
                changed_physics = physics_changed(scene, active_car)
                bake_invalid = active_car.rig_armature.collections["internal_warning_physics"].is_visible
                bugged_simulation_nodes = simulation_nodes_bugged(scene, active_car)

                
                if scene.settings.confirm_bake_state:

                    if scene.settings.bake_running:
                        #row = layout.row()
                        #row.label(text="Baking Physics...")
                        
                        row = layout.row()
                        row.operator(OBJECT_OT_physics_revert_to_main.bl_idname, icon="LOOP_BACK")

                    else:
                        row = layout.row()
                        row.label(text="Physics are ready to be Baked!")

                        layout.separator(factor=MEDIUM)

                        box = layout.box()
                        col = box.column(align=True)

                        row = col.row(align=True)

                        row.prop(scene.settings, "physics_use_warm_up", text="Warm Up",)
                        if scene.settings.physics_use_warm_up:
                            row.prop(scene.settings, "physics_warm_up_frames", text="Frames",)

                            if (scene.frame_preview_start - scene.settings.physics_warm_up_frames) < 0:
                                box.label(text="Frame Count cannot go below 0", icon="INFO")


                        # Try to get physics bake target from LC rig
                        has_physics_bake_target = hasattr(bpy.context.scene.settings, "physics_bake_target")

                        if bpy.app.version >= (4, 3, 0) and has_physics_bake_target:
                            row = col.row(align=True)
                            row.prop(scene.settings, "physics_bake_target", text="Bake Target",)
                            

                        box.separator(factor=LARGE)
                                                
                        box.operator(OBJECT_OT_execute_physics_bake.bl_idname, icon="CHECKMARK")

                        box.operator(OBJECT_OT_free_physics.bl_idname, icon="X")
                
                else:

                    if (switch > 0.5) or props.mute_physics:
                        
                        row = layout.row()
                        row.prop(active_car.properties, "physics_presets", text="")
                        row.enabled = not multi_edit

                        label, icon = physics_status(active_car, changed_physics, outdated_physics, props.baked_physics, bake_invalid, bugged_simulation_nodes, switch, switch_setup_mode)

                        flow = layout.column_flow(columns=2)
                        flow.label(text=label, icon=icon)
                        flow.prop(active_car.settings, "show_custom_physics", text="Customize", expand=True)

                        layout.separator(factor=SMALL)


                        if label == "Physics are LIVE":
                            box = layout.box()
                            box.label(text="Please bake before rendering or exporting", icon="INFO")

                            if scene.sync_mode != 'NONE':
                                box.label(text="Frame Dropping is Active.", icon="ERROR")
                                box.label(text="Physics will be inaccurate!")

                        if label == "Physics are BAKED":
                            box = layout.box()
                            start_frame = active_car.properties.baked_frame_start - scene.settings.physics_warm_up_frames
                            end_frame = active_car.properties.baked_frame_end
                            label_text = "Baked Frames: " + str(max(0, start_frame)) + " - " + str(end_frame)
                            box.label(text=label_text, icon="INFO")

                        layout.separator(factor=SMALL)

                        # Advance Physics
                        if active_car.settings.show_custom_physics:                            
                            row = layout.row()
                            row.prop(active_car.properties, "physics_tightness", text="Spring Hardness",)
                            row.enabled = not multi_edit
                            row = layout.row()
                            row.prop(active_car.properties, "physics_dampening", text="Spring Damping")
                            row.enabled = not multi_edit
                            row = layout.row()
                            row.prop(active_car.properties, "physics_softness", text="Smoothing")
                            row.enabled = not multi_edit
                            #row = layout.row()
                            #row.prop(active_car.properties, "physics_multiplier", text="Physics Multiplier")
                            #row.enabled = not multi_edit

                            layout.separator(factor=MEDIUM)

                            row = layout.row(align=True)
                            row.prop(active_car.properties, "use_gravity", text="Simulate Gravity")
                            row.enabled = not multi_edit
                            if active_car.properties.use_gravity:
                                row.prop(active_car.properties, "auto_level", text="Auto Level")
                                row.enabled = not multi_edit
                                
                                row = layout.row(align=True)
                                row.label(text="   ")
                                row.prop(active_car.properties, "mass", text="Vehicle Mass (Tons)")
                                row.enabled = not multi_edit
                                row = layout.row(align=True)
                                row.label(text="   ")
                                row.prop(active_car.properties, "spring_offset", text="Spring Offset")
                                row.enabled = not multi_edit

                        layout.separator(factor=SMALL)

                        if props.baked_physics:
                            row = layout.row(align=True)
                            row.operator(OBJECT_OT_free_physics.bl_idname, icon="PLAY")
                            if props.mute_physics:
                                row.operator(OBJECT_OT_unmute_physics.bl_idname, icon="RESTRICT_VIEW_OFF")
                            else:
                                row.operator(OBJECT_OT_mute_physics.bl_idname, icon="RESTRICT_VIEW_ON")
                            row.operator(OBJECT_OT_disable_physics.bl_idname, text="", icon="X")
                            row.operator(OBJECT_OT_bake_physics.bl_idname, text="", icon="FILE_REFRESH")
                            row.enabled = (not garage_mode)

                        else:
                            row = layout.row(align=True)
                            row.operator(OBJECT_OT_bake_physics.bl_idname, icon="FREEZE")
                            row.operator(OBJECT_OT_disable_physics.bl_idname, icon="X")
                            row.operator(OBJECT_OT_refresh_physics.bl_idname, text="", icon="FILE_REFRESH")
                            row.enabled = (not garage_mode)

                    else:
                        row = layout.row(align=True)
                        row.operator(OBJECT_OT_free_physics.bl_idname, icon="QUIT", text="Enable Physics!")
                        op = row.operator('wm.url_open', text='', icon='HELP')
                        op.url = 'https://launch-control-documentation.readthedocs.io/en/latest/launch-control-core.html#real-time-physics'
                        row.enabled = (not garage_mode)
        
            else:
                if not scene.settings.cad_setup:
                    layout.prop(scene.settings, "quick_tag", text="Quick Tag Tool")
                    show_quick_tag(context, scene, layout)

                if is_pro_license:
                    layout.prop(scene.settings, "cad_setup", text="CAD Data Setup")
                    show_cad_setup(context, scene, layout)
                
                for coll in scene.collection.children_recursive:
                    if coll.name == "CarRigAddon":
                        layout.separator(factor=LARGE)
                        layout.label(text="Legacy Rig detected", icon="INFO")
                        layout.label(text="Head to 'Manual Gearbox' -> 'Rig Info' to update it")

                row = layout.row(align=True)
                row.operator(OBJECT_OT_rig_car.bl_idname, text='Rig Vehicle')
                op = row.operator('wm.url_open', text='', icon='HELP')
                op.url = 'https://launch-control-documentation.readthedocs.io/en/latest/launch-control-core.html#rigging'
                    
                

def show_help(context, scene, layout):
    if scene.settings.rig_help:
        layout.separator(factor=SMALL)

        layout.label(text="Tags are needed to detect Car Parts", icon="INFO")

        layout.separator(factor=SMALL)

        box = layout.box()
        box.label(text="Required Car Parts:")
        box.label(text="     Car Body Tag:  'Body'")
        box.label(text="     Front Right Wheel Tag:  'wheel.FR'")
        box.label(text="     Front Left Wheel Tag:  'wheel.FL'")
        box.label(text="     Rear Right Wheel Tag:  'wheel.RR'")
        box.label(text="     Rear Left Wheel Tag:  'wheel.RL'")

        layout.separator(factor=SMALL)

        text = "Make sure above mentioned Car Parts exists in the scene, and that each one has the corresponding tag in its object name."
        label_multiline(context, text, layout, icon="DOT")

        layout.separator(factor=SMALL)

        box = layout.box()
        box.label(text="Optional Car Parts:")
        box.label(text="     Front Right Brake Tag:  'brake.FR'")
        box.label(text="     Front Left Brake Tag:  'brake.FL'")
        box.label(text="     Rear Right Brake Tag:  'brake.RR'")
        box.label(text="     Rear Left Brake Tag:  'brake.RL'")
        box.label(text="     Right Headlight Tag:  'headlight.R'")
        box.label(text="     Left Headlight Tag:  'headlight.L'")
        box.label(text="     Front Right Wheel Cover Tag:  'wheelcover.FR'")
        box.label(text="     Front Left Wheel Cover Tag:  'wheelcover.FL'")

        layout.separator(factor=SMALL)

        text = "Optional Car Parts will be rigged if found, but ignored if not found."
        label_multiline(context, text, layout, icon="DOT")
        
        layout.separator(factor=LARGE)

        text = "A wide variety of Tags can be detected by the add-on. Above, only the primary Tags are shown. See the full list of 'detectable' Tags in the documentation."
        label_multiline(context, text, layout, icon="INFO")
        
        layout.separator(factor=LARGE)


def show_quick_tag(context, scene, layout):
    if scene.settings.quick_tag:
        
        layout.separator(factor=SMALL)

        layout.label(text="Quick Renamer!", icon="GREASEPENCIL")

        layout.separator(factor=LARGE)

        text = "Select an object and click a button below, to rename it to the desired Tag."
        label_multiline(context, text, layout)

        layout.separator(factor=LARGE)

        layout.label(text="Required Tags:")

        box = layout.box()
        try: 
            box.prop(context.object, "name", text="Object Tag") 
        except: 
            pass
        box.operator("object.rename_to_option", text="body").option_name = "body"
        box.operator("object.rename_to_option", text="wheel.FL").option_name = "wheel.FL"
        box.operator("object.rename_to_option", text="wheel.FR").option_name = "wheel.FR"
        box.operator("object.rename_to_option", text="wheel.RL").option_name = "wheel.RL"
        box.operator("object.rename_to_option", text="wheel.RR").option_name = "wheel.RR"

        layout.separator(factor=LARGE)

        layout.label(text="Optional Tags:")

        box = layout.box()
        box.operator("object.rename_to_option", text="brake.FL").option_name = "brake.FL"
        box.operator("object.rename_to_option", text="brake.FR").option_name = "brake.FR"
        box.operator("object.rename_to_option", text="brake.RL").option_name = "brake.RL"
        box.operator("object.rename_to_option", text="brake.RR").option_name = "brake.RR"
        box.operator("object.rename_to_option", text="headlight.L").option_name = "headlight.L"
        box.operator("object.rename_to_option", text="headlight.R").option_name = "headlight.R"
        box.operator("object.rename_to_option", text="wheelcover.FL").option_name = "wheelcover.FL"
        box.operator("object.rename_to_option", text="wheelcover.FR").option_name = "wheelcover.FR"

        layout.separator(factor=LARGE)


# PHYSICS AUXILIAR FUNCTIONS
def physics_changed(scene, active_car):
    #True if physics have changed
    return not (
        active_car.properties.physics_tightness == active_car.properties.physics_baked_tightness
        and active_car.properties.physics_dampening == active_car.properties.physics_baked_dampening
        and active_car.properties.physics_softness == active_car.properties.physics_baked_softness
        and active_car.properties.physics_multiplier == active_car.properties.physics_baked_multiplier
        and active_car.properties.use_gravity == active_car.properties.baked_use_gravity
        and active_car.properties.auto_level == active_car.properties.baked_auto_level
        and active_car.properties.spring_offset == active_car.properties.baked_spring_offset
        and active_car.properties.mass == active_car.properties.baked_mass
    )

def physics_outdated(scene, active_car):
    
    outside_frame_range = False
    if scene.frame_start < active_car.properties.baked_frame_start - scene.settings.physics_warm_up_frames    or    scene.frame_end > active_car.properties.baked_frame_end:
        outside_frame_range = True

    is_outdated = False
    if active_car.path_changed or outside_frame_range:
        is_outdated = True

    return is_outdated

def simulation_nodes_bugged(scene, active_car):
    # Todo
    return False  

def physics_status(active_car, changed_physics, outdated_physics, baked_physics, bake_invalid, bugged_simulation_nodes, switch, switch_setup_mode):
    '''Returns label, icon symbolizing status of the physics'''
    if switch > 0.5:
        text = "Physics are LIVE"
        icon = "MOD_WAVE"

        if bugged_simulation_nodes:
            text = "Restart Blender Please"
            icon = "ERROR"

        if baked_physics:
            text = "Physics are BAKED"
            icon = "FREEZE"

            if outdated_physics or changed_physics:
                text = "Bake Outdated!"
                icon = "ERROR"

            if bake_invalid:
                text = "Bake Invalid - Please Reset"
                icon = "ERROR"

            

    elif active_car.properties.mute_physics:
        text = "Physics are MUTED"
        icon = "RESTRICT_VIEW_ON"
    
    else:
        text = "Physics are OFF"
        icon = "ONIONSKIN_OFF"

    return text, icon


class PANEL_PT_PostFX(bpy.types.Panel):
    bl_parent_id = "PANEL_PT_interface"
    bl_category = "Launch Control (Lap from JSON)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Physics Overdrive"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        selected_collection = scene.car_collection
        active_is_rigged = False
        physics_enabled = False

        if selected_collection:
            active_car = scene.lc.find_selected()
            if active_car and active_car.is_rigged:
                active_is_rigged = True
                physics_enabled = active_car.rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1]

        return (selected_collection) and (active_is_rigged) and (physics_enabled)
    

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        multi_edit = scene.settings.edit_all_mode
        
        selected_collection = scene.car_collection
        if selected_collection:
            active_car = scene.lc.find_selected()
            if active_car and active_car.is_rigged:
                car_properties = active_car.properties

                switch = active_car.rig_object.pose.bones[B_SWITCH_USE_SIMULATION].location[1]
                
                if switch > 0.5:

                    addon_root = ".".join(__package__.split(".")[:-2])
                    addon_preferences = bpy.context.preferences.addons[addon_root].preferences

                    

                    if (car_properties.baked_physics and not scene.settings.confirm_bake_state) or addon_preferences.allow_postfx_live:

                        layout.separator(factor=MEDIUM)

                        text_row1 = "Overdrive or Reduce the effect of the"
                        text_row2 = "simulated physics to fit your needs."
                        row = layout.row()
                        row.label(text=text_row1)
                        row.scale_y = 0.5
                        row = layout.row()
                        row.label(text=text_row2)
                        row.scale_y = 0.5
                        
                        layout.separator(factor=MEDIUM)
                        layout.separator(factor=LARGE)

                        layout.label(text="Body Forces: ")
                        
                        layout.use_property_split = True
                        col = layout.column()
                        col.prop(car_properties, "overdrive_pitch", text="Pitch")
                        col.enabled = not multi_edit
                        col.prop(car_properties, "overdrive_yaw", text="Yaw")
                        col.enabled = not multi_edit
                        col.prop(car_properties, "overdrive_roll", text="Roll")
                        col.enabled = not multi_edit

                        col = layout.column()
                        col.prop(car_properties, "overdrive_location", text="Up/Down Wobble")
                        col.enabled = not multi_edit

                        layout.separator(factor=MEDIUM)

                        layout.label(text=("Wheel Forces:"))
                        col = layout.column()
                        col.prop(car_properties, "overdrive_wheel_location", text="Ground Impact")
                        col.enabled = not multi_edit
                        col.prop(car_properties, "overdrive_wheel_pressure", text="Tire Pressure")
                        col.enabled = not multi_edit
                        
                        
                        layout.separator(factor=LARGE)
                        layout.separator(factor=LARGE)

                        
                        row = layout.row()
                        row.operator(OBJECT_OT_reset_postfx.bl_idname, text="Reset Overdrive", icon="LOOP_BACK")
                        row.enabled = not multi_edit

                    else:
                        text = "'Bake Physics' before adjusting or change User Preferences"
                        label_multiline(context, text, layout)

                else:
                    text = "Please 'Enable Physics' before adjusting the Physics PostFX"
                    label_multiline(context, text, layout)
                

# MANUAL GEARBOX -------------------------------------------------------------------------------------
class PANEL_AdvancedOverall:
    bl_category = "Launch Control (Lap from JSON)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        speed_segments_running = scene.settings.speed_segments_running
        selected_collection = scene.car_collection
        active_is_rigged = False

        if selected_collection:
            active_car = scene.lc.find_selected()
            if active_car and active_car.is_rigged:
                active_is_rigged = True

        return (not speed_segments_running) and (selected_collection) and (active_is_rigged)


class PANEL_PT_Advanced(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_idname = "PANEL_PT_Advanced"
    bl_label = "Manual Gearbox"

    def draw_header(self, context):
        self.layout.label(text="", icon="TOOL_SETTINGS")

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        selected_collection = scene.car_collection
        multi_edit = scene.settings.edit_all_mode

        garage_mode = False
        if scene.settings.mode == "garage_mode":
            garage_mode = True

        """if selected_collection == None: # In case vehicle collection is deleted while in Garage Mode
            row = layout.row()
            row.prop(scene.settings, "mode", expand=True)
            op = row.operator('wm.url_open', text='', icon='HELP')
            op.url = 'https://launch-control-documentation.readthedocs.io/en/latest/manual-gearbox.html#garage-mode'
            row.enabled = not multi_edit"""
            

        if selected_collection:
            active_car = scene.lc.find_selected()

            if active_car and active_car.is_rigged:
                row = layout.row()
                row.prop(scene.settings, "mode", expand=True)
                op = row.operator('wm.url_open', text='', icon='HELP')
                op.url = 'https://launch-control-documentation.readthedocs.io/en/latest/manual-gearbox.html#garage-mode'
                row.enabled = not multi_edit

                row = layout.row()
                row.operator(OBJECT_OT_reset_props.bl_idname, icon="LOOP_BACK")
                row.enabled = not multi_edit and not garage_mode
                    


class PANEL_PT_QuickFBX(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "Quick Export"

    def draw_header(self, context):
        self.layout.label(text="", icon="EXPORT")

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        selected_collection = scene.car_collection
        multi_edit = scene.settings.edit_all_mode

        if selected_collection:
            active_car = scene.lc.find_selected()
            if active_car and active_car.is_rigged:
                car_settings = active_car.settings

                layout.prop(car_settings, "export_path", text="Export Path")
                    
                row = layout.row()
                row.prop(scene.settings, "subframes", text="Animation Subframes")

                layout.separator(factor=LARGE)


                layout.operator(OBJECT_OT_quick_export_blend.bl_idname)

                layout.separator(factor=LARGE)
                layout.separator(factor=LARGE)
                layout.separator(factor=LARGE)

                layout.label(text="FBX exclusive settings", icon="OPTIONS")

                row = layout.row()

                # Show only if multiple cars are rigged 
                if len(scene.lc.cars) > 1:
                    row.prop(scene.settings, "export_all_cars", text="Export All Cars")
                    row.enabled = not multi_edit

                    layout.prop(scene.settings, "include_ground_for_all", text="Include Ground Colliders")
                
                else:
                    layout.prop(car_settings, "include_ground", text="Include Ground Colliders")
                    
                row = layout.row()

                row.prop(scene.settings, "include_anim", text="Include Animations")
                if scene.settings.include_anim:
                    row.prop(scene.settings, "export_anim_only", text="Only Animations")

                layout.operator(OBJECT_OT_quick_export.bl_idname)
                layout.operator(OBJECT_OT_quick_exportUE.bl_idname)



class PANEL_PT_BridgeTool(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "DCC Bridge"

    def draw_header(self, context):
        self.layout.label(text="", icon="EXPORT")

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        show_bridge_tool(context, scene, layout)


class PANEL_PT_ProxyTool(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "Proxy Tool"

    def draw_header(self, context):
        self.layout.label(text="", icon="MOD_REMESH")

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        show_proxy_tool(context, scene, layout)



class PANEL_PT_AdvancedHeadlights(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "Headlights (Cycles only)"

    def draw_header(self, context):
        self.layout.label(text="", icon="LIGHT")

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        selected_collection = scene.car_collection
        multi_edit = scene.settings.edit_all_mode

        if selected_collection:
            active_car = scene.lc.find_selected()
            if active_car.properties.has_lib_override:
                text = "For linked vehicles, enable headlights in Asset file"
                label_multiline(context, text, layout)

            else:
                if active_car and active_car.is_rigged:
                    car_settings = active_car.settings
                    car_properties = active_car.properties

                    layout.separator(factor = MEDIUM)

                    layout.prop(car_properties, "headlights_presets", text="Type")

                    layout.label(text="Beams Visibility:")
                    flow = layout.column_flow(columns=2)
                    flow.prop(car_settings, "low_beam_visibility", text="Low Beam")
                    flow.prop(car_settings, "high_beam_visibility", text="High Beam")

                    layout.separator(factor=MEDIUM)

                    if car_settings.low_beam_visibility or car_settings.high_beam_visibility:
                        layout.prop(car_settings, "link_beams", text="Link Beam Settings")

                        text = "Headlights" if car_settings.link_beams else "Low Beam"
                        layout.label(text=text + " Settings", icon="PROP_OFF")
                        layout.prop(car_properties, "low_beam_temperature", text="Temperature")
                        layout.prop(car_properties, "low_beam_intensity", text="Intensity")
                        row = layout.row()
                        row.prop(car_properties, "low_beam_spread", text="Spread")
                        row.enabled = not multi_edit
                        layout.prop(car_properties, "low_beam_sharpness", text="Sharpness")

                        if not car_settings.link_beams:
                            layout.label(text="High Beam Settings", icon="PROP_ON")
                            layout.prop(car_properties, "high_beam_temperature", text="Temperature")
                            layout.prop(car_properties, "high_beam_intensity", text="Intensity")
                            row = layout.row()
                            row.prop(car_properties, "high_beam_spread", text="Spread")
                            row.enabled = not multi_edit
                            layout.prop(car_properties, "high_beam_sharpness", text="Sharpness")

                        layout.separator(factor = MEDIUM)

                        layout.operator(OBJECT_OT_reload_headlight_tex.bl_idname, icon="FILE_REFRESH")

                    layout.separator(factor = MEDIUM)
            


class PANEL_PT_Skidmarks(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "Skidmarks"

    def draw_header(self, context):
        self.layout.label(text="", icon="PARTICLE_TIP")

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        selected_collection = scene.car_collection

        if selected_collection:
            active_car = scene.lc.find_selected()

            if active_car.properties.has_lib_override:
                text = "Not available for linked vehicles"
                label_multiline(context, text, layout)

            else:
                if active_car and active_car.is_rigged:
                    car_settings = active_car.settings
                    car_properties = active_car.properties

                    layout.label(text="Epic Skidmarks:")
                    
                    layout.separator(factor=MEDIUM)

                    layout.prop(car_settings, "enable_skidmarks", text="Enable Skidmark Generator")
                    if car_settings.enable_skidmarks:
                        layout.label(text="Is calculated based on G-force. Wheel spin and Wheel locking is not yet considered")

                        layout.separator(factor=SMALL)

                        flow = layout.column_flow(columns=2)
                        flow.operator(OBJECT_OT_bake_skidmarks.bl_idname, icon="FREEZE")
                        flow.operator(OBJECT_OT_free_skidmarks.bl_idname, icon="PLAY")
                        
                        layout.separator(factor=MEDIUM)

                        layout.prop(car_properties, "skidmarks_mul", text="Skidmark Intensity")

                        layout.separator(factor=SMALL)

                        layout.prop(car_properties, "skidmarks_var", text="Skidmark Variance")



class PANEL_PT_View(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "View"

    def draw_header(self, context):
        self.layout.label(text="", icon="HIDE_OFF")

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        selected_collection = scene.car_collection

        if selected_collection:
            active_car = scene.lc.find_selected()

            if active_car and active_car.is_rigged:
                car_settings = active_car.settings

                layout.label(text="Show in Viewport: ")
                box = layout.box()
                box.prop(car_settings, "ui_view_elements", text="")
                #box.prop(car_settings, "show_extra_animation_controls", text="Extra Animation Controls")
                box.prop(car_settings, "show_camera_hooks", text="Camera Hooks")
                box.prop(car_settings, "show_ground_grid", text="Show Detection Grid")
                box.prop(car_settings, "grid_resolution", text="Resolution")
                                
                
                layout.separator(factor=LARGE)

                layout.label(text="Debug Physics: ", icon="PHYSICS")
                box = layout.box()
                box.prop(car_settings, "show_acc_viz", text="G-Force Visualizer")
                box.prop(car_settings, "show_vel_viz", text="Velocity Visualizer")
            


class PANEL_PT_RigSettings(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "Settings"

    def draw_header(self, context):
        self.layout.label(text="", icon="SETTINGS")

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        multi_edit = scene.settings.edit_all_mode

        selected_collection = scene.car_collection

        if selected_collection:
            active_car = scene.lc.find_selected()

            if active_car and active_car.is_rigged:
                car_settings = active_car.settings
                car_properties = active_car.properties

                layout.label(text="Path: ") 
                box = layout.box()
                box.operator(OBJECT_OT_refresh_path_len.bl_idname, icon="FILE_REFRESH")
                box.prop(car_settings, "snap_path", text="Snap Control Points")

                layout.separator(factor=LARGE)
                layout.separator(factor=LARGE)

                layout.label(text="Ground Colliders: ") 

                ground_detect_collection = get_collection_by_name(COLLECTIONNAME_GROUNDDETECT, scene.collection)

                if ground_detect_collection is not None:  # Avoid breaking pre LC 1.6

                    c = layout.column()
                    row = c.row()
                    split = row.split(factor=0.10)
                    c = split.column()

                    split = split.box()
                    c = split.column()
                    for o in ground_detect_collection.objects: 
                        if (o.name!=""):
                            lisr = c.row()
                            lisr.label(text= ("•  " + o.name))
                    
                    if ("lisr" not in locals()):
                        lisr = c.row()
                        lisr.label(text="No Objects in Ground Detection", icon="ERROR")

                    lisr = c.row(align=True)
                    lisr.operator(OBJECT_OT_add_ground_colliders.bl_idname, text="Add Selected", icon="ADD")
                    lisr.operator(OBJECT_OT_remove_ground_colliders.bl_idname, text="Remove Selected", icon="REMOVE")
                    lisr.operator(OBJECT_OT_remove_all_ground_colliders.bl_idname, text="", icon="CANCEL")

                else:
                    pass
                    #log_info(f"Could not find 'ground_detection_collection' reference inside the LC data. Will not draw UI element. Remove all LC vehicles and rig them again to fix this.", "LC - missing data")

                layout.separator(factor=MEDIUM)


                layout.label(text="Ground Detection: ") 

                box = layout.box()

                if not car_settings.use_true_ground:
                    box.prop(car_settings, "show_ground_grid", text="Detection Grid")

                    if car_settings.show_ground_grid:
                        box.prop(car_settings, "grid_resolution", text="Resolution")

                box.prop(car_settings, "use_true_ground", text="Use True Ground")

                box.prop(car_settings, "legacy_ground_detection", text="Legacy Ground Detection")

                layout.separator(factor=LARGE)
                layout.separator(factor=LARGE)

                #layout.label(text="Animation: ") 
                #box = layout.box()
                #box.prop(car_settings, "limit_sliders", text="Limit animation sliders")
                #box.prop(car_properties, "shake_frequency", text="Wheel Shake Rate")

                #layout.separator(factor=LARGE)
                #layout.separator(factor=LARGE)

                layout.label(text="Find more settings inside 'Add-on Preferences'") 
                


class PANEL_PT_AdvancedPath(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "Jump Trajectory"

    def draw_header(self, context):
        self.layout.label(text="", icon="DRIVER_ROTATIONAL_DIFFERENCE")

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        multi_edit = scene.settings.edit_all_mode

        selected_collection = scene.car_collection
        addon_root = ".".join(__package__.split(".")[:-2])
        addon_preferences = context.preferences.addons[addon_root].preferences

        if selected_collection:
            active_car = scene.lc.find_selected()

            if active_car and active_car.is_rigged:
                car_settings = active_car.settings

                layout.separator(factor = MEDIUM)

                # info text
                text1 = "Generate points on the driving path that emulates a realistic car jump."
                label_multiline(context, text1, layout)

                # help
                layout.prop(car_settings, "show_jump_help", text="Show Help")
                if car_settings.show_jump_help:
                    step1 = "1. Select the last point before the car leaves the ground."
                    step2 = "2. Click 'Jump!'"
                    step3 = "3. Make sure the point handle is pointing in the direction the car will fly."
                    label_multiline(context, step1, layout)
                    label_multiline(context, step2, layout)
                    label_multiline(context, step3, layout)

                layout.separator(factor=LARGE)

                # Commands
                unit = "mph" if addon_preferences.use_imperial else "km/h"
                flow = layout.column_flow(columns=2)
                flow.prop(car_settings, "jump_speed", text=f"Speed ({unit})")
                flow.operator(OBJECT_OT_prepare_jump.bl_idname)
                flow.enabled = not multi_edit

                layout.separator(factor = MEDIUM)


class PANEL_PT_AdvancedCamera(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "Cinematographer "

    def draw_header(self, context):
        self.layout.label(text="", icon="CAMERA_DATA")

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        multi_edit = scene.settings.edit_all_mode

        selected_collection = scene.car_collection

        if selected_collection:
            active_car = scene.lc.find_selected()

            if active_car and active_car.is_rigged:
                car_settings = active_car.settings

                layout.separator(factor = MEDIUM)
                
                row = layout.row()
                row.label(text="Create Cameras from View:")

                row = layout.row()
                row.operator(CAMERAS_OT_create_follow_cam.bl_idname, text="Follow Camera", icon="CON_FOLLOWTRACK")
                row.operator(CAMERAS_OT_create_mounted_cam.bl_idname, text="Mounted Camera", icon="CON_CHILDOF")
                row.enabled = not multi_edit
                
                layout.separator(factor = MEDIUM)


class PANEL_PT_RigInfo(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "Rig Info"

    def draw_header(self, context):
        self.layout.label(text="", icon="INFO")

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        multi_edit = scene.settings.edit_all_mode

        selected_collection = scene.car_collection

        garage_mode = False
        if scene.settings.mode == "garage_mode":
            garage_mode = True

        if selected_collection:
            active_car = scene.lc.find_selected()

            if active_car.properties.has_lib_override:
                text = "Not available for linked vehicles"
                label_multiline(context, text, layout)

            else:
                if active_car and active_car.is_rigged:

                    if not multi_edit:
                        car_props = active_car.properties
                        has_attr = hasattr(car_props, 'lc_version')
                        
                        if has_attr:
                            if car_props.lc_version != "0.0.0":
                                
                                lc_version = str(car_props.lc_version).replace(", ", ".")
                                lc_version = lc_version.replace("(", "")
                                lc_version = lc_version.replace(")", "")

                            else:
                                lc_version = "-.-.-"
                        else:
                            lc_version = "-.-.-"
                        
                        addon_version = get_addon_version()
                        addon_version = addon_version.replace(", ", ".")
                        addon_version = addon_version.replace("(", "")
                        addon_version = addon_version.replace(")", "")

                        if addon_version == lc_version:
                            version_icon = "CHECKMARK"
                        else:
                            version_icon = "ERROR"

                        row = layout.row()
                        row.label(text=("Version Check:"))

                        row = layout.row(align=True)
                        row.label(text=("Vehicle: " + lc_version),icon=version_icon)
                        row.label(text=("Add-on: " + addon_version))

                        row = layout.row()
                        row.label(text="Please backup file before proceeding")

                        row = layout.row()
                        row.operator(OBJECT_OT_update_vehicle_rig.bl_idname)
                        row.enabled = not garage_mode


                    else:
                        row = layout.row()
                        row.label(text="Please disable 'Multi-Edit'")

                else:
                    legacy_detection = False

                    for coll in scene.collection.children_recursive:
                        if coll.name == "CarRigAddon":
                            legacy_detection = True

                    if legacy_detection:
                        row = layout.row()
                        row.label(text=("Version Check:"))
                        row = layout.row()
                        row.label(text="Legacy Rig Detected (1.0.0 - 1.3.5)")
                        row = layout.row()
                        row.operator(OBJECT_OT_update_vehicle_rig.bl_idname)
                        row.enabled = not garage_mode


class PANEL_PT_Data(PANEL_AdvancedOverall, bpy.types.Panel):
    bl_parent_id = "PANEL_PT_Advanced"
    bl_label = "LC Data"

    def draw_header(self, context):
        self.layout.label(text="", icon="FILE_CACHE")

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        multi_edit = scene.settings.edit_all_mode

        selected_collection = scene.car_collection

        garage_mode = False
        if scene.settings.mode == "garage_mode":
            garage_mode = True

        if selected_collection:
            active_car = scene.lc.find_selected()

            if active_car.properties.has_lib_override:
                text = "Not available for linked vehicles"
                label_multiline(context, text, layout)

            else:
                if active_car and active_car.is_rigged:

                    if not multi_edit:
                        row = layout.row()
                        row.operator(OBJECT_OT_update_vehicle_rig.bl_idname, text="Update Vehicle Rig")
                        
                        row = layout.row()
                        row.operator(OBJECT_OT_refresh_cache_dirs.bl_idname, text="Refresh Cache Locations")
                        
                        row = layout.row()
                        row.label(text="Headlight Texture Data:")
                        row = layout.row()
                        row.operator(OBJECT_OT_reload_all_headlight_tex.bl_idname, text="Reload All")
                        row.operator(OBJECT_OT_unload_headlight_tex.bl_idname, text="Unload Unused")




class ADDONPREFERENCES_UserPref(bpy.types.AddonPreferences):
    addon_root = ".".join(__package__.split(".")[:-2])
    bl_idname = addon_root

    show_vehicle_gallery: bpy.props.BoolProperty(
        name="Show Vehicle Gallery and Append options",
        default=True,
    )

    show_animation_gallery: bpy.props.BoolProperty(
        name="Show Animation Gallery",
        default=True,
    )
    
    animation_sliders_location: bpy.props.EnumProperty(
        items=[
            ('3d_interface', 'Floating in Viewport', '', '', 1),
            ('python_interface', 'Static in N-Panel', '', '', 0)   
        ],
        default='3d_interface'
    )

    show_slider_labels: bpy.props.BoolProperty(
        name="Show Animation Handle Labels",
        default=True,
        update=commands.update_labels
    )

    use_imperial: bpy.props.BoolProperty(
        name="Use Imperial Units",
        default=False,
        update=commands.reveal_imperial
    )

    override_anim_on_path_change: bpy.props.BoolProperty(
        name = "Override Animation Data",
        description="Remove current animation data when a new 'User Path' is picked in the interface and 'Animate Vehicle!' is pressed. Animation will be replaced by an automatically calculated offset animation", 
        default=True
    )

    open_graph_editor_segments: bpy.props.BoolProperty(
        name = "Open Graph Editor with Speed Segments",
        description="Allow LC to automatically turn your timeline into a graph editor when the Speed Segment Tool is activated. This makes sure that you can preview and debug the animation curve while using the Speed Segments in the viewport", 
        default=True
    )

    max_dur_speed_segments: bpy.props.IntProperty(
        name = "Speed Segment Animation Limit (Performance Limit)",
        description="Limit the max amount of frames the Speed Segments will allow animating across. Increasing this might drastically decrease performance!", 
        default=3000,
    )

    draw_hotkey_tips: bpy.props.BoolProperty(
        name = "Show Hotkeys Panel",
        description="Show the Hotkeys Tip Panel in the bottom left of the screen when Speed Segments are active.", 
        default=True
    )

    allow_postfx_live: bpy.props.BoolProperty(
        name = "Show PostFX with Live Physics",
        description="Allow PostFX to be changed while using the Live Physics in LC", 
        default=True
    )


    auto_pivot: bpy.props.BoolProperty(
        name="Calculate Tire Pivot",
        description="Let LC automatically create new pivots for the tire meshes used for rigging. The new pivots will override any user set pivots. Uncheck to keep user pivots. Auto Pivot will make each wheel a 'single user data'",
        default=True,
    )

    use_custom_tags: bpy.props.BoolProperty(
        name="Use Custom Tags",
        description="Allow the user to define custom search tags that LC will search for when rigging the car",
        default=0,
    )

    custom_tire: bpy.props.StringProperty(
        name="Custom Tire Tag",
        description="Custom rigging search tag for LC to detect tire meshes",
        default="tire",
    )

    custom_RL: bpy.props.StringProperty(
        name="Custom Rear Left Tag",
        description="Custom rigging search tag for LC to detect rear left (wheel) meshes. E.g. '_RL'",
        default="_RL",
    )

    custom_RR: bpy.props.StringProperty(
        name="Custom Rear Right Tag",
        description="Custom rigging search tag for LC to detect rear right (wheel) meshes. E.g. '_RR'",
        default="_RR",
    )

    custom_FR: bpy.props.StringProperty(
        name="Custom Front Right Tag",
        description="Custom rigging search tag for LC to detect front right (wheel) meshes. E.g. '_FR'",
        default="_FR",
    )

    custom_FL: bpy.props.StringProperty(
        name="Custom Front Left Tag",
        description="Custom rigging search tag for LC to detect front left (wheel) meshes. E.g. '_FL'",
        default="_FL",
    )

    custom_brake: bpy.props.StringProperty(
        name="Custom Brake Caliper Tag",
        description="Custom rigging search tag for LC to detect brake caliper meshes",
        default="brake",
    )

    custom_covers: bpy.props.StringProperty(
        name="Custom Wheelcovers Tag",
        description="Custom rigging search tag for LC to detect wheelcover meshes",
        default="wheelcover",
    )

    custom_body: bpy.props.StringProperty(
        name="Custom Body Tag",
        description="Custom rigging search tag for LC to detect body meshes",
        default="body",
    )

    force_rig_brakes: bpy.props.EnumProperty(
        name="Rigging brakes",
        description="Options for rigging brakes when clicking 'Rig Vehicle'",
        items=[
            (
                "OP1",
                "If possible",
                "Only rig the brakes if they can be found. If they cannot be found ignore them and move on",
            ),
            (
                "OP2",
                "Force it",
                "Force the brakes to be rigged. If brakes cannot be found give an error message",
            ),
            ("OP3", "Never", "Just ignore brakes. Don't even try..."),
        ],
    )

    force_rig_headlights: bpy.props.EnumProperty(
        name="Rigging Headlights",
        description="Options for rigging headlights when clicking 'Rig Vehicle'",
        items=[
            (
                "OP1",
                "If possible",
                "Only rig the headlights if they can be found. If they cannot be found, leave them at the location and let the user move them",
            ),
            ("OP2", "Never", "Just ignore headlights. Don't even try..."),
        ],
    )

    force_rig_wheelcovers: bpy.props.EnumProperty(
        name="Rigging Wheel Covers",
        description="Options for rigging Wheel Covers when clicking 'Rig Vehicle'",
        items=[
            (
                "OP1",
                "If possible",
                "Only rig the Wheel Covers if they can be found. If they cannot be found ignore them and move on",
            ),
            (
                "OP2",
                "Force it",
                "Force the Wheel Covers to be rigged. If Wheel Covers cannot be found give an error message",
            ),
            ("OP3", "Never", "Just ignore Wheel Covers. Don't even try..."),
        ],
    )

    apply_path_color: bpy.props.BoolProperty(
        name="Colorize Driving Paths",
        description="Automatically color the Driving Paths the color of the collection which the corrosponding vehicle exists in when clicking 'Animate Vehicle!'",
        default=True,
    )

    garage_mode_transforms: bpy.props.EnumProperty(
        name="Garage Mode Transforms",
        description="Set the vehicle Transforms you want LC to use when entering 'Garage Mode'.",
        items=[
            ('default', 'Scene Center', '', '', 1),
            ('unrigged', 'Unrigged State/Import Data', '', '', 0)   
        ],
        default='default'
    )

    if is_pro_license:
        anim_preset_lib_path: add_anim_preset_lib_path()
        


    
   


    def draw(self, context):
        layout = self.layout
        addon_root = ".".join(__package__.split(".")[:-2])
        addon_preferences = context.preferences.addons[addon_root].preferences
        layout.use_property_split = True


        layout.separator(factor=SMALL)


        row = layout.row(align=True)
        op = row.operator('wm.url_open', text='Launch Control Documentation', icon='URL')
        op.url = 'https://launch-control-documentation.readthedocs.io/en/latest/launch-control-core.html'

        layout.separator(factor=SMALL)

        box = layout.box()
        box.label(text="Interface:", icon="VIEW3D")
        box.prop(self, "show_vehicle_gallery", text="Vehicle Gallery")
        box.prop(self, "show_animation_gallery", text="Animation Gallery")
        #box.prop(self, "animation_sliders_location", text="Show Animation Sliders")

        if addon_preferences.animation_sliders_location == '3d_interface':
            box.prop(self, "show_slider_labels", text="Slider Labels")
        

        box = layout.box()
        box.label(text="Animation:", icon="GRAPH")
        if is_pro_license:
            box.prop(self, "anim_preset_lib_path", text="Custom Library")
        #box.prop(self, "override_anim_on_path_change", text="Override Animation Data")
        #box.prop(self, "apply_path_color", text="Colorize Driving Paths")
        box.prop(self, "use_imperial", text="Use Imperial Units")


        box = layout.box()
        box.label(text="Speed Segments:", icon="PARTICLE_POINT")
        box.prop(self, "draw_hotkey_tips", text="Show Hotkeys") 
        box.prop(self, "open_graph_editor_segments", text="Auto-convert Timeline into Graph Editor") 
        box.prop(self, "max_dur_speed_segments", text="Max Frames") 
         
        
        box = layout.box()
        
        box.label(text="Physics:", icon="PHYSICS")
        box.prop(self, "allow_postfx_live")


        box = layout.box()
        
        box.label(text="Rigging:", icon="ARMATURE_DATA")
        box.prop(self, "auto_pivot", text="Automatic Tire Pivot")
        box.prop(self, "garage_mode_transforms", text="Garage Transform")
        box.prop(self, "use_custom_tags", text="Use Custom Tags")

        if addon_preferences.use_custom_tags:
            box.prop(self, "custom_body", text="Body")
            box.prop(self, "custom_tire", text="Tire")
            box.prop(self, "custom_RL", text="Rear Left")
            box.prop(self, "custom_RR", text="Rear Right")
            box.prop(self, "custom_FR", text="Front Right")
            box.prop(self, "custom_FL", text="Front Left")
            box.prop(self, "custom_brake", text="Brake Caliper [Optional]")
            box.prop(self, "custom_covers", text="Wheel Covers [Optional]")
        

        box.prop(self, "force_rig_brakes", text="Rig Brakes")
        box.prop(self, "force_rig_headlights", text="Rig Headlights")
        box.prop(self, "force_rig_wheelcovers", text="Rig Wheel Covers")

        
        
        