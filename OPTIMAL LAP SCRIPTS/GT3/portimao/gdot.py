import cv2, numpy as np, json, sys
cap = cv2.VideoCapture(sys.argv[1]); X0, Y0 = 290, 520; pts = []
while True:
    ok, im = cap.read()
    if not ok: break
    c = im[Y0:Y0 + 150, X0:X0 + 200]; hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (20, 120, 150), (35, 255, 255))
    ys, xs = np.nonzero(m)
    pts.append([float(xs.mean()) + X0, float(ys.mean()) + Y0] if len(xs) > 20 else [np.nan, np.nan])
json.dump(pts, open('gdot.json', 'w')); p = np.array(pts); print('valid', np.isfinite(p[:, 0]).sum(), 'of', len(p))
for t, lat, lon in ((9, -0.9, 0.5), (15, -1.6, -0.2), (30, 0.2, -1.4), (52, 0.0, 0.5)):
    print(t, p[int(t * 30)], lat, lon)
