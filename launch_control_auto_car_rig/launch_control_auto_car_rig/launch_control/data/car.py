import bpy

from .properties import UIProperties, UISettings
from ..utils.maths import set_wheels_lattice
from ..utils.functions import get_collection_by_name
from ..utils.errors.exceptions import RigCollectionNotFound

from ..operators.low_level import (
    set_parent_keep_transform,
    clear_parent_keep_transform,
    set_parent_bone_keep_transform,
)

from ..globals import (
    B_WHEEL_DEFORM,
    B_BODY_DEFORM,
    B_WHEEL_CALIPER_DEFORM,
    OBJECT_LOWBEAM_L,
    OBJECT_LOWBEAM_R,
    OBJECT_HIGHBEAM_L,
    OBJECT_HIGHBEAM_R,
)


class Position(bpy.types.PropertyGroup):
    location: bpy.props.FloatVectorProperty(
        name="Initial Location",
        subtype="XYZ",  # This specifies the vector subtype
        size=3,  # Number of components in the vector
        default=(0.0, 0.0, 0.0),  # Default initial location
    )

    rotation: bpy.props.FloatVectorProperty(
        name="Initial Location",
        subtype="XYZ",  # This specifies the vector subtype
        size=3,  # Number of components in the vector
        default=(0.0, 0.0, 0.0),  # Default initial rotation
    )

    scale: bpy.props.FloatVectorProperty(
        name="Initial Location",
        subtype="XYZ",  # This specifies the vector subtype
        size=3,  # Number of components in the vector
        default=(0.0, 0.0, 0.0),  # Default initial rotation
    )


# CAR PARTS --------------------------------------------------------------------------------
class Body(bpy.types.PropertyGroup):
    body: bpy.props.PointerProperty(type=bpy.types.Object)

    position: bpy.props.PointerProperty(type=Position)

    def clear_parents(self):
        clear_parent_keep_transform(self.body)

    def attach_bone(self, car_rig):
        hub = car_rig.data.bones[B_BODY_DEFORM]
        set_parent_bone_keep_transform(self.body, hub, car_rig)


class Wheels(bpy.types.PropertyGroup):
    list_order = ["RL", "RR", "FR", "FL"]

    wheel_RL: bpy.props.PointerProperty(type=bpy.types.Object)
    wheel_RR: bpy.props.PointerProperty(type=bpy.types.Object)
    wheel_FR: bpy.props.PointerProperty(type=bpy.types.Object)
    wheel_FL: bpy.props.PointerProperty(type=bpy.types.Object)

    # positions
    position_wheel_RL: bpy.props.PointerProperty(type=Position)
    position_wheel_RR: bpy.props.PointerProperty(type=Position)
    position_wheel_FR: bpy.props.PointerProperty(type=Position)
    position_wheel_FL: bpy.props.PointerProperty(type=Position)

    def clear_parents(self):
        for wheel in self.to_list():
            clear_parent_keep_transform(wheel)

    def get_order(self):
        return ["RL", "RR", "FR", "FL"]

    def to_list(self):
        """Returns list of the wheels in the next order RL, gRR, FR, FL"""
        return [self.wheel_RL, self.wheel_RR, self.wheel_FR, self.wheel_FL]

    def attach_bone(self, car_rig):
        wheels_hubs = [
            car_rig.data.bones[f"{B_WHEEL_DEFORM}.{o}"] for o in self.list_order
        ]
        for wheel, hub in zip(self.to_list(), wheels_hubs):
            clear_parent_keep_transform(wheel)
            set_parent_bone_keep_transform(wheel, hub, car_rig)

    def set_lattice(self, scene, rig_scale):
        set_wheels_lattice(
            scene,
            self.wheel_RR,
            self.wheel_FR,
            self.to_list(),
            self.list_order,
            rig_scale,
        )


class Brakes(bpy.types.PropertyGroup):
    order = ["RL", "RR", "FR", "FL"]

    brake_RL: bpy.props.PointerProperty(type=bpy.types.Object)
    brake_RR: bpy.props.PointerProperty(type=bpy.types.Object)
    brake_FR: bpy.props.PointerProperty(type=bpy.types.Object)
    brake_FL: bpy.props.PointerProperty(type=bpy.types.Object)

    # positions
    position_brake_RL: bpy.props.PointerProperty(type=Position)
    position_brake_RR: bpy.props.PointerProperty(type=Position)
    position_brake_FR: bpy.props.PointerProperty(type=Position)
    position_brake_FL: bpy.props.PointerProperty(type=Position)

    def to_list(self):
        """Returns list of the brakes in the next order RL, RR, FR, FL."""
        return [self.brake_RL, self.brake_RR, self.brake_FR, self.brake_FL]

    def clear_parents(self):
        for brake in self.to_list():
            clear_parent_keep_transform(brake)

    def link_to_wheels(self, wheels: Wheels):
        for brake, wheel in zip(self.to_list(), wheels.to_list()):
            set_parent_keep_transform(brake, wheel)

    def attach_bone(self, car_rig):
        brake_hubs = [
            car_rig.data.bones[f"{B_WHEEL_CALIPER_DEFORM}.{o}"] for o in self.order
        ]
        for brake, hub in zip(self.to_list(), brake_hubs):
            set_parent_bone_keep_transform(brake, hub, car_rig)

    def ignore(self):
        if self.brake_RL and self.brake_RR and self.brake_FL and self.brake_FR:
            return False
        return True


class WheelCovers(bpy.types.PropertyGroup):
    order = ["FR", "FL"]

    wheelcover_FR: bpy.props.PointerProperty(type=bpy.types.Object)
    wheelcover_FL: bpy.props.PointerProperty(type=bpy.types.Object)

    # positions
    position_wheelcover_FR: bpy.props.PointerProperty(type=Position)
    position_wheelcover_FL: bpy.props.PointerProperty(type=Position)

    def to_list(self):
        """Returns list of the wheelcovers in the next order FR, FL."""
        return [self.wheelcover_FR, self.wheelcover_FL]

    def clear_parents(self):
        for wheelcover in self.to_list():
            clear_parent_keep_transform(wheelcover)

    def link_to_wheels(self, wheels: Wheels):
        for wheelcover, wheel in zip(self.to_list(), wheels.to_list()):
            set_parent_keep_transform(wheelcover, wheel)

    def attach_bone(self, car_rig):
        wheelcover_hubs = [
            car_rig.data.bones[f"{B_WHEEL_CALIPER_DEFORM}.{o}"] for o in self.order
        ]
        for wheelcover, hub in zip(self.to_list(), wheelcover_hubs):
            set_parent_bone_keep_transform(wheelcover, hub, car_rig)


class Headlights(bpy.types.PropertyGroup):
    order = ["R", "L"]
    headlight_R: bpy.props.PointerProperty(type=bpy.types.Object)
    headlight_L: bpy.props.PointerProperty(type=bpy.types.Object)

    def to_list(self):
        """Returns list of the headlights in the next order R, L."""
        return [self.headlight_R, self.headlight_L]

    def attach_bone(self, scene, car_rig):
        headlights = [
            scene.objects[OBJECT_LOWBEAM_L],
            scene.objects[OBJECT_LOWBEAM_R],
            scene.objects[OBJECT_HIGHBEAM_L],
            scene.objects[OBJECT_HIGHBEAM_R],
        ]
        hub_body = car_rig.data.bones[B_BODY_DEFORM]
        for headlight in headlights:
            set_parent_bone_keep_transform(headlight, hub_body, car_rig)


# CAR --------------------------------------------------------------------------------------
class Car(bpy.types.PropertyGroup):
    # main properties
    collection: bpy.props.PointerProperty(type=bpy.types.Collection)
    scene: bpy.props.PointerProperty(type=bpy.types.Scene)

    # body parts
    body: bpy.props.PointerProperty(type=Body)
    wheels: bpy.props.PointerProperty(type=Wheels)
    brakes: bpy.props.PointerProperty(type=Brakes)
    wheelcovers: bpy.props.PointerProperty(type=WheelCovers)
    headlights: bpy.props.PointerProperty(type=Headlights)

    # proxy parts
    body_proxy: bpy.props.PointerProperty(type=Body)
    wheels_proxy: bpy.props.PointerProperty(type=Wheels)
    brakes_proxy: bpy.props.PointerProperty(type=Brakes)

    # rig
    is_rigged: bpy.props.BoolProperty(default=True)
    rig_object: bpy.props.PointerProperty(type=bpy.types.Object)
    rig_armature: bpy.props.PointerProperty(type=bpy.types.Armature)
    rig_collection: bpy.props.PointerProperty(type=bpy.types.Collection)
    lc_collection: bpy.props.PointerProperty(type=bpy.types.Collection)

    # path
    driving_path: bpy.props.PointerProperty(type=bpy.types.Object)
    path_changed: bpy.props.BoolProperty(default=False)

    # skidmarks
    skidmark_collection: bpy.props.PointerProperty(type=bpy.types.Collection)
    skidmark_material: bpy.props.PointerProperty(type=bpy.types.Material)

    # ground detection
    ground_local_object: bpy.props.PointerProperty(type=bpy.types.Object)

    # physics
    sim_body: bpy.props.PointerProperty(type=bpy.types.Object)
    sim_wheels: bpy.props.PointerProperty(type=bpy.types.Object)
    sim_track_to: bpy.props.PointerProperty(type=bpy.types.Object)
    sim_acc_viz: bpy.props.PointerProperty(type=bpy.types.Object)
    sim_vel_viz: bpy.props.PointerProperty(type=bpy.types.Object)

    # speedometer
    speed_calculator: bpy.props.PointerProperty(type=bpy.types.Object)

    # properties
    properties: bpy.props.PointerProperty(type=UIProperties)

    # settings
    settings: bpy.props.PointerProperty(type=UISettings)

    def get_rig_collection(self):
        collection = get_collection_by_name(self.rig_collection.name, self.scene.collection)
        if collection:
            return collection
        else:
            raise RigCollectionNotFound(self.collection.name)


# LC CARS -----------------------------------------------------------------------------------
class LaunchControlCars(bpy.types.PropertyGroup):
    cars: bpy.props.CollectionProperty(type=Car)

    def find_selected(self):
        scene = bpy.context.scene
        collection = scene.car_collection
        for car in self.cars:
            if car.collection == collection:
                return car

        return None

    def add(self, collection, name):
        scene = bpy.context.scene
        item = self.cars.add()

        item.name = name 

        item.scene = scene
        item.collection = collection

        return item

    def remove(self, car: Car):
        for index, obj in enumerate(self.cars):
            if obj == car:
                self.cars.remove(index)

    def get_index(self, car: Car):
        for index, obj in enumerate(self.cars):
            if obj == car:
                return index
