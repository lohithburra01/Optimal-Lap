"""f1_track_setup_panel — minimal UI for the one-time-per-track setup.

Most of the user's flow is back-end: queue drivers → Generate Scene → done.
But two things have to happen ONCE for any new track .blend before the auto-
chain can produce styled lines:

  1. Install F1 track-viz dependencies (scipy, fastf1, quadprog, etc.) into
     the isolated modules/f1_track_viz_deps folder. ~one-time per machine.
  2. Generate CENTERLINE + Q_RACING_LINE for the track mesh. ~one-time per
     track .blend; saved with the file so it carries forward.

This subpanel surfaces those three operators (which would otherwise only be
reachable via F3 search). After setup is complete on a track, the panel
shows ✓ markers and the user never needs to touch it again — Generate Scene
in the F1 Studio panel auto-chains everything.
"""
import bpy
from bpy.types import Panel


def _deps_ok():
    try:
        from ..operators.f1_track_viz import dependencies_available
        return dependencies_available()
    except Exception:
        return False


class PANEL_PT_F1_TrackSetup(Panel):
    bl_label = "F1 Track Setup (one-time per track)"
    bl_idname = "PANEL_PT_f1_track_setup"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'F1 Studio'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        cl = bpy.data.objects.get("CENTERLINE") is not None
        ql = bpy.data.objects.get("Q_RACING_LINE") is not None
        if cl and ql and _deps_ok():
            self.layout.label(text="✓", icon='CHECKMARK')

    def draw(self, context):
        layout = self.layout
        try:
            props = context.scene.f1_track_props
        except AttributeError:
            layout.label(text="Track-viz module not registered yet.", icon='ERROR')
            return

        # Step 1 — dependencies
        box = layout.box()
        box.label(text="1. Dependencies", icon='IMPORT')
        if _deps_ok():
            box.label(text="✓ Installed (scipy / fastf1 / quadprog / etc.)", icon='CHECKMARK')
        else:
            box.label(text="Required: scipy, fastf1, quadprog, trajectory_planning_helpers", icon='INFO')
            box.operator("object.install_f1_dependencies", icon='IMPORT')
            box.label(text="Restart Blender after install if prompted.", icon='QUESTION')

        deps = _deps_ok()

        # Step 2 — centerline
        box = layout.box()
        box.label(text="2. Centerline (one-time per track)", icon='SNAP_MIDPOINT')
        col = box.column(align=True)
        col.prop(props, "track_mesh", icon='MESH_PLANE')
        col.prop(props, "centerline_iterations")
        col.prop(props, "centerline_ray_step")
        col.prop(props, "centerline_max_width")
        col.prop(props, "centerline_smooth_sigma")
        row = box.row()
        row.enabled = deps
        row.operator("object.generate_centerline", icon='SNAP_MIDPOINT')
        if bpy.data.objects.get("CENTERLINE") is not None:
            box.label(text="✓ CENTERLINE in scene", icon='CHECKMARK')

        # Step 3 — Q racing line
        box = layout.box()
        box.label(text="3. Q Racing Line (one-time per track, ~150s)", icon='GP_MULTIFRAME_EDITING')
        col = box.column(align=True)
        col.prop(props, "racing_line_inset")
        col.prop(props, "racing_line_kappa_bound")
        col.prop(props, "racing_line_veh_width")
        col.prop(props, "racing_line_stepsize")
        row = box.row()
        row.enabled = deps and bpy.data.objects.get("CENTERLINE") is not None
        row.operator("object.generate_racing_line", icon='GP_MULTIFRAME_EDITING')
        if bpy.data.objects.get("Q_RACING_LINE") is not None:
            box.label(text="✓ Q_RACING_LINE in scene — save the .blend", icon='CHECKMARK')

        # Footer
        layout.separator()
        if (
            _deps_ok()
            and bpy.data.objects.get("CENTERLINE") is not None
            and bpy.data.objects.get("Q_RACING_LINE") is not None
        ):
            layout.label(
                text="Setup complete. Generate Scene auto-runs styled lines + alignment.",
                icon='CHECKMARK',
            )


classes = (PANEL_PT_F1_TrackSetup,)
