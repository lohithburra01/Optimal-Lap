import bpy
import os
import json
import requests
from bpy.types import Operator, PropertyGroup
from bpy.props import StringProperty, EnumProperty, IntProperty, CollectionProperty, BoolProperty, PointerProperty

# Import F1 Baker
from . import F1_HiFi_Baker_Pro

# Import Launch Control Utilities
from ..utils.resources import get_resource_path
from ..logger import log_info, log_error
from ..ui.utils import show_message_box
from ..operators.append import OBJECT_OT_append_from_file

@bpy.app.handlers.persistent
def _f1_load_post_handler(dummy):
    """Reload databases after a blend file is opened so enums populate."""
    try:
        from ..data.f1_properties import load_databases
        load_databases()
    except Exception as e:
        print(f"[F1 Studio] load_post reload failed: {e}")

# ==============================================================================
# DATABASE MANAGER
# ==============================================================================
class F1_Database_Manager:
    """Resolves asset file paths from the local folder structure."""

    def __init__(self, context=None):
        blend_path = bpy.data.filepath
        if not blend_path:
            self.root = "c:/Users/91910/Downloads/F1_Builder_Context/F1_Pipeline_Assets"
        else:
            self.root = os.path.join(os.path.dirname(blend_path), "F1_Pipeline_Assets")

    def get_car_path(self, year, team, code):
        return os.path.join(self.root, "cars", str(year), team, f"{code}.blend")

    def get_car_path_with_round(self, year, team, code, round_num):
        override = os.path.join(self.root, "cars", str(year), team, f"{code}_Round{round_num}.blend")
        if os.path.exists(override):
            return override
        return self.get_car_path(year, team, code)

    def get_track_path(self, event_name):
        filename = event_name.lower().replace(" ", "_") + ".blend"
        return os.path.join(self.root, "tracks", filename)

    def get_temp_dir(self):
        temp = os.path.join(self.root, "temp_data")
        os.makedirs(temp, exist_ok=True)
        return temp

# ==============================================================================
# PIPELINE OPERATOR
# ==============================================================================
class OBJECT_OT_f1_generate_scene(Operator):
    bl_idname = "f1.generate_scene"
    bl_label = "Generate Scene"
    bl_description = "Generates the F1 Scene based on the Lap Queue"

    def execute(self, context):
        scene = context.scene
        queue = scene.f1_lap_queue

        if len(queue) == 0:
            self.report({'ERROR'}, "Queue is empty!")
            return {'CANCELLED'}

        db = F1_Database_Manager()

        # Resolve track path from first queue item
        first_item = scene.f1_lap_queue[0]
        track_path = db.get_track_path(first_item.event)

        # LOAD TRACK
        if os.path.exists(track_path):
            self.load_track(track_path)
        else:
            self.report({'WARNING'}, f"Track file not found: {track_path}")

        # GENERATE TELEMETRY
        batches = {}
        for item in queue:
            key = (item.year, item.event, item.session)
            if key not in batches:
                batches[key] = []
            batches[key].append(item.driver)

        temp_data_dir = db.get_temp_dir()
        generated_files = {}

        for (year, event, session), drivers in batches.items():
            settings = {
                'resolution': 0.5, 'width': 6.0, 'lookahead': 70,
                'output_dir': temp_data_dir
            }
            if F1_HiFi_Baker_Pro.MISSING_DEPS:
                self.report({'ERROR'}, "Missing Dependencies. Please install FastF1 via preferences.")
                return {'CANCELLED'}

            msg, map, lap_time = F1_HiFi_Baker_Pro.generate_multirail_data(year, event, session, drivers, settings)
            print(f"Baker: {msg}")

            for d in drivers:
                generated_files[d] = os.path.join(temp_data_dir, f"{d}_hifi_path.json")

        # STEP 1 - APPEND ALL CARS FIRST (no LC registration yet)
        for item in scene.f1_lap_queue:
            car_path = db.get_car_path(item.year, item.team, item.driver)
            if os.path.exists(car_path):
                self.append_car_lc(car_path)
            else:
                self.report({'WARNING'}, f"Car file not found: {car_path}")

        # STEP 2 - ALL CARS APPENDED, NOW REGISTER WITH LC AND APPLY JSON
        lc_colls = []
        for coll in scene.collection.children_recursive:
            if 'CarRig_lc' in coll.name:
                lc_colls.append(coll)
        lc_colls.sort(key=lambda c: c.name)

        print(f"[F1 Studio] Found {len(lc_colls)} LC collections for {len(scene.f1_lap_queue)} queue items")

        for i, item in enumerate(scene.f1_lap_queue):
            if i >= len(lc_colls):
                self.report({'WARNING'}, f"No LC collection found for {item.driver}")
                continue

            coll = lc_colls[i]
            print(f"[F1 Studio] Registering {item.driver} -> {coll.name}")

            rig_obj = None
            driving_path = None
            sim_body = None
            sim_wheels = None
            sim_track_to = None

            for obj in coll.all_objects:
                if obj.type == 'ARMATURE':
                    rig_obj = obj
                if obj.type == 'CURVE':
                    driving_path = obj
                if obj.name.startswith('sim_Body'):
                    sim_body = obj
                if obj.name.startswith('sim_Wheels_LC'):
                    sim_wheels = obj
                if obj.name.startswith('sim_TrackTo'):
                    sim_track_to = obj

            print(f"  rig={rig_obj.name if rig_obj else 'MISSING'} curve={driving_path.name if driving_path else 'MISSING'}")

            # Register with LC if not already
            car = None
            for c in scene.lc.cars:
                if c.collection and c.collection.name == coll.name:
                    car = c
                    break
            if car is None:
                car = scene.lc.add(coll, coll.name)

            car.rig_object = rig_obj
            car.driving_path = driving_path
            car.rig_collection = coll
            car.lc_collection = coll
            car.sim_body = sim_body
            car.sim_wheels = sim_wheels
            car.sim_track_to = sim_track_to

            # Set as active LC car
            scene.car_collection = coll

            # Apply telemetry JSON
            json_path = os.path.join(temp_data_dir, f"{item.driver}_hifi_path.json")
            if os.path.isfile(json_path):
                result = bpy.ops.object.apply_lap_from_json(
                    filepath=json_path,
                    curve_name=f"LC_LapPath_{item.driver}",
                )
                print(f"[F1 Studio] {item.driver} apply_lap result: {result}")
            else:
                self.report({'WARNING'}, f"JSON not found for {item.driver}: {json_path}")

        self.report({'INFO'}, "Scene Generated Successfully")
        return {'FINISHED'}

    def load_track(self, filepath):
        with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
            track_colls = [c for c in data_from.collections
                           if 'track' in c.lower() or 'circuit' in c.lower()]
            if not track_colls:
                return
            data_to.collections = [track_colls[0]]

        for coll in bpy.data.collections:
            if 'track' in coll.name.lower() or 'circuit' in coll.name.lower():
                if coll.name not in bpy.context.scene.collection.children:
                    bpy.context.scene.collection.children.link(coll)

    def append_car_lc(self, car_path):
        with bpy.data.libraries.load(car_path, link=False) as (data_from, data_to):
            car_colls = [c for c in data_from.collections if 'CarRig' in c]
            if not car_colls:
                return None
            data_to.collections = list(data_from.collections)

        for coll in bpy.data.collections:
            if coll.name not in bpy.context.scene.collection.children:
                # Only link top-level CarRig collections to scene root
                # sub-collections are already children of CarRig
                is_child = False
                for parent in bpy.data.collections:
                    if coll.name in [c.name for c in parent.children]:
                        is_child = True
                        break
                if not is_child:
                    try:
                        bpy.context.scene.collection.children.link(coll)
                    except:
                        pass

    def apply_path(self, lc_car, json_path):
        pass


# ==============================================================================
# QUEUE MANAGEMENT
# ==============================================================================
class OBJECT_OT_f1_add_lap_to_queue(Operator):
    bl_idname = "f1.add_lap"
    bl_label = "Add Lap to Queue"

    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props

        if len(scene.f1_lap_queue) >= 4:
            self.report({'WARNING'}, "Queue is full (Max 4)")
            return {'CANCELLED'}

        from ..data.f1_properties import _DRV_BY_RACE, _get_event

        # Resolve team from driver list
        session   = props.sel_session
        q_segment = props.sel_q_segment if session == 'Q' else ''
        year_str  = props.sel_year

        event_data = _DRV_BY_RACE.get(year_str, {}).get(props.sel_race)
        race_drivers = []
        if isinstance(event_data, list):
            race_drivers = event_data
        elif isinstance(event_data, dict):
            if session == 'Q':
                q_data = event_data.get('Q', {})
                seg_key = q_segment if q_segment and q_segment != 'Q_ALL' else '_all'
                race_drivers = q_data.get(seg_key, event_data.get('_all', []))
            elif session in ('Day 1', 'Day 2', 'Day 3'):
                race_drivers = event_data.get(session, [])
            else:
                race_drivers = event_data.get(session, event_data.get('_all', []))

        driver_entry = next((d for d in race_drivers if d['code'] == props.sel_driver), None)

        # Get track_key from calendar
        event = _get_event(year_str, props.sel_race)
        track_key = event.get('track_key', props.sel_race.lower().replace(' ', '_')) if event else props.sel_race.lower().replace(' ', '_')

        # Add to queue
        item = scene.f1_lap_queue.add()
        item.year        = int(props.sel_year)
        item.event       = props.sel_race
        item.session     = session
        item.q_segment   = q_segment if session == 'Q' else ''
        item.driver      = props.sel_driver
        item.team        = driver_entry['team_raw'] if driver_entry else "Unknown Team"
        item.track_id    = track_key
        item.fastest_lap = props.fastest_lap

        # Lock track after first lap
        if len(scene.f1_lap_queue) == 1:
            props.locked_track     = props.sel_race
            props.locked_track_key = track_key
            props.status_msg       = f"Ref: {item.driver} @ {item.event}"

        return {'FINISHED'}


class OBJECT_OT_f1_remove_lap(Operator):
    bl_idname = "f1.remove_lap"
    bl_label = "Remove Lap"
    index: IntProperty()

    def execute(self, context):
        scene = context.scene
        scene.f1_lap_queue.remove(self.index)
        return {'FINISHED'}


class OBJECT_OT_f1_clear_queue(Operator):
    bl_idname = "f1.clear_queue"
    bl_label = "Clear Queue"

    def execute(self, context):
        scene = context.scene
        scene.f1_lap_queue.clear()
        props = scene.f1_pipeline_props
        props.locked_track     = ""
        props.locked_track_key = ""
        props.status_msg       = "Ready"
        return {'FINISHED'}


def register():
    bpy.app.handlers.load_post.append(_f1_load_post_handler)


def unregister():
    if _f1_load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_f1_load_post_handler)