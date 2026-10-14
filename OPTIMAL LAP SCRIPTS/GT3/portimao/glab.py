import cv2, numpy as np, json, sys
cap = cv2.VideoCapture(sys.argv[1])
BOX = dict(lat=(292, 583, 340, 600), lon=(366, 516, 414, 533))
glyphs = []; per = []
while True:
    ok, im = cap.read()
    if not ok: break
    row = {}
    for k, (x0, y0, x1, y1) in BOX.items():
        c = cv2.resize(im[y0:y1, x0:x1], None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
        b = ((hsv[..., 2] > 150) & (hsv[..., 1] < 70)).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(b)
        comps = sorted([list(map(int, s)) for s in st[1:] if s[4] > 8], key=lambda s: s[0])
        items = []
        for x, y, w, h, a in comps:
            g = cv2.resize(b[y:y + h, x:x + w].astype(np.float32), (10, 16)).ravel()
            items.append(dict(x=x, y=y, w=w, h=h, gi=len(glyphs))); glyphs.append(np.r_[g, h / 30.0, w / 30.0])
        row[k] = items
    per.append(row)
np.save('lglyphs.npy', np.array(glyphs)); json.dump(per, open('lper.json', 'w')); print(len(per), len(glyphs))
