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

        # ── 2. QUERY ENGINE ──────────────────────────────────────────────
        box = layout.box()
        box.label(text="Query Engine", icon='WORLD_DATA')
        col = box.column(align=True)
        col.prop(props, "sel_event_type")
        col.prop(props, "sel_year")

        if props.sel_event_type == 'TESTING':
            col.prop(props, "sel_test_number")
            col.prop(props, "sel_test_session")
        else:
            col.prop(props, "sel_race")
            col.prop(props, "sel_session")

        col.prop(props, "sel_driver")

        row = box.row()
        row.scale_y = 1.2
        row.operator(OBJECT_OT_f1_add_lap_to_queue.bl_idname,
                     icon='ADD', text="ADD LAP")
        box.label(text="Data: 30-120 min after session ends; future sessions = no data", icon='INFO')

        # ── 3. LAP QUEUE ─────────────────────────────────────────────────
        layout.separator()
        box = layout.box()
        row = box.row()
        row.label(text="Lap Queue (Max 4)", icon='TEXT')
        row.operator(OBJECT_OT_f1_clear_queue.bl_idname, text="", icon='TRASH')

        if len(scene.f1_lap_queue) > 0:
            for i, item in enumerate(scene.f1_lap_queue):
                row = box.row()
                if item.is_testing:
                    # Look up track name from testing_events database
                    from ..data.f1_properties import _TESTING_EVENTS
                    _tests = _TESTING_EVENTS.get(item.year, [])
                    _loc = ""
                    for _t in _tests:
                        if str(_t.get('test_number', '')) == str(item.test_number):
                            _loc = _t.get('location', '')
                            break
                    _label = f"Test {item.test_number}"
                    if _loc:
                        _label += f" – {_loc}"
                    _label += f" Day {item.test_session}"
                    row.label(text=f"{i+1}. {item.driver}  |  {item.year}  |  {_label}")
                else:
                    row.label(text=f"{i+1}. {item.driver}  |  {item.year}  |  {item.event}")
                op = row.operator(OBJECT_OT_f1_remove_lap.bl_idname, text="", icon='X')
                op.index = i
        else:
            box.label(text="Queue is empty", icon='INFO')

        # ── 4. STATUS & GENERATE ─────────────────────────────────────────
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


classes = [PANEL_PT_F1_Studio]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
