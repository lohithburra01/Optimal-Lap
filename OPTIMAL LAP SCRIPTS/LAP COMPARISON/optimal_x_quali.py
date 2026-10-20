"""OPTIMAL x QUALI - one script: real laps -> lap-comparison video on the optimal-lap road.

Edit the SETTINGS block below (or pass the same things on the command line) and run:
    python optimal_x_quali.py
    python optimal_x_quali.py --track "Singapore" --year 2026 --session SQ --drivers TOP2
    python optimal_x_quali.py --track "Singapore" --year 2026 --session SQ --drivers VER,RUS
    python optimal_x_quali.py --track "Singapore" --drivers "VER 2026 SQ,RUS 2025 Q"     (cross-session)

No dropdowns, no driver database: the track is any name FastF1 understands, the drivers are TOP2 (fastest two
of the session) or any two codes you type. Timing = hifi_delta_v2.py (exact F1InsightsHub delta port, FastF1 car data).
Road + lines = the optimal-lap run for the track (F1_Pipeline_Assets/tracks/<track>_lapcomp.json, optimal_lines.py).
The faster lap is P1/reference. Each driver gets his own optimiser line (character_lines.per_driver_lines: same
optimiser as the optimal lap, CdA/CL/margin changed very slightly, cornering car from the data). First run per
track+driver pair: two optimiser runs, 4 workers, low priority, ~10 min each; afterwards cached = instant.
"""
# ==========================================================================================
# SETTINGS
# ==========================================================================================
TRACK = "Singapore Grand Prix"   # any FastF1 event name: "Singapore", "Monza", "British Grand Prix", ...
YEAR = 2026
SESSION = "SQ"                   # Q, SQ, R, S, FP1, FP2, FP3
DRIVERS = "TOP2"                 # "TOP2"  or  "VER,RUS"  or  "VER 2026 SQ,HAM 2019 Q" (year/session per driver)
ZOOM = 40.0
TRAIL_FRAMES = 60
FPS = 30
OUT = None                       # None = auto name in this folder
# ==========================================================================================

import argparse, colorsys, math, os, subprocess, sys, json
import numpy as np
import pandas as pd
import cv2
from PIL import Image, ImageDraw
from scipy.interpolate import interp1d

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lap_compare_optimal as LCO          # delta engine adapter + LineRail
import optimal_lines as OL                 # road/line recipe + per-driver optimiser lines
RV = LCO.RV                                # raceline_video.py: road helpers, heatmap colours, fonts, layout

WIDTH, HEIGHT = RV.WIDTH, RV.HEIGHT
WHITE = (255, 255, 255)
HUE_SHIFT_DEG = 10.0     # P2's heatmap is the same ramp rotated by this much hue: subtle, but tellable
SWAP_FRAMES = 12         # left/right name exchange animation length
SWAP_HYST_M = 0.5        # the order only flips once the new leader is this far ahead (no flicker when level)
NAME_DX = 250            # driver names sit this far left/right of the centre counter
RING_SAT = 0.80          # car-dot border = team colour at 80 % saturation
DIM = 0.55               # opacity of the red/green metres line


# ------------------------------------------------------------------ data (notebook logic)
def load_session(year, track, session):
    import fastf1
    s = fastf1.get_session(int(year), track, session)
    s.load(telemetry=True, laps=True, weather=False, messages=False)
    return s


def clean_trace(session, driver):
    laps = session.laps.pick_drivers(driver) if hasattr(session.laps, "pick_drivers") else session.laps.pick_driver(driver)
    if laps.empty:
        raise SystemExit(f"No laps for {driver} in {session.event['EventName']} {session.name}")
    lap = laps.pick_fastest()
    tel = lap.get_telemetry().dropna(subset=['Distance', 'Speed', 'X', 'Y']).drop_duplicates(subset=['Time'])
    dist = tel['Distance'].values.astype(float); dist -= dist[0]
    t = tel['Time'].dt.total_seconds().values
    # official sector gates (distance in own telemetry, cumulative official time) - as the v2 notebook's get_trace
    sec = [lap[k].total_seconds() if pd.notna(lap[k]) else None for k in ('Sector1Time', 'Sector2Time')]
    gates = {}
    if sec[0] is not None:
        gates['S1'] = (float(np.interp(sec[0], t, dist)), sec[0])
        if sec[1] is not None:
            gates['S2'] = (float(np.interp(sec[0] + sec[1], t, dist)), sec[0] + sec[1])
    return {'dist': dist, 'speed': tel['Speed'].values / 3.6, 'time': t, 'f1ih': LCO.H.get_trace(session, driver, lap),
            'lap_time': lap['LapTime'].total_seconds(), 'driver': driver, 'gates': gates}


def top_n(session, n):
    seen = []
    for _, lap in session.laps.pick_quicklaps().sort_values(by='LapTime').iterrows():
        if lap['Driver'] not in seen: seen.append(lap['Driver'])
        if len(seen) == n: break
    return seen


def parse_drivers(spec, year, session):
    """'TOP2' | 'VER,RUS' | 'VER 2026 SQ,HAM 2019 Q' -> [(code, year, session)] or 'TOP2'."""
    if spec.strip().upper() in ("TOP2", "TOP 2", "AUTO"):
        return "TOP2"
    out = []
    for item in spec.split(","):
        p = item.split()
        if not p: continue
        out.append((p[0].upper(), int(p[1]) if len(p) > 1 else int(year), p[2].upper() if len(p) > 2 else session))
    if len(out) != 2:
        raise SystemExit(f"Need exactly 2 drivers (got {len(out)}): the duel layout is P1 vs P2.")
    return out


def load_traces(track, year, session, spec, log=print):
    sessions = {}

    def get(y, s):
        if (y, s) not in sessions:
            log(f"Loading {y} {track} {s} ...")
            sessions[(y, s)] = load_session(y, track, s)
        return sessions[(y, s)]

    picks = parse_drivers(spec, year, session)
    if picks == "TOP2":
        picks = [(d, int(year), session) for d in top_n(get(int(year), session), 2)]
        log(f"Top 2: {picks[0][0]}, {picks[1][0]}")
    same = len({(y, s) for _, y, s in picks}) == 1
    traces = []
    for d, y, s in picks:
        tr = clean_trace(get(y, s), d)
        tr['label'] = d if same else f"{d} '{str(y)[-2:]}"
        tr['year'], tr['session'] = y, s
        traces.append(tr)
        log(f"   {tr['label']}: {tr['lap_time']:.3f}s")
    traces.sort(key=lambda tr: tr['lap_time'])        # faster lap = P1 = reference
    if traces[0]['label'] == traces[1]['label']:
        traces[1]['label'] += "*"
    event = get(*picks[0][1:]).event['EventName']
    return traces, event, same


# ------------------------------------------------------------------ colours
def shifted_heat(t, deg):
    b, g, r = RV.speed_color_bgr(t)
    if deg == 0: return (b, g, r)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    r2, g2, b2 = colorsys.hls_to_rgb((h + deg / 360.0) % 1.0, l, s)
    return (int(b2 * 255), int(g2 * 255), int(r2 * 255))


# ------------------------------------------------------------------ render
def render(traces, outline_path, line_paths, out_path, title1, title2, zoom=30.0, trail_frames=60, fps=30,
           max_seconds=None, still=None, log=print):
    """still = list of frame numbers -> writes <out_path>_f<N>.png mockups instead of a video."""
    ref = traces[0]; uids = [tr['label'] for tr in traces]
    master_len = ref['dist'][-1]
    # ---- timing: the notebook's bake() mapping, unchanged ----
    tmap, dfun = {}, {}
    for tr in traces:
        if tr is ref:
            mapped = ref['time']; dfun[tr['label']] = lambda d: 0.0
        else:
            _, fd = LCO.calculate_hifi_delta(ref, tr)
            mapped = ref['time'] + fd
            dfun[tr['label']] = interp1d(ref['dist'], fd, fill_value="extrapolate")
            log(f"[delta] {tr['label']}: final {fd[-1]:+.3f}s")
        tmap[tr['label']] = np.maximum.accumulate(mapped)
    total_frames = int(max(t[-1] for t in tmap.values()) * fps)
    if max_seconds: total_frames = min(total_frames, int(max_seconds * fps))
    # each car's own speed vs ref-distance (for its heatmap)
    spd = {tr['label']: (tr['dist'] * master_len / tr['dist'].max(), tr['speed']) for tr in traces}
    vmin = min(float(tr['speed'].min()) for tr in traces); vspan = max(max(float(tr['speed'].max()) for tr in traces) - vmin, 1e-6)
    hue = {uids[0]: 0.0, uids[1]: HUE_SHIFT_DEG}

    # ---- road + one racing line per car ----
    o = json.load(open(outline_path, encoding="utf-8"))
    outer = RV.smooth_resample_loop(np.array(o["outer"], float), RV.N_VISUAL_POINTS, RV.VISUAL_SMOOTH_S)
    inner = RV.smooth_resample_loop(np.array(o["inner"], float), RV.N_VISUAL_POINTS, RV.VISUAL_SMOOTH_S)
    outer, inner = RV.align_loops(outer, inner)
    kerbs = RV.compute_kerb_polygons(outer, is_outer=True) + RV.compute_kerb_polygons(inner, is_outer=False)
    rails = {u: LCO.LineRail(json.load(open(line_paths[u], encoding="utf-8"))["raceline"]) for u in uids}

    all_pts = np.vstack([outer, inner])
    scale = (min(WIDTH, HEIGHT * 0.5) / max(np.ptp(all_pts[:, 0]), np.ptp(all_pts[:, 1]))) * zoom

    def w2s(P, cam):
        P = np.atleast_2d(P)
        return np.column_stack([WIDTH / 2 + (P[:, 0] - cam[0]) * scale,
                                HEIGHT * RV.CAMERA_Y_FRAC - (P[:, 1] - cam[1]) * scale]).astype(np.int32)

    # minimap: same place / 45 deg rotation as the optimal-lap video
    MAP, MX, MY = RV.MAP_SIZE, WIDTH - RV.MAP_SIZE - RV.MAP_X_RIGHT_INSET, RV.MAP_Y_TOP
    c, s_ = math.cos(math.radians(45)), math.sin(math.radians(45))
    ctr = (all_pts.max(0) + all_pts.min(0)) / 2
    rot = lambda P: np.column_stack([(P[:, 0] - ctr[0]) * c - (P[:, 1] - ctr[1]) * s_,
                                     (P[:, 0] - ctr[0]) * s_ + (P[:, 1] - ctr[1]) * c])
    R = rot(all_pts); rc = (R.max(0) + R.min(0)) / 2; mscale = MAP / max(np.ptp(R[:, 0]), np.ptp(R[:, 1])) * 0.95

    def w2map(P):
        Q = rot(np.atleast_2d(P))
        return np.column_stack([MX + MAP / 2 + (Q[:, 0] - rc[0]) * mscale, MY + MAP / 2 - (Q[:, 1] - rc[1]) * mscale]).astype(np.int32)

    map_outer, map_inner = w2map(outer), w2map(inner)
    ring = {tr['label']: team_ring(tr['driver']) for tr in traces}
    F = dict(title=RV.load_font(42, True), sub=RV.load_font(26, False), gap=RV.load_font(72, True),
             unit=RV.load_font(28, False), name=RV.load_font(34, True), pos=RV.load_font(22, False),
             label=RV.load_font(22, False), metres=RV.load_font(26, False),
             car=RV.load_font(20, True), wm=RV.load_font(24, True))

    trails = {u: [] for u in uids}
    order = list(uids)                 # order[0] = shown on the LEFT (P1)
    slot_x = {u: WIDTH / 2 + (-NAME_DX if i == 0 else NAME_DX) for i, u in enumerate(order)}
    swap_from, swap_f = dict(slot_x), -999
    vw = None if still else cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (WIDTH, HEIGHT))
    log(f"[render] {total_frames} frames -> {out_path}")
    for f in range(total_frames):
        t = f / fps
        dist = {u: float(np.interp(t, tmap[u], ref['dist'])) for u in uids}
        v = {u: float(np.interp(dist[u], *spd[u])) for u in uids}
        pos = {u: rails[u].at(dist[u] / master_len) for u in uids}
        cam = pos[ref['label']]

        # running order with hysteresis -> animated left/right exchange
        lead, chase = order
        if dist[chase] - dist[lead] > SWAP_HYST_M:
            swap_from = {u: _ease_x(slot_x, swap_from, u, f - swap_f) for u in uids}
            order = [chase, lead]; swap_f = f
            slot_x = {order[0]: WIDTH / 2 - NAME_DX, order[1]: WIDTH / 2 + NAME_DX}

        draw_order = sorted(uids, key=lambda u: dist[u])          # leader painted on top
        for u in draw_order:
            trails[u].append((pos[u].copy(), v[u]))
            if len(trails[u]) > trail_frames: trails[u].pop(0)
        if still and f not in still:
            if f > max(still): break
            continue

        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        os_, is_ = w2s(outer, cam), w2s(inner, cam)
        cv2.fillPoly(frame, [os_], RV.TRACK_FILL); cv2.fillPoly(frame, [is_], (0, 0, 0))
        for poly in kerbs:
            cv2.fillPoly(frame, [w2s(np.asarray(poly)[:, :2], cam)], RV.KERB_COLOR, lineType=cv2.LINE_AA)
        cv2.polylines(frame, [os_.reshape(-1, 1, 2)], True, RV.TRACK_EDGE, RV.EDGE_THICKNESS, cv2.LINE_AA)
        cv2.polylines(frame, [is_.reshape(-1, 1, 2)], True, RV.TRACK_EDGE, RV.EDGE_THICKNESS, cv2.LINE_AA)
        for u in uids:
            cv2.polylines(frame, [w2s(rails[u].pts, cam).reshape(-1, 1, 2)], True, RV.RACELINE_COLOR, 3, cv2.LINE_AA)

        for u in draw_order:                                      # speed-heatmap trail, as the optimal lap
            if len(trails[u]) > 1:
                S = w2s(np.array([p for p, _ in trails[u]]), cam)
                for k in range(len(S) - 1):
                    col = shifted_heat((0.5 * (trails[u][k][1] + trails[u][k + 1][1]) - vmin) / vspan, hue[u])
                    cv2.line(frame, tuple(map(int, S[k])), tuple(map(int, S[k + 1])), col, RV.TRAIL_THICKNESS, cv2.LINE_AA)

        cv2.fillPoly(frame, [map_outer], RV.TRACK_FILL); cv2.fillPoly(frame, [map_inner], (0, 0, 0))
        cv2.polylines(frame, [map_outer.reshape(-1, 1, 2)], True, (120, 120, 120), 2, cv2.LINE_AA)
        cv2.polylines(frame, [map_inner.reshape(-1, 1, 2)], True, (120, 120, 120), 2, cv2.LINE_AA)
        for u in draw_order:
            col = shifted_heat((v[u] - vmin) / vspan, hue[u])
            sx, sy = w2s(pos[u], cam)[0]; mx, my = w2map(pos[u])[0]
            cv2.circle(frame, (int(sx), int(sy)), RV.DOT_RADIUS, col, -1, cv2.LINE_AA)
            cv2.circle(frame, (int(sx), int(sy)), RV.DOT_RADIUS, WHITE, 4, cv2.LINE_AA)
            cv2.circle(frame, (int(mx), int(my)), 9, col, -1, cv2.LINE_AA)
            cv2.circle(frame, (int(mx), int(my)), 9, WHITE, 2, cv2.LINE_AA)

        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)); draw = ImageDraw.Draw(img)
        RV.draw_centered(draw, WIDTH // 2, RV.TITLE_Y_1, title1, F['title'], WHITE)
        RV.draw_centered(draw, WIDTH // 2, RV.TITLE_Y_2, title2, F['sub'], WHITE)
        for u in draw_order:                                      # name tag over each car
            sx, sy = w2s(pos[u], cam)[0]
            bb = draw.textbbox((0, 0), u, font=F['car']); tw, th = bb[2] - bb[0], bb[3] - bb[1]; ly = sy - 55
            draw.rectangle([sx - tw / 2 - 8, ly - th / 2 - 6, sx + tw / 2 + 8, ly + th / 2 + 6], fill=(0, 0, 0))
            RV.draw_centered(draw, sx, ly, u, F['car'], WHITE)

        # centre HUD, optimal-lap hierarchy: one hero number (the gap), everything else small and dimmed.
        # Sign = notebook convention, relative to the reference (faster-lap) car: + behind (red), - ahead (green).
        lead, chase = order
        tgt = uids[1]
        gap_s = float(dfun[tgt](dist[tgt]))
        gap_m = dist[ref['label']] - dist[tgt]
        sg = "+" if gap_m >= 0 else "-"
        cx, cy = WIDTH // 2, RV.SPEED_Y
        RV.draw_centered(draw, cx, cy - 66, "GAP", F['label'], (150, 150, 150))
        num = f"{sg}{abs(gap_s):.3f}"
        bn = draw.textbbox((0, 0), num, font=F['gap']); bu = draw.textbbox((0, 0), "s", font=F['unit'])
        nw, uw = bn[2] - bn[0], bu[2] - bu[0]; x0 = cx - (nw + 6 + uw) / 2
        draw.text((x0 - bn[0], cy - (bn[3] - bn[1]) / 2 - 4 - bn[1]), num, font=F['gap'], fill=WHITE)
        draw.text((x0 + nw + 6 - bu[0], cy + (bn[3] - bn[1]) / 2 - 4 - bu[3]), "s", font=F['unit'], fill=(200, 200, 200))
        mcol = np.array((230, 60, 60) if gap_m >= 0 else (60, 220, 100), float)
        RV.draw_centered(draw, cx, cy + RV.KMH_Y_OFFSET, f"{sg}{abs(gap_m):.0f} METERS", F['metres'],
                         tuple(int(c) for c in mcol * DIM))
        for i, u in enumerate(order):
            x = _ease_x(slot_x, swap_from, u, f - swap_f)
            RV.draw_centered(draw, x, cy - 20, f"P{i + 1}", F['pos'], (150, 150, 150))
            RV.draw_centered(draw, x, cy + 18, u, F['name'], (220, 220, 220))
        RV.draw_centered(draw, WIDTH // 2, RV.WATERMARK_Y, RV.WATERMARK_TEXT, F['wm'], WHITE)
        if still:
            png = f"{os.path.splitext(out_path)[0]}_f{f}.png"; img.save(png); log(f"[mockup] {png}")
            continue
        vw.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))
        if (f + 1) % 300 == 0: log(f"  frame {f + 1}/{total_frames}")
    if vw: vw.release()
    log(f"[render] saved -> {out_path}")


def team_ring(code):
    b, g, r = LCO.team_bgr(code)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    r, g, b = colorsys.hls_to_rgb(h, l, s * RING_SAT)
    return (int(b * 255), int(g * 255), int(r * 255))


def _ease_x(slot_x, swap_from, u, df):
    if df >= SWAP_FRAMES: return slot_x[u]
    a = max(0.0, df / SWAP_FRAMES); a = a * a * (3 - 2 * a)
    return swap_from[u] + (slot_x[u] - swap_from[u]) * a


SESSION_NAMES = {"Q": "QUALIFYING", "SQ": "SPRINT QUALIFYING", "R": "RACE", "S": "SPRINT",
                 "FP1": "PRACTICE 1", "FP2": "PRACTICE 2", "FP3": "PRACTICE 3"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default=TRACK); ap.add_argument("--year", type=int, default=YEAR)
    ap.add_argument("--session", default=SESSION); ap.add_argument("--drivers", default=DRIVERS)
    ap.add_argument("--zoom", type=float, default=ZOOM); ap.add_argument("--trail-frames", type=int, default=TRAIL_FRAMES)
    ap.add_argument("--fps", type=int, default=FPS); ap.add_argument("--out", default=OUT)
    ap.add_argument("--mockup", default=None, help="frame numbers, e.g. 600,2200: PNG stills, no video")
    ap.add_argument("--max-seconds", type=float, default=None, help="preview: render only the first N seconds")
    a = ap.parse_args()
    if len(sys.argv) == 1 and sys.stdin.isatty():      # double-click / plain run: ask, Enter keeps the default
        ask = lambda q, d: (input(f"{q} [{d}]: ").strip() or str(d))
        a.track = ask("Track", a.track); a.year = int(ask("Year", a.year)); a.session = ask("Session", a.session)
        a.drivers = ask("Drivers (TOP2 or e.g. VER,RUS)", a.drivers); a.zoom = float(ask("Zoom", a.zoom))
    session = a.session.upper()

    traces, event, same = load_traces(a.track, a.year, session, a.drivers)
    recipe = OL.load_recipe(event)
    print(f"Road + line from the optimal lap: {os.path.basename(recipe['raceline'])}")
    if recipe.get('optimiser'):
        import character_lines as CL     # each driver's OWN optimiser line (tiny setup change, cached per driver)
        line_paths = CL.per_driver_lines(recipe, traces)
    else:
        line_paths = {tr['label']: recipe['raceline'] for tr in traces}

    title1 = event.upper()
    title2 = (f"{traces[0]['year']} {SESSION_NAMES.get(traces[0]['session'], traces[0]['session'])}" if same
              else "CROSS-SESSION LAP COMPARISON")
    out = a.out or os.path.join(HERE, f"{OL.slug(event)}_{a.year}_{session.lower()}_"
                                      f"{traces[0]['label'].split()[0]}_vs_{traces[1]['label'].split()[0]}.mp4")
    render(traces, recipe['outline'], line_paths, out, title1, title2, zoom=a.zoom, trail_frames=a.trail_frames,
           fps=a.fps, max_seconds=a.max_seconds,
           still=[int(x) for x in a.mockup.split(',')] if a.mockup else None)
    if not a.max_seconds and not a.mockup:
        subprocess.run(f'explorer /select,"{out}"', shell=True)


if __name__ == "__main__":
    main()
