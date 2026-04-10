import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d, location_3d_to_region_2d


class F1_OT_PathBrush(bpy.types.Operator):
    bl_idname  = "f1.path_brush"
    bl_label   = "F1 Path Brush"
    bl_options = {'REGISTER', 'UNDO'}

    _draw_handle = None
    _mouse_3d    = None
    _painting    = False

    def modal(self, context, event):
        context.area.tag_redraw()

        if event.type in {'MOUSEMOVE', 'LEFTMOUSE'}:
            self._mouse_3d = self._get_mouse_3d(context, event)

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self._finish(context)
            return {'FINISHED'}

        if event.type == 'LEFTMOUSE':
            self._painting = event.value == 'PRESS'

        if self._painting and self._mouse_3d:
            self._apply_brush(context)

        if event.type == 'WHEELUPMOUSE' and not event.shift:
            context.scene.f1_brush_radius += 2.0
            return {'RUNNING_MODAL'}
        if event.type == 'WHEELDOWNMOUSE' and not event.shift:
            context.scene.f1_brush_radius = max(0.5, context.scene.f1_brush_radius - 2.0)
            return {'RUNNING_MODAL'}
        if event.type == 'WHEELUPMOUSE' and event.shift:
            context.scene.f1_brush_strength = min(1.0, context.scene.f1_brush_strength + 0.05)
            return {'RUNNING_MODAL'}
        if event.type == 'WHEELDOWNMOUSE' and event.shift:
            context.scene.f1_brush_strength = max(0.01, context.scene.f1_brush_strength - 0.05)
            return {'RUNNING_MODAL'}
        if event.type == 'M' and event.value == 'PRESS':
            context.scene.f1_brush_mode = 'PULL' if context.scene.f1_brush_mode == 'PUSH' else 'PUSH'
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    def _get_mouse_3d(self, context, event):
        region = context.region
        rv3d   = context.region_data
        coord  = (event.mouse_region_x, event.mouse_region_y)
        origin = region_2d_to_origin_3d(region, rv3d, coord)
        vector = region_2d_to_vector_3d(region, rv3d, coord)
        if abs(vector.z) < 1e-8:
            return None
        t = -origin.z / vector.z
        return origin + vector * t

    def _apply_brush(self, context):
        scene     = context.scene
        radius    = scene.f1_brush_radius
        strength  = scene.f1_brush_strength
        obj       = scene.f1_path_object
        if obj is None or obj.type != 'CURVE':
            return

        mouse_pos = np.array([self._mouse_3d.x, self._mouse_3d.y])

        for spline in obj.data.splines:
            if spline.type != 'BEZIER':
                continue
            for bp in spline.bezier_points:
                pt_pos = np.array([bp.co.x, bp.co.y])
                dist   = np.linalg.norm(mouse_pos - pt_pos)
                if dist > radius:
                    continue
                falloff   = (np.cos(dist / radius * np.pi) + 1) / 2
                weight    = falloff * strength
                direction = (pt_pos - mouse_pos) if scene.f1_brush_mode == 'PUSH' else (mouse_pos - pt_pos)
                d_mag     = np.linalg.norm(direction)
                if d_mag < 1e-8:
                    continue
                direction /= d_mag
                bp.co.x += direction[0] * weight
                bp.co.y += direction[1] * weight
                bp.handle_left_type  = 'AUTO'
                bp.handle_right_type = 'AUTO'

    def _draw_brush_circle(self, context):
        if self._mouse_3d is None:
            return
        scene    = context.scene
        radius   = scene.f1_brush_radius
        strength = scene.f1_brush_strength
        mode     = scene.f1_brush_mode
        region   = context.region
        rv3d     = context.region_data

        angles = np.linspace(0, 2 * np.pi, 64, endpoint=False)
        coords = []
        for a in angles:
            wp = self._mouse_3d.copy()
            wp.x += np.cos(a) * radius
            wp.y += np.sin(a) * radius
            sp = location_3d_to_region_2d(region, rv3d, wp)
            if sp:
                coords.append((sp.x, sp.y))
        if len(coords) < 3:
            return
        coords.append(coords[0])

        color  = (0.2, 0.6, 1.0, 0.9 if self._painting else 0.5) if mode == 'PUSH' else (1.0, 0.5, 0.1, 0.9 if self._painting else 0.5)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch  = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(2.0)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)
        gpu.state.blend_set('NONE')
        gpu.state.line_width_set(1.0)

        context.area.header_text_set(
            f"F1 Brush | LMB=Paint  RMB/ESC=Done  M=Toggle | "
            f"Scroll=Radius({radius:.0f})  Shift+Scroll=Strength({strength:.2f}) | "
            f"Mode: {mode}"
        )

    def _finish(self, context):
        self._painting = False
        if self._draw_handle:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, 'WINDOW')
            self._draw_handle = None
        try:
            from .f1_trail import sync_all_trails_from_paths
            sync_all_trails_from_paths(context.scene)
        except Exception:
            pass
        context.area.header_text_set(None)
        context.area.tag_redraw()

    def invoke(self, context, event):
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "Must be in 3D viewport")
            return {'CANCELLED'}
        if context.scene.f1_path_object is None:
            self.report({'WARNING'}, "No path object set")
            return {'CANCELLED'}
        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_brush_circle, (context,), 'WINDOW', 'POST_PIXEL'
        )
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


def register():
    bpy.utils.register_class(F1_OT_PathBrush)
    bpy.types.Scene.f1_brush_radius   = bpy.props.FloatProperty(name="Brush Radius",   default=10.0, min=0.5,  max=500.0)
    bpy.types.Scene.f1_brush_strength = bpy.props.FloatProperty(name="Brush Strength", default=0.1,  min=0.01, max=1.0)
    bpy.types.Scene.f1_brush_mode     = bpy.props.EnumProperty(name="Brush Mode", items=[
                                            ('PUSH','Push','Push away'),
                                            ('PULL','Pull','Pull toward')], default='PUSH')
    bpy.types.Scene.f1_path_object    = bpy.props.PointerProperty(name="F1 Path Object", type=bpy.types.Object)


def unregister():
    bpy.utils.unregister_class(F1_OT_PathBrush)
    for name in ['f1_brush_radius','f1_brush_strength','f1_brush_mode','f1_path_object']:
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
