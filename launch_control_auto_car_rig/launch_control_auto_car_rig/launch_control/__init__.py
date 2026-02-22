'''
Copyright (C) 2021-2023 Daniel Vesterbaek
danielvesterbaekdesign@gmail.com

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

'''
from . import reload, patch, ui, data, operators

# Handle Reload Scripts
if 'reload' in locals():
    import importlib as il
    il.reload(reload)
    reload.all()

def register():
    patch.add_local_modules_to_path()
    
    # PANELS & MENUS
    ui.register()

    # OPERATORS
    operators.register()

    # PROPERTIES
    data.register()

    # DATASMITH
    




def unregister():
    # PANELS & MENUS
    ui.unregister()

    # OPERATORS
    operators.unregister()

    # PROPERTIES
    data.unregister()



if __name__ == "__main__":
    register()
