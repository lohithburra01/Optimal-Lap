import bpy
import json
import os
import math
from bpy.props import (StringProperty, IntProperty, EnumProperty,
                       CollectionProperty, PointerProperty, FloatProperty,
                       BoolProperty)

# ── DATABASE LOADER ──────────────────────────────────────────────────────────

_CALENDAR      = {}
_DRV_BY_RACE   = {}
_DRV_BY_SEASON = {}

def _get_db_root():
    """Resolve path to F1_Pipeline_Assets/database relative to the open .blend file."""
    try:
        blend_path = bpy.data.filepath
    except AttributeError:
        blend_path = ""
        
    if blend_path:
        return os.path.join(os.path.dirname(blend_path),
                            "F1_Pipeline_Assets", "database")
    # Fallback: walk up from this .py file
    this_dir = os.path.dirname(os.path.abspath(__file__))
    root = os.path.normpath(os.path.join(this_dir, "..", "..", ".."))
    return os.path.join(root, "F1_Pipeline_Assets", "database")

def load_databases():
    global _CALENDAR, _DRV_BY_RACE, _DRV_BY_SEASON
    db_dir = _get_db_root()
    try:
        if os.path.exists(os.path.join(db_dir, "calendar_cache.json")):
            with open(os.path.join(db_dir, "calendar_cache.json"),    encoding='utf-8') as f:
                _CALENDAR = json.load(f)
            with open(os.path.join(db_dir, "drivers_by_race.json"),   encoding='utf-8') as f:
                _DRV_BY_RACE = json.load(f)
            with open(os.path.join(db_dir, "drivers_by_season.json"), encoding='utf-8') as f:
                _DRV_BY_SEASON = json.load(f)
            print(f"[F1 Studio] Databases loaded. Years: {sorted(_CALENDAR.keys())}")
        else:
            print(f"[F1 Studio] Database files not found in: {db_dir}")
    except Exception as e:
        print(f"[F1 Studio] WARNING – Could not load databases: {e}")
        print(f"[F1 Studio] Looked in: {db_dir}")

# Removed global load_databases() call to avoid _RestrictData error on import


# ── ENUM ITEM CALLBACKS ───────────────────────────────────────────────────────

def _year_items(self, context):
    if not _CALENDAR:
        return [('2024', '2024', '')]
    return [(y, y, '') for y in sorted(_CALENDAR.keys(), reverse=True)]


def _race_items(self, context):
    year = self.sel_year
    events = _CALENDAR.get(year, [])
    if not events:
        return [('NONE', 'No data – check database', '')]
    return [
        (e['event_name'],
         e['event_name'],
         f"Round {e['round']}  |  {e.get('location','')}  {e.get('country','')}")
        for e in events
    ]


def _driver_items(self, context):
    year = self.sel_year
    race = self.sel_race
    drivers = _DRV_BY_RACE.get(year, {}).get(race, [])
    if not drivers:
        drivers = _DRV_BY_SEASON.get(year, [])
    if not drivers:
        return [('NONE', 'No drivers – check database', '')]

    # Sort drivers by team name so teammates are grouped together
    sorted_drivers = sorted(drivers, key=lambda d: d.get('team_raw', ''))

    items = []
    prev_team = None
    for d in sorted_drivers:
        team = d.get('team_raw', '')
        # Insert a separator between different teams
        if prev_team is not None and team != prev_team:
            items.append(('', '', ''))
        prev_team = team
        items.append((
            d['code'],
            f"{d['full_name']}  [{team}]",
            f"#{d['number']}  {d['code']}",
        ))
    return items


# ── UPDATE CALLBACKS ──────────────────────────────────────────────────────────

def _on_year_changed(self, context):
    items = _race_items(self, context)
    if items and items[0][0] != 'NONE':
        self['sel_race'] = 0

def _on_race_changed(self, context):
    items = _driver_items(self, context)
    if items and items[0][0] != 'NONE':
        self['sel_driver'] = 0


# ── PROPERTY GROUPS ───────────────────────────────────────────────────────────

class F1_Lap_Item(bpy.types.PropertyGroup):
    """One entry in the lap queue."""
    year:     IntProperty(name="Year",     default=2024)
    event:    StringProperty(name="Event",   default="Bahrain Grand Prix")
    session:  StringProperty(name="Session", default="Race")
    driver:   StringProperty(name="Driver",  default="VER")
    team:     StringProperty(name="Team",    default="Red Bull Racing")
    track_id: StringProperty(name="Track ID", default="bahrain_grand_prix")


class F1_Pipeline_Props(bpy.types.PropertyGroup):
    """All UI selection properties for the F1 Studio panel."""

    sel_year: EnumProperty(
        name="Season",
        description="Select the F1 season year",
        items=_year_items,
        update=_on_year_changed,
    )

    sel_race: EnumProperty(
        name="Race",
        description="Select the Grand Prix",
        items=_race_items,
        update=_on_race_changed,
    )

    sel_session: EnumProperty(
        name="Session",
        description="Select the session type",
        items=[
            ('Practice 1',  'FP1',        ''),
            ('Practice 2',  'FP2',        ''),
            ('Practice 3',  'FP3',        ''),
            ('Qualifying',  'Qualifying', ''),
            ('Sprint',      'Sprint',     ''),
            ('Race',        'Race',       ''),
        ],
        default='Race',
    )

    sel_driver: EnumProperty(
        name="Driver",
        description="Select a driver (updates based on year and race)",
        items=_driver_items,
    )

    status_msg: StringProperty(name="Status", default="Ready")

    # ── GENERATION OPTIONS ───────────────────────────────────────────────
    render_minimap: BoolProperty(
        name="Render Track Map",
        description="Generate minimap video frames during scene generation",
        default=True,
    )

    # ── TRACK ALIGNMENT ──────────────────────────────────────────────────
    align_offset_x: FloatProperty(
        name="Offset X",
        description="Shift all telemetry paths along X to align with the track model",
        default=0.0,
        unit='LENGTH',
        update=lambda self, ctx: _on_alignment_changed(self, ctx),
    )
    align_offset_y: FloatProperty(
        name="Offset Y",
        description="Shift all telemetry paths along Y to align with the track model",
        default=0.0,
        unit='LENGTH',
        update=lambda self, ctx: _on_alignment_changed(self, ctx),
    )
    align_rotation: FloatProperty(
        name="Rotation",
        description="Rotate all telemetry paths around Z to align with the track model",
        default=0.0,
        subtype='ANGLE',
        update=lambda self, ctx: _on_alignment_changed(self, ctx),
    )
    align_scale: FloatProperty(
        name="Scale",
        description="Uniformly scale all telemetry paths to match the track model size",
        default=1.0,
        min=0.01,
        soft_min=0.5,
        soft_max=2.0,
        update=lambda self, ctx: _on_alignment_changed(self, ctx),
    )

    # ── PATH DIAGNOSTIC / CORRECTION ─────────────────────────────────────
    track_surface_obj: PointerProperty(
        type=bpy.types.Object,
        name="Track Surface",
        description="Mesh object representing the track surface (used for on/off-track detection)",
        poll=lambda self, obj: obj.type == 'MESH',
    )
    correction_falloff: IntProperty(
        name="Falloff",
        description="Number of neighboring vertices on each side to blend the correction into",
        default=15,
        min=1,
        soft_max=50,
    )
    correction_strength: FloatProperty(
        name="Strength",
        description="How aggressively off-track vertices are pulled back (1.0 = fully to track edge)",
        default=1.0,
        min=0.0,
        max=1.0,
    )
    normalize_z_value: FloatProperty(
        name="Target Z",
        description="Target height when flattening path vertices",
        default=0.0,
        unit='LENGTH',
    )


# ── ALIGNMENT CALLBACK ──────────────────────────────────────────────────────

def _get_f1_path_curves(scene):
    """Return all F1 telemetry path curve objects in the scene."""
    paths = []
    for car in scene.lc.cars:
        if car.driving_path and car.driving_path.type == 'CURVE':
            paths.append(car.driving_path)
    return paths


def _on_alignment_changed(props, context):
    """Move/rotate/scale all F1 path curves when alignment sliders change."""
    scene = context.scene
    paths = _get_f1_path_curves(scene)
    if not paths:
        return

    ox = props.align_offset_x
    oy = props.align_offset_y
    rot = props.align_rotation
    sc = props.align_scale

    for path_obj in paths:
        path_obj.location.x = ox
        path_obj.location.y = oy
        path_obj.rotation_euler.z = rot
        path_obj.scale = (sc, sc, sc)


# ── REGISTRATION ──────────────────────────────────────────────────────────────

classes = [F1_Lap_Item, F1_Pipeline_Props]

def register():
    load_databases()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.f1_pipeline_props = PointerProperty(type=F1_Pipeline_Props)
    bpy.types.Scene.f1_lap_queue      = CollectionProperty(type=F1_Lap_Item)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.f1_pipeline_props
    del bpy.types.Scene.f1_lap_queue
