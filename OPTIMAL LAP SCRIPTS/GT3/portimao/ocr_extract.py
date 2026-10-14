import cv2, numpy as np, sys, json
cap = cv2.VideoCapture(sys.argv[1]); glyphs = []; per = []
BOX = dict(speed=(522, 572, 612, 618), lap=(612, 652, 735, 692))
f = 0
while True:
    ok, im = cap.read()
    if not ok: break
    row = {}
    for k, (x0, y0, x1, y1) in BOX.items():
        g = cv2.cvtColor(im[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY); b = (g > 140).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(b)
        comps = sorted([s for s in st[1:] if s[3] > 0.45 * (y1 - y0) and s[4] > 15], key=lambda s: s[0])
        gl = []
        for x, y, w, h, a in comps:
            c = cv2.resize(b[y:y + h, x:x + w].astype(np.float32), (12, 20)); gl.append(len(glyphs)); glyphs.append(c.ravel())
        row[k] = gl
    per.append(row); f += 1
np.save('glyphs.npy', np.array(glyphs)); json.dump(per, open('per.json', 'w')); print('frames', f, 'glyphs', len(glyphs))
