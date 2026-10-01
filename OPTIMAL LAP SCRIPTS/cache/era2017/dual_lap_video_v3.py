"""Two simulated laps on one map, same clock - v3 'signature' style (user spec 2026-10-01).

vs dual_lap_video.py (kept unchanged for the earlier videos):
  * FIXED zoom (default 19), camera locked on car B (the 2026 car) exactly like the single-car
    optimal-lap video (car at screen x=W/2, y=CAMERA_Y_FRAC*H). No dynamic zoom.
  * speed-heatmap trail + dot (raceline_video.speed_color_bgr) on BOTH cars, one shared speed scale;
    car A (2017) is a dulled version of the same heatmap.
  * draw order: leader's trail -> trailing car's trail at 70 % opacity -> leader dot -> trailing dot,
    so the car behind is never hidden under the leader's trail.
  * minimap moved to the empty band under the HUD and drawn BELOW the cars.
  * no stopwatch: each car shows its lap time. All text white except mode labels
    (DEPLOY / BRAKING / SUPERCLIP own colours, DRS green). No telemetry graph.
"""
import argparse, json, math, os, sys
import numpy as np, cv2
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import raceline_video as RV
from dual_lap_video import Car, MODE_TXT, fmt_lap

W, H = RV.WIDTH, RV.HEIGHT
CAM_Y = int(H * RV.CAMERA_Y_FRAC)
MAP_X, MAP_Y = W - RV.MAP_SIZE - RV.MAP_X_RIGHT_INSET, 1360       # below the HUD, above the platform-UI band
TRAIL_ALPHA = 0.70
TAG_ALPHA = 155            # ~60 % white: readable but subtle
WHITE = (255, 255, 255)
MODE_COL = dict(RV.MODE_COLORS, DRS=(40, 230, 90))


def dull(c):
    """Dulled heatmap colour for the 2017 car: half-desaturated and darkened."""
    b, g, r = c; l = 0.114 * b + 0.587 * g + 0.299 * r
    return tuple(int(0.8 * (0.45 * x + 0.55 * l)) for x in (b, g, r))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outline", required=True)
    ap.add_argument("--a-csv", required=True); ap.add_argument("--a-raceline", required=True)
    ap.add_argument("--a-label", default="2017 CAR"); ap.add_argument("--a-lap", type=float, default=None)
    ap.add_argument("--b-csv", required=True); ap.add_argument("--b-raceline", required=True)
    ap.add_argument("--b-label", default="2026 CAR"); ap.add_argument("--b-lap", type=float, default=None)
    ap.add_argument("--title", default="2017 vs 2026"); ap.add_argument("--track-name", default="Sepang")
    ap.add_argument("--zoom", type=float, default=19.0); ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--a-tag", default="2017"); ap.add_argument("--b-tag", default="2026")
    ap.add_argument("--tag-size", type=int, default=22, help="year tag beside each dot (px)")
    ap.add_argument("--hold-s", type=float, default=2.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default=None, help="debug: comma list of frame indices to PNG")
    a = ap.parse_args()

    data = json.load(open(a.outline, encoding="utf-8"))
    outer = RV.smooth_resample_loop(np.array(data["outer"], float), RV.N_VISUAL_POINTS, RV.VISUAL_SMOOTH_S)
    inner = RV.smooth_resample_loop(np.array(data["inner"], float), RV.N_VISUAL_POINTS, RV.VISUAL_SMOOTH_S)
    outer, inner = RV.align_loops(outer, inner)
    ok = RV.compute_kerb_polygons(outer, is_outer=True); ik = RV.compute_kerb_polygons(inner, is_outer=False)

    A = Car(a.a_csv, a.a_raceline, a.a_label, None); B = Car(a.b_csv, a.b_raceline, a.b_label, None)
    A.show = a.a_lap or A.lap; B.show = a.b_lap or B.lap
    A.dull, B.dull = True, False
    n_frames = int(math.ceil((max(A.lap, B.lap) + a.hold_s) * a.fps))
    v_lo = min(A.v.min(), B.v.min()); v_span = max(max(A.v.max(), B.v.max()) - v_lo, 1e-6)
    def col(car, v):
        c = RV.speed_color_bgr((v - v_lo) / v_span)
        return dull(c) if car.dull else c

    allp = np.vstack([outer, inner])
    scale = (min(W, H * 0.5) / max(np.ptp(allp[:, 0]), np.ptp(allp[:, 1]))) * a.zoom   # fixed, as raceline_video
    # minimap (same 45 deg rotation as the single-car video)
    rot = math.radians(45.0); c_, s_ = math.cos(rot), math.sin(rot)
    mcx, mcy = (allp[:, 0].max() + allp[:, 0].min()) / 2, (allp[:, 1].max() + allp[:, 1].min()) / 2
    def mrot(p):
        dx, dy = p[0] - mcx, p[1] - mcy
        return dx * c_ - dy * s_, dx * s_ + dy * c_
    R_all = np.array([mrot(p) for p in allp])
    rcx, rcy = (R_all[:, 0].max() + R_all[:, 0].min()) / 2, (R_all[:, 1].max() + R_all[:, 1].min()) / 2
    msc = RV.MAP_SIZE / max(np.ptp(R_all[:, 0]), np.ptp(R_all[:, 1])) * 0.95
    def w2map(p):
        rx, ry = mrot(p)
        return int(MAP_X + RV.MAP_SIZE / 2 + (rx - rcx) * msc), int(MAP_Y + RV.MAP_SIZE / 2 - (ry - rcy) * msc)
    map_o = np.array([w2map(p) for p in outer], np.int32); map_i = np.array([w2map(p) for p in inner], np.int32)

    f_title = RV.load_font(42, True); f_sub = RV.load_font(26, False); f_spd = RV.load_font(64, True)
    f_unit = RV.load_font(24, False); f_lab = RV.load_font(26, True); f_wm = RV.load_font(24, True)
    f_small = RV.load_font(20, False); f_gap = RV.load_font(34, True); f_tag = RV.load_font(a.tag_size, True)
    A.tag, B.tag = a.a_tag, a.b_tag

    dbg = set(int(x) for x in a.frames.split(",")) if a.frames else None
    vw = None if dbg else cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"), a.fps, (W, H))
    for car in (A, B): car.trail = []
    for fr in range(n_frames):
        t = fr / a.fps
        fa, va, ma = A.state(t); fb, vb, mb = B.state(t)
        pa, pb = A.pos(fa), B.pos(fb)
        for car, p, v in ((A, pa, va), (B, pb, vb)):
            car.trail.append((float(p[0]), float(p[1]), v)); car.trail = car.trail[-RV.DEFAULT_TRAIL:]
        if dbg is not None and fr not in dbg:
            if fr > max(dbg): break
            continue
        cam = pb                                            # follow the 2026 car, fixed zoom
        def w2s(p):
            return int(W / 2 + (p[0] - cam[0]) * scale), int(CAM_Y - (p[1] - cam[1]) * scale)
        img = np.zeros((H, W, 3), np.uint8)
        os_ = np.array([w2s(p) for p in outer], np.int32); is_ = np.array([w2s(p) for p in inner], np.int32)
        cv2.fillPoly(img, [os_], RV.TRACK_FILL); cv2.fillPoly(img, [is_], (0, 0, 0))
        for polys in (ok, ik):
            for poly in polys:
                cv2.fillPoly(img, [np.array([w2s(p) for p in poly], np.int32)], RV.KERB_COLOR, cv2.LINE_AA)
        cv2.polylines(img, [os_], True, RV.TRACK_EDGE, RV.EDGE_THICKNESS, cv2.LINE_AA)
        cv2.polylines(img, [is_], True, RV.TRACK_EDGE, RV.EDGE_THICKNESS, cv2.LINE_AA)
        # both ideal lines, subtle grey (2017 a shade darker)
        for car, g in ((B, RV.RACELINE_COLOR), (A, (60, 60, 60))):
            cv2.polylines(img, [np.array([w2s(p) for p in car.rl], np.int32)], True, g, 3, cv2.LINE_AA)
        # minimap UNDER the cars
        cv2.fillPoly(img, [map_o], RV.TRACK_FILL); cv2.fillPoly(img, [map_i], (0, 0, 0))
        cv2.polylines(img, [map_o], True, (120, 120, 120), 2, cv2.LINE_AA)
        cv2.polylines(img, [map_i], True, (120, 120, 120), 2, cv2.LINE_AA)
        for car, p, v in ((A, pa, va), (B, pb, vb)):
            m = w2map(p); cv2.circle(img, m, 9, col(car, v), -1, cv2.LINE_AA); cv2.circle(img, m, 9, WHITE, 2, cv2.LINE_AA)
        # leader = further round the lap; trailing car's trail on top at 70 % opacity, then dots
        lead, trail_car = (A, B) if fa >= fb else (B, A)
        def draw_trail(dst, car):
            tr = car.trail
            for k in range(len(tr) - 1):
                cv2.line(dst, w2s(tr[k]), w2s(tr[k + 1]), col(car, 0.5 * (tr[k][2] + tr[k + 1][2])),
                         RV.TRAIL_THICKNESS, cv2.LINE_AA)
        draw_trail(img, lead)
        ov = img.copy(); draw_trail(ov, trail_car)
        img = cv2.addWeighted(ov, TRAIL_ALPHA, img, 1.0 - TRAIL_ALPHA, 0)
        dots = {}
        for car, p, v in ((lead, *(((pa, va) if lead is A else (pb, vb)))), (trail_car, *(((pa, va) if trail_car is A else (pb, vb))))):
            x, y = w2s(p); dots[car.tag] = (x, y)
            cv2.circle(img, (x, y), RV.DOT_RADIUS, col(car, v), -1, cv2.LINE_AA)
            cv2.circle(img, (x, y), RV.DOT_RADIUS, WHITE, 4, cv2.LINE_AA)

        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)); dr = ImageDraw.Draw(pil)
        # subtle year tag beside each dot (small, ~60 % white)
        tag_layer = Image.new("RGBA", pil.size, (0, 0, 0, 0)); td = ImageDraw.Draw(tag_layer)
        for tag, (x, y) in dots.items():
            td.text((x + RV.DOT_RADIUS * 0.75, y - RV.DOT_RADIUS * 1.75), tag, font=f_tag, fill=(255, 255, 255, TAG_ALPHA))
        pil = Image.alpha_composite(pil.convert("RGBA"), tag_layer).convert("RGB"); dr = ImageDraw.Draw(pil)
        RV.draw_centered(dr, W // 2, RV.TITLE_Y_1, a.title, f_title, WHITE)
        RV.draw_centered(dr, W // 2, RV.TITLE_Y_2, a.track_name.upper(), f_sub, WHITE)
        for car, x, v, m in ((A, W // 4, va, ma), (B, 3 * W // 4, vb, mb)):
            RV.draw_centered(dr, x, 990, car.label, f_lab, WHITE)
            RV.draw_centered(dr, x, 1040, MODE_TXT.get(m, m), f_small, MODE_COL.get(m, WHITE))
            RV.draw_centered(dr, x, 1112, f"{int(round(v * 3.6))}", f_spd, WHITE)
            RV.draw_centered(dr, x, 1180, "KM/H", f_unit, WHITE)
            RV.draw_centered(dr, x, 1240, fmt_lap(car.show), f_sub, WHITE)
        if fa >= fb:
            gap = t - A.t_of_frac(fb) if fb < 1 else B.show - A.show
        else:
            gap = t - B.t_of_frac(fa) if fa < 1 else A.show - B.show
        RV.draw_centered(dr, W // 2, 1112, f"{gap:.2f}s" if gap > 0.005 else "0.00s", f_gap, WHITE)
        RV.draw_centered(dr, W // 2, 1160, "GAP", f_small, WHITE)
        RV.draw_centered(dr, W // 2, RV.WATERMARK_Y, RV.WATERMARK_TEXT, f_wm, WHITE)
        out = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        if dbg is not None:
            cv2.imwrite(f"{os.path.splitext(a.out)[0]}_f{fr:05d}.png", out)
        else:
            vw.write(out)
            if (fr + 1) % 300 == 0: print(f"  frame {fr + 1}/{n_frames}", flush=True)
    if vw is not None:
        vw.release(); print(f"[dual-v3] saved -> {a.out}  ({n_frames} frames)")


if __name__ == "__main__":
    main()
