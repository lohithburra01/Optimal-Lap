"""Two simulated laps on one map, same clock: e.g. the 2017-era car vs the 2026 car at Sepang.

Imports raceline_video.py helpers (never edits it). Each car has its own raceline + CSV
(frame,time_s,distance,speed,...,mode). Camera follows the midpoint of the two cars and
zooms out smoothly when they separate. Bottom panel: live speed-vs-distance traces.
"""
import argparse, json, math, os, sys
import numpy as np, cv2
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
import raceline_video as RV

W, H = RV.WIDTH, RV.HEIGHT
COL_A = (0, 150, 255)     # BGR orange  (car A, e.g. 2017)
COL_B = (255, 205, 0)     # BGR cyan    (car B, e.g. 2026)
GRAPH_Y0, GRAPH_Y1 = 1350, 1830
CAM_Y = 720              # map-band centre (title above ~430, HUD below ~960)
GRAPH_X0, GRAPH_X1 = 90, 1010
V_LO, V_HI = 50.0, 350.0
MODE_TXT = {"DEPLOY": "DEPLOY", "NORMAL": "NORMAL", "SUPERCLIP": "SUPERCLIP", "REGEN": "BRAKING",
            "DRS": "DRS OPEN", "FULL": "FULL POWER"}


class Car:
    def __init__(self, csv_path, rl_path, label, color):
        t, d, v, lap, _, mode = RV.load_telemetry(csv_path)
        self.t, self.d, self.v, self.lap, self.mode = t, d, v, lap, mode
        self.rl = np.asarray(json.load(open(rl_path))["raceline"], float)[:, :2]
        seg = np.linalg.norm(np.roll(self.rl, -1, axis=0) - self.rl, axis=1)
        self.arc = np.concatenate([[0.0], np.cumsum(seg)]); self.L = float(self.arc[-1])
        self.D = float(d[-1] + (d[-1] - d[-2]))           # distance at the finish line
        self.label, self.color = label, color
        self.frac_of_t = lambda tt: float(np.interp(tt, t, d)) / self.D
        # time at a lap fraction (for the live gap)
        self.t_of_frac = lambda f: float(np.interp(f * self.D, d, t))
        self.trail = []

    def state(self, tt):
        if tt >= self.lap:
            return 1.0, float(self.v[-1]), "FINISH"
        f = self.frac_of_t(tt)
        v = float(np.interp(tt, self.t, self.v))
        i = max(0, min(len(self.mode) - 1, int(np.searchsorted(self.t, tt, side="right")) - 1))
        return f, v, self.mode[i] if self.mode else ""

    def pos(self, f):
        s = (f % 1.0) * self.L
        i = max(0, min(int(np.searchsorted(self.arc, s)) - 1, len(self.rl) - 1))
        sl = self.arc[i + 1] - self.arc[i]; u = 0.0 if sl <= 0 else (s - self.arc[i]) / sl
        return self.rl[i] + u * (self.rl[(i + 1) % len(self.rl)] - self.rl[i])


def fmt_lap(x):
    return f"{int(x // 60)}:{x % 60:06.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outline", required=True)
    ap.add_argument("--a-csv", required=True); ap.add_argument("--a-raceline", required=True)
    ap.add_argument("--a-label", default="2017 CAR")
    ap.add_argument("--b-csv", required=True); ap.add_argument("--b-raceline", required=True)
    ap.add_argument("--b-label", default="2026 CAR")
    ap.add_argument("--a-lap", type=float, default=None, help="official lap time to display (s)")
    ap.add_argument("--b-lap", type=float, default=None, help="official lap time to display (s)")
    ap.add_argument("--title", default="2017 vs 2026")
    ap.add_argument("--track-name", default="Sepang")
    ap.add_argument("--zoom", type=float, default=18.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--no-graph", action="store_true", help="no speed panel (map only)")
    ap.add_argument("--white-text", action="store_true",
                    help="all text white except the mode labels DEPLOY/BRAKING/SUPERCLIP (own colours) and DRS (green)")
    ap.add_argument("--hold-s", type=float, default=2.0, help="freeze at the end")
    ap.add_argument("--out", required=True)
    ap.add_argument("--frames", default=None, help="debug: comma list of frame indices to PNG")
    a = ap.parse_args()

    data = json.load(open(a.outline, encoding="utf-8"))
    outer = RV.smooth_resample_loop(np.array(data["outer"], float), RV.N_VISUAL_POINTS, RV.VISUAL_SMOOTH_S)
    inner = RV.smooth_resample_loop(np.array(data["inner"], float), RV.N_VISUAL_POINTS, RV.VISUAL_SMOOTH_S)
    outer, inner = RV.align_loops(outer, inner)
    ok = RV.compute_kerb_polygons(outer, is_outer=True); ik = RV.compute_kerb_polygons(inner, is_outer=False)

    A = Car(a.a_csv, a.a_raceline, a.a_label, COL_A)
    B = Car(a.b_csv, a.b_raceline, a.b_label, COL_B)
    A.show = a.a_lap or A.lap; B.show = a.b_lap or B.lap
    T = max(A.lap, B.lap) + a.hold_s
    n_frames = int(math.ceil(T * a.fps))

    allp = np.vstack([outer, inner])
    span = max(np.ptp(allp[:, 0]), np.ptp(allp[:, 1]))
    base_scale = (min(W, H * 0.5) / span) * a.zoom
    # minimap (same rotation as the single-car video)
    MAP_X = W - RV.MAP_SIZE - RV.MAP_X_RIGHT_INSET; MAP_Y = RV.MAP_Y_TOP
    rot = math.radians(45.0); c_, s_ = math.cos(rot), math.sin(rot)
    mcx, mcy = (allp[:, 0].max() + allp[:, 0].min()) / 2, (allp[:, 1].max() + allp[:, 1].min()) / 2
    def mrot(p):
        dx, dy = p[0] - mcx, p[1] - mcy
        return dx * c_ - dy * s_, dx * s_ + dy * c_
    R_all = np.array([mrot(p) for p in allp]); rcx = (R_all[:, 0].max() + R_all[:, 0].min()) / 2
    rcy = (R_all[:, 1].max() + R_all[:, 1].min()) / 2
    msc = RV.MAP_SIZE / max(np.ptp(R_all[:, 0]), np.ptp(R_all[:, 1])) * 0.95
    def w2map(p):
        rx, ry = mrot(p)
        return int(MAP_X + RV.MAP_SIZE / 2 + (rx - rcx) * msc), int(MAP_Y + RV.MAP_SIZE / 2 - (ry - rcy) * msc)
    map_o = np.array([w2map(p) for p in outer], np.int32); map_i = np.array([w2map(p) for p in inner], np.int32)

    # graph geometry: x = lap fraction, y = speed
    gx = lambda f: GRAPH_X0 + f * (GRAPH_X1 - GRAPH_X0)
    gy = lambda v: GRAPH_Y1 - (min(max(v, V_LO), V_HI) - V_LO) / (V_HI - V_LO) * (GRAPH_Y1 - GRAPH_Y0)
    def trace_pts(car):
        f = car.d / car.D
        return np.array([[gx(x), gy(v * 3.6)] for x, v in zip(f, car.v)], np.int32), f

    trA, fA = trace_pts(A); trB, fB = trace_pts(B)

    f_title = RV.load_font(42, True); f_sub = RV.load_font(26, False); f_spd = RV.load_font(64, True)
    f_unit = RV.load_font(24, False); f_lab = RV.load_font(26, True); f_wm = RV.load_font(24, True)
    f_small = RV.load_font(20, False); f_gap = RV.load_font(34, True)

    dbg = set(int(x) for x in a.frames.split(",")) if a.frames else None
    vw = None if dbg else cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"), a.fps, (W, H))
    scale = base_scale
    for fr in range(n_frames):
        if dbg is not None and fr not in dbg and fr < max(dbg):
            # still advance trails/zoom state cheaply
            pass
        t = fr / a.fps
        fa, va, ma = A.state(t); fb, vb, mb = B.state(t)
        pa, pb = A.pos(fa), B.pos(fb)
        cam = 0.5 * (pa + pb)
        sep = float(np.linalg.norm(pa - pb))
        dx, dy = abs(pa[0] - pb[0]), abs(pa[1] - pb[1])
        # keep both dots inside the map band (x: 55% of width; y: above the HUD at ~960 px)
        want = min(base_scale, 0.55 * W / max(dx, 1e-6), 2 * 200 / max(dy, 1e-6))
        scale += (want - scale) * 0.08          # smooth zoom
        for car, p in ((A, pa), (B, pb)):
            car.trail.append(p.copy()); car.trail = car.trail[-RV.DEFAULT_TRAIL:]
        if dbg is not None and fr not in dbg:
            continue

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
        # both racing lines, thin, in each car's colour (dimmed) -> the line difference is visible
        for car in (A, B):
            dim = tuple(int(c * 0.55) for c in car.color)
            cv2.polylines(img, [np.array([w2s(p) for p in car.rl], np.int32)], True, dim, 3, cv2.LINE_AA)
        # trails + dots (trail thinner than the single-car video so two fit side by side)
        for car, p in ((B, pb), (A, pa)):
            tr = np.array([w2s(q) for q in car.trail], np.int32)
            if len(tr) > 1:
                cv2.polylines(img, [tr], False, car.color, 10, cv2.LINE_AA)
            x, y = w2s(p)
            cv2.circle(img, (x, y), 20, car.color, -1, cv2.LINE_AA)
            cv2.circle(img, (x, y), 20, (255, 255, 255), 3, cv2.LINE_AA)
        # minimap
        cv2.fillPoly(img, [map_o], RV.TRACK_FILL); cv2.fillPoly(img, [map_i], (0, 0, 0))
        cv2.polylines(img, [map_o], True, (120, 120, 120), 2, cv2.LINE_AA)
        cv2.polylines(img, [map_i], True, (120, 120, 120), 2, cv2.LINE_AA)
        for car, p in ((B, pb), (A, pa)):
            cv2.circle(img, w2map(p), 8, car.color, -1, cv2.LINE_AA)
            cv2.circle(img, w2map(p), 8, (255, 255, 255), 2, cv2.LINE_AA)
        if not a.no_graph:
          # graph panel sits on a black band that fades the map out above it
          band = img[GRAPH_Y0 - 120:]
          fade = np.ones((band.shape[0], 1, 1)); fade[:70, 0, 0] = np.linspace(1.0, 0.0, 70); fade[70:] = 0.0
          img[GRAPH_Y0 - 120:] = (band * fade).astype(np.uint8)
          # graph: faint full traces, bright up to each car, cursor dots
          cv2.rectangle(img, (GRAPH_X0 - 10, GRAPH_Y0 - 10), (GRAPH_X1 + 10, GRAPH_Y1 + 10), (25, 25, 25), -1)
          for vv in (100, 200, 300):
              y = int(gy(vv)); cv2.line(img, (GRAPH_X0, y), (GRAPH_X1, y), (55, 55, 55), 1, cv2.LINE_AA)
          for car, tr, ff, f_now in ((A, trA, fA, fa), (B, trB, fB, fb)):
              dim = tuple(int(c * 0.30) for c in car.color)
              cv2.polylines(img, [tr], False, dim, 2, cv2.LINE_AA)
              k = int(np.searchsorted(ff, f_now))
              if k > 1:
                  cv2.polylines(img, [tr[:k]], False, car.color, 3, cv2.LINE_AA)
          for car, f_now, v_now in ((A, fa, va), (B, fb, vb)):
              cv2.circle(img, (int(gx(min(f_now, 1.0))), int(gy(v_now * 3.6))), 7, car.color, -1, cv2.LINE_AA)

        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)); dr = ImageDraw.Draw(pil)
        WT = (255, 255, 255)
        rgb = (lambda c: WT) if a.white_text else (lambda c: (c[2], c[1], c[0]))
        tc = (lambda c: WT) if a.white_text else (lambda c: c)
        mode_col = (lambda m: dict(RV.MODE_COLORS, DRS=(40, 230, 90)).get(m, WT)) if a.white_text else (lambda m: (190, 190, 190))
        RV.draw_centered(dr, W // 2, RV.TITLE_Y_1, a.title, f_title, (255, 255, 255))
        RV.draw_centered(dr, W // 2, RV.TITLE_Y_2, a.track_name.upper(), f_sub, tc((200, 200, 200)))
        for car, x, v, m in ((A, W // 4, va, ma), (B, 3 * W // 4, vb, mb)):
            RV.draw_centered(dr, x, 990, car.label, f_lab, rgb(car.color))
            RV.draw_centered(dr, x, 1040, MODE_TXT.get(m, m), f_small, mode_col(m))
            RV.draw_centered(dr, x, 1112, f"{int(round(v * 3.6))}", f_spd, (255, 255, 255))
            RV.draw_centered(dr, x, 1180, "KM/H", f_unit, tc((200, 200, 200)))
            shown = car.show if t >= car.lap else min(t, car.lap)
            RV.draw_centered(dr, x, 1240, fmt_lap(shown), f_sub,
                             rgb(car.color) if t >= car.lap else tc((180, 180, 180)))
        # live gap at the trailing car's position: who is ahead and by how much (s)
        if fa >= fb:
            gap = t - A.t_of_frac(fb) if fb < 1 else B.show - A.show; lead = A
        else:
            gap = t - B.t_of_frac(fa) if fa < 1 else A.show - B.show; lead = B
        RV.draw_centered(dr, W // 2, 1112, f"{gap:+.2f}s".replace("+", "") if gap > 0.005 else "0.00s",
                         f_gap, rgb(lead.color))
        RV.draw_centered(dr, W // 2, 1160, "GAP", f_small, tc((170, 170, 170)))
        if not a.no_graph:
            dr.text((GRAPH_X0, GRAPH_Y0 - 42), "SPEED  km/h", font=f_small, fill=(170, 170, 170))
            for vv in (100, 200, 300):
                dr.text((GRAPH_X0 - 62, gy(vv) - 12), str(vv), font=f_small, fill=(120, 120, 120))
        RV.draw_centered(dr, W // 2, RV.WATERMARK_Y, RV.WATERMARK_TEXT, f_wm, tc((150, 150, 150)))
        out = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        if dbg is not None:
            cv2.imwrite(os.path.splitext(a.out)[0] + f"_f{fr:05d}.png", out)
            if fr >= max(dbg):
                break
        else:
            vw.write(out)
            if (fr + 1) % 300 == 0:
                print(f"  frame {fr + 1}/{n_frames}", flush=True)
    if vw is not None:
        vw.release(); print(f"[dual] saved -> {a.out}  ({n_frames} frames)")


if __name__ == "__main__":
    main()
