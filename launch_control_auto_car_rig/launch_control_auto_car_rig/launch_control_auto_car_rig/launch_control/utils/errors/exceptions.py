from ...logger import log_error, log_info
from ...ui.utils import show_message_box

class LCException(Exception):
    """Exception raised for errors in Launch Control.

    Attributes:
        message -- explanation of the error
        status -- ERROR / INFO
        method -- function where the error occured
    """

    def __init__(self, method="", message="A custom error occurred.", status="ERROR"):
        self.message = message
        self.status = status
        self.method = method
        
        super().__init__(self.message)

    def show_error_message(self, title = ""):
        # log
        if self.status == "ERROR":
            log_error(self.message, self.method)

        if self.status == "INFO":
            log_info(self.message, self.method)

        # show message box
        title_to_use = title if title != "" else self.method
        show_message_box(self.message, title_to_use, self.status)


class RigCollectionNotFound(LCException):
    """Exception raised when rig collection not present in scene.

    Attributes:
        message -- explanation of the error
        status -- ERROR / INFO
        method -- function where the error occured
    """

    def __init__(self, car_name):
        self.message = f"Launch Control Rig Collection for '{car_name}' not found in scene."
        self.status = "ERROR"
        self.method = "Searching for Rig Collection"
        
        super().__init__(self.method, self.message, self.status)


class DrivingPathnNotFound(LCException):
    """Exception raised when rig collection not present in scene.

    Attributes:
        message -- explanation of the error
        status -- ERROR / INFO
        method -- function where the error occured
    """

    def __init__(self, car_name):
        self.message = f"Launch Control Driving Path object for '{car_name}' not found in scene. Please make sure it's not hidden or deleted."
        self.status = "ERROR"
        self.method = "Searching for Driving Path"
        
        super().__init__(self.method, self.message, self.status)


class WrongContext(LCException):
    """Exception raised when context is wrong and could not be changed.

    Attributes:
        message -- explanation of the error
        status -- ERROR / INFO
        method -- function where the error occured
    """

    def __init__(self, car_name):
        self.message = f"Could not animte vehicle, please select the rig, change to 'Pose Mode' and then back to 'Object Mode' and try again"
        self.status = "ERROR"
        self.method = "Failed to access Rig"
        
        super().__init__(self.method, self.message, self.status)