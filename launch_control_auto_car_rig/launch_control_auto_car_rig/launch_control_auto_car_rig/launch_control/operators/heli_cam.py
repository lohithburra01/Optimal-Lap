"""F1 Helicopter Camera — auto-tracking with user-overridable markers.

The auto-tracker follows cars and computes height, orbit, distance, and
focal length dynamically.  Users can drop override markers at specific
frames to adjust these values.  Between markers the overrides interpolate
smoothly (cubic smoothstep).

Sliders update the camera in real-time (instant feedback).  During
playback, markers auto-animate the sliders — exactly like keyframes.

When the user sets an explicit angle_offset, the auto-orbit is disabled
so the chosen viewing angle stays fixed.
"""

import bpy
import math
import json
from mathutils import Vector
from bpy.types import Operator
from bpy.props import FloatProperty

HELI_CAM_NAME = "F1_HeliCam"
HELI_TARGET_NAME = "F1_HeliCam_Target"

# ---------------------------------------------------------------------------
# Marker storage & interpolation
# ---------------------------------------------------------------------------

def get_markers(scene):
    """Public: get sorted marker list from scene custom property."""
    raw = scene.get("_heli_markers", "[]")
    try:
        return sorted(json.loads(raw), key=lambda m: m["frame"])
    except Exception:
        return []


def _set_markers(scene, markers):
    scene["_heli_markers"] = json.dumps(
        sorted(markers, key=lambda m: m["frame"]))


def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _lerp_angle(a, b, t):
    """Shortest-path angle interpolation (degrees)."""
    diff = ((b - a + 180) % 360) - 180
    return a + diff * t


_OVERRIDE_KEYS = ("height_offset", "angle_offset", "distance_mult",
                  "focal_override")
_OVERRIDE_DEFAULTS = {
    "height_offset": 0.0,
    "angle_offset":  0.0,
    "distance_mult": 1.0,
    "focal_override": 0.0,
}


def _interpolate_markers(markers, frame):
    """Interpolate override values at *frame*.  Returns dict or None."""
    if not markers:
        return None

    before = None
    after = None
    for m in markers:
        if m["frame"] <= frame:
            before = m
        if m["frame"] >= frame and after is None:
            after = m

    if before is None and after is None:
        return None
    if before is None:
        return {k: after.get(k, _OVERRIDE_DEFAULTS[k]) for k in _OVERRIDE_KEYS}
    if after is None:
        return {k: before.get(k, _OVERRIDE_DEFAULTS[k]) for k in _OVERRIDE_KEYS}
    if before["frame"] == after["frame"]:
        return {k: before.get(k, _OVERRIDE_DEFAULTS[k]) for k in _OVERRIDE_KEYS}

    t = _smoothstep(
        (frame - before["frame"]) / (after["frame"] - before["frame"]))

    result = {}
    for key in _OVERRIDE_KEYS:
        a = before.get(key, _OVERRIDE_DEFAULTS[key])
        b = after.get(key, _OVERRIDE_DEFAULTS[key])
        if key == "angle_offset":
            result[key] = _lerp_angle(a, b, t)
        else:
            result[key] = a + (b - a) * t
    return result


# ---------------------------------------------------------------------------
# Car state helpers
# ---------------------------------------------------------------------------

def _get_car_states(scene, depsgraph=None):
    states = []
    try:
        cars = scene.lc.cars
    except Exception as e:
        print(f"[HeliCam] Cannot access scene.lc.cars: {e}")
        return states

    if depsgraph is None:
        try:
            depsgraph = bpy.context.evaluated_depsgraph_get()
        except Exception:
            pass

    for car in cars:
        rig = car.rig_object
        if not rig:
            continue
        try:
            rig_eval = rig.evaluated_get(depsgraph) if depsgraph else rig

            bone = rig_eval.pose.bones.get("bone_find_up_dir")
            if bone:
                world_mat = rig_eval.matrix_world @ bone.matrix
                pos = world_mat.to_translation()
                fwd = (world_mat.to_3x3() @ Vector((0, 1, 0))).normalized()
            else:
                pos = rig_eval.matrix_world.to_translation()
                fwd = (rig_eval.matrix_world.to_3x3()
                       @ Vector((0, 1, 0))).normalized()

            pos = pos.copy()
            fwd = fwd.copy()
            fwd.z = 0
            if fwd.length > 1e-4:
                fwd.normalize()
            else:
                fwd = Vector((0, 1, 0))

            progress = 0.0
            sr = rig_eval.pose.bones.get("bone_Speed_Rotate")
            if sr:
                progress = sr.rotation_euler[2]

            states.append((pos, fwd, progress))
        except Exception as e:
            print(f"[HeliCam] Error reading car '{rig.name}': {e}")
    return states


def _find_lead_index(states):
    if not states:
        return 0
    best = -1e18
    best_i = 0
    for i, (_, _, prog) in enumerate(states):
        if prog > best:
            best = prog
            best_i = i
    return best_i


# ---------------------------------------------------------------------------
# Camera solver
# ---------------------------------------------------------------------------

def _compute_raw_target(scene, frame, centroid, spread,
                        lead_pos, lead_fwd, overrides=None):
    if overrides is None:
        overrides = {}

    height_offset  = overrides.get("height_offset", 0.0)
    angle_offset   = overrides.get("angle_offset", 0.0)
    distance_mult  = overrides.get("distance_mult", 1.0)
    focal_override = overrides.get("focal_override", 0.0)

    look_at = centroid.copy()

    height = 20.0 + spread * 0.35 + height_offset
    ahead_dist = max(25.0, spread * 0.3 + 20.0) * distance_mult

    # Auto-orbit is disabled when user has set an explicit angle
    if abs(angle_offset) < 0.1:
        fps = max(scene.render.fps, 1)
        t = frame / fps
        orbit_period = 14.0 + spread * 0.06
        orbit_angle = (t / orbit_period) * 2.0 * math.pi
        lateral = Vector((-lead_fwd.y, lead_fwd.x, 0.0))
        orbit_amp = ahead_dist * 0.15
        orbit_offset = lateral * math.sin(orbit_angle) * orbit_amp
    else:
        orbit_offset = Vector((0, 0, 0))

    cam_pos = centroid + lead_fwd * ahead_dist + orbit_offset
    cam_pos.z = centroid.z + height

    # Rotate camera position around centroid by user angle offset
    if abs(angle_offset) > 0.01:
        to_cam = Vector((cam_pos.x - centroid.x,
                         cam_pos.y - centroid.y, 0.0))
        angle_rad = math.radians(angle_offset)
        cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
        rotated = Vector((to_cam.x * cos_a - to_cam.y * sin_a,
                          to_cam.x * sin_a + to_cam.y * cos_a, 0.0))
        cam_pos.x = centroid.x + rotated.x
        cam_pos.y = centroid.y + rotated.y

    # Focal length
    if focal_override > 0:
        focal = focal_override
    else:
        dist_to_centroid = (cam_pos - centroid).length
        cam_obj = bpy.data.objects.get(HELI_CAM_NAME)
        sensor_w = 36.0
        if cam_obj and cam_obj.data:
            sensor_w = cam_obj.data.sensor_width

        if spread > 0.5 and dist_to_centroid > 1.0:
            half_fov = math.atan((spread * 1.6) / dist_to_centroid)
            focal = sensor_w / (2.0 * math.tan(max(half_fov, 0.01)))
            focal = max(18.0, min(135.0, focal))
        else:
            focal = 70.0

    return cam_pos, look_at, focal


# ---------------------------------------------------------------------------
# Smoothing state
# ---------------------------------------------------------------------------

_smooth = {
    "cam":           None,
    "tgt":           None,
    "focal":         None,
    "fwd":           None,
    "prev_centroid": None,
    "last_frame":    -999,
}


def _reset_smooth():
    for k in _smooth:
        _smooth[k] = None if k != "last_frame" else -999


# ---------------------------------------------------------------------------
# Core camera refresh (reads from scene slider properties)
# ---------------------------------------------------------------------------

def _refresh_camera(scene, depsgraph=None, apply_smoothing=True):
    """Update camera position/rotation from current slider values.

    *apply_smoothing*: False for instant response (slider drag),
                       True for playback (helicopter inertia).
    """
    cam_obj = bpy.data.objects.get(HELI_CAM_NAME)
    if cam_obj is None:
        return

    target_obj = bpy.data.objects.get(HELI_TARGET_NAME)
    frame = scene.frame_current
    smoothing = scene.get("_heli_smoothing", 0.05)

    frame_gap = abs(frame - _smooth["last_frame"])
    if frame_gap > 3:
        _reset_smooth()
    _smooth["last_frame"] = frame

    states = _get_car_states(scene, depsgraph)
    if not states:
        return

    positions = [s[0] for s in states]
    n = len(positions)

    lead_i = _find_lead_index(states)
    lead_pos = positions[lead_i]
    centroid = sum(positions, Vector((0, 0, 0))) / n
    spread = (max((p - centroid).length for p in positions)
              if n > 1 else 0.0)

    # Forward direction from centroid velocity
    if _smooth["prev_centroid"] is not None:
        move = centroid - _smooth["prev_centroid"]
        move.z = 0
        if move.length > 0.005:
            velocity_fwd = move.normalized()
            if _smooth["fwd"] is not None:
                blend = _smooth["fwd"].lerp(velocity_fwd, smoothing * 0.3)
                if blend.length > 1e-4:
                    blend.normalize()
                _smooth["fwd"] = blend
            else:
                _smooth["fwd"] = velocity_fwd
    _smooth["prev_centroid"] = centroid.copy()

    lead_fwd = (_smooth["fwd"] if _smooth["fwd"] is not None
                else states[lead_i][1])

    # Always read overrides from the slider properties
    overrides = {
        "height_offset":  getattr(scene, "heli_adj_height", 0.0),
        "angle_offset":   getattr(scene, "heli_adj_angle", 0.0),
        "distance_mult":  getattr(scene, "heli_adj_distance", 1.0),
        "focal_override": getattr(scene, "heli_adj_focal", 0.0),
    }

    cam_pos, look_at, focal = _compute_raw_target(
        scene, frame, centroid, spread, lead_pos, lead_fwd, overrides)

    # Temporal smoothing (skipped for instant slider feedback)
    if apply_smoothing and _smooth["cam"] is not None:
        cam_pos = _smooth["cam"].lerp(cam_pos, smoothing)
        look_at = _smooth["tgt"].lerp(look_at, smoothing)
        focal = (_smooth["focal"]
                 + (focal - _smooth["focal"]) * smoothing * 0.4)

    _smooth["cam"] = cam_pos.copy()
    _smooth["tgt"] = look_at.copy()
    _smooth["focal"] = focal

    cam_obj.location = cam_pos
    if target_obj:
        target_obj.location = look_at
    if cam_obj.data:
        cam_obj.data.lens = focal

    direction = look_at - cam_pos
    if direction.length > 1e-4:
        rot = direction.to_track_quat('-Z', 'Y')
        cam_obj.rotation_euler = rot.to_euler()


# ---------------------------------------------------------------------------
# Frame-change handler
# ---------------------------------------------------------------------------

_handler_ref = None

# Flag to prevent property-update → handler recursion when we push
# interpolated marker values into the sliders.
_applying_markers = False


def _heli_cam_update(scene, depsgraph=None):
    """frame_change_post handler.

    If markers exist, push interpolated values into the sliders (like
    keyframes animating the properties).  Then call _refresh_camera
    which always reads from the sliders.
    """
    global _applying_markers

    cam_obj = bpy.data.objects.get(HELI_CAM_NAME)
    if cam_obj is None:
        return

    frame = scene.frame_current

    # Apply marker overrides to the slider properties
    markers = get_markers(scene)
    interp = _interpolate_markers(markers, frame)
    if interp is not None:
        _applying_markers = True
        try:
            scene.heli_adj_height   = interp["height_offset"]
            scene.heli_adj_angle    = interp["angle_offset"]
            scene.heli_adj_distance = interp["distance_mult"]
            scene.heli_adj_focal    = interp["focal_override"]
        finally:
            _applying_markers = False

    _refresh_camera(scene, depsgraph, apply_smoothing=True)


def _on_adj_change(self, context):
    """Property update callback — instant camera feedback when user drags
    a slider.  Skipped when the frame handler is pushing marker values."""
    if _applying_markers:
        return
    _refresh_camera(context.scene, apply_smoothing=False)


# ---------------------------------------------------------------------------
# Handler management
# ---------------------------------------------------------------------------

def _purge_stale_handlers():
    """Remove ALL heli-cam handlers (handles addon reload safely)."""
    to_remove = [h for h in bpy.app.handlers.frame_change_post
                 if getattr(h, '__name__', '') == '_heli_cam_update']
    for h in to_remove:
        try:
            bpy.app.handlers.frame_change_post.remove(h)
        except ValueError:
            pass


def _register_handler():
    global _handler_ref
    _purge_stale_handlers()
    bpy.app.handlers.frame_change_post.append(_heli_cam_update)
    _handler_ref = _heli_cam_update
    print("[HeliCam] Handler registered")


def _unregister_handler():
    global _handler_ref
    _purge_stale_handlers()
    _handler_ref = None


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class F1_OT_create_heli_cam(Operator):
    bl_idname = "f1.create_heli_cam"
    bl_label = "Create Heli-Cam"
    bl_description = ("Create a dynamic helicopter camera that tracks all "
                      "cars — adjustable via markers")
    bl_options = {'REGISTER', 'UNDO'}

    smoothing: FloatProperty(
        name="Smoothing", default=0.05, min=0.01, max=1.0,
        description="Camera inertia (lower = smoother helicopter feel)")

    def execute(self, context):
        scene = context.scene

        for name in (HELI_CAM_NAME, HELI_TARGET_NAME):
            old = bpy.data.objects.get(name)
            if old:
                bpy.data.objects.remove(old, do_unlink=True)

        target = bpy.data.objects.new(HELI_TARGET_NAME, None)
        target.empty_display_type = 'SPHERE'
        target.empty_display_size = 2.0
        scene.collection.objects.link(target)

        cam_data = bpy.data.cameras.new(HELI_CAM_NAME)
        cam_data.lens = 70
        cam_data.clip_start = 0.5
        cam_data.clip_end = 5000
        cam_obj = bpy.data.objects.new(HELI_CAM_NAME, cam_data)
        scene.collection.objects.link(cam_obj)

        scene["_heli_smoothing"] = self.smoothing
        scene["_heli_markers"] = "[]"
        scene.heli_adj_height = 0.0
        scene.heli_adj_angle = 0.0
        scene.heli_adj_distance = 1.0
        scene.heli_adj_focal = 0.0

        _reset_smooth()
        _register_handler()

        scene.camera = cam_obj
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces[0].region_3d.view_perspective = 'CAMERA'
                break

        _refresh_camera(scene, apply_smoothing=False)

        self.report({'INFO'}, "F1 Heli-Cam created")
        return {'FINISHED'}


class F1_OT_remove_heli_cam(Operator):
    bl_idname = "f1.remove_heli_cam"
    bl_label = "Remove Heli-Cam"
    bl_description = "Remove the helicopter camera, handler, and markers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _unregister_handler()
        _reset_smooth()
        for name in (HELI_CAM_NAME, HELI_TARGET_NAME):
            obj = bpy.data.objects.get(name)
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)
        cam_data = bpy.data.cameras.get(HELI_CAM_NAME)
        if cam_data:
            bpy.data.cameras.remove(cam_data)

        scene = context.scene
        if "_heli_markers" in scene:
            del scene["_heli_markers"]

        self.report({'INFO'}, "F1 Heli-Cam removed")
        return {'FINISHED'}


# ── Marker operators ──────────────────────────────────────────────────────

class F1_OT_heli_set_marker(Operator):
    bl_idname = "f1.heli_set_marker"
    bl_label = "Set Marker"
    bl_description = "Save current adjustment values as a marker at this frame"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        frame = scene.frame_current
        markers = get_markers(scene)
        markers = [m for m in markers if m["frame"] != frame]
        markers.append({
            "frame":          frame,
            "height_offset":  scene.heli_adj_height,
            "angle_offset":   scene.heli_adj_angle,
            "distance_mult":  scene.heli_adj_distance,
            "focal_override": scene.heli_adj_focal,
        })
        _set_markers(scene, markers)
        self.report({'INFO'}, f"Marker set at frame {frame}")
        return {'FINISHED'}


class F1_OT_heli_delete_marker(Operator):
    bl_idname = "f1.heli_delete_marker"
    bl_label = "Delete Marker"
    bl_description = "Remove the marker at the current frame"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        frame = scene.frame_current
        markers = get_markers(scene)
        before = len(markers)
        markers = [m for m in markers if m["frame"] != frame]
        _set_markers(scene, markers)
        if len(markers) < before:
            self.report({'INFO'}, f"Marker at frame {frame} deleted")
        else:
            self.report({'WARNING'}, f"No marker at frame {frame}")
        return {'FINISHED'}


class F1_OT_heli_clear_markers(Operator):
    bl_idname = "f1.heli_clear_markers"
    bl_label = "Clear All Markers"
    bl_description = "Remove every camera override marker"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _set_markers(context.scene, [])
        self.report({'INFO'}, "All markers cleared")
        return {'FINISHED'}


class F1_OT_heli_prev_marker(Operator):
    bl_idname = "f1.heli_prev_marker"
    bl_label = "Previous Marker"
    bl_description = "Jump to the previous marker and load its values"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        markers = get_markers(scene)
        prev = [m for m in markers if m["frame"] < scene.frame_current]
        if not prev:
            self.report({'INFO'}, "No previous marker")
            return {'CANCELLED'}
        m = prev[-1]
        scene.frame_set(m["frame"])
        scene.heli_adj_height   = m.get("height_offset", 0.0)
        scene.heli_adj_angle    = m.get("angle_offset", 0.0)
        scene.heli_adj_distance = m.get("distance_mult", 1.0)
        scene.heli_adj_focal    = m.get("focal_override", 0.0)
        return {'FINISHED'}


class F1_OT_heli_next_marker(Operator):
    bl_idname = "f1.heli_next_marker"
    bl_label = "Next Marker"
    bl_description = "Jump to the next marker and load its values"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        markers = get_markers(scene)
        nxt = [m for m in markers if m["frame"] > scene.frame_current]
        if not nxt:
            self.report({'INFO'}, "No next marker")
            return {'CANCELLED'}
        m = nxt[0]
        scene.frame_set(m["frame"])
        scene.heli_adj_height   = m.get("height_offset", 0.0)
        scene.heli_adj_angle    = m.get("angle_offset", 0.0)
        scene.heli_adj_distance = m.get("distance_mult", 1.0)
        scene.heli_adj_focal    = m.get("focal_override", 0.0)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Persistent handler — re-register after file load if heli-cam exists
# ---------------------------------------------------------------------------

@bpy.app.handlers.persistent
def _heli_load_post(dummy):
    if bpy.data.objects.get(HELI_CAM_NAME):
        _reset_smooth()
        _register_handler()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register():
    bpy.types.Scene.heli_adj_height = FloatProperty(
        name="Height Offset", default=0.0, min=-50.0, max=200.0,
        description="Height adjustment above auto-computed position",
        update=_on_adj_change)
    bpy.types.Scene.heli_adj_angle = FloatProperty(
        name="Angle Offset", default=0.0, min=-180.0, max=180.0,
        description="Rotate camera around the cars (degrees)",
        update=_on_adj_change)
    bpy.types.Scene.heli_adj_distance = FloatProperty(
        name="Distance", default=1.0, min=0.2, max=5.0,
        description="Distance multiplier (1.0 = auto)",
        update=_on_adj_change)
    bpy.types.Scene.heli_adj_focal = FloatProperty(
        name="Focal Length", default=0.0, min=0.0, max=200.0,
        description="Focal length override in mm (0 = auto)",
        update=_on_adj_change)
    bpy.app.handlers.load_post.append(_heli_load_post)

    try:
        if bpy.data.objects.get(HELI_CAM_NAME):
            _reset_smooth()
            _register_handler()
    except Exception:
        pass


def unregister():
    _unregister_handler()
    for attr in ("heli_adj_height", "heli_adj_angle",
                 "heli_adj_distance", "heli_adj_focal"):
        try:
            delattr(bpy.types.Scene, attr)
        except Exception:
            pass
    try:
        bpy.app.handlers.load_post.remove(_heli_load_post)
    except ValueError:
        pass
