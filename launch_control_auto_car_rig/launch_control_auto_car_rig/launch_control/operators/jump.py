import bpy
import math
import mathutils
import numpy as np

from ..ui.utils import show_message_box
from ..utils.errors.path_errors import path_error_messages, PathErrorTypes
from ..logger import log_info, log_error, log_debug

class OBJECT_OT_prepare_jump(bpy.types.Operator):
    bl_label = "Jump!"
    bl_idname = "object.prepare_jump"
    bl_description = "Calculate the realistic path for a jump"
    bl_options = {"REGISTER", "UNDO"}

    def unit_vector(self, vector):
        """Returns the unit vector of the vector."""
        try:
            return vector / np.linalg.norm(vector)
        except:
            path_error_messages(PathErrorTypes.DIVISION0)                
            return 0

    def angle_between(self, v1, v2):
        """Returns the angle in radians between vectors 'v1' and 'v2'::
        >>> angle_between((1, 0, 0), (0, 1, 0))
        1.5707963267948966
        >>> angle_between((1, 0, 0), (1, 0, 0))
        0.0
        >>> angle_between((1, 0, 0), (-1, 0, 0))
        3.141592653589793
        """
        v1_u = self.unit_vector(v1)
        v2_u = self.unit_vector(v2)
        return np.arccos(np.clip(np.dot(v1_u, v2_u), -1.0, 1.0))

    def execute(self, context):
        scene = context.scene

        car = scene.lc.find_selected()
        driving_path = car.driving_path
        addon_root = ".".join(__package__.split(".")[:-2])
        addon_preferences = context.preferences.addons[addon_root].preferences
        use_imperial = addon_preferences.use_imperial

        # Check if mode is correct and such stuffs...
        if context.mode != "EDIT_CURVE":
            path_error_messages(PathErrorTypes.NOT_EDIT_MODE)
            return {"CANCELLED"}

        if driving_path not in context.selected_objects:
            print("path not in selected objs (cancelled)")
            path_error_messages(PathErrorTypes.NOT_EDIT_MODE)
            return {"CANCELLED"}

        if driving_path.data.splines[0].type != 'BEZIER':
            path_error_messages(PathErrorTypes.SPLINE_TYPE)
            return {"CANCELLED"}

        # Create undo point
        bpy.ops.ed.undo_push()

        # Store Pivot tool!
        restore_pivot_tool = scene.tool_settings.transform_pivot_point
        scene.tool_settings.transform_pivot_point = "MEDIAN_POINT"

        # speed = 50 #km/h
        speed = car.settings.jump_speed
        if use_imperial: 
            speed = speed * 1.609
        speed = speed * 1
        airDrag_factor = 0.85

        # Finding the Maximum height
        spline = driving_path.data.splines[0]
        g = 9.82

        # Find selected points
        selected_points = [point for point in spline.bezier_points if point.select_control_point]

        if len(selected_points) != 1:
            path_error_messages(PathErrorTypes.TOO_MANY_POINTS)
            scene.tool_settings.transform_pivot_point = restore_pivot_tool
            return {"CANCELLED"}

        # Find index of the one and ONLY selcted point
        point_index = 0
        for point in spline.bezier_points:
            if point.select_control_point:
                break
            point_index = point_index + 1

        # Save initial handle loc for the end!
        init_end_handle_loc = spline.bezier_points[point_index].handle_right.copy()

        # point_loc is easy access to the location of the main point
        point_loc = spline.bezier_points[
            (point_index)
        ].co.copy()  # Without copy, the value would sometimes explode...

        # Find angle
        handle_loc = spline.bezier_points[
            (point_index)
        ].handle_left  # the handle before the jump!

        init_vctr = (
            spline.bezier_points[(point_index)].co
            - spline.bezier_points[(point_index)].handle_left
        )
        flat_vctr = np.array([init_vctr[0], init_vctr[1], 0])

        angle = self.angle_between(flat_vctr, init_vctr)

        if angle < 0.01:
            path_error_messages(PathErrorTypes.TANGENT_ANGLE)
            scene.tool_settings.transform_pivot_point = restore_pivot_tool
            return {"CANCELLED"}

        # Check if it is part of a jump already!
        x = [0, 1]
        for n in x:
            try:
                spline.bezier_points[(point_index + n)]
                if spline.bezier_points[(point_index + n)].weight_softbody == 0.5:
                    bpy.ops.curve.select_all(action="DESELECT")
                    spline.bezier_points[(point_index + n)].select_control_point = True
                    try:
                        spline.bezier_points[
                            (point_index + n + 1)
                        ].select_control_point = (
                            True  # In case the landing point is there, delete that too
                        )
                    except:
                        pass
                    bpy.ops.curve.delete(type="VERT")
                    log_debug("Removed existing jump points.", "OBJECT_OT_prepare_jump")
            except:
                log_error("Not a top-jump point.", "OBJECT_OT_prepare_jump")

        # Find initial height
        h_init = point_loc[2]

        # Find v_init_y
        v_init = speed / 3.6  # User variable to m/s

        v_init_len = v_init * math.cos(angle)
        v_init_h = v_init * math.sin(angle)

        # Find h_max
        h_max = h_init + v_init_h**2 / (2 * g)

        # Find len_maxH
        t_max = v_init_h / g

        len_maxH = v_init_len * t_max

        # Add new point (y_max
        x_final = (
            len_maxH * airDrag_factor * self.unit_vector(init_vctr)[0]
        ) + point_loc[
            0
        ]  # Add offset from jump start pos

        y_final = (
            len_maxH * airDrag_factor * self.unit_vector(init_vctr)[1]
        ) + point_loc[
            1
        ]  # Add offset from the start pos of jump

        h_final = (
            h_max * airDrag_factor
        )  # Don't add the height of the jump as it's already in the formula

        # Select next point and subdivide if avaible. If not add the point!
        try:
            spline.bezier_points[(point_index)].select_control_point = True
            spline.bezier_points[(point_index + 1)].select_control_point = True
            bpy.ops.curve.subdivide()
        except:
            bpy.ops.curve.select_all(action="DESELECT")
            spline.bezier_points[(point_index)].select_control_point = True
            bpy.ops.curve.extrude_move(
                CURVE_OT_extrude={"mode": "TRANSLATION"},
                TRANSFORM_OT_translate={
                    "value": (0, 1, 0),
                    "orient_type": "GLOBAL",
                    "orient_matrix": ((0, 0, 0), (0, 0, 0), (0, 0, 0)),
                    "orient_matrix_type": "GLOBAL",
                    "constraint_axis": (False, False, False),
                    "mirror": False,
                    "use_proportional_edit": False,
                    "proportional_edit_falloff": "SMOOTH",
                    "proportional_size": 1,
                    "use_proportional_connected": False,
                    "use_proportional_projected": False,
                    "snap": False,
                    "snap_target": "CLOSEST",
                    "snap_point": (0, 0, 0),
                    "snap_align": False,
                    "snap_normal": (0, 0, 0),
                    "gpencil_strokes": False,
                    "cursor_transform": False,
                    "texture_space": False,
                    "remove_on_cancel": False,
                    "view2d_edge_pan": False,
                    "release_confirm": False,
                    "use_accurate": False,
                    "use_automerge_and_split": False,
                },
            )
            spline.bezier_points[(point_index)].select_control_point = True
            spline.bezier_points[(point_index + 1)].select_control_point = True

        # Move the point
        h_max_vector = mathutils.Vector((x_final, y_final, h_final))
        spline.bezier_points[(point_index + 1)].co = h_max_vector

        # Set to automatic interpolation
        bpy.ops.curve.select_all(action="DESELECT")

        spline.bezier_points[(point_index + 1)].select_control_point = True
        spline.bezier_points[(point_index + 1)].select_left_handle = True
        spline.bezier_points[(point_index + 1)].select_right_handle = True
        spline.bezier_points[(point_index + 1)].weight_softbody = 0.5

        bpy.ops.curve.handle_type_set(type="AUTOMATIC")

        # POINT TOP HAS BEEN PLACED

        # find range (x_range)

        # find t_flight first!
        h_landing = 0
        t_flight = (
            v_init_h + math.sqrt(v_init_h**2 + 2 * g * (h_init - h_landing))
        ) / g

        x_range = t_flight * v_init_len

        x02_final = (
            x_range * airDrag_factor * self.unit_vector(init_vctr)[0]
        ) + point_loc[0]
        y02_final = (
            x_range * airDrag_factor * self.unit_vector(init_vctr)[1]
        ) + point_loc[1]
        h02_final = h_landing * airDrag_factor

        try:
            bpy.ops.curve.select_all(action="DESELECT")
            spline.bezier_points[(point_index + 1)].select_control_point = True
            spline.bezier_points[(point_index + 2)].select_control_point = True
            bpy.ops.curve.subdivide()
        except:
            log_info("Adding extra point for landing point", "OBJECT_OT_prepare_jump")
            bpy.ops.curve.select_all(action="DESELECT")
            spline.bezier_points[(point_index + 1)].select_control_point = True
            bpy.ops.curve.extrude_move(
                CURVE_OT_extrude={"mode": "TRANSLATION"},
                TRANSFORM_OT_translate={
                    "value": (0, 1, 0),
                    "orient_type": "GLOBAL",
                    "orient_matrix": ((0, 0, 0), (0, 0, 0), (0, 0, 0)),
                    "orient_matrix_type": "GLOBAL",
                    "constraint_axis": (False, False, False),
                    "mirror": False,
                    "use_proportional_edit": False,
                    "proportional_edit_falloff": "SMOOTH",
                    "proportional_size": 1,
                    "use_proportional_connected": False,
                    "use_proportional_projected": False,
                    "snap": False,
                    "snap_target": "CLOSEST",
                    "snap_point": (0, 0, 0),
                    "snap_align": False,
                    "snap_normal": (0, 0, 0),
                    "gpencil_strokes": False,
                    "cursor_transform": False,
                    "texture_space": False,
                    "remove_on_cancel": False,
                    "view2d_edge_pan": False,
                    "release_confirm": False,
                    "use_accurate": False,
                    "use_automerge_and_split": False,
                },
            )
            spline.bezier_points[(point_index + 1)].select_control_point = True
            spline.bezier_points[(point_index + 2)].select_control_point = True

        # Moving the 2nd point
        range_vector = mathutils.Vector((x02_final, y02_final, h02_final))
        spline.bezier_points[(point_index + 2)].co = range_vector

        # Scale point to 0
        bpy.ops.curve.select_all(action="DESELECT")
        spline.bezier_points[(point_index + 2)].select_control_point = True
        spline.bezier_points[(point_index + 2)].select_left_handle = True
        spline.bezier_points[(point_index + 2)].select_right_handle = True
        bpy.ops.transform.resize(
            value=(0, 0, 0),
            orient_type="GLOBAL",
            orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
            orient_matrix_type="GLOBAL",
            mirror=False,
            use_proportional_edit=False,
            proportional_edit_falloff="SMOOTH",
            proportional_size=1,
            use_proportional_connected=False,
            use_proportional_projected=False,
        )

        # Set "is top point" to 0 for the end point
        spline.bezier_points[(point_index + 2)].weight_softbody = 0.0

        # Resetting handle to original pos
        spline.bezier_points[(point_index)].handle_right = init_end_handle_loc

        unit = "km/h"
        if use_imperial:
            unit = "mph"
            speed = speed / 1.609

        # Show message
        jump_options = (
            "You can change 'Jump Speed' in 'Jump Trajectory' and re-generate jump points."
        )
        message = f"Expected speed of vehicle at the jump to be: {int(speed)}{unit}. {jump_options}"
        show_message_box(message, "Added 2 points for the jump", "INFO")

        bpy.ops.object.refresh_path_len()

        scene.tool_settings.transform_pivot_point = restore_pivot_tool

        return {"FINISHED"}
