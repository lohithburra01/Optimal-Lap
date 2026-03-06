import bpy
import json
import os
import math
from bpy.props import (StringProperty, IntProperty, EnumProperty,
                       CollectionProperty, PointerProperty, FloatProperty,
                       BoolProperty)

# ── DATABASE LOADER ──────────────────────────────────────────────────────────

_CALENDAR        = {}
_DRV_BY_RACE     = {}
_DRV_BY_SEASON   = {}
_TESTING_EVENTS  = {}
_SESSION_MAP     = {}  # event_type -> display names (from event_session_map.json)

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
    global _CALENDAR, _DRV_BY_RACE, _DRV_BY_SEASON, _TESTING_EVENTS, _SESSION_MAP
    db_dir = _get_db_root()
    if not os.path.isdir(db_dir):
        print(f"[F1 Studio] Database dir not found: {db_dir}")
        return
    # Load each file independently so missing drivers/calendar don't break the rest
    cal_path = os.path.join(db_dir, "calendar_cache.json")
    if os.path.exists(cal_path):
        try:
            with open(cal_path, encoding='utf-8') as f:
                _CALENDAR = json.load(f)
            print(f"[F1 Studio] Calendar loaded. Years: {sorted(_CALENDAR.keys())}")
        except Exception as e:
            print(f"[F1 Studio] WARNING – Could not load calendar: {e}")
    else:
        print(f"[F1 Studio] No calendar_cache.json in {db_dir}")

    for name, key in [
        ("drivers_by_race.json", "_DRV_BY_RACE"),
        ("drivers_by_season.json", "_DRV_BY_SEASON"),
    ]:
        path = os.path.join(db_dir, name)
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
                if key == "_DRV_BY_RACE":
                    _DRV_BY_RACE = data
                else:
                    _DRV_BY_SEASON = data
            except Exception as e:
                print(f"[F1 Studio] WARNING – Could not load {name}: {e}")
    # Testing events (optional) — Pre-Season Test 1/2 appear in Event dropdown
    test_path = os.path.join(db_dir, "testing_events.json")
    if os.path.exists(test_path):
        try:
            with open(test_path, encoding='utf-8') as f:
                _TESTING_EVENTS = json.load(f)
            n = sum(len(v) for v in _TESTING_EVENTS.values())
            print(f"[F1 Studio] Testing events loaded: {n} pre-season test(s) for {list(_TESTING_EVENTS.keys())}")
        except Exception as e:
            print(f"[F1 Studio] WARNING – Could not load testing_events: {e}")
    # event_session_map (optional) — session display names
    esm_path = os.path.join(db_dir, "event_session_map.json")
    if os.path.exists(esm_path):
        try:
            with open(esm_path, encoding='utf-8') as f:
                _SESSION_MAP = json.load(f)
        except Exception as e:
            print(f"[F1 Studio] WARNING – Could not load event_session_map: {e}")


# ── HELPERS (Lohith-style data fetching) ──────────────────────────────────────

def _get_event(year_str, race_name):
    """Return the calendar/testing entry dict for a given year + event name."""
    # Check races in calendar
    for e in _CALENDAR.get(year_str, []):
        if e.get('event_name') == race_name:
            out = dict(e)
            out['event_type'] = e.get('event_type', 'race')
            out['has_sprint'] = e.get('has_sprint', False)
            return out
    # Check testing events
    for t in _TESTING_EVENTS.get(year_str, []):
        if t.get('event_name') == race_name or f"Pre-Season Test {t.get('test_number', 1)}" == race_name:
            return {
                'event_name': race_name,
                'event_type': 'testing',
                'test_number': t.get('test_number', 1),
                'location': t.get('location', ''),
                'country': t.get('country', ''),
            }
    return None


def _get_race_events_for_year(year_str):
    """Build unified list: races first, then testing events."""
    events = []
    for e in _CALENDAR.get(year_str, []):
        ev = dict(e)
        ev['event_type'] = ev.get('event_type', 'race')
        ev['has_sprint'] = ev.get('has_sprint', False)
        events.append(ev)
    for t in _TESTING_EVENTS.get(year_str, []):
        events.append({
            'event_name': f"Pre-Season Test {t.get('test_number', 1)}",
            'event_type': 'testing',
            'test_number': t.get('test_number', 1),
            'round': 0,
            'location': t.get('location', ''),
            'country': t.get('country', ''),
        })
    return events


def _get_drivers_for_session(year_str, race_name, session_key, q_segment=None):
    """
    Return driver list for a specific session.
    Handles both flat list and per-session dict format. Falls back to drivers_by_season.
    """
    event_data = _DRV_BY_RACE.get(year_str, {}).get(race_name)

    if event_data is None:
        return _DRV_BY_SEASON.get(year_str, [])

    # Per-session dict format (e.g. {"Q": {"Q1": [...], "Q2": [...], "Q3": [...]}, "R": [...]})
    if isinstance(event_data, dict):
        if session_key == 'Q':
            q_data = event_data.get('Q', {})
            if isinstance(q_data, dict):
                if q_segment and q_segment in q_data:
                    return q_data[q_segment]
                return q_data.get('_all', event_data.get('_all', []))
            return event_data.get('_all', [])

        if session_key in ('Day 1', 'Day 2', 'Day 3'):
            return event_data.get(session_key, [])

        return event_data.get(session_key, event_data.get('_all', []))

    # Flat list format
    if isinstance(event_data, list):
        if session_key == 'Q' and q_segment == 'Q3':
            return event_data[:10]
        if session_key == 'Q' and q_segment == 'Q2':
            return event_data[:15]
        return event_data

    return _DRV_BY_SEASON.get(year_str, [])


# ── ENUM ITEM CALLBACKS ───────────────────────────────────────────────────────

def _year_items(self, context):
    years = set(_CALENDAR.keys()) | set(_TESTING_EVENTS.keys())
    if not years:
        return [('2024', '2024', '')]
    return [(y, y, '') for y in sorted(years, reverse=True)]


def _race_items(self, context):
    """Unified list: races + testing events (Lohith-style)."""
    year = self.sel_year
    events = _get_race_events_for_year(year)
    if not events:
        return [('NONE', 'No data – check database', '')]
    items = []
    for e in events:
        etype = e.get('event_type', 'race')
        if etype == 'testing':
            desc = f"Pre-Season  |  {e.get('location','')}  {e.get('country','')}"
        else:
            desc = f"Round {e.get('round',0)}  |  {e.get('location','')}  {e.get('country','')}"
        items.append((e['event_name'], e['event_name'], desc))
    return items


def _session_items(self, context):
    """Dynamic sessions based on event type (Lohith-style)."""
    year = self.sel_year
    race = self.sel_race
    event = _get_event(year, race)
    if not event:
        return [('R', 'Race', '')]

    etype = event.get('event_type', 'race')
    has_sprint = event.get('has_sprint', False)
    display = _SESSION_MAP.get(etype, {}).get('display', {})

    if etype == 'testing':
        return [
            ('Day 1', 'Day 1', ''),
            ('Day 2', 'Day 2', ''),
            ('Day 3', 'Day 3', ''),
            ('Day Best', '★ Best Across Days', ''),
        ]

    if has_sprint:
        sessions = ['FP1', 'SQ', 'Sprint', 'Q', 'R']
        display = _SESSION_MAP.get('sprint_weekend', {}).get('display', display)
    else:
        sessions = ['FP1', 'FP2', 'FP3', 'Q', 'R']

    return [(s, display.get(s, s), '') for s in sessions]


def _q_segment_items(self, context):
    return [
        ('Q_ALL', '★ Best Q (Fastest)', 'Fastest lap across all Q segments'),
        ('Q1', 'Q1', 'Qualifying segment 1 — all 20 drivers'),
        ('Q2', 'Q2', 'Qualifying segment 2 — top 15'),
        ('Q3', 'Q3', 'Qualifying segment 3 — top 10'),
    ]


def _driver_items(self, context):
    """Drivers for current year/race/session (Lohith-style via _get_drivers_for_session)."""
    year = self.sel_year
    race = self.sel_race
    session = self.sel_session
    q_seg = getattr(self, 'sel_q_segment', 'Q_ALL') if session == 'Q' else None
    if q_seg == 'Q_ALL':
        q_seg = None

    if session == 'Day Best':
        drivers = _get_drivers_for_session(year, race, 'Day 1', None)
    else:
        drivers = _get_drivers_for_session(year, race, session, q_seg)

    if not drivers:
        drivers = _DRV_BY_SEASON.get(year, [])
    if not drivers:
        return [('NONE', 'No drivers – check database', '')]

    items = []
    for d in drivers:
        if not isinstance(d, dict):
            continue
        code = d.get('code', '')
        if not code:
            continue
        items.append((
            code,
            f"{d.get('full_name', code)}  [{d.get('team_raw', '')}]",
            f"#{d.get('number', '')}  {code}",
        ))
    return items if items else [('NONE', 'No drivers – check database', '')]


# ── UPDATE CALLBACKS ──────────────────────────────────────────────────────────

def _on_year_changed(self, context):
    props = getattr(context.scene, 'f1_pipeline_props', None) if context else None
    if props and getattr(props, 'locked_track', ''):
        # Keep selection on locked track if it exists in new year
        events = _get_race_events_for_year(self.sel_year)
        for i, e in enumerate(events):
            if e.get('event_name') == props.locked_track:
                self['sel_race'] = i
                self['sel_session'] = 0
                self['sel_q_segment'] = 0
                self['sel_driver'] = 0
                return
    items = _race_items(self, context)
    for i, (val, _, _) in enumerate(items):
        if val != 'NONE':
            event = _get_event(self.sel_year, val)
            if event and event.get('event_type') != 'testing':
                self['sel_race'] = i
                break
    self['sel_session'] = 0
    self['sel_q_segment'] = 0
    self['sel_driver'] = 0


def _on_race_changed(self, context):
    self['sel_session'] = 0
    self['sel_q_segment'] = 0
    self['sel_driver'] = 0


def _on_session_changed(self, context):
    self['sel_q_segment'] = 0
    self['sel_driver'] = 0


def _on_q_segment_changed(self, context):
    self['sel_driver'] = 0
    if context and context.area:
        context.area.tag_redraw()


# ── PROPERTY GROUPS ───────────────────────────────────────────────────────────

class F1_Lap_Item(bpy.types.PropertyGroup):
    """One entry in the lap queue (Lohith-style + pipeline compatibility)."""
    year:         IntProperty(name="Year",       default=2024)
    event:        StringProperty(name="Event",   default="Bahrain Grand Prix")
    session:      StringProperty(name="Session", default="R")  # R, Q, FP1, Day 1, etc.
    q_segment:    StringProperty(name="Q Seg",   default="")
    driver:       StringProperty(name="Driver",  default="VER")
    team:         StringProperty(name="Team",    default="Red Bull Racing")
    track_id:     StringProperty(name="Track ID", default="bahrain_grand_prix")
    fastest_lap:  BoolProperty(name="Fastest Lap", default=True)
    compound:     StringProperty(name="Compound", default="UNKNOWN")
    # Pipeline compatibility
    is_testing:   BoolProperty(name="Is Testing", default=False)
    test_number:  IntProperty(name="Test Number", default=1)
    test_session: IntProperty(name="Test Session", default=1)


class F1_Pipeline_Props(bpy.types.PropertyGroup):
    """All UI selection properties (Lohith-style Query Engine)."""

    sel_year: EnumProperty(
        name="Season",
        items=_year_items,
        update=_on_year_changed,
    )

    sel_race: EnumProperty(
        name="Race / Event",
        items=_race_items,
        update=_on_race_changed,
    )

    sel_session: EnumProperty(
        name="Session",
        items=_session_items,
        update=_on_session_changed,
    )

    sel_q_segment: EnumProperty(
        name="Q Segment",
        items=_q_segment_items,
        update=_on_q_segment_changed,
    )

    sel_driver: EnumProperty(
        name="Driver",
        items=_driver_items,
    )

    fastest_lap: BoolProperty(
        name="Fastest Lap (auto)",
        description="Always use the fastest lap from the selected session",
        default=True,
    )

    locked_track: StringProperty(name="Locked Track", default="")
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
    trail_z_offset: FloatProperty(
        name="Trail Height",
        description="Height above track for trail ribbon (snap-to-track + this value)",
        default=0.2,
        unit='LENGTH',
        update=lambda self, ctx: _on_trail_z_offset_changed(ctx),
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
    """Move/rotate/scale all F1 path curves and their trails when alignment sliders change."""
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

    # Sync trails so they match path transform
    try:
        from ..operators.f1_trail import sync_all_trails_from_paths
        sync_all_trails_from_paths(scene)
    except Exception:
        pass


def _on_trail_z_offset_changed(context):
    """When trail height slider changes, re-sync trails with new offset."""
    try:
        from ..operators.f1_trail import sync_all_trails_from_paths
        sync_all_trails_from_paths(context.scene)
    except Exception:
        pass


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
