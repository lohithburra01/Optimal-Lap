import bpy
import bpy.utils.previews
from bpy.app.handlers import persistent

import os

from .properties import GlobalSettings, UISettings, UIProperties
from .f1_properties import F1_Lap_Item, F1_Pipeline_Props
from .car import LaunchControlCars, Car, Body, Wheels, Brakes, WheelCovers, Headlights, Position
from ..utils.functions import get_all_children_collections
from ..utils.resources import enum_previews_from_directory_items_anims, enum_previews_from_directory_items_cars
from ..globals import COLLECTIONNAME_ADDON



### Filters ###
def p_filter(scene, object):

    if scene.settings.show_rigged_coll_only:
        rigged_collections = []
        for car in scene.lc.cars:
            rigged_collections.append(car.collection)

        print("rigged_collections: ", rigged_collections)

        if object in rigged_collections:
            return object
    
    else:
        lc_collection = scene.collection.children.get(COLLECTIONNAME_ADDON)
        lc_descendents = get_all_children_collections(lc_collection) if lc_collection else []
        scene_collections_descendents = get_all_children_collections(scene.collection)

        if object in scene_collections_descendents:
            return object not in [lc_collection] + lc_descendents
    

# It needs to be in correct order so it does not reaise error => dependencies first
classes = (GlobalSettings, UISettings, UIProperties, F1_Lap_Item, F1_Pipeline_Props, Position, Body, Wheels, Brakes, WheelCovers, Headlights, Car, LaunchControlCars)

# Images enum
preview_animation_collections = {}
def get_animation_presets(self, context):
    return enum_previews_from_directory_items_anims(self, context, preview_animation_collections)

preview_vehicle_collections = {}
def get_vehicle_presets(self, context):
    return enum_previews_from_directory_items_cars(self, context, preview_vehicle_collections)



def register():               

    # IMAGES
    bpy.types.WindowManager.animation_presets_dir = bpy.props.StringProperty(
        name="Folder Path",
        subtype='DIR_PATH',
        default=""
    )

    bpy.types.WindowManager.animation_presets = bpy.props.EnumProperty(
        items=(get_animation_presets),
    )

    pcoll_anim = bpy.utils.previews.new()
    pcoll_anim.animation_presets_dir = ""
    pcoll_anim.animation_presets = ()
    preview_animation_collections["main"] = pcoll_anim


    bpy.types.WindowManager.vehicle_presets_dir = bpy.props.StringProperty(
        name="Folder Path",
        subtype='DIR_PATH',
        default=""
    )

    bpy.types.WindowManager.vehicle_presets = bpy.props.EnumProperty(
        items=get_vehicle_presets,
    )

    pcoll_car = bpy.utils.previews.new()
    pcoll_car.vehicle_presets_dir = ""
    pcoll_car.vehicle_presets = ()
    preview_vehicle_collections["main"] = pcoll_car


    # CLASSES
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # PROPERTIES (scene)
    bpy.types.Scene.car_collection = bpy.props.PointerProperty(type=bpy.types.Collection, name="", description="The Collection which holds the vehicle parts (body and wheels, optionally brakes and headlights) of the vehicle which is to be rigged or adjusted", poll=p_filter)
    bpy.types.Scene.car_collection_previous = bpy.props.PointerProperty(type=bpy.types.Collection, name="internal", description="internal")
    bpy.types.Scene.lc = bpy.props.PointerProperty(type=LaunchControlCars)
    bpy.types.Scene.settings = bpy.props.PointerProperty(type=GlobalSettings)
    bpy.types.Scene.f1_pipeline_props = bpy.props.PointerProperty(type=F1_Pipeline_Props)
    bpy.types.Scene.f1_lap_queue = bpy.props.CollectionProperty(type=F1_Lap_Item)
    bpy.types.Scene.body_assembly = bpy.props.PointerProperty(type=bpy.types.Object, name="", description="The overall null/empty holding the entire vehicle.")
    bpy.types.Scene.anim_rot_fr_assembly = bpy.props.PointerProperty(type=bpy.types.Object, name="", description="The null/empty holding the front, right wheel - Rims, tires and other parts that needs to be steering and spinning.")
    bpy.types.Scene.anim_rot_fl_assembly = bpy.props.PointerProperty(type=bpy.types.Object, name="", description="The null/empty holding the front, left wheel - Rims, tires and other parts that needs to be steering and spinning.")
    bpy.types.Scene.anim_rot_rr_assembly = bpy.props.PointerProperty(type=bpy.types.Object, name="", description="The null/empty holding the rear, right wheel - Rims, tires and other parts that needs to be spinning.")
    bpy.types.Scene.anim_rot_rl_assembly = bpy.props.PointerProperty(type=bpy.types.Object, name="", description="The null/empty holding the rear, left wheel - Rims, tires and other parts that needs to be spinning.")
    bpy.types.Scene.no_rot_fr_assembly = bpy.props.PointerProperty(type=bpy.types.Object, name="", description="The null/empty holding the front, right non-rotating parts - Brake Calipers and similar.")
    bpy.types.Scene.no_rot_fl_assembly = bpy.props.PointerProperty(type=bpy.types.Object, name="", description="The null/empty holding the front, left non-rotating parts - Brake Calipers and similar.")
    bpy.types.Scene.no_rot_rr_assembly = bpy.props.PointerProperty(type=bpy.types.Object, name="", description="The null/empty holding the rear, right non-rotating parts - Brake Calipers and similar.")
    bpy.types.Scene.no_rot_rl_assembly = bpy.props.PointerProperty(type=bpy.types.Object, name="", description="The null/empty holding the rear, left non-rotating parts - Brake Calipers and similar.")    


def unregister():
    # IMAGES
    for pcoll in preview_animation_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_animation_collections.clear()

    for pcoll in preview_vehicle_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_vehicle_collections.clear()

    # CLASSES
    for cls in classes:
        bpy.utils.unregister_class(cls)

    # PROPERTIES
    properties = (
        bpy.types.WindowManager.animation_presets_dir,
        bpy.types.WindowManager.animation_presets,
        bpy.types.WindowManager.vehicle_presets_dir,
        bpy.types.WindowManager.vehicle_presets,
        bpy.types.Scene.lc,
        bpy.types.Scene.car_collection,
        bpy.types.Scene.settings,
    )

    for prop in properties:
        del prop
    
    del bpy.types.Scene.f1_pipeline_props
    del bpy.types.Scene.f1_lap_queue