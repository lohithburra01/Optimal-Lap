from .logger import log_info

def all():
    from .. import launch_control
    import importlib as il

    # Reload package
    il.reload(launch_control)
        
    log_info("Done", "reload")
