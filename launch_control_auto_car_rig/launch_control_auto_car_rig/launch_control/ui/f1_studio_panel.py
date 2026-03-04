import bpy
from ..operators.F1_HiFi_Baker_Pro import F1_OT_InstallDeps, MISSING_DEPS
from ..operators.f1_pipeline import (
    OBJECT_OT_f1_generate_scene,
    OBJECT_OT_f1_add_lap_to_queue,
    OBJECT_OT_f1_remove_lap,
    OBJECT_OT_f1_clear_queue,
)
from ..data.f1_properties import _get_event


class PANEL_PT_F1_Studio(bpy.types.Panel):
    bl_label       = "F1 Race Replay Studio"
    bl_idname      = "PANEL_PT_F1_Studio"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = "Launch Control"

    def draw(self, context):
        layout = self.layout
        scene  = context.scene
        props  = scene.f1_pipeline_props

        # ── 1. DEPENDENCY CHECK ──────────────────────────────────────────────
        if MISSING_DEPS:
            box = layout.box()
            box.label(text="Missing Libraries!", icon='ERROR')
            box.label(text="F1 Studio requires fastf1 & pandas")
            box.operator(F1_OT_InstallDeps.bl_idname,
                         icon='PREFERENCES', text="Install Dependencies")
            return

        # ── 2. TRACK LOCK BAR ────────────────────────────────────────────────
        queue_len = len(scene.f1_lap_queue)
        if queue_len > 0 and props.locked_track:
            box = layout.box()
            row = box.row()
            row.alert = False
            row.label(text=f"🔒  {props.locked_track}", icon='LOCKED')

        # ── 3. QUERY ENGINE ──────────────────────────────────────────────────
        box = layout.box()
        box.label(text="Query Engine", icon='WORLD_DATA')
        col = box.column(align=True)

        # Year
        col.prop(props, "sel_year")

        # Race / Event — disabled (greyed) if track is locked
        row = col.row(align=True)
        row.enabled = (queue_len == 0)
        row.prop(props, "sel_race")

        # Determine event type for conditional UI
        event = _get_event(props.sel_year, props.sel_race)
        event_type = event.get('event_type', 'race') if event else 'race'
        is_testing = (event_type == 'testing')

        col.separator()

        # Session
        col.prop(props, "sel_session")

        # Q Segment row — only when session = Q (not testing)
        if not is_testing and props.sel_session == 'Q':
            row = col.row(align=True)
            row.label(text="", icon='BLANK1')  # indent
            sub = row.column(align=True)
            sub.prop(props, "sel_q_segment", expand=False)

        col.separator()

        # Fastest lap toggle
        row = col.row(align=True)
        row.prop(props, "fastest_lap", toggle=True,
                 icon='SORTTIME',
                 text="Fastest Lap (auto)" if props.fastest_lap else "Fastest Lap (auto): OFF")

        col.separator()

        # Driver
        col.prop(props, "sel_driver")

        # ADD LAP button
        row = box.row()
        row.scale_y = 1.3
        row.operator(OBJECT_OT_f1_add_lap_to_queue.bl_idname,
                     icon='ADD', text="Add Lap to Queue")

        # ── 4. LAP QUEUE ─────────────────────────────────────────────────────
        layout.separator()
        box = layout.box()
        row = box.row()
        row.label(text=f"Lap Queue  ({queue_len}/4)", icon='LINENUMBERS_ON')
        row.operator(OBJECT_OT_f1_clear_queue.bl_idname, text="", icon='TRASH')

        if queue_len > 0:
            for i, item in enumerate(scene.f1_lap_queue):
                row = box.row(align=True)
                # Session label — compact
                sess_label = item.session
                if item.q_segment:
                    sess_label = item.q_segment
                lap_label = "FAST" if item.fastest_lap else f"Lap ?"
                row.label(text=f"{i+1}.  {item.driver}  |  {item.year}  {sess_label}  {lap_label}")
                op = row.operator(OBJECT_OT_f1_remove_lap.bl_idname, text="", icon='X')
                op.index = i
        else:
            box.label(text="Queue is empty", icon='INFO')

        # ── 5. STATUS & GENERATE ─────────────────────────────────────────────
        layout.separator()
        layout.label(text=f"Status: {props.status_msg}")

        row = layout.row()
        row.scale_y = 2.0
        row.enabled = queue_len > 0
        row.operator(OBJECT_OT_f1_generate_scene.bl_idname,
                     icon='RENDER_ANIMATION', text="GENERATE SCENE")

        # ── 6. PATH BRUSH ─────────────────────────────────────────────────────
        layout.separator()
        layout.label(text="Path Sculpt Tools", icon='BRUSH_DATA')
        layout.prop_search(scene, "f1_path_object", bpy.data, "objects", text="Path")
        row = layout.row(align=True)
        row.prop(scene, "f1_brush_radius",   text="Radius")
        row.prop(scene, "f1_brush_strength", text="Strength")
        layout.prop(scene, "f1_brush_mode", text="Mode")
        layout.operator("f1.path_brush", text="Sculpt Path", icon='SCULPTMODE_HLT')
        layout.label(text="M=Push/Pull  Scroll=Radius  Shift+Scroll=Strength", icon='INFO')


classes = [PANEL_PT_F1_Studio]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
