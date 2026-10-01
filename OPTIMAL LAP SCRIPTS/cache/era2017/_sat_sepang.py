"""Download Esri World Imagery tiles over Sepang and stitch a mosaic (real-world evidence for the 2017 line).
  python _sat_sepang.py <zoom> <lat_min> <lat_max> <lon_min> <lon_max> <out.png>
Writes <out>.json with the pixel->lat/lon georeference (Web Mercator)."""
import math, os, sys, json, io, requests
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); TC = os.path.join(HERE, "sat", "tiles"); os.makedirs(TC, exist_ok=True)
URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def tile_xy(lat, lon, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def get(z, x, y):
    p = os.path.join(TC, f"{z}_{x}_{y}.jpg")
    if not os.path.exists(p):
        r = requests.get(URL.format(z=z, x=x, y=y), timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status(); open(p, "wb").write(r.content)
    return Image.open(p).convert("RGB")


def main():
    z = int(sys.argv[1]); la0, la1, lo0, lo1 = map(float, sys.argv[2:6]); out = sys.argv[6]
    x0, y0 = tile_xy(la1, lo0, z); x1, y1 = tile_xy(la0, lo1, z)
    X0, Y0, X1, Y1 = int(x0), int(y0), int(x1), int(y1)
    im = Image.new("RGB", ((X1 - X0 + 1) * 256, (Y1 - Y0 + 1) * 256))
    for x in range(X0, X1 + 1):
        for y in range(Y0, Y1 + 1):
            im.paste(get(z, x, y), ((x - X0) * 256, (y - Y0) * 256))
    im.save(out)
    json.dump({"z": z, "tx0": X0, "ty0": Y0, "w": im.width, "h": im.height}, open(out[:-4] + ".json", "w"))
    print(out, im.size)


if __name__ == "__main__":
    main()
