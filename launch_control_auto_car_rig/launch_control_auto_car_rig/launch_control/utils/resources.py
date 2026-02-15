import bpy
import os
import zipfile

from ..logger import log_error, log_info, log_debug
from .functions import get_collection_by_name
from ..globals import *
from pathlib import Path


def get_resource_path(file_name):
    addons_path = bpy.utils.user_resource("EXTENSIONS", path="user_default")
    file_path = os.path.join(addons_path, "launch_control_auto_car_rig", "assets", file_name)

    if not Path(file_path).exists():
        log_info("Didn't find add-on in default location. Will try user paths", "get_resource_path")

        for user_file_path in bpy.context.preferences.extensions.repos:
            file_path = os.path.join(user_file_path.directory, "launch_control_auto_car_rig", "assets", file_name)

            log_info(f"Trying path: {file_path}", "get_resource_path")

            if not Path(file_path).exists():
                file_path = None
    
    return file_path


def get_addon_path():
    addons_dir = bpy.utils.user_resource("EXTENSIONS", path="user_default")
    addons_path = os.path.join(addons_dir, "launch_control_auto_car_rig")

    if not Path(addons_path).exists():
        log_debug("Didn't find add-on in default location. Will try user paths", "get_addon_path")

        for user_file_path in bpy.context.preferences.extensions.repos:
            addons_dir = user_file_path.directory
            addons_path = os.path.join(addons_dir, "launch_control_auto_car_rig")

            log_debug(f"Trying path: {addons_path}", "get_addon_path")
            if not Path(addons_path).exists():
                addons_path = None

    return addons_path


def upload_asset(file_path, inner_path, file_name):

    #### Testing the new upload method
    """c = []

    path = os.path.join(file_path, inner_path, file_name)
    with bpy.data.libraries.load(file_path) as (data_from, data_to):
            for name in data_from.collections:
                c.append(name)
                
    print("c: ", c)""" 


    bpy.ops.wm.append(
         filepath=os.path.join(file_path, inner_path, file_name),
         directory=os.path.join(file_path, inner_path),
         filename=file_name,
         instance_collections=False,
     )
    

def upload_multi_asset(file_path, inner_path, files):


    bpy.ops.wm.append(
         directory=os.path.join(file_path, inner_path),
         files=files,
         instance_collections=False,
     )


def enum_previews_from_directory_items_anims(self, context, preview_collections):
    """EnumProperty callback for generating preview thumbnails from images in a directory."""
    enum_items = []
    scene = bpy.context.scene

    if context is None:
        return enum_items
    
    addons_path = get_addon_path()
    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = context.preferences.addons[addon_root].preferences

    directory_default = os.path.join(addons_path, "assets", "images")
    directory_custom = os.path.join(addons_path, "assets", "images", "custom_presets")
    directory_library = None
    try:
        directory_library = os.path.join(addon_preferences.anim_preset_lib_path)
    except:
        pass
    

    if scene.settings.filter_anim_presets == "default":
        directory = directory_default

    elif scene.settings.filter_anim_presets == "custom":
        directory = directory_custom
    
    elif scene.settings.filter_anim_presets == "library" and directory_library is not None:
        directory = directory_library
        

    # Get the preview collection (defined in the register function).
    pcoll = preview_collections["main"]

    # If the directory is the same as the animation presets directory, return the existing animation presets.
    if directory == pcoll.animation_presets_dir:
        return pcoll.animation_presets

    if directory and os.path.exists(directory):
        # Scan the directory for png files.
        image_paths = [
            fn for fn in os.listdir(directory) if fn.lower().endswith(".png")
        ]

        # Iterate over the images and generate a thumbnail preview for each.
        for i, name in enumerate(image_paths):
            filepath = os.path.join(directory, name)

            # Check if a preview icon for this image already exists in the collection.
            icon = pcoll.get(name)
            if not icon:
                # If no icon exists, load the image and generate a new thumbnail.
                thumb = pcoll.load(name, filepath, "IMAGE")
            else:
                # If an icon exists, use the existing thumbnail.
                thumb = pcoll[name]

            label = os.path.splitext(name)[0]  # remove extension to the name
            enum_items.append((name, label, "", thumb.icon_id, i))

    pcoll.animation_presets = enum_items
    pcoll.animation_presets_dir = directory

    return pcoll.animation_presets


def enum_previews_from_directory_items_cars(self, context, preview_collections):
    """EnumProperty callback for generating preview thumbnails from images in a directory."""
    enum_items = []

    if context is None:
        return enum_items

    # wm = context.window_manager
    addons_path = get_addon_path() 
    directory = os.path.join(addons_path, "assets", "vehicles")

    # Get the preview collection (defined in the register function).
    pcoll = preview_collections["main"]

    # If the directory is the same as the animation presets directory, return the existing animation presets.
    if directory == pcoll.vehicle_presets_dir:
        return pcoll.vehicle_presets

    if directory and os.path.exists(directory):
        # Scan the directory for png files.
        image_paths = [
            fn for fn in os.listdir(directory) if fn.lower().endswith(".png")
        ]

        # Iterate over the images and generate a thumbnail preview for each.
        for i, name in enumerate(image_paths):
            filepath = os.path.join(directory, name)

            # Check if a preview icon for this image already exists in the collection.
            icon = pcoll.get(name)
            if not icon:
                # If no icon exists, load the image and generate a new thumbnail.
                thumb = pcoll.load(name, filepath, "IMAGE")
            else:
                # If an icon exists, use the existing thumbnail.
                thumb = pcoll[name]

            label = os.path.splitext(name)[0]  # remove extension to the name
            enum_items.append((name, label, "", thumb.icon_id, i))

    pcoll.vehicle_presets = enum_items
    pcoll.vehicle_presets_dir = directory

    return pcoll.vehicle_presets


def rename_rig_objects(scene, collection_name):
    files = [
        OBJECT_HIGHBEAM_L,
        OBJECT_HIGHBEAM_R ,
        OBJECT_LOWBEAM_L,
        OBJECT_LOWBEAM_R,
        FILENAME_DRIVINGPATH,
        FILENAME_CAR_RIG,
        FILENAME_LATTICE_FR,
        FILENAME_LATTICE_FL,
        FILENAME_LATTICE_RR,
        FILENAME_LATTICE_RL,
        FILENAME_SHRINKWRAP,
        FILENAME_SHRINKWRAPTOP,
        FILENAME_WHEELANIMPROPS,
        FILENAME_SKIDMARK_ENGINE_FL,
        FILENAME_SKIDMARK_ENGINE_FR,
        FILENAME_SKIDMARK_ENGINE_RL,
        FILENAME_SKIDMARK_ENGINE_RR,
        FILENAME_SKIDMARK_MEASURE_FL,
        FILENAME_SKIDMARK_MEASURE_FR,
        FILENAME_SKIDMARK_MEASURE_RL,
        FILENAME_SKIDMARK_MEASURE_RR,
        FILENAME_GROUND_LOCAL,
        FILENAME_COLLIDER_DEFAULT,
        FILENAME_SIM_BODY,
        FILENAME_SIM_WHEELS,
        FILENAME_SIM_ACC_VIZ,
        FILENAME_SIM_VEL_VIZ,
        FILENAME_SIM_TRACK_TO,
        FILENAME_TRACK_WHEEL_FL,
        FILENAME_TRACK_WHEEL_FR,
        FILENAME_TRACK_WHEEL_RL,
        FILENAME_TRACK_WHEEL_RR,
        FILENAME_DUMMY,
        FILENAME_DUMMY_GROUND,
        FILENAME_CUSTOM_PROPS,
        FILENAME_SPEEDOMETER,
        FILENAME_UNIT,
        FILENAME_UNIT_FLIPPED,
        FILENAME_SPEED_CALCULATOR,
    ]

    lights = [
        (FILENAME_L_HIGHBEAM_L),
        (FILENAME_L_HIGHBEAM_R),
        (FILENAME_L_LOWBEAM_L),
        (FILENAME_L_LOWBEAM_R),
    ]

    collections = [
        COLLECTIONNAME_CARRIG,
        COLLECTIONNAME_LIGHTS,
        COLLECTIONNAME_INTERNAL,
        COLLECTIONNAME_SKIDMARK,
    ]

    armatures = [
        FILENAME_CARRIG_ARMATURE
    ]

    materials = [
        M_SKIDMARK_MATERIAL
    ]

    node_groups = [
        PHYSICS_BODY,
        PHYSICS_WHEELS,
        GEONODE_SKIDMARK,
    ]

    for f in files:
        try:
            scene.objects[f].name += ("_" + collection_name)
        except:
            log_error(f"Cant find object {f}", "rename_rig_objects")

    for c in collections:
        try:
            current = get_collection_by_name(c, scene.collection)
            current.name += ("_" + collection_name).capitalize()
        except:
            log_error(f"Cant find collection {c}", "rename_rig_objects")

    for l in lights:
        try:
            bpy.data.lights[l].name += ("_" + collection_name)
        except:
            log_error(f"Cant find light {l}", "rename_rig_objects")

    for a in armatures:
        try:
            bpy.data.armatures[a].name += ("_" + collection_name)
        except:
            log_error(f"Cant find armature {a}", "rename_rig_objects")

    for m in materials:
        try:
            bpy.data.materials[m].name += ("_" + collection_name)
        except:
            log_error(f"Cant find material {m}", "rename_rig_objects")

    for n in node_groups:
        try:
            bpy.data.node_groups[n].name += ("_" + collection_name)
        except:
            log_error(f"Cant find node_group {n}", "rename_rig_objects")


def get_headlights(new_image):
    return (new_image + ".exr", new_image + "_Blur01.exr", new_image + "_Blur02.exr")
    
    
def add_headlights_images():
    images = ["Circular", "Exotic", "LED", "Matrix", "Prism", "Vintage"]

    addons_path = get_addon_path()
    directory = os.path.join(addons_path, "assets", "headlights")

    for img in images:
        bpy.data.images[img].filepath = os.path.join(directory, img, ".exr")
        bpy.data.images[img + "_Blur01"].filepath = os.path.join(directory, img, "_Blur01.exr")
        bpy.data.images[img + "_Blur02"].filepath = os.path.join(directory, img, "_Blur02.exr")


def prepare_cache(default_path, active_car):
    blend_name = get_blend_name_clean()

    new_path = default_path.replace("file", blend_name)
    new_path = new_path.replace("lc_car", active_car.collection.name)

    return new_path


def prepare_cache_physics(active_car):

    # Try to get physics bake target from LC rig
    physics_bake_target = None
    has_physics_bake_target = hasattr(bpy.context.scene.settings, "physics_bake_target")
    if has_physics_bake_target:
        physics_bake_target = bpy.context.scene.settings.physics_bake_target


    # Fallback for Blender 4.0 because of altered naming
    if bpy.app.version < (4, 1, 0):
        cache_path = prepare_cache(SIM_BODY_DEFAULTPATH, active_car)
        active_car.sim_body.modifiers["GeometryNodes"].simulation_bake_directory = cache_path
        cache_path = prepare_cache(SIM_WHEELS_DEFAULTPATH, active_car)
        active_car.sim_wheels.modifiers["GeometryNodes"].simulation_bake_directory = cache_path

    elif bpy.app.version >= (4, 3, 0) and physics_bake_target is not None:
        active_car.sim_body.modifiers["GeometryNodes"].bake_target = physics_bake_target
        active_car.sim_wheels.modifiers["GeometryNodes"].bake_target = physics_bake_target

        if physics_bake_target == "PACKED":
            active_car.sim_body.modifiers["GeometryNodes"].bake_directory = ""
            active_car.sim_wheels.modifiers["GeometryNodes"].bake_directory = ""

    else:
        cache_path = prepare_cache(SIM_BODY_DEFAULTPATH, active_car)
        active_car.sim_body.modifiers["GeometryNodes"].bake_directory = cache_path
        cache_path = prepare_cache(SIM_WHEELS_DEFAULTPATH, active_car)
        active_car.sim_wheels.modifiers["GeometryNodes"].bake_directory = cache_path

    

def prepare_cache_skidmarks(skidmarks, active_car):

    # Fallback for Blender 4.0 because of altered naming
    if bpy.app.version < (4, 1, 0):
        cache_path = prepare_cache(SKIDMARK_ENGINE_FL_DEFAULTPATH, active_car)
        skidmarks[0].modifiers["GeometryNodes"].simulation_bake_directory = cache_path
        cache_path = prepare_cache(SKIDMARK_ENGINE_FR_DEFAULTPATH, active_car)
        skidmarks[1].modifiers["GeometryNodes"].simulation_bake_directory = cache_path
        cache_path = prepare_cache(SKIDMARK_ENGINE_RL_DEFAULTPATH, active_car)
        skidmarks[2].modifiers["GeometryNodes"].simulation_bake_directory = cache_path
        cache_path = prepare_cache(SKIDMARK_ENGINE_RR_DEFAULTPATH, active_car)
        skidmarks[3].modifiers["GeometryNodes"].simulation_bake_directory = cache_path

    elif bpy.app.version >= (4, 3, 0):
        skidmarks[0].modifiers["GeometryNodes"].bake_target = 'PACKED'
        skidmarks[1].modifiers["GeometryNodes"].bake_target = 'PACKED'
        skidmarks[2].modifiers["GeometryNodes"].bake_target = 'PACKED'
        skidmarks[3].modifiers["GeometryNodes"].bake_target = 'PACKED'
        skidmarks[0].modifiers["GeometryNodes"].bake_directory = ""
        skidmarks[1].modifiers["GeometryNodes"].bake_directory = ""
        skidmarks[2].modifiers["GeometryNodes"].bake_directory = ""
        skidmarks[3].modifiers["GeometryNodes"].bake_directory = ""
    
    else:
        cache_path = prepare_cache(SKIDMARK_ENGINE_FL_DEFAULTPATH, active_car)
        skidmarks[0].modifiers["GeometryNodes"].bake_directory = cache_path
        cache_path = prepare_cache(SKIDMARK_ENGINE_FR_DEFAULTPATH, active_car)
        skidmarks[1].modifiers["GeometryNodes"].bake_directory = cache_path
        cache_path = prepare_cache(SKIDMARK_ENGINE_RL_DEFAULTPATH, active_car)
        skidmarks[2].modifiers["GeometryNodes"].bake_directory = cache_path
        cache_path = prepare_cache(SKIDMARK_ENGINE_RR_DEFAULTPATH, active_car)
        skidmarks[3].modifiers["GeometryNodes"].bake_directory = cache_path


def validate_cache(active_car, filename):
    blend_dir = bpy.path.abspath("//")
    blend_name = get_blend_name_clean()

    return os.path.exists(os.path.join(blend_dir, "blendcache_Launch_Control", blend_name, active_car.collection.name, filename))


def get_blend_name_clean():
    blend_name_dirty = bpy.path.basename(bpy.context.blend_data.filepath)
    blend_name = os.path.splitext(blend_name_dirty)[0]

    return blend_name


def unzip_in_location(zip_path, target_path):
    """unzip given zip file"""

    """with closing(zipfile.ZipFile(sys.argv[1])) as archive:
        count = len(archive.infolist())"""

    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(target_path)

    return None
