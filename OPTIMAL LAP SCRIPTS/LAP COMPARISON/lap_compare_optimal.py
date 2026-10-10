"""Lap comparison on the OPTIMAL-LAP track.

Timing = LAPCOMP.IPYNB, untouched: calculate_hifi_delta() is copied verbatim and the time mapping
(ref time + delta, np.maximum.accumulate, np.interp(t, time, ref_dist)) is the notebook's bake() loop.
Only the picture changes: the road is the optimal-lap road (outline + kerbs + white edges, drawn with
raceline_video.py's own helpers) and every car rides ITS OWN optimiser racing line, placed at the same lap
fraction the notebook uses (dist / master_len), measured along that line's arc length.

  python lap_compare_optimal.py --traces singapore_sq/sq_traces.npz --drivers VER,RUS
      --outline <outline.json> --lines VER=<rl.json>,RUS=<rl.json> --track "Singapore Grand Prix"
      --year 2026 --session SQ --zoom 28 --out <mp4>
"""
import argparse, json, os, sys
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
from scipy.interpolate import interp1d
from scipy.signal import correlate, medfilt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import raceline_video as RV   # road drawing helpers only (imported, never edited)


# ==========================================
# 1. HIGH-FIDELITY DELTA ENGINE (PURE MATH)  -- verbatim from LAPCOMP.IPYNB
# ==========================================
def calculate_hifi_delta(ref_trace, tgt_trace):
    master_len = ref_trace['dist'].max()
    scale = master_len / tgt_trace['dist'].max()
    tgt_dist_scaled = tgt_trace['dist'] * scale

    grid_len = 10000; window_size = 300; step_size = 50
    common_grid = np.linspace(0, master_len, grid_len)
    v_ref = np.interp(common_grid, ref_trace['dist'], ref_trace['speed'])
    v_tgt = np.interp(common_grid, tgt_dist_scaled, tgt_trace['speed'])

    shifts, positions = [], []
    for start_pos in range(0, int(master_len), step_size):
        end_pos = start_pos + window_size
        if end_pos > master_len: break
        i0 = int((start_pos / master_len) * grid_len)
        i1 = int((end_pos / master_len) * grid_len)
        corr = correlate(v_ref[i0:i1], v_tgt[i0:i1], mode='same')
        if len(corr) == 0: continue
        lag_idx = np.argmax(corr) - (len(corr) // 2)
        shift_m = lag_idx * (master_len / grid_len)
        if abs(shift_m) < 40:
            shifts.append(shift_m); positions.append(start_pos + window_size/2)

    if positions:
        if positions[0] > 0: positions.insert(0, 0); shifts.insert(0, shifts[0])
        if positions[-1] < master_len: positions.append(master_len); shifts.append(shifts[-1])
        positions, shifts = zip(*sorted(zip(positions, shifts)))
        shift_interp = interp1d(positions, shifts, kind='linear', fill_value="extrapolate")
        tgt_dist_warped = tgt_dist_scaled + shift_interp(tgt_dist_scaled)
    else:
        tgt_dist_warped = tgt_dist_scaled

    f_tgt_time = interp1d(tgt_dist_warped, tgt_trace['time'], fill_value="extrapolate")
    raw_delta = f_tgt_time(ref_trace['dist']) - ref_trace['time']
    delta_smooth = medfilt(raw_delta, kernel_size=15)
    delta_zeroed = delta_smooth - delta_smooth[0]

    actual_lap_diff = tgt_trace['lap_time'] - ref_trace['lap_time']
    residual_error = delta_zeroed[-1] - actual_lap_diff

    if abs(residual_error) > 1e-6:
        ramp = np.linspace(0, 1, len(delta_zeroed))
        final_delta = delta_zeroed - (ramp * residual_error)
    else:
        final_delta = delta_zeroed

    return ref_trace['dist'], final_delta


# ==========================================
# helpers (notebook look)
# ==========================================
DRIVER_COLOR_MAP = {'VER': '#3671C6', 'HAD': '#3671C6', 'LEC': '#E8002D', 'HAM': '#E8002D',
                    'NOR': '#FF8000', 'PIA': '#FF8000', 'RUS': '#27F4D2', 'ANT': '#27F4D2',
                    'ALO': '#229971', 'STR': '#229971', 'GAS': '#0090FF', 'COL': '#0090FF',
                    'ALB': '#005AFF', 'SAI': '#005AFF', 'LAW': '#C8D2F0', 'LIN': '#C8D2F0',
                    'OCO': '#B6BABD', 'BEA': '#B6BABD', 'HUL': '#C0003C', 'BOR': '#C0003C',
                    'BOT': '#A0A0A0', 'PER': '#A0A0A0'}


def team_bgr(code):
    h = DRIVER_COLOR_MAP.get(code, '#FFFFFF').lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)


def draw_centered(draw, x, y, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]; h = bbox[3] - bbox[1]
    draw.text((x - w/2, y - h/2 - 4), text, font=font, fill=fill)


def load_fonts():
    d = r"C:\Users\91910\Downloads\Formula1"
    B = os.path.join(d, "Formula1-Bold_web_0.ttf.ttf"); R = os.path.join(d, "Formula1-Regular_web_0.ttf.ttf")
    try:
        return dict(title=ImageFont.truetype(B, 42), sub=ImageFont.truetype(R, 26), lb_pos=ImageFont.truetype(B, 20),
                    lb_name=ImageFont.truetype(B, 30), lb_gap=ImageFont.truetype(R, 26),
                    car=ImageFont.truetype(B, 20), wm=ImageFont.truetype(B, 24))
    except Exception:
        f = ImageFont.load_default(); return dict.fromkeys(["title", "sub", "lb_pos", "lb_name", "lb_gap", "car", "wm"], f)


class LineRail:
    """A closed racing line; position at lap fraction p (0..1) by arc length."""
    def __init__(self, pts):
        self.pts = np.asarray(pts, float)
        seg = np.linalg.norm(np.roll(self.pts, -1, axis=0) - self.pts, axis=1)
        self.arc = np.concatenate([[0.0], np.cumsum(seg)])
        self.L = float(self.arc[-1])
        self.closed = np.vstack([self.pts, self.pts[:1]])

    def at(self, p):
        s = np.clip(p, 0.0, 1.0) * self.L
        return np.array([np.interp(s, self.arc, self.closed[:, 0]), np.interp(s, self.arc, self.closed[:, 1])])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", required=True); ap.add_argument("--drivers", required=True)
    ap.add_argument("--outline", required=True); ap.add_argument("--lines", required=True)
    ap.add_argument("--track", required=True); ap.add_argument("--year", default="2026")
    ap.add_argument("--session", default="SQ"); ap.add_argument("--zoom", type=float, default=28.0)
    ap.add_argument("--trail-frames", type=int, default=60); ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--max-seconds", type=float, default=None); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    drivers = a.drivers.split(",")
    Z = np.load(a.traces)
    traces = [{'dist': Z[d + "_dist"].astype(float), 'speed': Z[d + "_speed"].astype(float),
               'time': Z[d + "_time"].astype(float), 'lap_time': float(Z[d + "_lap_time"]), 'driver': d}
              for d in drivers]
    line_paths = dict(kv.split("=", 1) for kv in a.lines.split(","))
    render(traces, a.outline, line_paths, a.track, a.year, a.session, a.out, a.zoom, a.trail_frames, a.fps, a.max_seconds)


def render(traces, outline_path, line_paths, track, year, session, out_path, zoom=28.0, trail_frames=60, fps=30,
           max_seconds=None, title1=None, title2=None, log=print):
    """traces: list of notebook-style traces (dist/speed/time/lap_time/driver), traces[0] = reference.
    line_paths: {label: raceline json in the outline's frame}; label = tr.get('label', driver)."""
    for tr in traces: tr['uid'] = tr.get('label', tr['driver'])
    drivers = [tr['uid'] for tr in traces]
    ref_trace = traces[0]; ref_uid = ref_trace['uid']
    # ---- timing: the notebook's bake() mapping, unchanged ----
    master_len = ref_trace['dist'][-1]
    time_mappings, delta_functions = {}, {}
    for tr in traces:
        if tr is ref_trace:
            mapped_time = ref_trace['time']
            delta_functions[tr['uid']] = lambda d: 0.0
        else:
            _, final_delta = calculate_hifi_delta(ref_trace, tr)
            mapped_time = ref_trace['time'] + final_delta
            delta_functions[tr['uid']] = interp1d(ref_trace['dist'], final_delta, fill_value="extrapolate")
            log(f"[delta] {tr['uid']}: final {final_delta[-1]:+.3f}s  range [{final_delta.min():+.3f}, {final_delta.max():+.3f}]")
        time_mappings[tr['uid']] = np.maximum.accumulate(mapped_time)
    max_time = max(t[-1] for t in time_mappings.values())
    total_frames = int(max_time * fps)
    if max_seconds: total_frames = min(total_frames, int(max_seconds * fps))

    # ---- picture: optimal-lap road + one racing line per car ----
    o = json.load(open(outline_path, encoding="utf-8"))
    outer = RV.smooth_resample_loop(np.array(o["outer"], float), RV.N_VISUAL_POINTS, RV.VISUAL_SMOOTH_S)
    inner = RV.smooth_resample_loop(np.array(o["inner"], float), RV.N_VISUAL_POINTS, RV.VISUAL_SMOOTH_S)
    outer, inner = RV.align_loops(outer, inner)
    outer_kerbs = RV.compute_kerb_polygons(outer, is_outer=True)
    inner_kerbs = RV.compute_kerb_polygons(inner, is_outer=False)
    rails = {d: LineRail(json.load(open(line_paths[d], encoding="utf-8"))["raceline"]) for d in drivers}
    for d in drivers: log(f"[line] {d}: {rails[d].L:.1f} m")

    WIDTH, HEIGHT = 1080, 1920
    all_pts = np.vstack([outer, inner])
    track_w = np.ptp(all_pts[:, 0]); track_h = np.ptp(all_pts[:, 1])
    scale = (min(WIDTH, HEIGHT * 0.5) / max(track_w, track_h)) * zoom
    cxy = np.array([(all_pts[:, 0].max() + all_pts[:, 0].min()) / 2, (all_pts[:, 1].max() + all_pts[:, 1].min()) / 2])

    def w2s(P, cam):
        P = np.atleast_2d(P)
        return np.column_stack([WIDTH/2 + (P[:, 0] - cam[0]) * scale, HEIGHT*0.4 - (P[:, 1] - cam[1]) * scale]).astype(np.int32)

    MAP_SIZE = 280; MAP_X = WIDTH - MAP_SIZE - 60
    lb_y_start = 1350 - (len(traces) * 70); MAP_Y = 1350 - MAP_SIZE
    map_scale = MAP_SIZE / max(track_w, track_h) * 0.95

    def w2map(P):
        P = np.atleast_2d(P) - cxy
        return np.column_stack([MAP_X + MAP_SIZE/2 + P[:, 0] * map_scale, MAP_Y + MAP_SIZE/2 - P[:, 1] * map_scale]).astype(np.int32)

    map_outer, map_inner = w2map(outer), w2map(inner)
    F = load_fonts()
    title_line1 = title1 or f"{track.upper()} - {year}"
    title_line2 = title2 or f"TOP {len(traces)} - {session.upper()} LAP COMPARISON"
    vec_arrays = {tr['uid']: (time_mappings[tr['uid']], ref_trace['dist']) for tr in traces}
    trails = {tr['uid']: [] for tr in traces}
    car_radius = 30

    out = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (WIDTH, HEIGHT))
    log(f"[render] {total_frames} frames -> {out_path}")
    for f in range(total_frames):
        t = f / fps
        current_distances = {}
        for tr in traces:
            t_arr, d_arr = vec_arrays[tr['uid']]
            current_distances[tr['uid']] = np.interp(t, t_arr, d_arr)
        ref_dist = current_distances[ref_uid]
        pos = {tr['uid']: rails[tr['uid']].at(current_distances[tr['uid']] / master_len) for tr in traces}
        cam = pos[ref_uid]

        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        os_, is_ = w2s(outer, cam), w2s(inner, cam)
        cv2.fillPoly(frame, [os_], RV.TRACK_FILL); cv2.fillPoly(frame, [is_], (0, 0, 0))
        for polys in (outer_kerbs, inner_kerbs):
            for poly in polys:
                cv2.fillPoly(frame, [w2s(np.asarray(poly)[:, :2], cam)], RV.KERB_COLOR, lineType=cv2.LINE_AA)
        cv2.polylines(frame, [os_.reshape(-1, 1, 2)], True, RV.TRACK_EDGE, RV.EDGE_THICKNESS, cv2.LINE_AA)
        cv2.polylines(frame, [is_.reshape(-1, 1, 2)], True, RV.TRACK_EDGE, RV.EDGE_THICKNESS, cv2.LINE_AA)
        for d in drivers:   # each car's own racing line, subtle grey like the optimal-lap video
            cv2.polylines(frame, [w2s(rails[d].pts, cam).reshape(-1, 1, 2)], True, RV.RACELINE_COLOR, 3, cv2.LINE_AA)

        draw_order = sorted(traces, key=lambda tr: current_distances[tr['uid']])
        for tr in draw_order:
            uid = tr['uid']
            trails[uid].append(pos[uid].copy())
            if len(trails[uid]) > trail_frames: trails[uid].pop(0)
            if len(trails[uid]) > 1:
                cv2.polylines(frame, [w2s(np.array(trails[uid]), cam).reshape(-1, 1, 2)], False,
                              team_bgr(tr['driver']), thickness=18, lineType=cv2.LINE_AA)

        cv2.fillPoly(frame, [map_outer], RV.TRACK_FILL); cv2.fillPoly(frame, [map_inner], (0, 0, 0))
        cv2.polylines(frame, [map_outer.reshape(-1, 1, 2)], True, (120, 120, 120), 2, cv2.LINE_AA)
        cv2.polylines(frame, [map_inner.reshape(-1, 1, 2)], True, (120, 120, 120), 2, cv2.LINE_AA)
        for tr in draw_order:
            c = team_bgr(tr['driver'])
            sx, sy = w2s(pos[tr['uid']], cam)[0]; mx, my = w2map(pos[tr['uid']])[0]
            cv2.circle(frame, (int(sx), int(sy)), car_radius, c, -1, cv2.LINE_AA)
            cv2.circle(frame, (int(sx), int(sy)), car_radius, (255, 255, 255), 4, cv2.LINE_AA)
            cv2.circle(frame, (int(mx), int(my)), 8, c, -1, cv2.LINE_AA)
            cv2.circle(frame, (int(mx), int(my)), 8, (255, 255, 255), 2, cv2.LINE_AA)

        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)); draw = ImageDraw.Draw(img)
        draw_centered(draw, WIDTH//2, 250, title_line1, F['title'], (255, 255, 255))
        draw_centered(draw, WIDTH//2, 300, title_line2, F['sub'], (200, 200, 200))
        for tr in draw_order:
            sx, sy = w2s(pos[tr['uid']], cam)[0]; name = tr['uid']
            bb = draw.textbbox((0, 0), name, font=F['car']); tw = bb[2] - bb[0]; th = bb[3] - bb[1]
            ly = sy - 55
            draw.rectangle([sx - tw/2 - 8, ly - th/2 - 6, sx + tw/2 + 8, ly + th/2 + 6], fill=(0, 0, 0))
            draw_centered(draw, sx, ly, name, F['car'], (255, 255, 255))

        # leaderboard: notebook logic unchanged (gap in m from distances, gap in s from the delta engine)
        for i, tr in enumerate(sorted(traces, key=lambda tr: current_distances[tr['uid']], reverse=True)):
            uid = tr['uid']; dist = current_distances[uid]
            c = team_bgr(tr['driver']); rgb = (c[2], c[1], c[0])
            cy = lb_y_start + i * 70 + 15
            dist_to_ref = abs(dist - ref_dist)
            if uid == ref_uid:
                gap_text = "LEADER"; gcol = (150, 150, 150)
            else:
                sign = "+" if dist < ref_dist else "-"
                time_gap = delta_functions[uid](dist)
                gap_text = f"{sign}{dist_to_ref:.0f}m ({sign}{abs(time_gap):.3f}s)"
                gcol = (230, 50, 50) if dist < ref_dist else (50, 230, 50)
            draw.ellipse([80-18, cy-18, 80+18, cy+18], fill=rgb)
            draw_centered(draw, 80, cy, f"P{i+1}", F['lb_pos'], (255, 255, 255))
            draw.text((120, cy - 18), tr['uid'], font=F['lb_name'], fill=rgb)
            name_w = draw.textbbox((0, 0), tr['uid'], font=F['lb_name'])[2]
            draw.text((120 + name_w + 35, cy - 14), gap_text, font=F['lb_gap'], fill=gcol)

        draw_centered(draw, WIDTH//2, 1450, "@formulytics", F['wm'], (150, 150, 150))
        out.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))
        if (f + 1) % 300 == 0: log(f"  frame {f+1}/{total_frames}")
    out.release()
    log(f"[render] saved -> {out_path}")


if __name__ == "__main__":
    main()
