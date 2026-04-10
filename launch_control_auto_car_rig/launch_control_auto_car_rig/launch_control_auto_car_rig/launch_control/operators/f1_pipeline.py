import bpy
import os
import json
import math
import numpy as np
import requests
from mathutils import Vector
from bpy.types import Operator, PropertyGroup
from bpy.props import StringProperty, EnumProperty, IntProperty, CollectionProperty, BoolProperty, PointerProperty

# Import F1 Baker
from . import F1_HiFi_Baker_Pro

# Import Launch Control Utilities
from ..utils.resources import get_resource_path
from ..logger import log_info, log_error
from ..ui.utils import show_message_box
from ..operators.append import OBJECT_OT_append_from_file
from ..operators.f1_trail import setup_trail_for_driver, sync_all_trails_from_paths

CONSTRUCTOR_COLORS = {
    "Red Bull Racing": "#3671C6",
    "McLaren":         "#FF8000",
    "Ferrari":         "#E8002D",
    "Mercedes":        "#27F4D2",
    "Aston Martin":    "#229971",
    "Alpine":          "#FF87BC",
    "Williams":        "#64C4FF",
    "Haas":            "#B6BABD",
    "Kick Sauber":     "#52E252",
    "Racing Bulls":    "#6692FF",
}


def get_lc_curve_for_rig(rig_obj):
    """Find the driving path curve LC assigned to this rig."""
    if not rig_obj:
        return None
    rig_name = rig_obj.name
    suffix = rig_name.replace("car_rig_", "")
    target_curve_name = f"driving_path_{suffix}"

    curve = bpy.data.objects.get(target_curve_name)
    if curve and curve.type == 'CURVE':
        return curve

    base_suffix = suffix.split(".")[0]
    target_base = f"driving_path_{base_suffix}"
    for obj in bpy.data.objects:
        if obj.type == 'CURVE' and obj.name.startswith(target_base):
            return obj

    return None


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

    def get_exports_dir(self):
        exports = os.path.join(self.root, "exports")
        os.makedirs(exports, exist_ok=True)
        return exports

# ==============================================================================
# PIPELINE OPERATOR
# ==============================================================================
# ---------------------------------------------------------------------------
# Module-level state for the deferred per-car pipeline.
# bpy.app.timers callbacks don't carry instance state, so we store it here.
# ---------------------------------------------------------------------------
_pipeline_queue = []        # list of dicts (one per car to process)
_pipeline_index = 0
_pipeline_temp_dir = ""
_pipeline_first_event = ""
_pipeline_original_edit_all = False


def _deferred_process_next_car():
    """bpy.app.timers callback — processes the next car in the queue.

    Returning None means 'don't reschedule'. Returning a float reschedules
    after that many seconds.  We process ONE car per call so Blender gets a
    full event-loop cycle between cars (exactly like clicking Generate twice).
    """
    global _pipeline_queue, _pipeline_index

    scene = bpy.context.scene
    if _pipeline_index >= len(_pipeline_queue):
        # All done — run the finishing steps
        _pipeline_finish()
        return None                      # stop the timer

    item = _pipeline_queue[_pipeline_index]
    i = _pipeline_index
    total = len(_pipeline_queue)
    _pipeline_index += 1

    print(f"\n[F1 Studio] ═══ Processing car {i+1}/{total}: {item['driver']} ═══")

    try:
        _generate_single_car(item)
    except Exception as e:
        print(f"[F1 Studio] ❌ Error processing {item['driver']}: {e}")
        import traceback
        traceback.print_exc()

    # Return 0.5 to schedule the *next* car after 0.5 s, giving Blender a
    # full event-loop cycle to flush depsgraph, exactly like the manual flow.
    if _pipeline_index < len(_pipeline_queue):
        return 0.5
    else:
        _pipeline_finish()
        return None


def _generate_single_car(item):
    """Append one car, register it with LC, apply its telemetry JSON."""
    global _pipeline_temp_dir

    scene = bpy.context.scene
    db = F1_Database_Manager()

    # Force single-car mode so prepare_animation only touches THIS car
    scene.settings.edit_all_mode = False

    # --- 1. APPEND ---
    car_path = db.get_car_path(item['year'], item['team'], item['driver'])
    if not os.path.exists(car_path):
        print(f"[F1 Studio] ⚠️ Car file not found: {car_path}")
        return

    existing_colls = set(c.name for c in bpy.data.collections)

    with bpy.data.libraries.load(car_path, link=False) as (data_from, data_to):
        car_colls = [c for c in data_from.collections if 'CarRig' in c]
        if not car_colls:
            print(f"[F1 Studio] ⚠️ No CarRig collection in {car_path}")
            return
        data_to.collections = list(data_from.collections)

    carrig_coll = None
    for coll in bpy.data.collections:
        if coll.name in existing_colls:
            continue
        if coll.name.startswith('CarRig'):
            carrig_coll = coll
        is_child = False
        for parent in bpy.data.collections:
            if parent is coll:
                continue
            if coll.name in [c.name for c in parent.children]:
                is_child = True
                break
        if not is_child:
            try:
                scene.collection.children.link(coll)
            except RuntimeError:
                pass

    if not carrig_coll:
        print(f"[F1 Studio] ⚠️ No CarRig collection found after append for {item['driver']}")
        return
    print(f"[F1 Studio] Appended {item['driver']} -> {carrig_coll.name}")

    bpy.context.view_layer.update()

    # --- 2. FIND LAUNCHCONTROL PARENT ---
    # Use the appended collection (carrig_coll) — critical when same driver is loaded twice
    # (e.g. HAM from Day 1 + HAM from Day 2). Searching by driver name would match the first
    # car and apply path/trail to the wrong instance.
    car_coll = carrig_coll

    lc_parents = []
    for coll in scene.collection.children:
        if 'LaunchControl' in coll.name:
            lc_parents.append(coll)
    for coll in scene.collection.children_recursive:
        if 'LaunchControl' in coll.name and coll not in lc_parents:
            lc_parents.append(coll)

    search_coll = None
    for lc in lc_parents:
        for child in lc.children_recursive:
            if child == carrig_coll:
                search_coll = lc
                break
        if search_coll:
            break

    if search_coll is None and lc_parents:
        search_coll = lc_parents[-1]

    if search_coll is None:
        print(f"[F1 Studio] ⚠️ No LaunchControl found for {item['driver']}")
        return

    # --- 3. REGISTER WITH LC ---
    rig_obj = None
    driving_path = None
    sim_body = None
    sim_wheels = None
    sim_track_to = None

    for obj in search_coll.all_objects:
        n = obj.name
        if obj.type == 'ARMATURE' and rig_obj is None:
            rig_obj = obj
        if obj.type == 'CURVE' and driving_path is None:
            driving_path = obj
        if n.startswith('sim_Body') and sim_body is None:
            sim_body = obj
        if n.startswith('sim_Wheels') and 'initial' not in n.lower() and sim_wheels is None:
            sim_wheels = obj
        if n.startswith('sim_TrackTo') and sim_track_to is None:
            sim_track_to = obj

    print(f"[F1 Studio] Registering {item['driver']} -> {car_coll.name}")
    print(f"  rig={rig_obj.name if rig_obj else 'MISSING'}  "
          f"curve={driving_path.name if driving_path else 'MISSING'}")

    car = None
    for c in scene.lc.cars:
        if c.collection and c.collection.name == car_coll.name:
            car = c
            break
    if car is None:
        car = scene.lc.add(car_coll, car_coll.name)

    car.rig_object = rig_obj
    car.driving_path = driving_path
    car.rig_collection = car_coll
    car.lc_collection = search_coll
    car.sim_body = sim_body
    car.sim_wheels = sim_wheels
    car.sim_track_to = sim_track_to

    scene.car_collection = car_coll          # make LC's find_selected() return THIS car

    # --- 4. APPLY TELEMETRY JSON ---
    slot_id = item.get("slot_id", 0)
    json_path = os.path.join(_pipeline_temp_dir, f"{item['driver']}_{slot_id}_hifi_path.json")
    if not os.path.isfile(json_path):
        json_path = os.path.join(_pipeline_temp_dir, f"{item['driver']}_hifi_path.json")
    if os.path.isfile(json_path):
        result = bpy.ops.object.apply_lap_from_json(filepath=json_path)
        print(f"[F1 Studio] {item['driver']} apply_lap result: {result}")
        # Setup trail — get the curve LC actually assigned to this rig
        if rig_obj:
            lc_curve = get_lc_curve_for_rig(rig_obj) or driving_path
            if lc_curve:
                color = CONSTRUCTOR_COLORS.get(item.get("team", ""), "#FFFFFF")
                setup_trail_for_driver(item['driver'], color, rig_obj, lc_curve)
            else:
                print(f"[F1Trail] Could not find LC curve for {item['driver']}")
    else:
        print(f"[F1 Studio] ⚠️ JSON not found: {json_path}")

    bpy.context.view_layer.update()
    print(f"[F1 Studio] ═══ {item['driver']} COMPLETE ═══\n")


def _pipeline_finish():
    """Final housekeeping after all cars are processed."""
    global _pipeline_original_edit_all, _pipeline_first_event

    scene = bpy.context.scene
    scene.settings.edit_all_mode = _pipeline_original_edit_all

    # Link track meshes into each car's GroundDetection
    # (track is already in scene — just need to reference it)
    track_surface = bpy.data.objects.get("Track")
    if track_surface:
        ground_objects = [track_surface]
        cosmetic_coll = bpy.data.collections.get("track_cosmetic")
        if cosmetic_coll:
            for obj in cosmetic_coll.all_objects:
                if obj.type == 'MESH' and obj not in ground_objects:
                    ground_objects.append(obj)

        for coll in scene.collection.children_recursive:
            if coll.name.startswith('GroundDetection'):
                existing = {o.name for o in coll.objects}
                for obj in ground_objects:
                    if obj.name not in existing:
                        try:
                            coll.objects.link(obj)
                        except RuntimeError:
                            pass

    print(f"[F1 Studio] ═══ ALL {len(_pipeline_queue)} CARS COMPLETE ═══")


class OBJECT_OT_f1_generate_scene(Operator):
    bl_idname = "f1.generate_scene"
    bl_label = "Generate Scene"
    bl_description = "Generates the F1 Scene based on the Lap Queue"

    def execute(self, context):
        global _pipeline_queue, _pipeline_index, _pipeline_temp_dir
        global _pipeline_first_event, _pipeline_original_edit_all

        scene = context.scene
        queue = scene.f1_lap_queue

        if len(queue) == 0:
            self.report({'ERROR'}, "Queue is empty!")
            return {'CANCELLED'}

        db = F1_Database_Manager()

        # ── 1. LOAD TRACK (only if not already present) ──
        first_item = queue[0]
        _pipeline_first_event = first_item.event

        track_already_loaded = bpy.data.objects.get("Track") is not None
        if not track_already_loaded:
            track_path = db.get_track_path(first_item.event)
            if os.path.exists(track_path):
                self.load_track(track_path)
            else:
                self.report({'WARNING'}, f"Track file not found: {track_path}")

        # ── 2. GENERATE TELEMETRY for ALL drivers upfront ──
        batches = {}
        for idx, item in enumerate(queue):
            if item.is_testing:
                key = (item.year, item.event, item.session,
                       True, item.test_number, item.test_session)
            else:
                key = (item.year, item.event, item.session,
                       False, 0, 0)
            if key not in batches:
                batches[key] = []
            batches[key].append((item.driver, idx))

        _pipeline_temp_dir = db.get_temp_dir()
        _pipeline_exports_dir = db.get_exports_dir()

        props = scene.f1_pipeline_props
        for (year, event, session, is_testing, test_num, test_sess), driver_slots in batches.items():
            drivers = [x[0] for x in driver_slots]
            slot_ids = [x[1] for x in driver_slots]
            settings = {
                'resolution': 0.5,
                'output_dir': _pipeline_temp_dir,
                'exports_dir': _pipeline_exports_dir,
                'render_minimap': props.render_minimap,
                'slot_ids': slot_ids,
            }
            if is_testing:
                settings['is_testing']    = True
                settings['test_number']   = test_num
                settings['test_session']  = test_sess
                session_for_baker = str(test_sess)  # Day 1/2/3
            else:
                session_for_baker = _session_key_to_baker(session)

            if F1_HiFi_Baker_Pro.MISSING_DEPS:
                self.report({'ERROR'}, "Missing Dependencies. Please install FastF1 via preferences.")
                return {'CANCELLED'}

            msg, _map, _lt = F1_HiFi_Baker_Pro.generate_multirail_data(
                year, event, session_for_baker, drivers, settings)
            print(f"Baker: {msg}")
            if _lt is None or msg.startswith("Error") or msg.startswith("FastF1"):
                self.report({'ERROR'}, msg[:200] if len(msg) > 200 else msg)
                scene.f1_pipeline_props.status_msg = "FastF1: no data"
                return {'CANCELLED'}

        # ── 3. SNAPSHOT the queue and clear it ──
        _pipeline_queue = []
        for idx, item in enumerate(queue):
            _pipeline_queue.append({
                'year': item.year, 'event': item.event,
                'session': item.session, 'driver': item.driver,
                'team': item.team, 'track_id': item.track_id,
                'is_testing': item.is_testing,
                'test_number': item.test_number,
                'test_session': item.test_session,
                'slot_id': idx,
            })

        _pipeline_original_edit_all = scene.settings.edit_all_mode
        scene.settings.edit_all_mode = False

        # ── 4. PROCESS CAR 1 immediately (inside this execute) ──
        _pipeline_index = 0
        first_car = _pipeline_queue[0]
        _pipeline_index = 1
        print(f"\n[F1 Studio] ═══ Processing car 1/{len(_pipeline_queue)}: {first_car['driver']} ═══")
        _generate_single_car(first_car)

        # ── 5. SCHEDULE remaining cars via bpy.app.timers ──
        if len(_pipeline_queue) > 1:
            print(f"[F1 Studio] Scheduling {len(_pipeline_queue)-1} more car(s) via timer...")
            bpy.app.timers.register(_deferred_process_next_car, first_interval=1.0)
        else:
            _pipeline_finish()

        # Apply saved alignment
        track_id = _pipeline_first_event.lower().replace(" ", "_")
        self._apply_saved_alignment(context, track_id)

        self.report({'INFO'}, "Scene generation started" if len(_pipeline_queue) > 1
                     else "Scene Generated Successfully")
        return {'FINISHED'}

    def _apply_saved_alignment(self, context, track_id):
        """Load saved alignment from tracks.json and apply to UI sliders."""
        db = F1_Database_Manager()
        tracks_json = os.path.join(db.root, "database", "tracks.json")
        if not os.path.isfile(tracks_json):
            return

        try:
            with open(tracks_json, 'r', encoding='utf-8') as f:
                tracks_data = json.load(f)
        except Exception:
            return

        track_entry = tracks_data.get(track_id, {})
        alignment = track_entry.get("alignment", None)
        if not alignment:
            return

        props = context.scene.f1_pipeline_props
        props.align_offset_x = alignment.get("offset_x", 0.0)
        props.align_offset_y = alignment.get("offset_y", 0.0)
        props.align_rotation = alignment.get("rotation", 0.0)
        props.align_scale    = alignment.get("scale", 1.0)
        print(f"[F1 Studio] Loaded saved alignment for '{track_id}'")

    def load_track(self, filepath):
        """Append the entire track .blend file (all collections & loose objects).
        Returns a list of newly loaded MESH objects (for ground detection linking).
        """
        print(f"[F1 Studio] Loading track from: {filepath}")
        existing_colls = set(c.name for c in bpy.data.collections)
        existing_objs = set(o.name for o in bpy.data.objects)

        with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
            print(f"[F1 Studio]   Collections in file: {list(data_from.collections)}")
            print(f"[F1 Studio]   Objects in file: {len(list(data_from.objects))} objects")
            data_to.collections = list(data_from.collections)
            data_to.objects = list(data_from.objects)

        # Link top-level collections to the scene
        # (sub-collections are already parented inside their loaded parents)
        for coll in bpy.data.collections:
            if coll.name in existing_colls:
                continue
            is_child = False
            for parent in bpy.data.collections:
                if parent is coll:
                    continue
                if coll.name in [c.name for c in parent.children]:
                    is_child = True
                    break
            if not is_child:
                try:
                    bpy.context.scene.collection.children.link(coll)
                except RuntimeError:
                    pass

        # Collect all newly loaded MESH objects (these are the track assets)
        new_mesh_objects = []
        for obj in bpy.data.objects:
            if obj.name in existing_objs:
                continue
            if obj.type == 'MESH':
                new_mesh_objects.append(obj)
            # Link any loose objects that aren't in any collection
            if not obj.users_collection:
                try:
                    bpy.context.scene.collection.objects.link(obj)
                except RuntimeError:
                    pass

        print(f"[F1 Studio] Loaded {len(new_mesh_objects)} track mesh objects: "
              f"{[o.name for o in new_mesh_objects[:10]]}{'...' if len(new_mesh_objects) > 10 else ''}")

        # Auto-assign the "Track" mesh to the diagnostic track_surface_obj
        track_mesh = bpy.data.objects.get("Track")
        if track_mesh and track_mesh.type == 'MESH':
            props = bpy.context.scene.f1_pipeline_props
            props.track_surface_obj = track_mesh
            print(f"[F1 Studio] Auto-assigned track surface: '{track_mesh.name}'")

        return new_mesh_objects

    def _link_track_to_ground_detection(self, scene, track_mesh_objects):
        """Link the track surface mesh into each car's GroundDetection collection.
        Only the actual driving surface is needed — linking all track meshes
        (barriers, grandstands, trees, etc.) tanks performance.
        """
        # Collect the ground-relevant track surface objects
        ground_objects = []

        # 1. Primary track surface — auto-assigned by load_track()
        props = scene.f1_pipeline_props
        track_surface = props.track_surface_obj
        if track_surface is None:
            track_surface = bpy.data.objects.get("Track")
        if track_surface is not None:
            ground_objects.append(track_surface)

        # 2. track_cosmetic — a COLLECTION of runoff areas, kerbs, etc.
        #    Link all mesh objects from this collection into GroundDetection.
        cosmetic_coll = bpy.data.collections.get("track_cosmetic")
        if cosmetic_coll is not None:
            for obj in cosmetic_coll.all_objects:
                if obj.type == 'MESH' and obj not in ground_objects:
                    ground_objects.append(obj)

        if not ground_objects:
            print("[F1 Studio] ⚠️ No track surface meshes found — "
                  "ground detection will not work. "
                  "Name your track surface 'Track' and/or use a 'track_cosmetic' collection.")
            return

        # Find all GroundDetection collections in the scene
        gd_collections = []
        for coll in scene.collection.children_recursive:
            if coll.name.startswith('GroundDetection'):
                gd_collections.append(coll)

        if not gd_collections:
            print("[F1 Studio] ⚠️ No GroundDetection collections found — "
                  "track surfaces not linked for ground detection")
            return

        obj_names = [o.name for o in ground_objects]
        print(f"[F1 Studio] 🔗 Linking {obj_names} into "
              f"{len(gd_collections)} GroundDetection collection(s)")

        for gd_coll in gd_collections:
            existing = {o.name for o in gd_coll.objects}
            for obj in ground_objects:
                if obj.name not in existing:
                    try:
                        gd_coll.objects.link(obj)
                        print(f"  ✅ {gd_coll.name}: linked '{obj.name}'")
                    except RuntimeError:
                        print(f"  ⚠️ {gd_coll.name}: could not link '{obj.name}'")

    def append_car_lc(self, car_path):
        """Append car from .blend and return the top-level CarRig collection."""
        existing_colls = set(c.name for c in bpy.data.collections)

        with bpy.data.libraries.load(car_path, link=False) as (data_from, data_to):
            car_colls = [c for c in data_from.collections if 'CarRig' in c]
            if not car_colls:
                print(f"[F1 Studio] No CarRig collection in {car_path}")
                print(f"  Available collections: {list(data_from.collections)}")
                return None
            data_to.collections = list(data_from.collections)

        # Find newly added collections and link top-level ones to scene
        carrig_coll = None
        for coll in bpy.data.collections:
            if coll.name in existing_colls:
                continue
            # Track the CarRig collection
            if coll.name.startswith('CarRig'):
                carrig_coll = coll
            # Link only top-level (not children of another new collection)
            is_child = False
            for parent in bpy.data.collections:
                if parent is coll:
                    continue
                if coll.name in [c.name for c in parent.children]:
                    is_child = True
                    break
            if not is_child:
                try:
                    bpy.context.scene.collection.children.link(coll)
                except RuntimeError:
                    pass

        return carrig_coll

    def apply_path(self, lc_car, json_path):
        pass


# ==============================================================================
# TRACK ALIGNMENT OPERATORS
# ==============================================================================
class OBJECT_OT_f1_save_alignment(Operator):
    bl_idname = "f1.save_alignment"
    bl_label = "Save Track Alignment"
    bl_description = "Save current alignment values to tracks.json for this track"

    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props
        queue = scene.f1_lap_queue

        if len(queue) == 0:
            self.report({'WARNING'}, "No laps in queue – cannot determine track")
            return {'CANCELLED'}

        track_id = queue[0].event.lower().replace(" ", "_")
        db = F1_Database_Manager()
        tracks_json = os.path.join(db.root, "database", "tracks.json")

        if not os.path.isfile(tracks_json):
            self.report({'ERROR'}, f"tracks.json not found: {tracks_json}")
            return {'CANCELLED'}

        try:
            with open(tracks_json, 'r', encoding='utf-8') as f:
                tracks_data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read tracks.json: {e}")
            return {'CANCELLED'}

        if track_id not in tracks_data:
            tracks_data[track_id] = {"track_name": queue[0].event, "versions": []}

        tracks_data[track_id]["alignment"] = {
            "offset_x": round(props.align_offset_x, 4),
            "offset_y": round(props.align_offset_y, 4),
            "rotation": round(props.align_rotation, 6),
            "scale":    round(props.align_scale, 6),
        }

        try:
            with open(tracks_json, 'w', encoding='utf-8') as f:
                json.dump(tracks_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to write tracks.json: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Alignment saved for '{track_id}'")
        return {'FINISHED'}


class OBJECT_OT_f1_load_alignment(Operator):
    bl_idname = "f1.load_alignment"
    bl_label = "Load Track Alignment"
    bl_description = "Load saved alignment values from tracks.json for this track"

    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props
        queue = scene.f1_lap_queue

        if len(queue) == 0:
            self.report({'WARNING'}, "No laps in queue – cannot determine track")
            return {'CANCELLED'}

        track_id = queue[0].event.lower().replace(" ", "_")
        db = F1_Database_Manager()
        tracks_json = os.path.join(db.root, "database", "tracks.json")

        if not os.path.isfile(tracks_json):
            self.report({'ERROR'}, f"tracks.json not found: {tracks_json}")
            return {'CANCELLED'}

        try:
            with open(tracks_json, 'r', encoding='utf-8') as f:
                tracks_data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read tracks.json: {e}")
            return {'CANCELLED'}

        track_entry = tracks_data.get(track_id, {})
        alignment = track_entry.get("alignment", None)

        if not alignment:
            self.report({'WARNING'}, f"No saved alignment for '{track_id}'")
            return {'CANCELLED'}

        props.align_offset_x = alignment.get("offset_x", 0.0)
        props.align_offset_y = alignment.get("offset_y", 0.0)
        props.align_rotation = alignment.get("rotation", 0.0)
        props.align_scale    = alignment.get("scale", 1.0)

        self.report({'INFO'}, f"Alignment loaded for '{track_id}'")
        return {'FINISHED'}


class OBJECT_OT_f1_reset_alignment(Operator):
    bl_idname = "f1.reset_alignment"
    bl_label = "Reset Alignment"
    bl_description = "Reset all alignment values to defaults"

    def execute(self, context):
        props = context.scene.f1_pipeline_props
        props.align_offset_x = 0.0
        props.align_offset_y = 0.0
        props.align_rotation = 0.0
        props.align_scale    = 1.0
        self.report({'INFO'}, "Alignment reset")
        return {'FINISHED'}


# ==============================================================================
# PATH DIAGNOSTIC & CORRECTION
# ==============================================================================

def _get_path_points(path_obj):
    """Return list of point accessors for the first spline (Bezier or Poly)."""
    spline = path_obj.data.splines[0]
    if spline.type == 'BEZIER':
        return spline.bezier_points, 'BEZIER'
    return spline.points, 'POLY'


def _get_point_co(point, point_type):
    """Get (x, y, z) Vector from a spline point."""
    if point_type == 'BEZIER':
        return point.co.copy()
    return point.co.to_3d()


def _set_point_co(point, point_type, co):
    """Set position on a spline point."""
    if point_type == 'BEZIER':
        delta = co - point.co
        point.co = co
        point.handle_left += delta
        point.handle_right += delta
    else:
        point.co = (co.x, co.y, co.z, point.co.w)


def _ray_test_on_track(world_xy, track_obj):
    """
    Check if a world-space XY position is above the track surface.
    Returns (is_on_track, nearest_world_point).
    """
    inv = track_obj.matrix_world.inverted()

    # Ray from high above, casting downward
    ray_origin = Vector((world_xy.x, world_xy.y, 10000.0))
    ray_dir = Vector((0.0, 0.0, -1.0))

    local_origin = inv @ ray_origin
    local_dir = (inv.to_3x3() @ ray_dir).normalized()

    hit, loc, _normal, _idx = track_obj.ray_cast(local_origin, local_dir)
    if hit:
        return True, track_obj.matrix_world @ loc

    # Off-track — find nearest point on mesh surface
    local_pos = inv @ Vector((world_xy.x, world_xy.y, 0.0))
    _result, nearest_local, _normal, _idx = track_obj.closest_point_on_mesh(local_pos)
    return False, track_obj.matrix_world @ nearest_local


def _gaussian_smooth_vectors(vectors, radius, closed=True):
    """Gaussian-blur a list of Vector corrections. Handles wrap-around for closed paths."""
    n = len(vectors)
    if radius <= 0 or n == 0:
        return list(vectors)

    sigma = max(radius / 3.0, 1.0)
    kernel = [math.exp(-(j ** 2) / (2.0 * sigma ** 2))
              for j in range(-radius, radius + 1)]
    k_sum = sum(kernel)
    kernel = [k / k_sum for k in kernel]

    result = []
    for i in range(n):
        smoothed = Vector((0.0, 0.0, 0.0))
        for j, w in enumerate(kernel):
            if closed:
                idx = (i + j - radius) % n
            else:
                idx = max(0, min(n - 1, i + j - radius))
            smoothed += vectors[idx] * w
        result.append(smoothed)
    return result


class OBJECT_OT_f1_diagnose_path(Operator):
    bl_idname = "f1.diagnose_path"
    bl_label = "Diagnose Path"
    bl_description = "Ray-cast each path vertex against the track surface and show on/off-track overlay"

    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props
        track_obj = props.track_surface_obj

        if not track_obj or track_obj.type != 'MESH':
            self.report({'ERROR'}, "Select a valid Track Surface mesh object")
            return {'CANCELLED'}

        # Gather all F1 driving-path curves
        paths = []
        for car in scene.lc.cars:
            dp = car.driving_path
            if dp and dp.type == 'CURVE' and dp.data.splines:
                paths.append(dp)
        if not paths:
            self.report({'WARNING'}, "No F1 path curves found in scene")
            return {'CANCELLED'}

        # Remove old diagnostic overlay
        old = bpy.data.objects.get("F1_Path_Diagnostic")
        if old:
            bpy.data.objects.remove(old, do_unlink=True)

        all_verts = []
        all_colors = []
        total_pts = 0
        off_count = 0

        for path_obj in paths:
            points, ptype = _get_path_points(path_obj)
            for pt in points:
                co_local = _get_point_co(pt, ptype)
                co_world = path_obj.matrix_world @ co_local
                on_track, _nearest = _ray_test_on_track(co_world, track_obj)
                all_verts.append(co_world)
                if on_track:
                    all_colors.append((0.0, 1.0, 0.0, 1.0))  # green
                else:
                    all_colors.append((1.0, 0.0, 0.0, 1.0))  # red
                    off_count += 1
                total_pts += 1

        # Build diagnostic mesh (vertex point cloud with vertex colors)
        mesh = bpy.data.meshes.new("F1_Path_Diagnostic")
        mesh.from_pydata([v[:] for v in all_verts], [], [])
        mesh.update()

        color_attr = mesh.color_attributes.new("diagnostic", 'FLOAT_COLOR', 'POINT')
        for i, c in enumerate(all_colors):
            color_attr.data[i].color = c

        diag_obj = bpy.data.objects.new("F1_Path_Diagnostic", mesh)
        scene.collection.objects.link(diag_obj)
        diag_obj.show_in_front = True

        pct = (off_count / total_pts * 100) if total_pts else 0
        self.report({'INFO'},
                    f"Diagnostic: {off_count}/{total_pts} vertices OFF-TRACK ({pct:.1f}%)")
        return {'FINISHED'}


def _correct_single_pass(path_obj, track_obj, falloff, strength, inset=0.0):
    """Run one correction pass on a single path. Returns number of off-track vertices found.

    *inset*: extra distance (meters) to push corrected vertices past the
    track edge toward the track center, preventing cars from riding the edge.
    """
    points, ptype = _get_path_points(path_obj)
    closed = path_obj.data.splines[0].use_cyclic_u
    off_count = 0

    raw_corrections = []
    for pt in points:
        co_local = _get_point_co(pt, ptype)
        co_world = path_obj.matrix_world @ co_local
        on_track, nearest_world = _ray_test_on_track(co_world, track_obj)
        if on_track:
            raw_corrections.append(Vector((0.0, 0.0, 0.0)))
        else:
            correction = nearest_world - co_world
            correction.z = 0.0

            # Extend correction past the edge by inset amount.
            # The correction vector already points from the off-track
            # position toward the track, so its direction is always
            # "inward" regardless of which side the point is on.
            if abs(inset) > 1e-4 and correction.length > 1e-4:
                correction += correction.normalized() * inset

            raw_corrections.append(correction * strength)
            off_count += 1

    if off_count == 0:
        return 0

    smoothed = _gaussian_smooth_vectors(raw_corrections, falloff, closed=closed)

    inv_rot = path_obj.matrix_world.inverted().to_3x3()
    for i, pt in enumerate(points):
        if smoothed[i].length < 1e-6:
            continue
        local_corr = inv_rot @ smoothed[i]
        co = _get_point_co(pt, ptype)
        _set_point_co(pt, ptype, co + local_corr)

    path_obj.data.update_tag()
    return off_count


# ==============================================================================
# APEX CORRECTION
# ==============================================================================

def _detect_corners(path_obj, curvature_threshold=0.005):
    """Detect corner and straight segments of a path using curvature.

    Returns list of {'type': 'CORNER'|'STRAIGHT', 'start': int, 'end': int,
                      'direction': 'LEFT'|'RIGHT'|None}.
    """
    import numpy as np
    from scipy.ndimage import binary_dilation, binary_erosion

    points, ptype = _get_path_points(path_obj)
    n = len(points)
    if n < 3:
        return [{'type': 'STRAIGHT', 'start': 0, 'end': n - 1, 'direction': None}]

    mw = path_obj.matrix_world
    coords = [mw @ _get_point_co(pt, ptype) for pt in points]

    # Tangent via central difference
    tangents = []
    for i in range(n):
        prev_co = coords[(i - 1) % n]
        next_co = coords[(i + 1) % n]
        t = (next_co - prev_co)
        if t.length > 1e-6:
            t.normalize()
        tangents.append(t)

    # Curvature = angle between consecutive tangents
    curvature = []
    for i in range(n):
        t0 = tangents[i]
        t1 = tangents[(i + 1) % n]
        dot = max(-1.0, min(1.0, t0.dot(t1)))
        curvature.append(math.acos(dot))

    # Gaussian smooth curvature (sigma=5)
    curv_arr = np.array(curvature)
    sigma = 5.0
    kernel_r = 15
    kernel = np.array([math.exp(-j**2 / (2 * sigma**2)) for j in range(-kernel_r, kernel_r + 1)])
    kernel /= kernel.sum()
    curv_padded = np.pad(curv_arr, kernel_r, mode='wrap')
    curv_smooth = np.convolve(curv_padded, kernel, mode='valid')

    is_corner = curv_smooth > curvature_threshold

    # Morphological close: fill small gaps
    is_corner = binary_dilation(is_corner, iterations=10)
    is_corner = binary_erosion(is_corner, iterations=10)

    # Build contiguous runs
    MIN_CORNER   = 20
    MIN_STRAIGHT = 10
    raw_segs = []
    cur_type  = 'CORNER' if is_corner[0] else 'STRAIGHT'
    seg_start = 0
    for i in range(1, n):
        t = 'CORNER' if is_corner[i] else 'STRAIGHT'
        if t != cur_type:
            raw_segs.append({'type': cur_type, 'start': seg_start, 'end': i - 1, 'direction': None})
            cur_type  = t
            seg_start = i
    raw_segs.append({'type': cur_type, 'start': seg_start, 'end': n - 1, 'direction': None})

    # Merge short segments
    changed = True
    while changed:
        changed = False
        merged = []
        i = 0
        while i < len(raw_segs):
            seg    = raw_segs[i]
            length = seg['end'] - seg['start'] + 1
            too_short = ((seg['type'] == 'CORNER'   and length < MIN_CORNER) or
                         (seg['type'] == 'STRAIGHT' and length < MIN_STRAIGHT))
            if too_short:
                changed = True
                if merged:
                    merged[-1]['end'] = seg['end']
                elif i + 1 < len(raw_segs):
                    raw_segs[i + 1]['start'] = seg['start']
                    i += 1
                    continue
                else:
                    merged.append(seg)
            else:
                merged.append(seg)
            i += 1
        raw_segs = merged

    # Determine turn direction for each CORNER segment
    for seg in raw_segs:
        if seg['type'] != 'CORNER':
            continue
        cross_sum = 0.0
        for i in range(seg['start'], seg['end']):
            t0 = tangents[i]
            t1 = tangents[(i + 1) % n]
            cross_sum += t0.x * t1.y - t0.y * t1.x  # Z component of cross product
        seg['direction'] = 'LEFT' if cross_sum > 0 else 'RIGHT'

    return raw_segs


def _find_inside_edge_distance(point_co, inside_direction, track_obj, max_search=5.0, step=0.1):
    """Step along inside_direction until we fall off the track edge.

    Returns (edge_distance, edge_point) or (max_search, None) if not found.
    """
    last_hit_pos = None
    last_hit_dist = 0.0

    dist = 0.0
    while dist <= max_search:
        probe = Vector((point_co.x + inside_direction.x * dist,
                        point_co.y + inside_direction.y * dist,
                        point_co.z))
        on_track, world_pt = _ray_test_on_track(probe, track_obj)
        if on_track:
            last_hit_pos  = world_pt
            last_hit_dist = dist
            dist += step
        else:
            # First miss — the previous hit was the edge
            if last_hit_pos is None:
                # Already off track at step 0
                return (0.0, point_co.copy())
            return (last_hit_dist, last_hit_pos)

    return (max_search, None)


def _apply_apex_correction(path_obj, track_obj, corners, strength=0.7, inset=0.15, falloff=15):
    """Push corner path points toward the track apex.

    For each CORNER segment: finds the inside edge, computes a raised-cosine
    weighted correction vector toward a target `inset` distance from the edge,
    gaussian-smooths the full correction array, then applies it in-place.
    """
    points, ptype = _get_path_points(path_obj)
    n = len(points)
    if n < 3:
        return

    mw     = path_obj.matrix_world
    inv_mw = mw.inverted()
    closed = path_obj.data.splines[0].use_cyclic_u

    # World-space coords and tangents
    coords = [mw @ _get_point_co(pt, ptype) for pt in points]
    tangents = []
    for i in range(n):
        prev_co = coords[(i - 1) % n]
        next_co = coords[(i + 1) % n]
        t = (next_co - prev_co)
        if t.length > 1e-6:
            t.normalize()
        tangents.append(t)

    # Per-point curvature (for apex detection)
    curvature = []
    for i in range(n):
        t0 = tangents[i]
        t1 = tangents[(i + 1) % n]
        dot = max(-1.0, min(1.0, t0.dot(t1)))
        curvature.append(math.acos(dot))

    raw_corrections = [Vector((0.0, 0.0, 0.0))] * n

    for seg in corners:
        if seg['type'] != 'CORNER':
            continue

        s   = seg['start']
        e   = seg['end']
        direction = seg.get('direction', 'LEFT')

        # Apex = index of maximum curvature in this segment
        apex_idx = s + max(range(e - s + 1), key=lambda k: curvature[s + k])
        half_len  = max((e - s) / 2.0, 1.0)

        for i in range(s, e + 1):
            co      = coords[i]
            tangent = tangents[i]

            # Inside = left-perpendicular for LEFT turns, right for RIGHT turns
            if direction == 'LEFT':
                inside_dir = Vector((-tangent.y,  tangent.x, 0.0))
            else:
                inside_dir = Vector(( tangent.y, -tangent.x, 0.0))

            if inside_dir.length > 1e-6:
                inside_dir.normalize()

            # Find inside track edge
            edge_dist, edge_pt = _find_inside_edge_distance(
                co, inside_dir, track_obj, max_search=5.0, step=0.1)

            if edge_pt is None:
                # Could not find edge within max_search — skip
                continue

            # Target = inset distance back from the edge toward track center
            apex_target = edge_pt + (-inside_dir * inset)

            # Raised-cosine weight: 1.0 at apex, 0.0 at segment entry/exit
            dist_from_apex = abs(i - apex_idx)
            if dist_from_apex < half_len:
                weight = 0.5 * (1.0 + math.cos(math.pi * dist_from_apex / half_len))
            else:
                weight = 0.0

            corr_vec = (apex_target - co) * (weight * strength)
            corr_vec.z = 0.0
            raw_corrections[i] = corr_vec

    # Gaussian smooth to prevent discontinuities at segment boundaries
    smoothed = _gaussian_smooth_vectors(raw_corrections, falloff, closed=closed)

    # Apply corrections
    inv_rot = mw.inverted().to_3x3()
    for i, pt in enumerate(points):
        if smoothed[i].length < 1e-6:
            continue
        local_corr = inv_rot @ smoothed[i]
        co = _get_point_co(pt, ptype)
        _set_point_co(pt, ptype, co + local_corr)

    path_obj.data.update_tag()


def _apex_correct_all_paths(scene, strength, inset, falloff):
    """Run apex correction on every registered driving path in the scene.

    Returns the number of paths corrected.
    """
    props = scene.f1_pipeline_props
    track_obj = props.track_surface_obj
    if track_obj is None:
        return 0

    corrected = 0
    for car in scene.lc.cars:
        path_obj = car.driving_path
        if path_obj is None:
            continue
        corners = _detect_corners(path_obj)
        corner_segments = [s for s in corners if s['type'] == 'CORNER']
        if corner_segments:
            _apply_apex_correction(path_obj, track_obj, corner_segments,
                                   strength=strength, inset=inset, falloff=falloff)
            corrected += 1

    sync_all_trails_from_paths(scene)
    return corrected


class OBJECT_OT_f1_apex_correct(Operator):
    bl_idname  = "f1.apex_correct"
    bl_label   = "Apex Correction"
    bl_description = "Push corner paths toward track apexes using curvature detection and inside-edge raycasting"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props
        if props.track_surface_obj is None:
            self.report({'ERROR'}, "Set Track Surface object first")
            return {'CANCELLED'}

        count = _apex_correct_all_paths(
            scene,
            strength=props.correction_strength,
            inset=props.correction_inset,
            falloff=props.correction_falloff,
        )
        self.report({'INFO'}, f"Apex correction applied to {count} path(s)")
        return {'FINISHED'}



# ==============================================================================
# CENTERLINE CORRECTION
# ==============================================================================

def _find_edge_distance(point_xy, direction, track_obj, max_search=15.0, step=0.1):
    """
    Step along `direction` from `point_xy`, raycasting down at each step.
    Returns (edge_distance, edge_xy) — distance to last hit, and its XY position.
    If never misses within max_search, returns (max_search, last_test_xy).
    If first step misses, returns (0.0, point_xy).
    """
    inv = track_obj.matrix_world.inverted()
    ray_dir_local = (inv.to_3x3() @ Vector((0, 0, -1))).normalized()

    last_hit_dist = 0.0
    last_hit_xy = Vector((point_xy.x, point_xy.y))

    d = step
    while d <= max_search:
        test_xy = point_xy + direction * d
        origin_world = Vector((test_xy.x, test_xy.y, 10000.0))
        origin_local = inv @ origin_world
        hit, loc, _, _ = track_obj.ray_cast(origin_local, ray_dir_local)
        if not hit:
            return last_hit_dist, last_hit_xy
        last_hit_dist = d
        last_hit_xy = Vector((test_xy.x, test_xy.y))
        d += step

    return max_search, last_hit_xy


def _extract_path_geometry(path_obj):
    """
    Extract world-space positions and tangents from a driving path.
    Returns: coords (n,2 numpy array), tangents (n,2 numpy array), closed (bool)
    """
    points, ptype = _get_path_points(path_obj)
    n = len(points)
    closed = path_obj.data.splines[0].use_cyclic_u
    
    coords = np.zeros((n, 2))
    for i, pt in enumerate(points):
        co_local = _get_point_co(pt, ptype)
        co_world = path_obj.matrix_world @ co_local
        coords[i] = (co_world.x, co_world.y)
    
    # Tangents via central difference
    tangents = np.zeros((n, 2))
    for i in range(n):
        if closed:
            prev_i = (i - 1) % n
            next_i = (i + 1) % n
        else:
            prev_i = max(0, i - 1)
            next_i = min(n - 1, i + 1)
        diff = coords[next_i] - coords[prev_i]
        norm = np.linalg.norm(diff)
        tangents[i] = diff / norm if norm > 1e-8 else np.array([1.0, 0.0])
    
    return coords, tangents, closed


def _compute_curvature(coords, tangents, closed, smooth_sigma=10):
    """
    Compute signed curvature at each point. Positive = turning left, negative = turning right.
    Returns: curvature (numpy array, length n), smoothed
    """
    from scipy.ndimage import gaussian_filter1d
    n = len(coords)
    curvature = np.zeros(n)
    
    for i in range(n):
        next_i = (i + 1) % n if closed else min(i + 1, n - 1)
        # Cross product of tangent[i] x tangent[next_i] gives signed angle
        cross = tangents[i][0] * tangents[next_i][1] - tangents[i][1] * tangents[next_i][0]
        dot = np.clip(np.dot(tangents[i], tangents[next_i]), -1.0, 1.0)
        angle = np.arccos(dot)
        curvature[i] = angle * np.sign(cross)
    
    # Smooth curvature
    if closed:
        padded = np.concatenate([curvature, curvature, curvature])
        smoothed = gaussian_filter1d(padded, sigma=smooth_sigma)
        return smoothed[n:2*n]
    else:
        return gaussian_filter1d(curvature, sigma=smooth_sigma)


def _detect_track_boundaries(coords, tangents, track_obj, max_half_width=4.0, step=0.1):
    """
    For each point, find distance to track edge on both sides.
    Capped at max_half_width to ignore pit lane mergers and access roads.
    
    Returns: dist_left (n,), dist_right (n,) — numpy arrays of edge distances
    """
    n = len(coords)
    dist_left = np.full(n, max_half_width)
    dist_right = np.full(n, max_half_width)
    
    for i in range(n):
        pt_xy = Vector((float(coords[i][0]), float(coords[i][1])))
        left_dir = Vector((-tangents[i][1], tangents[i][0]))   # perpendicular left
        right_dir = Vector((tangents[i][1], -tangents[i][0]))   # perpendicular right
        
        dl, _ = _find_edge_distance(pt_xy, left_dir, track_obj, 
                                     max_search=max_half_width, step=step)
        dr, _ = _find_edge_distance(pt_xy, right_dir, track_obj, 
                                     max_search=max_half_width, step=step)
        dist_left[i] = dl
        dist_right[i] = dr
    
    return dist_left, dist_right


def _segment_corners(curvature, min_corner_length=20, min_straight_length=10, 
                      curvature_threshold=0.003):
    """
    Returns list of segments: [{'type': 'CORNER'|'STRAIGHT', 'start': int, 'end': int, 
                                 'direction': 'LEFT'|'RIGHT'|None, 'apex_idx': int|None}]
    """
    from scipy.ndimage import binary_dilation, binary_erosion
    
    n = len(curvature)
    abs_curv = np.abs(curvature)
    is_corner = abs_curv > curvature_threshold
    
    # Morphological close to fill small gaps
    struct = np.ones(5)
    is_corner = binary_dilation(is_corner, structure=struct, iterations=4)
    is_corner = binary_erosion(is_corner, structure=struct, iterations=4)
    
    # Build contiguous segments
    segments = []
    in_corner = False
    start = 0
    for i in range(n):
        if is_corner[i] and not in_corner:
            # End previous straight if exists
            if i > 0 and (not segments or segments[-1]['end'] < i - 1):
                segments.append({'type': 'STRAIGHT', 'start': start, 'end': i - 1,
                                  'direction': None, 'apex_idx': None})
            start = i
            in_corner = True
        elif not is_corner[i] and in_corner:
            segments.append({'type': 'CORNER', 'start': start, 'end': i - 1,
                              'direction': None, 'apex_idx': None})
            start = i
            in_corner = False
    # Handle final segment
    if in_corner:
        segments.append({'type': 'CORNER', 'start': start, 'end': n - 1,
                          'direction': None, 'apex_idx': None})
    elif start < n - 1:
        segments.append({'type': 'STRAIGHT', 'start': start, 'end': n - 1,
                          'direction': None, 'apex_idx': None})
    
    # Merge short segments
    merged = []
    for seg in segments:
        length = seg['end'] - seg['start'] + 1
        if seg['type'] == 'CORNER' and length < min_corner_length and merged:
            merged[-1]['end'] = seg['end']  # absorb into previous
        elif seg['type'] == 'STRAIGHT' and length < min_straight_length and merged:
            merged[-1]['end'] = seg['end']  # absorb into previous
        else:
            merged.append(seg)
    
    # Compute direction and apex for each CORNER
    for seg in merged:
        if seg['type'] == 'CORNER':
            s, e = seg['start'], seg['end']
            avg_curv = np.mean(curvature[s:e+1])
            seg['direction'] = 'LEFT' if avg_curv > 0 else 'RIGHT'
            # Apex = point of maximum absolute curvature within segment
            seg['apex_idx'] = s + int(np.argmax(abs_curv[s:e+1]))
    
    return merged


def _generate_ideal_line(coords, tangents, curvature, segments, dist_left, dist_right,
                          closed, apex_inset_frac=0.15, entry_width_frac=0.7):
    """
    Generate ideal racing line as TARGET lateral fractions of track width.
    
    For each point, computes where the car SHOULD be as a fraction of track width:
      0.0 = inside edge (for corners, relative to turn direction)
      0.5 = center
      1.0 = outside edge
    
    On straights: target = 0.5 (center)
    At corner apex: target = apex_inset_frac (close to inside, e.g. 0.15 = 15% from inside)
    At corner entry/exit: target = entry_width_frac (wide, e.g. 0.7 = 70% from inside = outside)
    
    Returns: target_fractions (numpy array, length n) — where each point should be
             in terms of left-right fraction: 0=full left edge, 1=full right edge
    """
    n = len(coords)
    
    # First compute where each point currently IS as a left-right fraction
    # fraction = dist_left / (dist_left + dist_right)
    # 0 = at left edge, 0.5 = center, 1 = at right edge
    total_width = dist_left + dist_right
    total_width = np.clip(total_width, 0.1, None)  # avoid division by zero
    current_frac = dist_left / total_width  # 0=left edge, 1=right edge
    
    # Start with current fractions (no change)
    target_frac = current_frac.copy()
    
    for seg in segments:
        if seg['type'] == 'STRAIGHT':
            # On straights: target center
            for i in range(seg['start'], seg['end'] + 1):
                target_frac[i] = 0.5
            continue
        
        # CORNER segment
        s, e = seg['start'], seg['end']
        apex = seg['apex_idx']
        direction = seg['direction']
        
        for i in range(s, e + 1):
            # Phase through the corner: 0 at entry/exit, 1 at apex
            if i <= apex:
                dist_to_apex = apex - i
                half_len = max(apex - s, 1)
                phase = 1.0 - (dist_to_apex / half_len)
            else:
                dist_from_apex = i - apex
                half_len = max(e - apex, 1)
                phase = 1.0 - (dist_from_apex / half_len)
            
            # Cosine smoothing
            weight = 0.5 * (1.0 - math.cos(math.pi * phase))
            
            # Inside and outside target fractions depend on turn direction
            if direction == 'LEFT':
                # Left turn: inside = left edge (fraction 0), outside = right edge (fraction 1)
                inside_target = apex_inset_frac           # close to left edge
                outside_target = entry_width_frac         # toward right edge
            else:
                # Right turn: inside = right edge (fraction 1), outside = left edge (fraction 0)
                inside_target = 1.0 - apex_inset_frac     # close to right edge
                outside_target = 1.0 - entry_width_frac   # toward left edge
            
            # Blend between outside (entry/exit) and inside (apex)
            target_frac[i] = outside_target + (inside_target - outside_target) * weight
    
    # Smooth target fractions for continuity at segment boundaries
    from scipy.ndimage import gaussian_filter1d
    if closed:
        padded = np.concatenate([target_frac, target_frac, target_frac])
        smoothed = gaussian_filter1d(padded, sigma=12)
        target_frac = smoothed[n:2*n]
    else:
        target_frac = gaussian_filter1d(target_frac, sigma=12)
    
    # Clamp to valid range
    target_frac = np.clip(target_frac, 0.05, 0.95)
    
    return target_frac, current_frac


def _extract_driver_style(coords, tangents, segments, dist_left, dist_right):
    """
    For each corner segment, extract broad driver style from GPS positions:
    - apex_shift: how many points early(negative) or late(positive) the driver's 
      closest-to-inside point is vs the geometric apex
    - apex_depth: fraction of available inside room the driver actually uses (0-1)
    - entry_exit_ratio: >1 means wider entry than exit, <1 means wider exit than entry
    
    Returns: list of dicts, one per corner segment in order
    """
    styles = []
    
    for seg in segments:
        if seg['type'] != 'CORNER':
            continue
        
        s, e = seg['start'], seg['end']
        geo_apex = seg['apex_idx']
        direction = seg['direction']
        
        # For each point in corner, compute distance to inside edge
        inside_distances = []
        for i in range(s, e + 1):
            if direction == 'LEFT':
                inside_distances.append(dist_left[i])
            else:
                inside_distances.append(dist_right[i])
        
        inside_distances = np.array(inside_distances)
        
        if len(inside_distances) == 0:
            styles.append({'apex_shift': 0, 'apex_depth': 0.5, 'entry_exit_ratio': 1.0})
            continue
        
        # Driver's apex = point closest to inside edge (minimum inside_distance)
        driver_apex_local = int(np.argmin(inside_distances))
        driver_apex_global = s + driver_apex_local
        
        # Apex shift: positive = late apex, negative = early apex
        apex_shift = driver_apex_global - geo_apex
        
        # Apex depth: how much of the available room does the driver use?
        # If inside_distance at driver apex is small → driver goes deep (close to edge)
        geo_apex_inside_dist = inside_distances[geo_apex - s] if (geo_apex - s) < len(inside_distances) else inside_distances[0]
        driver_min_inside_dist = inside_distances[driver_apex_local]
        if geo_apex_inside_dist > 0.01:
            apex_depth = 1.0 - (driver_min_inside_dist / geo_apex_inside_dist)
        else:
            apex_depth = 0.5
        apex_depth = np.clip(apex_depth, 0.0, 1.0)
        
        # Entry/exit asymmetry
        mid_local = len(inside_distances) // 2
        if mid_local > 0 and mid_local < len(inside_distances):
            entry_avg = np.mean(inside_distances[:mid_local])
            exit_avg = np.mean(inside_distances[mid_local:])
            if exit_avg > 0.01:
                entry_exit_ratio = entry_avg / exit_avg
            else:
                entry_exit_ratio = 1.0
        else:
            entry_exit_ratio = 1.0
        
        entry_exit_ratio = np.clip(entry_exit_ratio, 0.3, 3.0)
        
        styles.append({
            'apex_shift': int(apex_shift),
            'apex_depth': float(apex_depth),
            'entry_exit_ratio': float(entry_exit_ratio)
        })
    
    return styles


def _apply_style_to_ideal(target_frac, segments, styles, style_blend=0.5):
    """
    Blend driver style into the ideal racing line.
    style_blend: 0 = pure ideal line, 1 = fully styled. Default 0.5 = half and half.
    
    Modifies target_frac in-place.
    """
    corner_idx = 0
    for seg in segments:
        if seg['type'] != 'CORNER':
            continue
        if corner_idx >= len(styles):
            break
        
        style = styles[corner_idx]
        s, e = seg['start'], seg['end']
        apex = seg['apex_idx']
        seg_len = e - s + 1
        
        # Apply apex shift: shift the peak of the offset curve
        shift = int(round(style['apex_shift'] * style_blend))
        if shift != 0 and seg_len > abs(shift) * 2:
            section = target_frac[s:e+1].copy()
            shifted = np.zeros_like(section)
            for i in range(len(section)):
                src = i - shift
                if 0 <= src < len(section):
                    shifted[i] = section[src]
                else:
                    shifted[i] = section[max(0, min(len(section)-1, src))]
            target_frac[s:e+1] = section * (1 - style_blend) + shifted * style_blend
        
        # Apply apex depth: scale how far from center the target goes
        # depth > 0.5 means driver goes deeper, < 0.5 means stays wider
        depth_scale = 1.0 + (style['apex_depth'] - 0.5) * style_blend * 0.5
        mid_frac = 0.5  # center
        for i in range(s, e + 1):
            # Scale the deviation from center
            target_frac[i] = mid_frac + (target_frac[i] - mid_frac) * depth_scale
        
        corner_idx += 1


def _build_racing_line_qp(path_obj, track_obj, strength=0.8, style_blend=0.5):
    """
    Build an ideal racing line using TUMFTM QP optimizer + Kabsch alignment.
    
    Requires TRACK_CENTER_FIXED curve in the scene.
    Requires trajectory_planning_helpers installed.
    
    strength:    how much to move toward aligned position (0=keep GPS, 1=full aligned)
    style_blend: racing line blend in Kabsch step (0=raw GPS, 1=fully snapped)
    
    Returns: number of centerline points processed (or 0 on failure)
    """
    try:
        import numpy as np
        import math
        from mathutils import Vector
        from scipy.ndimage import gaussian_filter1d
    except ImportError as e:
        print(f"  [QP Racing Line] Missing dependency: {e}")
        return 0

    try:
        import trajectory_planning_helpers as tph
    except ImportError:
        print("  [QP Racing Line] trajectory_planning_helpers not installed. Skipping.")
        return 0

    # --- Check centerline ---
    cl_obj = bpy.data.objects.get("TRACK_CENTER_FIXED")
    if not cl_obj:
        print("  [QP Racing Line] TRACK_CENTER_FIXED not found. Skipping.")
        return 0

    # --- Extract centerline ---
    sp = cl_obj.data.splines[0]
    n = len(sp.points)
    cl = np.zeros((n, 2))
    for i in range(n):
        co = cl_obj.matrix_world @ Vector(sp.points[i].co[:3])
        cl[i] = [co.x, co.y]

    # --- Tangents and normals from centerline ---
    tangents = np.zeros((n, 2))
    for i in range(n):
        diff = cl[(i + 3) % n] - cl[(i - 3) % n]
        nm = np.linalg.norm(diff)
        tangents[i] = diff / nm if nm > 1e-8 else [1, 0]

    normals = np.zeros((n, 2))
    for i in range(n):
        normals[i] = [-tangents[i][1], tangents[i][0]]

    # --- Raycast real track widths against Track mesh ---
    inv = track_obj.matrix_world.inverted()
    ray_dir = (inv.to_3x3() @ Vector((0, 0, -1))).normalized()

    inset = 0.10
    w_tr_left  = np.zeros(n)
    w_tr_right = np.zeros(n)

    print("  [QP Racing Line] Raycasting track widths...")
    for i in range(n):
        pt = cl[i]
        # Left
        last_hit = 0.0
        for si in range(1, 200):
            d = si * 0.15
            test = pt + normals[i] * d
            origin = Vector((test[0], test[1], 10000.0))
            hit, _, _, _ = track_obj.ray_cast(inv @ origin, ray_dir)
            if hit:
                last_hit = d
            else:
                break
        w_tr_left[i] = max(last_hit - inset, 0.05)

        # Right
        last_hit = 0.0
        for si in range(1, 200):
            d = si * 0.15
            test = pt - normals[i] * d
            origin = Vector((test[0], test[1], 10000.0))
            hit, _, _, _ = track_obj.ray_cast(inv @ origin, ray_dir)
            if hit:
                last_hit = d
            else:
                break
        w_tr_right[i] = max(last_hit - inset, 0.05)

    # --- Build reftrack and run TUMFTM optimizer ---
    cl_closed = np.vstack([cl, cl[0]])
    reftrack  = np.column_stack([cl, w_tr_right, w_tr_left])

    coeffs_x, coeffs_y, A, _ = tph.calc_splines.calc_splines(
        path=cl_closed, use_dist_scaling=True
    )
    ind_spls = np.arange(len(coeffs_x))
    t_spls   = np.zeros(len(coeffs_x))

    psi, kappa = tph.calc_head_curv_an.calc_head_curv_an(
        coeffs_x=coeffs_x, coeffs_y=coeffs_y,
        ind_spls=ind_spls, t_spls=t_spls,
        calc_curv=True, calc_dcurv=False
    )[:2]

    normvec_normalized = tph.calc_normal_vectors.calc_normal_vectors(psi=psi)

    print("  [QP Racing Line] Running TUMFTM optimizer...")
    alpha_mincurv, _ = tph.opt_min_curv.opt_min_curv(
        reftrack=reftrack,
        normvectors=normvec_normalized,
        A=A,
        kappa_bound=0.50,
        w_veh=2.0,
        print_debug=False,
        plot_debug=False,
        closed=True
    )

    raceline = tph.create_raceline.create_raceline(
        refline=cl,
        normvectors=normvec_normalized,
        alpha=alpha_mincurv,
        stepsize_interp=2.0
    )[0]

    # --- Store Q_RACING_LINE in scene for reference ---
    rl_name = "Q_RACING_LINE"
    for d in [bpy.data.objects, bpy.data.curves]:
        if rl_name in d:
            d.remove(d[rl_name], do_unlink=True)
    rl_curve = bpy.data.curves.new(rl_name, 'CURVE')
    rl_curve.dimensions = '3D'
    rl_sp = rl_curve.splines.new('POLY')
    rl_sp.points.add(len(raceline) - 1)
    for i in range(len(raceline)):
        rl_sp.points[i].co = (raceline[i, 0], raceline[i, 1], 0, 1)
    rl_sp.use_cyclic_u = True
    rl_obj = bpy.data.objects.new(rl_name, rl_curve)
    bpy.context.collection.objects.link(rl_obj)
    print(f"  [QP Racing Line] Q_RACING_LINE created: {len(raceline)} pts")

    # --- Extract GPS driving path points ---
    coords, _, closed = _extract_path_geometry(path_obj)
    P_raw = np.zeros((len(coords), 3))
    P_raw[:, :2] = coords

    Q_raw = np.zeros((len(raceline), 3))
    Q_raw[:, :2] = raceline

    # --- Resample both to N points ---
    N = 1000

    def resample(pts, n_out):
        from scipy.interpolate import interp1d
        mask = np.ones(len(pts), dtype=bool)
        for i in range(1, len(pts)):
            if np.linalg.norm(pts[i] - pts[i-1]) < 1e-10:
                mask[i] = False
        pts = pts[mask]
        cl2 = np.vstack((pts, pts[0]))
        diffs = cl2[1:] - cl2[:-1]
        dists = np.linalg.norm(diffs, axis=1)
        cum   = np.concatenate(([0], np.cumsum(dists)))
        total = cum[-1]
        targets = np.linspace(0, total, n_out, endpoint=False)
        ext = np.vstack((pts, pts, pts))
        exc = np.concatenate((cum[:-1] - total, cum[:-1], cum[:-1] + total))
        out = np.zeros((n_out, 3))
        for ax in range(3):
            f = interp1d(exc, ext[:, ax], kind='cubic')
            out[:, ax] = f(targets)
        return out

    P_res = resample(P_raw, N)
    Q_res = resample(Q_raw, N)

    # --- Cyclic shift search for best Kabsch alignment ---
    def kabsch(P, Q):
        cP = P.mean(axis=0)
        cQ = Q.mean(axis=0)
        H  = (P - cP).T @ (Q - cQ)
        U, S, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T
        if np.linalg.det(R) < 0:
            Vt[-1, :] *= -1
            R = Vt.T @ U.T
        return R, cQ - R @ cP

    best_rms   = float('inf')
    best_shift = 0
    step       = max(1, N // 100)

    for s in range(0, N, step):
        Q_shifted = np.roll(Q_res, -s, axis=0)
        R, t = kabsch(P_res, Q_shifted)
        P_al = (R @ P_res.T).T + t
        rms  = np.sqrt(((P_al - Q_shifted) ** 2).mean())
        if rms < best_rms:
            best_rms   = rms
            best_shift = s

    for s in range(max(0, best_shift - step), min(N, best_shift + step + 1)):
        Q_shifted = np.roll(Q_res, -s, axis=0)
        R, t = kabsch(P_res, Q_shifted)
        P_al = (R @ P_res.T).T + t
        rms  = np.sqrt(((P_al - Q_shifted) ** 2).mean())
        if rms < best_rms:
            best_rms   = rms
            best_shift = s

    Q_final  = np.roll(Q_res, -best_shift, axis=0)
    R, t     = kabsch(P_res, Q_final)
    P_aligned = (R @ P_raw.T).T + t

    # --- Blend aligned GPS toward racing line ---
    if style_blend > 0.0:
        M      = len(P_aligned)
        K      = len(Q_raw)
        shift_ratio = best_shift / N
        window = max(20, int(K * 0.15))

        A_pts    = Q_raw
        B_pts    = np.roll(Q_raw, -1, axis=0)
        AB       = B_pts - A_pts
        AB_sq    = np.sum(AB ** 2, axis=1)
        AB_sq[AB_sq < 1e-12] = 1e-12

        P_projected = np.zeros((M, 3))
        for i in range(M):
            pt  = P_aligned[i]
            exp_k = int(((i / M) + shift_ratio) * K) % K
            idx   = np.arange(exp_k - window, exp_k + window + 1) % K
            AP    = pt - A_pts[idx]
            t_par = np.clip(np.sum(AP * AB[idx], axis=1) / AB_sq[idx], 0, 1)
            proj  = A_pts[idx] + t_par[:, np.newaxis] * AB[idx]
            P_projected[i] = proj[np.argmin(np.sum((pt - proj) ** 2, axis=1))]

        P_out = P_aligned * (1.0 - style_blend) + P_projected * style_blend
    else:
        P_out = P_aligned.copy()

    P_out[:, 2] = 0.0

    # --- Write aligned points back onto driving_path in-place ---
    # This preserves the Follow Path constraint target — car follows automatically
    points, ptype = _get_path_points(path_obj)
    inv_mat = path_obj.matrix_world.inverted()

    # Resample P_out to match exact point count of the driving path
    P_final = resample(P_out, len(points))

    for i in range(len(points)):
        new_world = Vector((float(P_final[i, 0]), float(P_final[i, 1]), float(P_final[i, 2])))
        new_local = inv_mat @ new_world
        _set_point_co(points[i], ptype, new_local)

    path_obj.data.update_tag()
    print(f"  [QP Racing Line] Done. RMS={best_rms:.2f}. Path updated in-place.")
    return n


def _build_racing_line(path_obj, track_obj, strength=0.8, max_half_width=4.0,
                        style_blend=0.5):
    """
    Build an ideal racing line for a single path.
    
    strength: how much to move toward ideal position (0=keep GPS, 1=full ideal)
    max_half_width: cap for edge detection (ignores pit mergers beyond this)
    style_blend: how much driver style to apply (0=pure geometric ideal, 1=full GPS style)
    
    Returns: number of corners processed
    """
    coords, tangents, closed = _extract_path_geometry(path_obj)
    n = len(coords)
    
    curvature = _compute_curvature(coords, tangents, closed, smooth_sigma=10)
    
    dist_left, dist_right = _detect_track_boundaries(
        coords, tangents, track_obj, max_half_width=max_half_width, step=0.1
    )
    
    segments = _segment_corners(curvature)
    
    # Generate ideal target fractions and get current fractions
    target_frac, current_frac = _generate_ideal_line(
        coords, tangents, curvature, segments, dist_left, dist_right, closed
    )
    
    # Extract driver style and apply it
    styles = _extract_driver_style(coords, tangents, segments, dist_left, dist_right)
    _apply_style_to_ideal(target_frac, segments, styles, style_blend=style_blend)
    
    # Clamp again after style application
    target_frac = np.clip(target_frac, 0.05, 0.95)
    
    # Blend between current position and target position
    blended_frac = current_frac * (1.0 - strength) + target_frac * strength
    
    # Convert fractions back to world positions
    points, ptype = _get_path_points(path_obj)
    inv_mat = path_obj.matrix_world.inverted()
    
    total_width = dist_left + dist_right
    total_width = np.clip(total_width, 0.1, None)
    
    for i in range(n):
        # Current position is at current_frac[i] of the width
        # Target position is at blended_frac[i] of the width
        # Shift needed (in left-right fraction)
        frac_shift = blended_frac[i] - current_frac[i]
        
        # Convert fraction shift to world-space displacement
        # Positive frac_shift = move toward right edge (positive right direction)
        # The total width at this point determines the scale
        displacement_bu = frac_shift * total_width[i]
        
        # Right direction vector
        right_dir = np.array([tangents[i][1], -tangents[i][0]])
        
        new_x = coords[i][0] + right_dir[0] * displacement_bu
        new_y = coords[i][1] + right_dir[1] * displacement_bu
        
        # Preserve Z
        co_local = _get_point_co(points[i], ptype)
        co_world = path_obj.matrix_world @ co_local
        
        new_world = Vector((new_x, new_y, co_world.z))
        new_local = inv_mat @ new_world
        _set_point_co(points[i], ptype, new_local)
    
    path_obj.data.update_tag()
    
    corner_count = sum(1 for seg in segments if seg['type'] == 'CORNER')
    return corner_count


class OBJECT_OT_f1_centerline_correct(bpy.types.Operator):
    bl_idname = "f1.centerline_correct"
    bl_label = "Build Racing Line"
    bl_description = "Generate ideal racing line from track geometry with driver style from GPS"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props
        track_obj = props.track_surface_obj
        
        if track_obj is None:
            self.report({'ERROR'}, "Set Track Surface object first")
            return {'CANCELLED'}
        
        total_corners = 0
        path_count = 0
        for car in scene.lc.cars:
            path_obj = car.driving_path
            if path_obj is None:
                continue
            
            corners = _build_racing_line_qp(
                path_obj, track_obj,
                strength=props.correction_strength,
                style_blend=props.correction_inset
            )
            total_corners += corners
            path_count += 1
        
        from .f1_trail import sync_all_trails_from_paths
        sync_all_trails_from_paths(scene)
        
        self.report({'INFO'}, f"Racing line built for {path_count} paths ({total_corners} corners)")
        return {'FINISHED'}


class OBJECT_OT_f1_correct_path(Operator):
    bl_idname = "f1.correct_path"
    bl_label = "Correct Path to Track"
    bl_description = "Pull off-track vertices back toward the track edge with smooth falloff (single pass)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props
        track_obj = props.track_surface_obj
        falloff = props.correction_falloff
        strength = props.correction_strength
        inset = props.correction_inset

        if not track_obj or track_obj.type != 'MESH':
            self.report({'ERROR'}, "Select a valid Track Surface mesh object")
            return {'CANCELLED'}

        paths = []
        for car in scene.lc.cars:
            dp = car.driving_path
            if dp and dp.type == 'CURVE' and dp.data.splines:
                paths.append(dp)
        if not paths:
            self.report({'WARNING'}, "No F1 path curves found in scene")
            return {'CANCELLED'}

        total_corrected = 0
        for path_obj in paths:
            total_corrected += _correct_single_pass(path_obj, track_obj, falloff, strength, inset)

        if bpy.data.objects.get("F1_Path_Diagnostic"):
            bpy.ops.f1.diagnose_path()

        sync_all_trails_from_paths(scene)
        self.report({'INFO'}, f"Corrected {total_corrected} off-track vertices across {len(paths)} paths")
        return {'FINISHED'}


MAX_AUTO_ITERATIONS = 50


class OBJECT_OT_f1_auto_correct_path(Operator):
    bl_idname = "f1.auto_correct_path"
    bl_label = "Auto-Correct Path"
    bl_description = "Iteratively correct until all vertices are on-track (or max iterations reached)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props
        track_obj = props.track_surface_obj
        falloff = props.correction_falloff
        strength = props.correction_strength
        inset = props.correction_inset

        if not track_obj or track_obj.type != 'MESH':
            self.report({'ERROR'}, "Select a valid Track Surface mesh object")
            return {'CANCELLED'}

        paths = []
        for car in scene.lc.cars:
            dp = car.driving_path
            if dp and dp.type == 'CURVE' and dp.data.splines:
                paths.append(dp)
        if not paths:
            self.report({'WARNING'}, "No F1 path curves found in scene")
            return {'CANCELLED'}

        iteration = 0
        while iteration < MAX_AUTO_ITERATIONS:
            iteration += 1
            still_off = 0
            for path_obj in paths:
                still_off += _correct_single_pass(path_obj, track_obj, falloff, strength, inset)
            if still_off == 0:
                break

        if bpy.data.objects.get("F1_Path_Diagnostic"):
            bpy.ops.f1.diagnose_path()

        sync_all_trails_from_paths(scene)
        if still_off == 0:
            self.report({'INFO'},
                        f"All vertices on-track after {iteration} iteration(s)")
        else:
            self.report({'WARNING'},
                        f"Stopped after {MAX_AUTO_ITERATIONS} iterations — "
                        f"{still_off} vertices still off-track")
        return {'FINISHED'}


def _apex_tighten_pass(path_obj, track_obj, push_strength=0.3, falloff=15):
    """
    Push corner points toward inside of turns. Uses speed stored in rig keyframes
    to detect corners, and path curvature to determine inside direction.
    
    Only affects points where the car is going slow (corners).
    Leaves straights untouched.
    
    push_strength: how far toward inside to push (fraction of current distance to inside edge)
    falloff: gaussian smooth radius for the push vectors
    
    Returns: number of points pushed
    """
    points, ptype = _get_path_points(path_obj)
    n = len(points)
    closed = path_obj.data.splines[0].use_cyclic_u
    
    # Get world coords
    world_coords = []
    for pt in points:
        co = path_obj.matrix_world @ _get_point_co(pt, ptype)
        world_coords.append(co)
    
    # Compute tangents and curvature sign from path geometry
    # Curvature sign tells us turn direction: positive = left, negative = right
    curvature_sign = []
    for i in range(n):
        prev_i = (i - 1) % n if closed else max(0, i - 1)
        next_i = (i + 1) % n if closed else min(n - 1, i + 1)
        
        v1 = world_coords[i] - world_coords[prev_i]
        v2 = world_coords[next_i] - world_coords[i]
        
        # Cross product Z component = turn direction
        cross_z = v1.x * v2.y - v1.y * v2.x
        curvature_sign.append(cross_z)
    
    # Compute approximate speed at each point from spacing
    # Points closer together = car going slower (since timing is baked at constant frame rate)
    # Actually simpler: use the distance between adjacent points as a speed proxy
    # Large spacing = fast, small spacing = slow
    spacing = []
    for i in range(n):
        next_i = (i + 1) % n if closed else min(n - 1, i + 1)
        d = (world_coords[next_i] - world_coords[i]).length
        spacing.append(d)
    spacing = np.array(spacing)
    
    # Smooth spacing to get clean speed proxy
    from scipy.ndimage import gaussian_filter1d
    if closed:
        padded = np.concatenate([spacing, spacing, spacing])
        spacing_smooth = gaussian_filter1d(padded, sigma=5)[n:2*n]
    else:
        spacing_smooth = gaussian_filter1d(spacing, sigma=5)
    
    # Normalize: 0 = slowest point (tightest corner), 1 = fastest (straight)
    sp_min = np.min(spacing_smooth)
    sp_max = np.max(spacing_smooth)
    if sp_max - sp_min > 1e-8:
        speed_norm = (spacing_smooth - sp_min) / (sp_max - sp_min)
    else:
        speed_norm = np.ones(n)
    
    # Corner weight: 1 at slowest points, 0 at fastest
    # Use a threshold: only affect points below 50th percentile speed
    corner_weight = np.clip(1.0 - speed_norm * 2.0, 0.0, 1.0)
    # Smooth the weight so transitions are gradual
    if closed:
        padded = np.concatenate([corner_weight, corner_weight, corner_weight])
        corner_weight = gaussian_filter1d(padded, sigma=8)[n:2*n]
    else:
        corner_weight = gaussian_filter1d(corner_weight, sigma=8)
    corner_weight = np.clip(corner_weight, 0.0, 1.0)
    
    # Build push vectors
    raw_pushes = []
    pushed_count = 0
    
    for i in range(n):
        if corner_weight[i] < 0.01:
            raw_pushes.append(Vector((0, 0, 0)))
            continue
        
        # Inside direction: perpendicular to tangent, toward turn center
        prev_i = (i - 1) % n if closed else max(0, i - 1)
        next_i = (i + 1) % n if closed else min(n - 1, i + 1)
        tangent = (world_coords[next_i] - world_coords[prev_i])
        tangent.z = 0
        if tangent.length > 1e-8:
            tangent.normalize()
        
        # Perpendicular: left = (-ty, tx), right = (ty, -tx)
        # If curvature_sign > 0 (turning left), inside = left
        # If curvature_sign < 0 (turning right), inside = right
        if curvature_sign[i] > 0:
            inside_dir = Vector((-tangent.y, tangent.x, 0))
        else:
            inside_dir = Vector((tangent.y, -tangent.x, 0))
        
        # How far to push: use closest_point_on_mesh to find distance to nearest edge
        # Then push a fraction of that distance toward inside
        pt_xy = Vector((world_coords[i].x, world_coords[i].y))
        
        # Find inside edge by stepping along inside_dir
        inv = track_obj.matrix_world.inverted()
        ray_dir_local = (inv.to_3x3() @ Vector((0, 0, -1))).normalized()
        
        inside_edge_dist = 0.0
        step = 0.1
        max_search = 4.0
        d = step
        while d <= max_search:
            test = pt_xy + Vector((inside_dir.x, inside_dir.y)) * d
            origin = Vector((test.x, test.y, 10000.0))
            local_o = inv @ origin
            hit, _, _, _ = track_obj.ray_cast(local_o, ray_dir_local)
            if not hit:
                inside_edge_dist = d
                break
            d += step
        
        if inside_edge_dist < 0.01:
            raw_pushes.append(Vector((0, 0, 0)))
            continue
        
        # Push toward inside: strength * corner_weight * distance_to_edge
        push_amount = push_strength * corner_weight[i] * inside_edge_dist
        push_vec = inside_dir * push_amount
        push_vec.z = 0
        raw_pushes.append(push_vec)
        pushed_count += 1
    
    # Gaussian smooth the push vectors
    smoothed = _gaussian_smooth_vectors(raw_pushes, falloff, closed=closed)
    
    # Apply
    inv_rot = path_obj.matrix_world.inverted().to_3x3()
    for i in range(n):
        if smoothed[i].length < 1e-6:
            continue
        local_push = inv_rot @ smoothed[i]
        co = _get_point_co(points[i], ptype)
        _set_point_co(points[i], ptype, co + local_push)
    
    path_obj.data.update_tag()
    return pushed_count


class OBJECT_OT_f1_apex_tighten(bpy.types.Operator):
    bl_idname = "f1.apex_tighten"
    bl_label = "Tighten Apexes"
    bl_description = "Push corner points toward inside of turns for tighter apex lines"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props
        track_obj = props.track_surface_obj
        
        if track_obj is None:
            self.report({'ERROR'}, "Set Track Surface object first")
            return {'CANCELLED'}
        
        total_pushed = 0
        path_count = 0
        for car in scene.lc.cars:
            path_obj = car.driving_path
            if path_obj is None:
                continue
            pushed = _apex_tighten_pass(
                path_obj, track_obj,
                push_strength=props.correction_strength,
                falloff=props.correction_falloff
            )
            total_pushed += pushed
            path_count += 1
        
        from .f1_trail import sync_all_trails_from_paths
        sync_all_trails_from_paths(scene)
        
        self.report({'INFO'}, f"Tightened {total_pushed} apex points across {path_count} paths")
        return {'FINISHED'}


class OBJECT_OT_f1_clear_diagnostic(Operator):
    bl_idname = "f1.clear_diagnostic"
    bl_label = "Clear Diagnostic"
    bl_description = "Remove the diagnostic overlay from the scene"

    def execute(self, context):
        old = bpy.data.objects.get("F1_Path_Diagnostic")
        if old:
            bpy.data.objects.remove(old, do_unlink=True)
        self.report({'INFO'}, "Diagnostic cleared")
        return {'FINISHED'}


def _flatten_bezier_handles_z(point, target_z):
    """Force both Bezier handles to the same Z as the control point.
    This ensures the curve between control points stays at the target height
    instead of dipping above/below due to handle Z offsets."""
    hl = point.handle_left.copy()
    hr = point.handle_right.copy()
    hl.z = target_z
    hr.z = target_z
    point.handle_left = hl
    point.handle_right = hr


class OBJECT_OT_f1_flatten_z(Operator):
    bl_idname = "f1.flatten_z"
    bl_label = "Flatten Z"
    bl_description = "Set all path vertices and handles to a uniform Z height"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props
        target_z = props.normalize_z_value

        paths = []
        for car in scene.lc.cars:
            dp = car.driving_path
            if dp and dp.type == 'CURVE' and dp.data.splines:
                paths.append(dp)
        if not paths:
            self.report({'WARNING'}, "No F1 path curves found in scene")
            return {'CANCELLED'}

        count = 0
        for path_obj in paths:
            points, ptype = _get_path_points(path_obj)
            inv = path_obj.matrix_world.inverted()
            local_target = (inv @ Vector((0.0, 0.0, target_z))).z

            for pt in points:
                co = _get_point_co(pt, ptype)
                co.z = local_target
                _set_point_co(pt, ptype, co)
                # Force handles to same Z so curve doesn't dip between points
                if ptype == 'BEZIER':
                    _flatten_bezier_handles_z(pt, local_target)
                count += 1
            path_obj.data.update_tag()

        sync_all_trails_from_paths(scene)
        self.report({'INFO'}, f"Flattened {count} vertices + handles to Z={target_z:.3f}")
        return {'FINISHED'}


def _interpolate_missed_z(z_values, hit_flags, closed):
    """Fill missed (False) entries by interpolating from nearest hit neighbors.
    Properly handles closed-path wrap-around and searches outward for hits."""
    n = len(z_values)
    if n == 0:
        return list(z_values)

    # If nothing hit at all, use average of all existing Z (fallback)
    if not any(hit_flags):
        avg_z = sum(z_values) / n if n else 0.0
        return [avg_z] * n

    result = list(z_values)

    # For each missed vertex, find nearest hit in both directions
    for i in range(n):
        if hit_flags[i]:
            continue

        # Search backward for nearest hit
        prev_z = None
        prev_dist = 0
        for step in range(1, n):
            idx = (i - step) % n if closed else i - step
            if not closed and idx < 0:
                break
            prev_dist = step
            if hit_flags[idx]:
                prev_z = z_values[idx]
                break

        # Search forward for nearest hit
        next_z = None
        next_dist = 0
        for step in range(1, n):
            idx = (i + step) % n if closed else i + step
            if not closed and idx >= n:
                break
            next_dist = step
            if hit_flags[idx]:
                next_z = z_values[idx]
                break

        # Interpolate
        if prev_z is not None and next_z is not None:
            total = prev_dist + next_dist
            t = prev_dist / total if total > 0 else 0.5
            result[i] = prev_z + t * (next_z - prev_z)
        elif prev_z is not None:
            result[i] = prev_z
        elif next_z is not None:
            result[i] = next_z

    return result


def _smooth_z_values(z_values, radius, closed):
    """Gaussian-smooth a list of Z floats to eliminate spikes."""
    n = len(z_values)
    if radius <= 0 or n == 0:
        return list(z_values)
    sigma = max(radius / 3.0, 1.0)
    kernel = [math.exp(-(j ** 2) / (2.0 * sigma ** 2))
              for j in range(-radius, radius + 1)]
    k_sum = sum(kernel)
    kernel = [k / k_sum for k in kernel]

    result = []
    for i in range(n):
        val = 0.0
        for j, w in enumerate(kernel):
            if closed:
                idx = (i + j - radius) % n
            else:
                idx = max(0, min(n - 1, i + j - radius))
            val += z_values[idx] * w
        result.append(val)
    return result


class OBJECT_OT_f1_snap_z_to_track(Operator):
    bl_idname = "f1.snap_z_to_track"
    bl_label = "Snap Z to Track"
    bl_description = ("Project path vertices onto the track surface height, "
                      "interpolate missed vertices, and smooth the result")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props
        track_obj = props.track_surface_obj
        falloff = props.correction_falloff

        if not track_obj or track_obj.type != 'MESH':
            self.report({'ERROR'}, "Select a valid Track Surface mesh object")
            return {'CANCELLED'}

        paths = []
        for car in scene.lc.cars:
            dp = car.driving_path
            if dp and dp.type == 'CURVE' and dp.data.splines:
                paths.append(dp)
        if not paths:
            self.report({'WARNING'}, "No F1 path curves found in scene")
            return {'CANCELLED'}

        inv_track = track_obj.matrix_world.inverted()
        local_down = (inv_track.to_3x3() @ Vector((0, 0, -1))).normalized()
        total_snapped = 0
        total_interpolated = 0

        for path_obj in paths:
            points, ptype = _get_path_points(path_obj)
            n = len(points)
            closed = path_obj.data.splines[0].use_cyclic_u
            inv_path = path_obj.matrix_world.inverted()

            # Pass 1: ray-cast to get Z where possible
            world_positions = []
            z_values = [0.0] * n
            hit_flags = [False] * n

            for i, pt in enumerate(points):
                co_local = _get_point_co(pt, ptype)
                co_world = path_obj.matrix_world @ co_local
                world_positions.append(co_world)

                ray_origin = Vector((co_world.x, co_world.y, 10000.0))
                local_origin = inv_track @ ray_origin
                hit, loc, _norm, _idx = track_obj.ray_cast(local_origin, local_down)

                if hit:
                    hit_world = track_obj.matrix_world @ loc
                    z_values[i] = hit_world.z
                    hit_flags[i] = True
                    total_snapped += 1

            # Pass 2: interpolate missed vertices from neighbors
            missed = hit_flags.count(False)
            if missed > 0 and missed < n:
                z_values = _interpolate_missed_z(z_values, hit_flags, closed)
                total_interpolated += missed

            # Pass 3: gaussian-smooth all Z to eliminate remaining spikes
            z_values = _smooth_z_values(z_values, falloff, closed)

            # Apply final Z values
            for i, pt in enumerate(points):
                co_world = world_positions[i]
                new_world = Vector((co_world.x, co_world.y, z_values[i]))
                new_local = inv_path @ new_world
                _set_point_co(pt, ptype, new_local)
                if ptype == 'BEZIER':
                    _flatten_bezier_handles_z(pt, new_local.z)

            path_obj.data.update_tag()

        sync_all_trails_from_paths(scene)
        msg = f"Snapped {total_snapped} vertices to track"
        if total_interpolated:
            msg += f", interpolated {total_interpolated} off-track"
        msg += f", smoothed with falloff={falloff}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ==============================================================================
# QUEUE MANAGEMENT
# ==============================================================================
def _session_key_to_baker(session_key):
    """Map Lohith UI session keys to FastF1/Baker session names."""
    m = {'R': 'Race', 'Q': 'Qualifying', 'FP1': 'Practice 1', 'FP2': 'Practice 2', 'FP3': 'Practice 3',
         'SQ': 'Sprint Qualifying', 'Sprint': 'Sprint',
         'Day 1': '1', 'Day 2': '2', 'Day 3': '3', 'Day Best': '1'}
    return m.get(session_key, session_key)


class OBJECT_OT_f1_add_lap_to_queue(Operator):
    bl_idname = "f1.add_lap"
    bl_label = "Add Lap to Queue"

    def execute(self, context):
        scene = context.scene
        props = scene.f1_pipeline_props

        if len(scene.f1_lap_queue) >= 4:
            self.report({'WARNING'}, "Queue is full (Max 4)")
            return {'CANCELLED'}

        from ..data.f1_properties import _get_event, _DRV_BY_RACE, _DRV_BY_SEASON, _get_drivers_for_session

        event = _get_event(props.sel_year, props.sel_race)
        is_testing = event and event.get('event_type') == 'testing'

        item = scene.f1_lap_queue.add()
        item.year       = int(props.sel_year)
        item.driver     = props.sel_driver
        item.fastest_lap = props.fastest_lap
        item.q_segment  = getattr(props, 'sel_q_segment', 'Q_ALL') if props.sel_session == 'Q' else ''

        if is_testing:
            item.is_testing   = True
            item.test_number  = event.get('test_number', 1)
            item.test_session = int(_session_key_to_baker(props.sel_session)) if props.sel_session in ('Day 1', 'Day 2', 'Day 3') else 1
            if props.sel_session == 'Day Best':
                item.test_session = 1  # Day Best: use Day 1 for now
            item.event    = event.get('event_name', f"Pre-Season Test {item.test_number}")
            item.session  = props.sel_session  # Day 1, Day 2, Day 3, Day Best
            item.track_id = f"testing_{item.year}_test{item.test_number}"
        else:
            item.is_testing   = False
            item.test_number  = 1
            item.test_session = 1
            item.event    = props.sel_race
            item.session  = props.sel_session  # R, Q, FP1, etc.
            item.track_id = props.sel_race.lower().replace(" ", "_")

        # Resolve team from _get_drivers_for_session
        q_seg = item.q_segment if item.q_segment != 'Q_ALL' else None
        drivers = _get_drivers_for_session(props.sel_year, props.sel_race, props.sel_session, q_seg)
        if not drivers:
            drivers = _DRV_BY_SEASON.get(props.sel_year, [])
        driver_entry = next((d for d in drivers if isinstance(d, dict) and d.get('code') == props.sel_driver), None)
        item.team = driver_entry['team_raw'] if driver_entry else "Unknown Team"

        # Track lock (Lohith-style)
        if len(scene.f1_lap_queue) == 1:
            props.locked_track = item.event
            props.status_msg = f"Ref: {item.driver} @ {item.event}"

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
        context.scene.f1_lap_queue.clear()
        props = context.scene.f1_pipeline_props
        props.locked_track = ""
        props.status_msg = "Ready"
        return {'FINISHED'}


class OBJECT_OT_f1_render_minimap(Operator):
    bl_idname = "f1.render_minimap"
    bl_label = "Render Minimap"
    bl_description = (
        "Render minimap frames from existing telemetry CSVs "
        "(no asset import needed)"
    )

    def execute(self, context):
        if F1_HiFi_Baker_Pro.MISSING_DEPS:
            self.report({'ERROR'}, "Missing Dependencies. Install FastF1 first.")
            return {'CANCELLED'}

        scene = context.scene
        queue = scene.f1_lap_queue

        db = F1_Database_Manager()
        exports_dir = db.get_exports_dir()

        # Discover drivers from existing CSVs
        csv_drivers = []
        if os.path.isdir(exports_dir):
            for fname in sorted(os.listdir(exports_dir)):
                if fname.endswith("_telemetry.csv"):
                    code = fname.replace("_telemetry.csv", "")
                    csv_drivers.append(code)

        if not csv_drivers:
            self.report({'ERROR'}, "No telemetry CSVs found in exports folder.")
            return {'CANCELLED'}

        # Determine year/event/session from queue or properties
        if len(queue) > 0:
            first = queue[0]
            year = first.year
            event = first.event
            session_key = first.session
            is_testing = first.is_testing
            test_number = first.test_number
            test_session = first.test_session
        else:
            props = scene.f1_pipeline_props
            year = int(props.sel_year)
            event = props.sel_race
            session_key = props.sel_session
            is_testing = False
            test_number = 1
            test_session = 1

        import fastf1
        cache_dir = os.path.join(os.path.expanduser("~"), "fastf1_cache")
        os.makedirs(cache_dir, exist_ok=True)
        fastf1.Cache.enable_cache(cache_dir)

        try:
            if is_testing:
                session = fastf1.get_testing_session(
                    year, int(test_number), int(test_session))
            else:
                session = fastf1.get_session(
                    year, event, _session_key_to_baker(session_key))
            session.load(telemetry=True, laps=True,
                         weather=False, messages=False)
        except Exception as e:
            self.report({'ERROR'}, f"FastF1 load error: {e}")
            return {'CANCELLED'}

        ref_driver = csv_drivers[0]
        F1_HiFi_Baker_Pro.generate_minimap_frames(
            session, csv_drivers, exports_dir, ref_driver, year, event)

        self.report({'INFO'},
                    f"Minimap rendered for {len(csv_drivers)} driver(s)")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(OBJECT_OT_f1_apex_correct)
    bpy.utils.register_class(OBJECT_OT_f1_centerline_correct)
    bpy.utils.register_class(OBJECT_OT_f1_apex_tighten)
    bpy.app.handlers.load_post.append(_f1_load_post_handler)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_f1_apex_correct)
    bpy.utils.unregister_class(OBJECT_OT_f1_centerline_correct)
    bpy.utils.unregister_class(OBJECT_OT_f1_apex_tighten)
    if _f1_load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_f1_load_post_handler)
    from .f1_trail import unregister_trail_handler
    unregister_trail_handler()