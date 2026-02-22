import bpy
import os

from ..utils.functions import get_addon_path
from ..utils.resources import get_resource_path
from .. import data
from ..globals import FILENAME_BLEND

from ..ui.utils import show_message_box
from ..logger import log_info, log_debug, log_error


def anim_preset_categories_callback(scene, context):

    lc_addon_path = get_addon_path()
    pro_path = os.path.join(lc_addon_path, "pro_features")
    if os.path.isdir(pro_path):
        items=[
            ("default", "Presets", ""),
            ("custom", "Local", ""),
            ("library","Library", ""),
        ]
    else:
        items=[
            ("default", "Presets", ""),
            ("custom", "Custom", ""),
        ]

    return items

def crop_image(orig_img, cropped_min_x, cropped_max_x, cropped_min_y, cropped_max_y):
    '''Crops an image object of type <class 'bpy.types.Image'>.  For example, for a 10x10 image, 
    if you put cropped_min_x = 2 and cropped_max_x = 6,
    you would get back a cropped image with width 4, and 
    pixels ranging from the 2 to 5 in the x-coordinate

    Note: here y increasing as you down the image.  So, 
    if cropped_min_x and cropped_min_y are both zero, 
    you'll get the top-left of the image (as in GIMP).

    Returns: An image of type  <class 'bpy.types.Image'>
    '''

    num_channels=orig_img.channels
    #calculate cropped image size
    cropped_size_x = cropped_max_x - cropped_min_x
    cropped_size_y = cropped_max_y - cropped_min_y
    #original image size
    orig_size_x = orig_img.size[0]
    orig_size_y = orig_img.size[1]

    cropped_img = bpy.data.images.new(name="cropped_img", width=cropped_size_x, height=cropped_size_y)

    #print("Exctracting image fragment, this could take a while...")

    #loop through each row of the cropped image grabbing the appropriate pixels from original
    #the reason for the strange limits is because of the 
    #order that Blender puts pixels into a 1-D array.
    current_cropped_row = 0
    for yy in range(orig_size_y - cropped_max_y, orig_size_y - cropped_min_y):
        #the index we start at for copying this row of pixels from the original image
        orig_start_index = (cropped_min_x + yy*orig_size_x) * num_channels
        #and to know where to stop we add the amount of pixels we must copy
        orig_end_index = orig_start_index + (cropped_size_x * num_channels)
        #the index we start at for the cropped image
        cropped_start_index = (current_cropped_row * cropped_size_x) * num_channels 
        cropped_end_index = cropped_start_index + (cropped_size_x * num_channels)

        #copy over pixels 
        cropped_img.pixels[cropped_start_index : cropped_end_index] = orig_img.pixels[orig_start_index : orig_end_index]

        #move to the next row before restarting loop
        current_cropped_row += 1

    return cropped_img


class OBJECT_OT_save_anim_preset(bpy.types.Operator):
    bl_label = "Save Current Animation to Preset"
    bl_idname = "object.save_anim_preset"
    bl_description = "Saves the current animation in the scene to an Animation Preset with the specified name for later use"

    overwrite: bpy.props.BoolProperty(name="overwrite", default=False, options={'SKIP_SAVE'})
    input_name: bpy.props.StringProperty(name="input_name", default="", options={'SKIP_SAVE'})

    def execute(self, context):
        scene = context.scene
        active_car = scene.lc.find_selected()

        addons_path = get_addon_path()
        addon_root = ".".join(__package__.split(".")[:-2])
        addon_preferences = context.preferences.addons[addon_root].preferences


        if scene.settings.filter_anim_presets == "custom":
            destination_folder = os.path.join(addons_path, "assets", "images", "custom_presets")
    
        elif scene.settings.filter_anim_presets == "library":
            destination_folder = os.path.join(addon_preferences.anim_preset_lib_path)


        #print("self.overwrite", self.overwrite)
        #print("self.input_name", self.input_name)

        if self.overwrite == False:
            filename_base = scene.settings.anim_preset_name
        else:
            filename_base = self.input_name


        #print("filename_base", filename_base)

        # If preset name in use
        if self.overwrite == False:
            for cur_fn in os.listdir(destination_folder):
                if cur_fn.lower() == (filename_base + '.blend').lower():
                    text = "Animation Preset already exists. Pick another name"
                    show_message_box(text, "Save Custom Animation Preset", "ERROR")
                    log_info(text, "OBJECT_OT_save_anim_preset")
                    return {'CANCELLED'}

                if len(filename_base) == 0:
                    text = "Please Write a name for the Animation Preset"
                    show_message_box(text, "Save Custom Animation Preset", "ERROR")
                    log_info(text, "OBJECT_OT_save_anim_preset")
                    return {'CANCELLED'}
                

        filename = filename_base + '.blend'
                

        # Create undo point
        bpy.ops.ed.undo_push()

        path = active_car.driving_path
        action = active_car.rig_object.animation_data.action

        ground_coll = None
        for coll in bpy.context.scene.collection.children_recursive:
            if coll.name == "GroundDetection":
                ground_coll = coll

        data_blocks = []
        data_blocks.append(ground_coll)
        data_blocks.append(path)
        data_blocks.append(action)

        filepath = os.path.join(destination_folder, filename)
        #print("filepath", filepath)
        bpy.data.libraries.write(filepath, set(data_blocks), fake_user=True)


        self.filename_snap = filename_base + '.png'
        self.filepath_snap = os.path.join(destination_folder, self.filename_snap)

        self.modal_i = 0

        restore_overlays = bpy.context.space_data.overlay.show_overlays 
        restore_region_header = bpy.context.space_data.show_region_header
        restore_tool_header = bpy.context.space_data.show_region_tool_header
        restore_gizmo = bpy.context.space_data.show_gizmo 

        self.restore_overlays = [restore_overlays, restore_region_header, restore_tool_header, restore_gizmo]
        
        self.model_i = 0

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.0001, window=context.window)
        wm.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}
    

    def modal(self, context, event):

        if event.type in {'ESC'}:
            self.cancel(context)
            return {'CANCELLED'}
        
        if self.modal_i > 2:
            self.cancel(context)
            return {'FINISHED'}
        
        if bpy.context.area.type == 'VIEW_3D':
            bpy.context.space_data.overlay.show_overlays = False 
            bpy.context.space_data.show_region_header = False
            bpy.context.space_data.show_region_tool_header = False
            bpy.context.space_data.show_gizmo = False 

        self.modal_i += 1

        return {'PASS_THROUGH'}


    def cancel(self, context):

        bpy.ops.screen.screenshot_area(filepath=self.filepath_snap, hide_props_region=True, check_existing=False)

        wm = context.window_manager
        wm.event_timer_remove(self._timer)

        bpy.context.space_data.overlay.show_overlays = self.restore_overlays[0] 
        bpy.context.space_data.show_region_header = self.restore_overlays[1]
        bpy.context.space_data.show_region_tool_header = self.restore_overlays[2]
        bpy.context.space_data.show_gizmo = self.restore_overlays[3]
        
        snap_img = None
        snap_img = bpy.data.images.load(self.filepath_snap, check_existing=False)
        if snap_img is not None:

            x, y = snap_img.size
            scale_factor = 0.33
            snap_img.scale( int(x*scale_factor), int(y*scale_factor) )

            x, y = snap_img.size
            x_center = x*0.5
            y_center = y*0.5

            min_dimension = min(x,y)
            offset = min_dimension*0.45
            
            cropped_image = crop_image(snap_img, int(x_center-offset), int(x_center+offset), int(y_center-offset), int(y_center+offset))

            cropped_image.filepath_raw = self.filepath_snap
            cropped_image.file_format = 'PNG'
            cropped_image.save()

            bpy.data.images.remove(cropped_image)
            bpy.data.images.remove(snap_img)
        

        # Re-Register "Data" to reload Galleries
        data.unregister()
        data.register()

        bpy.data.window_managers["WinMan"].animation_presets = self.filename_snap

        return {'FINISHED'}
    


class OBJECT_OT_remove_anim_preset(bpy.types.Operator):
    bl_label = "Remove Animation Preset"
    bl_idname = "object.remove_anim_preset"
    bl_description = "Removes the currently selected animation preset from the gallery"

    

    def execute(self, context):
        scene = context.scene
        active_car = scene.lc.find_selected()

        # Create undo point
        bpy.ops.ed.undo_push()

        bpy.ops.wm.delete_anim_preset_confirm('INVOKE_DEFAULT')

        return {'FINISHED'}


def delete_anim_preset():
    scene = bpy.context.scene

    addons_path = get_addon_path()
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = bpy.context.preferences.addons[addon_root].preferences
    
    if scene.settings.filter_anim_presets == "custom":
        file_dir = os.path.join(addons_path, "assets", "images", "custom_presets")

    elif scene.settings.filter_anim_presets == "library":
        file_dir = os.path.join(addon_preferences.anim_preset_lib_path)


    sel_anim = os.path.splitext(bpy.data.window_managers["WinMan"].animation_presets)[0]

    file_name = (sel_anim + ".blend")
    file_path = os.path.join(file_dir, file_name)

    os.remove(file_path)


    file_name = (sel_anim + ".png")
    file_path = os.path.join(file_dir, file_name)

    os.remove(file_path)

    bpy.data.window_managers["WinMan"].animation_presets = '一 Create 一.png'

    return None


def overwrite_anim_preset():

    current_preset_name = os.path.splitext(bpy.data.window_managers["WinMan"].animation_presets)[0]
    bpy.ops.object.save_anim_preset(overwrite=True, input_name=current_preset_name)

    return None
    



class OBJECT_OT_edit_anim_preset(bpy.types.Operator):
    bl_label = "Override Animation Preset"
    bl_idname = "object.edit_anim_preset"
    bl_description = "Override the currently selected animation preset from the gallery with animation in the viewport"

    def execute(self, context):
        scene = context.scene

        # Create undo point
        bpy.ops.ed.undo_push()

        bpy.ops.wm.overwrite_anim_preset_confirm('INVOKE_DEFAULT')

        return {'FINISHED'}