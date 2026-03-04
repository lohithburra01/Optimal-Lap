import bpy
import json
import os
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty, CollectionProperty, PointerProperty

# ── DATABASE LOADER ────────────────────────────────────────────────────────────

_CALENDAR        = {}
_DRV_BY_RACE     = {}
_DRV_BY_SEASON   = {}
_SESSION_MAP     = {}

def _get_db_root():
    # Try blend file location first
    try:
        blend_path = bpy.data.filepath
        if blend_path:
            db = os.path.join(os.path.dirname(blend_path), "F1_Pipeline_Assets", "database")
            if os.path.exists(db):
                return db
    except Exception:
        pass
    # Fallback — won't work for most users, but prevents crash
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(this_dir, "..", "..", "..", "F1_Pipeline_Assets", "database")

def load_databases():
    global _CALENDAR, _DRV_BY_RACE, _DRV_BY_SEASON, _SESSION_MAP
    db_dir = _get_db_root()
    try:
        if os.path.exists(os.path.join(db_dir, "calendar_cache.json")):
            with open(os.path.join(db_dir, "calendar_cache.json"),    encoding='utf-8') as f:
                _CALENDAR = json.load(f)
            with open(os.path.join(db_dir, "drivers_by_race.json"),   encoding='utf-8') as f:
                _DRV_BY_RACE = json.load(f)
            with open(os.path.join(db_dir, "drivers_by_season.json"), encoding='utf-8') as f:
                _DRV_BY_SEASON = json.load(f)
            esm_path = os.path.join(db_dir, "event_session_map.json")
            if os.path.exists(esm_path):
                with open(esm_path, encoding='utf-8') as f:
                    _SESSION_MAP = json.load(f)
            print(f"[F1 Studio] Databases loaded. Years: {sorted(_CALENDAR.keys())}")
        else:
            print(f"[F1 Studio] Database not found in: {db_dir}")
    except Exception as e:
        print(f"[F1 Studio] WARNING – Could not load databases: {e}")


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _get_event(year_str, race_name):
    """Return the calendar entry dict for a given year + event name."""
    for e in _CALENDAR.get(year_str, []):
        if e['event_name'] == race_name:
            return e
    return None

def _get_drivers_for_session(year_str, race_name, session_key, q_segment=None):
    """
    Return driver list for a specific session.
    Handles both old flat-list format and new per-session dict format.
    Falls back to drivers_by_season if nothing found.
    """
    event_data = _DRV_BY_RACE.get(year_str, {}).get(race_name)

    if event_data is None:
        # Not in drivers_by_race at all — use season list
        return _DRV_BY_SEASON.get(year_str, [])

    # ── NEW FORMAT: dict per session ──────────────────────────────────────────
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

    # ── OLD FORMAT: flat list ─────────────────────────────────────────────────
    if isinstance(event_data, list):
        if session_key == 'Q' and q_segment == 'Q3':
            return event_data[:10]
        if session_key == 'Q' and q_segment == 'Q2':
            return event_data[:15]
        return event_data

    return _DRV_BY_SEASON.get(year_str, [])


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
    items = []
    for e in events:
        rnd = e['round']
        etype = e.get('event_type', 'race')
        if etype == 'testing':
            label = e['event_name']
            desc  = f"Pre-Season  |  {e.get('location','')}  {e.get('country','')}"
        else:
            label = e['event_name']
            desc  = f"Round {rnd}  |  {e.get('location','')}  {e.get('country','')}"
        items.append((e['event_name'], label, desc))
    return items


def _session_items(self, context):
    year  = self.sel_year
    race  = self.sel_race
    event = _get_event(year, race)
    if not event:
        return [('R', 'Race', '')]

    etype      = event.get('event_type', 'race')
    has_sprint = event.get('has_sprint', False)
    sess_map   = _SESSION_MAP.get(etype, {})
    display    = sess_map.get('display', {})

    if etype == 'testing':
        return [
            ('Day 1', 'Day 1', ''),
            ('Day 2', 'Day 2', ''),
            ('Day 3', 'Day 3', ''),
            ('Day Best', '★ Best Across Days', ''),
        ]

    if has_sprint:
        sessions = ['FP1', 'SQ', 'Sprint', 'Q', 'R']
    else:
        sessions = ['FP1', 'FP2', 'FP3', 'Q', 'R']

    return [(s, display.get(s, s), '') for s in sessions]


def _q_segment_items(self, context):
    return [
        ('Q_ALL', '★ Best Q (Fastest)',  'Fastest lap across all Q segments'),
        ('Q1',    'Q1',                  'Qualifying segment 1 — all 20 drivers'),
        ('Q2',    'Q2',                  'Qualifying segment 2 — top 15'),
        ('Q3',    'Q3',                  'Qualifying segment 3 — top 10'),
    ]


def _get_driver_context_key(props):
    """Cache-buster: encodes the current selection context.
    Blender re-calls _driver_items when _driver_context changes."""
    seg = props.sel_q_segment if props.sel_session == 'Q' else ''
    return f"{props.sel_year}|{props.sel_race}|{props.sel_session}|{seg}"


def _driver_items(self, context):
    year    = self.sel_year
    race    = self.sel_race
    session = self.sel_session
    q_seg   = self.sel_q_segment if session == 'Q' else None

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

    result = []
    for d in drivers:
        if not isinstance(d, dict):
            continue
        code = d.get('code', '')
        if not code:
            continue
        result.append((
            code,
            f"{d.get('full_name', code)}  [{d.get('team_raw', '')}]",
            f"#{d.get('number', '')}  {code}"
        ))

    return result if result else [('NONE', 'No drivers – check database', '')]


# ── UPDATE CALLBACKS ──────────────────────────────────────────────────────────

def _on_year_changed(self, context):
    # If track is locked, keep the same race selected across year change
    if context and hasattr(context, 'scene'):
        try:
            props = context.scene.f1_pipeline_props
            if props.locked_track:
                items = _race_items(self, context)
                for i, (val, label, desc) in enumerate(items):
                    if val == props.locked_track:
                        self['sel_race'] = i
                        self['sel_session'] = 0
                        self['sel_q_segment'] = 0
                        self['sel_driver'] = 0
                        self.driver_context_key = _get_driver_context_key(self)
                        return
                # Locked track not available in this year — just reset
        except Exception:
            pass

    # No lock — default to first race event (skip testing)
    items = _race_items(self, context)
    for i, (val, label, desc) in enumerate(items):
        event = _get_event(self.sel_year, val)
        if event and event.get('event_type') != 'testing':
            self['sel_race'] = i
            break
    self['sel_session'] = 0
    self['sel_q_segment'] = 0
    self['sel_driver'] = 0
    self.driver_context_key = _get_driver_context_key(self)

def _on_race_changed(self, context):
    self['sel_session'] = 0
    self['sel_q_segment'] = 0
    self['sel_driver'] = 0
    self.driver_context_key = _get_driver_context_key(self)

def _on_session_changed(self, context):
    self['sel_q_segment'] = 0
    self['sel_driver'] = 0
    self.driver_context_key = _get_driver_context_key(self)

def _on_q_segment_changed(self, context):
    self['sel_driver'] = 0
    self.driver_context_key = _get_driver_context_key(self)
    if context and context.area:
        context.area.tag_redraw()


# ── PROPERTY GROUPS ───────────────────────────────────────────────────────────

class F1_Lap_Item(bpy.types.PropertyGroup):
    """One entry in the lap queue."""
    year:       IntProperty(name="Year",       default=2024)
    event:      StringProperty(name="Event",   default="Bahrain Grand Prix")
    session:    StringProperty(name="Session", default="R")
    q_segment:  StringProperty(name="Q Seg",   default="")
    driver:     StringProperty(name="Driver",  default="VER")
    team:       StringProperty(name="Team",    default="Unknown")
    track_id:   StringProperty(name="Track ID",default="bahrain")
    fastest_lap: BoolProperty(name="Fastest Lap", default=True)
    compound:    StringProperty(name="Compound",   default="UNKNOWN")


class F1_Pipeline_Props(bpy.types.PropertyGroup):
    """All UI selection properties for the F1 Studio panel."""

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

    # Cache-buster — changing this forces Blender to re-evaluate sel_driver items
    driver_context_key: StringProperty(default="")

    sel_driver: EnumProperty(
        name="Driver",
        items=_driver_items,
    )

    fastest_lap: BoolProperty(
        name="Fastest Lap (auto)",
        description="Always use the fastest lap from the selected session",
        default=True,
    )

    # Track lock — set after first lap is added, cleared when queue is cleared
    locked_track: StringProperty(
        name="Locked Track",
        default="",
    )
    locked_track_key: StringProperty(
        name="Locked Track Key",
        default="",
    )

    status_msg: StringProperty(name="Status", default="Ready")


# ── REGISTRATION ──────────────────────────────────────────────────────────────

classes = [F1_Lap_Item, F1_Pipeline_Props]

@bpy.app.handlers.persistent
def _load_post_handler(dummy):
    load_databases()

def register():
    load_databases()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.f1_pipeline_props = PointerProperty(type=F1_Pipeline_Props)
    bpy.types.Scene.f1_lap_queue      = CollectionProperty(type=F1_Lap_Item)
    bpy.app.handlers.load_post.append(_load_post_handler)

def unregister():
    if _load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post_handler)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.f1_pipeline_props
    del bpy.types.Scene.f1_lap_queue
