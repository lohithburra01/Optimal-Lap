import bpy
from ..operators.F1_HiFi_Baker_Pro import F1_OT_InstallDeps, MISSING_DEPS
from ..operators.f1_pipeline import (
    OBJECT_OT_f1_generate_scene,
    OBJECT_OT_f1_add_lap_to_queue,
    OBJECT_OT_f1_remove_lap,
    OBJECT_OT_f1_clear_queue
)


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

        # ── 1. DEPENDENCY CHECK ──────────────────────────────────────────
        if MISSING_DEPS:
            box = layout.box()
            box.label(text="Missing Libraries!", icon='ERROR')
            box.label(text="F1 Studio requires fastf1 & pandas")
            box.operator(F1_OT_InstallDeps.bl_idname,
                         icon='PREFERENCES', text="Install Dependencies")
            return

        # ── 2. QUERY ENGINE ──────────────────────────────────────────────
        box = layout.box()
        box.label(text="Query Engine", icon='WORLD_DATA')
        col = box.column(align=True)
        col.prop(props, "sel_year")
        col.prop(props, "sel_race")
        col.prop(props, "sel_session")
        col.prop(props, "sel_driver")

        row = box.row()
        row.scale_y = 1.2
        row.operator(OBJECT_OT_f1_add_lap_to_queue.bl_idname,
                     icon='ADD', text="ADD LAP")

        # ── 3. LAP QUEUE ─────────────────────────────────────────────────
        layout.separator()
        box = layout.box()
        row = box.row()
        row.label(text="Lap Queue (Max 4)", icon='TEXT')
        row.operator(OBJECT_OT_f1_clear_queue.bl_idname, text="", icon='TRASH')

        if len(scene.f1_lap_queue) > 0:
            for i, item in enumerate(scene.f1_lap_queue):
                row = box.row()
                row.label(text=f"{i+1}. {item.driver}  |  {item.year}  |  {item.event}")
                op = row.operator(OBJECT_OT_f1_remove_lap.bl_idname, text="", icon='X')
                op.index = i
        else:
            box.label(text="Queue is empty", icon='INFO')

        # ── 4. STATUS & GENERATE ─────────────────────────────────────────
        layout.separator()
        layout.label(text=f"Status: {props.status_msg}")

        row = layout.row()
        row.scale_y = 2.0
        row.enabled = len(scene.f1_lap_queue) > 0
        row.operator(OBJECT_OT_f1_generate_scene.bl_idname,
                     icon='RENDER_ANIMATION', text="GENERATE SCENE")

        # ── PATH BRUSH ──────────────────────────────
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
