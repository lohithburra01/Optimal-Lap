from enum import Enum

from ...logger import log_error
from ...ui.utils import show_message_box

class PathErrorTypes(Enum):
    DIVISION0 = 0
    NOT_EDIT_MODE = 1
    TOO_MANY_POINTS = 2
    NO_POINTS = 3
    TANGENT_ANGLE = 4
    GROUND_DETECTION = 5
    DRIVING_PATH= 6
    SPLINE_TYPE=7
    CALCULATE_PATH_LENGTH=8


def path_error_messages(errors_type: PathErrorTypes):
    if errors_type == PathErrorTypes.DIVISION0:
        division_by0()
    if errors_type == PathErrorTypes.NOT_EDIT_MODE:
        not_edit_mode()
    if errors_type == PathErrorTypes.TOO_MANY_POINTS:
        none_too_many_points()
    if errors_type == PathErrorTypes.TANGENT_ANGLE:
        small_tangent()
    if errors_type == PathErrorTypes.GROUND_DETECTION:
        ground_detection_not_found()
    if errors_type == PathErrorTypes.DRIVING_PATH:
        driving_path_not_found()
    if errors_type == PathErrorTypes.SPLINE_TYPE:
        spline_type()
    if errors_type == PathErrorTypes.CALCULATE_PATH_LENGTH:
        curve_length_not_recieved()

def division_by0():
    log_error("Division by 0.", "OBJECT_OT_prepare_jump")
    show_message_box(
        "Division by 0. Please re-genrate the tangents for this point.",
        "ERROR",
    )

def not_edit_mode():
    log_error("Not in edit mode", "OBJECT_OT_prepare_jump")
    show_message_box(
        "Please enter 'Edit Mode' on the 'DrivingPath' object to add a jump",
        "Calculate Jump",
        "ERROR",
    )

def none_too_many_points():
    log_error(
        "Only one point allowed.",
        "OBJECT_OT_prepare_jump",
    )
    show_message_box(
        "Select one and only 1 point, which is the last point before the car is taking off and will be flying",
        "Calculate Jump",
        "ERROR",
    )

def small_tangent():
    log_error("Tangent has an angle of 0 or less.", "OBJECT_OT_prepare_jump")
    show_message_box(
        "Please rotate the control point, so the tangent shows the direction the car will fly. Right now the tangent has an angle of 0 or less",
        "ERROR",
    )

def ground_detection_not_found():
    log_error(
        "Could not find 'ground_detect_remeshed'. Please rig vehicle again.Enable Curve Tools Add-on.",
        "Show Groung Grid",
    )
    show_message_box(
        "Could not find 'ground_detect_remeshed'. Please rig vehicle again.",
        "Visualize Ground Detection",
        "ERROR",
    )

def driving_path_not_found():
    log_error(
        f"Cannot find the Driving Path object for calculating the length", "OBJECT_OT_refresh_path_len"
    )
    show_message_box(
        f"Cannot access the 'Driving Path' Object for the active vehicle. Please make sure it's not hidden in the scene. If it has been deleted a re-rig would be required",
        "Error while updating Driving Path",
        "ERROR",
    )

def spline_type():
    show_message_box(
        f"The 'DrivingPath' curve is of the spline type: Please change it to the Spline Type 'Bezier' to continue.",
        "Driving Path Issue",
        "ERROR",
    )
    log_error(
        "Need to change DrivingPath to the Spline Type 'Bezier'.",
        "refresh_path_len",
    )

def curve_length_not_recieved():
    log_error("Cannot get path length.", "OBJECT_OT_refresh_path_len")
    show_message_box(
            "Could not calculate the Driving Path Length", "Car Rig", "ERROR"
        )