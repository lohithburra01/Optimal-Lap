import bpy
from ..operators.F1_HiFi_Baker_Pro import F1_OT_InstallDeps, MISSING_DEPS
from ..operators.f1_pipeline import (
    OBJECT_OT_f1_generate_scene,
    OBJECT_OT_f1_add_lap_to_queue,
    OBJECT_OT_f1_remove_lap,
    OBJECT_OT_f1_clear_queue,
    OBJECT_OT_f1_save_alignment,
    OBJECT_OT_f1_load_alignment,
    OBJECT_OT_f1_reset_alignment,
    OBJECT_OT_f1_diagnose_path,
    OBJECT_OT_f1_correct_path,
    OBJECT_OT_f1_auto_correct_path,
    OBJECT_OT_f1_clear_diagnostic,
    OBJECT_OT_f1_flatten_z,
    OBJECT_OT_f1_snap_z_to_track,
)
from ..data.f1_properties import _get_event


class PANEL_PT_F1_Studio(bpy.types.Panel):
    bl_label       = "Hot Lap – F1 Race Replay Studio"
    bl_idname      = "PANEL_PT_F1_Studio"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = "Hot Lap"

    def draw(self, context):
        layout = self.layout
        scene  = context.scene
        props  = scene.f1_pipeline_props

        # ── 1. DEPENDENCY CHECK ──────────────────────────────────────────
        if MISSING_DEPS:
            box = layout.box()
            box.label(text="Missing Libraries!", icon='ERROR')
            box.label(text="F1 Studio requires fastf1 & pandas")
            box.operator(F1_OT_InstallDeps.bl_idname,
                         icon='PREFERENCES', text="Install Dependencies")
            return

        # When deps are present, show upgrade option (e.g. 3.7 → 3.8.1)
        row = layout.row()
        row.operator(F1_OT_InstallDeps.bl_idname,
                     icon='IMPORT', text="Upgrade / Reinstall FastF1 (3.8.1+)")

        # ── 2. TRACK LOCK BAR (Lohith-style) ──────────────────────────────
        queue_len = len(scene.f1_lap_queue)
        if queue_len > 0 and props.locked_track:
            box = layout.box()
            row = box.row()
            row.alert = False
            row.label(text=f"🔒  {props.locked_track}", icon='LOCKED')

        # ── 3. QUERY ENGINE (Lohith-style UI) ─────────────────────────────
        box = layout.box()
        box.label(text="Query Engine", icon='WORLD_DATA')
        col = box.column(align=True)

        col.prop(props, "sel_year")

        row = col.row(align=True)
        row.enabled = (queue_len == 0)
        row.prop(props, "sel_race")

        event = _get_event(props.sel_year, props.sel_race)
        event_type = event.get('event_type', 'race') if event else 'race'
        is_testing = (event_type == 'testing')

        col.separator()
        col.prop(props, "sel_session")

        if not is_testing and props.sel_session == 'Q':
            row = col.row(align=True)
            row.label(text="", icon='BLANK1')
            sub = row.column(align=True)
            sub.prop(props, "sel_q_segment", expand=False)

        col.separator()
        row = col.row(align=True)
        row.prop(props, "fastest_lap", toggle=True,
                 icon='SORTTIME',
                 text="Fastest Lap (auto)" if props.fastest_lap else "Fastest Lap (auto): OFF")

        col.separator()
        col.prop(props, "sel_driver")

        row = box.row()
        row.scale_y = 1.3
        row.operator(OBJECT_OT_f1_add_lap_to_queue.bl_idname,
                     icon='ADD', text="Add Lap to Queue")

        # ── 4. LAP QUEUE (Lohith-style) ───────────────────────────────────
        layout.separator()
        box = layout.box()
        row = box.row()
        row.label(text=f"Lap Queue  ({queue_len}/4)", icon='LINENUMBERS_ON')
        row.operator(OBJECT_OT_f1_clear_queue.bl_idname, text="", icon='TRASH')

        if queue_len > 0:
            for i, item in enumerate(scene.f1_lap_queue):
                row = box.row(align=True)
                sess_label = item.session
                if item.q_segment:
                    sess_label = item.q_segment
                lap_label = "FAST" if item.fastest_lap else "Lap ?"
                row.label(text=f"{i+1}.  {item.driver}  |  {item.year}  {sess_label}  {lap_label}")
                op = row.operator(OBJECT_OT_f1_remove_lap.bl_idname, text="", icon='X')
                op.index = i
        else:
            box.label(text="Queue is empty", icon='INFO')

        # ── 5. STATUS & GENERATE ─────────────────────────────────────────
        layout.separator()
        layout.label(text=f"Status: {props.status_msg}")

        layout.prop(props, "render_minimap", icon='SEQ_PREVIEW')

        row = layout.row()
        row.scale_y = 2.0
        row.enabled = len(scene.f1_lap_queue) > 0
        row.operator(OBJECT_OT_f1_generate_scene.bl_idname,
                     icon='RENDER_ANIMATION', text="GENERATE SCENE")

        # ── 5. TRACK ALIGNMENT ─────────────────────────────────────────
        layout.separator()
        box = layout.box()
        row = box.row()
        row.label(text="Track Alignment", icon='ORIENTATION_GLOBAL')
        row.operator(OBJECT_OT_f1_reset_alignment.bl_idname, text="", icon='LOOP_BACK')

        col = box.column(align=True)
        col.prop(props, "align_offset_x")
        col.prop(props, "align_offset_y")
        col.prop(props, "align_rotation")
        col.prop(props, "align_scale")

        row = box.row(align=True)
        row.operator(OBJECT_OT_f1_save_alignment.bl_idname,
                     icon='FILE_TICK', text="Save")
        row.operator(OBJECT_OT_f1_load_alignment.bl_idname,
                     icon='FILE_FOLDER', text="Load")

        # ── 6. PATH DIAGNOSTIC ────────────────────────────────────────
        layout.separator()
        box = layout.box()
        row = box.row()
        row.label(text="Path Diagnostic", icon='OUTLINER_OB_CURVE')
        row.operator(OBJECT_OT_f1_clear_diagnostic.bl_idname, text="", icon='TRASH')

        box.prop(props, "track_surface_obj")

        # Height normalization
        row = box.row(align=True)
        row.label(text="Height:", icon='EMPTY_SINGLE_ARROW')
        row.operator(OBJECT_OT_f1_flatten_z.bl_idname, text="Flatten")
        row.operator(OBJECT_OT_f1_snap_z_to_track.bl_idname, text="Snap to Track")
        box.prop(props, "normalize_z_value")

        box.separator()

        # XY correction
        row = box.row(align=True)
        row.scale_y = 1.3
        row.operator(OBJECT_OT_f1_diagnose_path.bl_idname,
                     icon='VIEWZOOM', text="Diagnose")
        row.operator(OBJECT_OT_f1_correct_path.bl_idname,
                     icon='MOD_SMOOTH', text="Correct")

        row = box.row()
        row.scale_y = 1.5
        row.operator(OBJECT_OT_f1_auto_correct_path.bl_idname,
                     icon='FILE_REFRESH', text="Auto-Correct (until on-track)")

        col = box.column(align=True)
        col.prop(props, "correction_falloff")
        col.prop(props, "correction_strength")

        # ── 7. PATH SCULPT TOOLS ────────────────────────────────────────
        layout.separator()
        box = layout.box()
        box.label(text="Path Sculpt Tools", icon='BRUSH_DATA')
        box.prop_search(scene, "f1_path_object", bpy.data, "objects", text="Path")
        row = box.row(align=True)
        row.prop(scene, "f1_brush_radius",   text="Radius")
        row.prop(scene, "f1_brush_strength", text="Strength")
        box.prop(scene, "f1_brush_mode", text="Mode")
        box.operator("f1.path_brush", text="Sculpt Path", icon='SCULPTMODE_HLT')
        box.label(text="M=Push/Pull  Scroll=Radius  Shift+Scroll=Strength", icon='INFO')


classes = [PANEL_PT_F1_Studio]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
