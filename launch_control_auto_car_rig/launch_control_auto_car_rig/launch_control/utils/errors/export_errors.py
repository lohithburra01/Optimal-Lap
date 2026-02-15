import bpy
from enum import Enum

from ...logger import log_error
from ...ui.utils import show_message_box

class ExportErrorTypes(Enum):
    NOT_SAVED = 0
    NOT_FOUND = 1
    DATASMITH_NOT_FOUND = 2
    DATA_NOT_FOUND = 3
    BLEND_NOT_FOUND = 4
    NOT_WRITABLE = 5

def export_error_messages(errors_type: ExportErrorTypes, payload=None):
    if errors_type == ExportErrorTypes.NOT_SAVED:
        file_not_saved()
    if errors_type == ExportErrorTypes.NOT_FOUND:
        filepath_not_found()
    if errors_type == ExportErrorTypes.DATASMITH_NOT_FOUND:
        datasmith_not_found()
    if errors_type == ExportErrorTypes.DATA_NOT_FOUND:
        data_not_found()
    if errors_type == ExportErrorTypes.BLEND_NOT_FOUND:
        blend_not_found()
    if errors_type == ExportErrorTypes.NOT_WRITABLE:
        not_writable()

def file_not_saved():
    log_error("File not saved. Cannot export.", "OBJECT_OT_quick_export")
    show_message_box(
        "Requested to export relative to the .blend, but the file is not saved. Please save your file or change the export path.",
        "Could not export",
        "ERROR",
    )

def filepath_not_found():
    show_message_box(
        "Please make sure you are exporting to a valid absolute or relative path with a filename",
        "Could not export",
        "ERROR",
    )
    log_error("Cannot export.", "OBJECT_OT_quick_export")

def datasmith_not_found():
    show_message_box(
        "Error Writing File to datasmith format. Please make sure you are exporting to a valid absolute or relative path with a filename",
        "Could not export",
        "ERROR",
    )
    log_error("Cannot export - Error Writing File to datasmith format", "OBJECT_OT_quick_export_datasmith")

def data_not_found():
    show_message_box(
        "Could not locate all the needed data for export. Please make sure the Launch Control collections and objects are not corrupted or altered. You can try using 'Rig Info -> Update Vehicle Rig' to re-rig the vehicle and keep the animation.",
        "Could not export",
        "ERROR",
    )
    log_error("Cannot export.", "OBJECT_OT_quick_export_datasmith")

def blend_not_found():
    show_message_box(
        "Please make sure you are exporting to a valid absolute or relative path with a filename and 'File -> External Data -> Automatically pack Resources' is unchecked",
        "Could not export",
        "ERROR",
    )
    log_error("Cannot export.", "OBJECT_OT_quick_export_blend")

def not_writable():
    show_message_box(
        "File is in use by another Problem. Please change the name or close the other Program first.",
        "Could not export",
        "ERROR",
    )
    log_error("Cannot export.", "OBJECT_OT_quick_export_blend")