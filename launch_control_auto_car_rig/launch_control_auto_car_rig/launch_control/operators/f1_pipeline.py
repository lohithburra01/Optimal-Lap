import bpy
import os
import json
import math
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
        track_mesh_objects = []
        if os.path.exists(track_path):
            track_mesh_objects = self.load_track(track_path)
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

        props = scene.f1_pipeline_props
        for (year, event, session), drivers in batches.items():
            settings = {
                'resolution': 0.5, 'width': 6.0, 'lookahead': 70,
                'output_dir': temp_data_dir,
                'render_minimap': props.render_minimap,
            }
            if F1_HiFi_Baker_Pro.MISSING_DEPS:
                self.report({'ERROR'}, "Missing Dependencies. Please install FastF1 via preferences.")
                return {'CANCELLED'}

            msg, map, lap_time = F1_HiFi_Baker_Pro.generate_multirail_data(year, event, session, drivers, settings)
            print(f"Baker: {msg}")

            for d in drivers:
                generated_files[d] = os.path.join(temp_data_dir, f"{d}_hifi_path.json")

        # STEP 1 - APPEND ALL CARS FIRST (no LC registration yet)
        appended_colls = []
        for item in scene.f1_lap_queue:
            car_path = db.get_car_path(item.year, item.team, item.driver)
            if os.path.exists(car_path):
                new_coll = self.append_car_lc(car_path)
                if new_coll:
                    appended_colls.append((item.driver, new_coll))
                    print(f"[F1 Studio] Appended {item.driver} -> {new_coll.name}")
                else:
                    self.report({'WARNING'}, f"No CarRig collection found in {car_path}")
            else:
                self.report({'WARNING'}, f"Car file not found: {car_path}")

        # STEP 2 - ALL CARS APPENDED, NOW REGISTER WITH LC AND APPLY JSON
        # Strategy: Find LaunchControl collections first (top-level containers),
        # then match each driver to the LaunchControl that owns their CarRig.

        # Collect all LaunchControl collections in the scene
        lc_parents = []
        for coll in scene.collection.children:
            if 'LaunchControl' in coll.name:
                lc_parents.append(coll)
        # Also check deeper nesting just in case
        for coll in scene.collection.children_recursive:
            if 'LaunchControl' in coll.name and coll not in lc_parents:
                lc_parents.append(coll)

        # Debug: dump the full hierarchy
        print(f"[F1 Studio] Found {len(lc_parents)} LaunchControl collection(s):")
        for lc in lc_parents:
            child_names = [c.name for c in lc.children_recursive]
            print(f"  {lc.name} -> children: {child_names}")

        for i, item in enumerate(scene.f1_lap_queue):
            # Find the LaunchControl that contains this driver's CarRig
            search_coll = None
            coll = None  # the CarRig collection for this driver

            for lc in lc_parents:
                for child in lc.children_recursive:
                    if child.name.startswith('CarRig') and item.driver in child.name:
                        search_coll = lc
                        coll = child
                        break
                if search_coll:
                    break

            # Fallback: use index-based matching
            if search_coll is None and i < len(lc_parents):
                search_coll = lc_parents[i]
                # Find any CarRig child
                for child in search_coll.children_recursive:
                    if child.name.startswith('CarRig'):
                        coll = child
                        break
                if coll is None:
                    coll = search_coll

            if search_coll is None:
                self.report({'WARNING'}, f"No LaunchControl found for {item.driver}")
                continue

            print(f"[F1 Studio] Registering {item.driver} -> {coll.name} (parent: {search_coll.name})")

            rig_obj = None
            driving_path = None
            sim_body = None
            sim_wheels = None
            sim_track_to = None

            # Search the LaunchControl collection for armature/curve/sim objects
            print(f"  Searching for objects in: {search_coll.name}")

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

            print(f"  rig={rig_obj.name if rig_obj else 'MISSING'} "
                  f"curve={driving_path.name if driving_path else 'MISSING'} "
                  f"sim_body={sim_body.name if sim_body else 'MISSING'} "
                  f"sim_wheels={sim_wheels.name if sim_wheels else 'MISSING'} "
                  f"sim_track_to={sim_track_to.name if sim_track_to else 'MISSING'}")

            # The LC collection is the LaunchControl parent, CarRig is the rig sub-collection
            lc_coll = search_coll

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
            car.lc_collection = lc_coll
            car.sim_body = sim_body
            car.sim_wheels = sim_wheels
            car.sim_track_to = sim_track_to

            # Set as active LC car
            scene.car_collection = coll

            # Apply telemetry JSON
            json_path = os.path.join(temp_data_dir, f"{item.driver}_hifi_path.json")
            if os.path.isfile(json_path):
                result = bpy.ops.object.apply_lap_from_json(filepath=json_path)
                print(f"[F1 Studio] {item.driver} apply_lap result: {result}")
            else:
                self.report({'WARNING'}, f"JSON not found for {item.driver}: {json_path}")

        # STEP 3 - LINK TRACK MESHES INTO EACH CAR'S GROUND DETECTION
        if track_mesh_objects:
            self._link_track_to_ground_detection(scene, track_mesh_objects)

        # STEP 4 - AUTO-LOAD SAVED ALIGNMENT FOR THIS TRACK
        track_id = first_item.event.lower().replace(" ", "_")
        self._apply_saved_alignment(context, track_id)

        self.report({'INFO'}, "Scene Generated Successfully")
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


def _correct_single_pass(path_obj, track_obj, falloff, strength):
    """Run one correction pass on a single path. Returns number of off-track vertices found."""
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
            total_corrected += _correct_single_pass(path_obj, track_obj, falloff, strength)

        if bpy.data.objects.get("F1_Path_Diagnostic"):
            bpy.ops.f1.diagnose_path()

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
                still_off += _correct_single_pass(path_obj, track_obj, falloff, strength)
            if still_off == 0:
                break

        if bpy.data.objects.get("F1_Path_Diagnostic"):
            bpy.ops.f1.diagnose_path()

        if still_off == 0:
            self.report({'INFO'},
                        f"All vertices on-track after {iteration} iteration(s)")
        else:
            self.report({'WARNING'},
                        f"Stopped after {MAX_AUTO_ITERATIONS} iterations — "
                        f"{still_off} vertices still off-track")
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

        msg = f"Snapped {total_snapped} vertices to track"
        if total_interpolated:
            msg += f", interpolated {total_interpolated} off-track"
        msg += f", smoothed with falloff={falloff}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


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

        item = scene.f1_lap_queue.add()
        item.year     = int(props.sel_year)
        item.event    = props.sel_race
        item.session  = props.sel_session
        item.driver   = props.sel_driver
        item.track_id = props.sel_race.lower().replace(" ", "_")

        from ..data.f1_properties import _DRV_BY_RACE
        race_drivers = _DRV_BY_RACE.get(props.sel_year, {}).get(props.sel_race, [])
        driver_entry = next((d for d in race_drivers if d['code'] == props.sel_driver), None)
        item.team = driver_entry['team_raw'] if driver_entry else "Unknown Team"

        if len(scene.f1_lap_queue) == 1:
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
        context.scene.f1_pipeline_props.status_msg = "Ready"
        return {'FINISHED'}


def register():
    bpy.app.handlers.load_post.append(_f1_load_post_handler)


def unregister():
    if _f1_load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_f1_load_post_handler)