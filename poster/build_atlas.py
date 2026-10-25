"""Builds poster/atlas.svg + atlas.html: "Julia at 24", the atlas plate.

36 x 24 in landscape. A flat Winkel Tripel world map -- the projection atlases
actually use -- with two lenses cut into it: New York magnified in the middle
of the plate, and the Northeast beside it, since at world scale Boston and
Beacon land on top of the city.

Pure Python, so it builds without node (poster/build_poster.mjs, the fisheye
poster, still needs npm). Geometry comes from the same poster/geo files.

  python3 poster/build_atlas.py             -> atlas.svg + atlas.html
  python3 poster/build_atlas.py --render    -> ... + atlas.pdf + atlas-preview.png
                                               (set CHROME=/path/to/chrome)
"""
import base64
import io as _io
import json
import math
import os
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GEO = os.path.join(HERE, "geo")


def read_json(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- palette
C = dict(paper="#FBF5EA", ink="#2A2420", muted="#6B5F55", tomato="#E4572E",
         sun="#F2B630", water="#C9DFEA", deep="#2D5D7B", land="#EFE6D2",
         line="#D9CCB0", park="#BFD6A8", road="#FBF5EA")

# ------------------------------------------------- layout (1 unit = 0.01 in)
W, H = 3600, 2400                       # 36 x 24 in, the map plate
DW, DH = 1800, 2400                     # 18 x 24 in, the directory sheet beside it
MAP_TOP, MAP_BOT = 320, 2300
LAT_N, LAT_S = 84, -58                  # Antarctica cropped, as atlas plates do

# The two lenses: where they sit on the plate, and the ground window each shows.
CITY = dict(cx=1800, cy=1414, r=561, lon=-73.999, lat=40.719, span_km=17.0,
            title="NEW YORK CITY", sub="stops 1-17", bar_km=5)
NE = dict(cx=688, cy=1570, r=358, lon=-73.42, lat=41.38, span_km=640.0,
          title="THE NORTHEAST", sub="stops 18-23", bar_km=100)

# Where each pin's badge sits, as a fraction of the lens radius from its centre
# (dx, dy), plus which side its label hangs off. Hand-placed so the labels in
# the crowded bottom of Manhattan don't collide.
BADGE = {
    # --- city lens
    "home":          (-0.10, 0.34, "left"),
    "spongies":      (-0.50, 0.16, "left"),
    "bao":           (-0.40, 0.52, "left"),
    "wus":           (-0.14, 0.68, "left"),
    "ludlow":        (0.30, 0.46, "right"),
    "recente":       (0.38, 0.14, "right"),
    "mimis":         (-0.56, -0.04, "left"),
    "sobs":          (-0.62, -0.26, "left"),
    "msg":           (-0.46, -0.48, "left"),
    "pennclub":      (-0.16, -0.60, "above"),
    "centralpark":   (0.16, -0.70, "above"),
    "sonic":         (0.64, -0.28, "right"),
    "gantry":        (0.46, -0.52, "right"),
    "brooklynsteel": (0.66, 0.06, "right"),
    "mccarren":      (0.56, 0.30, "right"),
    "williamsburg":  (0.40, 0.54, "right"),
    "botanic":       (0.08, 0.72, "below"),
    # --- northeast lens
    "oley":          (-0.62, 0.26, "left"),
    "beacon":        (-0.26, -0.40, "left"),
    "hamptons":      (0.40, 0.46, "right"),
    "atlantic":      (-0.08, 0.62, "below"),
    "harvard":       (0.46, -0.56, "right"),
    "boston":        (0.70, -0.24, "right"),
}

# Pins out on the world map: label side, and an optional shared callout.
WORLD_LABEL = {
    "vancouver":   ("above", None, None),
    "ginza":       ("right", "japan", "Seafood buffet, Ginza"),
    "kiyomizu":    ("right", "japan", None),
    "shinsaibashi": ("right", "japan", None),
    "usj":         ("right", "japan", None),
    "chengdu":     ("left", None, None),
    "manila":      ("below", None, None),
}
# Badge anchors for the world pins (plate coordinates), hand-placed.
WORLD_BADGE = {
    "vancouver":   (700, 687),
    "ginza":       (3120, 754),
    "kiyomizu":    (3120, 827),
    "shinsaibashi": (3120, 902),
    "usj":         (3120, 976),
    "chengdu":     (2420, 1257),
    "manila":      (2880, 1581),
}

# Ocean and continent names, atlas-style. Any that a lens covers is dropped.
OCEANS = [(-158, 38, "PACIFIC OCEAN", 36), (-48, 66, "NORTH ATLANTIC", 26),
          (-30, -52, "SOUTH ATLANTIC", 26), (75, -25, "INDIAN OCEAN", 34),
          (-158, -40, "SOUTH PACIFIC", 24),
          (-110, 58, "NORTH AMERICA", 28), (-66, -38, "SOUTH AMERICA", 26),
          (100, 55, "ASIA", 30), (32, 66, "EUROPE", 24), (134, -25, "AUSTRALIA", 26),
          (-45, 74, "GREENLAND", 20)]


# ---------------------------------------------------------------- topojson
def topo_decode(topo, name):
    """-> [(geometry type, properties, coords in lon/lat degrees)]"""
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def line(idxs):
        out = []
        for i in idxs:
            a = arcs[~i][::-1] if i < 0 else arcs[i]
            out.extend(a if not out else a[1:])
        return out

    feats = []
    for g in topo["objects"][name]["geometries"]:
        t, props = g["type"], g.get("properties", {})
        if t == "Polygon":
            coords = [line(r) for r in g["arcs"]]
        elif t == "MultiPolygon":
            coords = [[line(r) for r in poly] for poly in g["arcs"]]
        elif t == "LineString":
            coords = line(g["arcs"])
        elif t == "MultiLineString":
            coords = [line(ln) for ln in g["arcs"]]
        else:
            continue
        feats.append((t, props, coords))
    return feats


# ------------------------------------------------------------- projections
def winkel_raw(lon, lat):
    """Winkel Tripel. Degrees in, unit plane out."""
    lam, phi = math.radians(lon), math.radians(lat)
    alpha = math.acos(max(-1.0, min(1.0, math.cos(phi) * math.cos(lam / 2))))
    sinc = 1.0 if abs(alpha) < 1e-12 else math.sin(alpha) / alpha
    x = 0.5 * (lam * (2 / math.pi) + 2 * math.cos(phi) * math.sin(lam / 2) / sinc)
    y = 0.5 * (phi + math.sin(phi) / sinc)
    return x, y


def make_world():
    """Fit the cropped Winkel world into the map band. -> project, frame path"""
    xs, ys = [], []
    for lon in range(-180, 181, 2):
        for lat in (LAT_S, LAT_N):
            x, y = winkel_raw(lon, lat)
            xs.append(x)
            ys.append(y)
    for lat in range(LAT_S, LAT_N + 1, 2):
        for lon in (-180, 180):
            x, y = winkel_raw(lon, lat)
            xs.append(x)
            ys.append(y)
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = min((W - 240) / (x1 - x0), (MAP_BOT - MAP_TOP) / (y1 - y0))
    ox = W / 2 - s * (x0 + x1) / 2
    oy = (MAP_TOP + MAP_BOT) / 2 + s * (y0 + y1) / 2

    def project(lon, lat):
        x, y = winkel_raw(lon, lat)
        return ox + s * x, oy - s * y

    frame = [project(lon, LAT_N) for lon in range(-180, 181, 2)]
    frame += [project(180, lat) for lat in range(LAT_N, LAT_S - 1, -2)]
    frame += [project(lon, LAT_S) for lon in range(180, -181, -2)]
    frame += [project(-180, lat) for lat in range(LAT_S, LAT_N + 1, 2)]
    return project, "M" + " L".join("%.1f %.1f" % p for p in frame) + "Z"


def make_lens(lens):
    """Azimuthal equidistant about the lens centre, scaled to its plate radius."""
    lon0, lat0 = math.radians(lens["lon"]), math.radians(lens["lat"])
    k = lens["r"] / (lens["span_km"] / 2 / 6371.0)

    def project(lon, lat):
        lam, phi = math.radians(lon), math.radians(lat)
        dl = lam - lon0
        cosc = math.sin(lat0) * math.sin(phi) + math.cos(lat0) * math.cos(phi) * math.cos(dl)
        c = math.acos(max(-1.0, min(1.0, cosc)))
        kk = 1.0 if abs(c) < 1e-12 else c / math.sin(c)
        return (lens["cx"] + k * kk * math.cos(phi) * math.sin(dl),
                lens["cy"] - k * kk * (math.cos(lat0) * math.sin(phi)
                                       - math.sin(lat0) * math.cos(phi) * math.cos(dl)))

    return project


# -------------------------------------------------------------- svg helpers
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def f(n):
    return ("%.1f" % n).rstrip("0").rstrip(".")


def d_ring(ring, project, close=True, tol=0.35):
    pts = [project(lon, lat) for lon, lat in ring]
    if not pts:
        return ""
    out = ["M%s %s" % (f(pts[0][0]), f(pts[0][1]))]
    last = pts[0]
    for p in pts[1:]:
        if abs(p[0] - last[0]) < tol and abs(p[1] - last[1]) < tol:
            continue
        out.append("L%s %s" % (f(p[0]), f(p[1])))
        last = p
    if len(out) == 1:
        return ""
    return " ".join(out) + ("Z" if close else "")


def d_feature(kind, coords, project, tol=0.35):
    if kind == "Polygon":
        return " ".join(d_ring(r, project, True, tol) for r in coords)
    if kind == "MultiPolygon":
        return " ".join(d_ring(r, project, True, tol) for poly in coords for r in poly)
    if kind == "LineString":
        return d_ring(coords, project, False, tol)
    if kind == "MultiLineString":
        return " ".join(d_ring(ln, project, False, tol) for ln in coords)
    return ""


def bbox_of(coords):
    lo = [180.0, 90.0]
    hi = [-180.0, -90.0]

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            lo[0] = min(lo[0], c[0])
            hi[0] = max(hi[0], c[0])
            lo[1] = min(lo[1], c[1])
            hi[1] = max(hi[1], c[1])
        else:
            for x in c:
                walk(x)

    walk(coords)
    return lo[0], lo[1], hi[0], hi[1]


def lens_box(lens, pad=1.25):
    """Lon/lat window a lens can show, with a little slack."""
    dlat = lens["span_km"] / 2 / 111.32 * pad
    dlon = dlat / max(0.2, math.cos(math.radians(lens["lat"])))
    return (lens["lon"] - dlon, lens["lat"] - dlat, lens["lon"] + dlon, lens["lat"] + dlat)


def overlaps(b, box):
    return not (b[2] < box[0] or b[0] > box[2] or b[3] < box[1] or b[1] > box[3])


def name_lines(place, limit=26):
    names = [p["name"] for p in place["people"]]
    joined = ", ".join(names)
    if len(joined) <= limit or len(names) == 1:
        return [joined]
    best = None
    for i in range(1, len(names)):
        a, b = ", ".join(names[:i]) + ",", ", ".join(names[i:])
        score = max(len(a), len(b))
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1]


# ------------------------------------------------------------------ photos
PHOTO_PX = 190          # plenty at a 0.5 in disc; keeps the SVG a sane size
_photo_defs = {}


def photo_symbol(rel_path):
    """Embed a pin thumbnail once, as a circular <symbol>. -> its id, or None."""
    full = os.path.join(ROOT, rel_path.replace("/", os.sep))
    if not os.path.exists(full):
        return None
    sid = "ph-" + os.path.splitext(os.path.basename(rel_path))[0]
    if sid not in _photo_defs:
        im = Image.open(full).convert("RGB")
        if max(im.size) > PHOTO_PX:
            im = im.resize((PHOTO_PX, PHOTO_PX), Image.LANCZOS)
        buf = _io.BytesIO()
        im.save(buf, "JPEG", quality=78, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        _photo_defs[sid] = (
            f'<symbol id="{sid}" viewBox="0 0 100 100">'
            f'<clipPath id="{sid}-c"><circle cx="50" cy="50" r="50"/></clipPath>'
            f'<image clip-path="url(#{sid}-c)" x="0" y="0" width="100" height="100" '
            f'preserveAspectRatio="xMidYMid slice" href="data:image/jpeg;base64,{b64}"/></symbol>')
    return sid


def photo_disc(x, y, r, rel_path, ring=2.6):
    """A person's face as a circular pin, ringed so it reads against the map."""
    sid = photo_symbol(rel_path)
    out = [f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r + ring)}" fill="{C["paper"]}"/>']
    if sid:
        out.append(f'<use href="#{sid}" x="{f(x - r)}" y="{f(y - r)}" '
                   f'width="{f(r * 2)}" height="{f(r * 2)}"/>')
    else:
        out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{C["land"]}"/>')
    out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r + ring / 2)}" fill="none" '
               f'stroke="{C["ink"]}" stroke-width="{f(ring)}" stroke-opacity=".9"/>')
    return out


def first_thumb(person):
    return person["photos"][0]["thumb"] if person.get("photos") else None


# ------------------------------------------------------------------- build
def build():
    data = read_json(ROOT, "data", "memmap.json")
    places = data["places"]
    by_key = {p["key"]: p for p in places}
    n_people = sum(len(p["people"]) for p in places)

    world = topo_decode(read_json(GEO, "world-countries-110m.topo.json"), "countries")
    states = topo_decode(read_json(GEO, "us-states-500k.topo.json"), "states")
    boroughs = topo_decode(read_json(GEO, "nyc-boroughs.topo.json"), "b")
    osm = topo_decode(read_json(GEO, "nyc-osm.topo.json"), "osm")
    lakes = read_json(GEO, "lakes-50m.json")["features"]

    project, d_frame = make_world()
    city = make_lens(CITY)
    ne = make_lens(NE)

    out = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">')
    add("""  <style>
    .t-display { font-family: 'Fraunces', Georgia, serif; font-variation-settings: "SOFT" 100, "WONK" 0; }
    .t-body { font-family: 'DM Sans', 'Helvetica Neue', Arial, sans-serif; }
    .t-hand { font-family: 'Caveat', 'Bradley Hand', cursive; }
    .halo { paint-order: stroke; stroke: #FBF5EA; stroke-linejoin: round; }
    .halo-w { paint-order: stroke; stroke: #C9DFEA; stroke-linejoin: round; }
  </style>""")
    add('<defs>')
    add(f'<clipPath id="world-clip"><path d="{d_frame}"/></clipPath>')
    add(f'<clipPath id="city-clip"><circle cx="{CITY["cx"]}" cy="{CITY["cy"]}" r="{CITY["r"]}"/></clipPath>')
    add(f'<clipPath id="ne-clip"><circle cx="{NE["cx"]}" cy="{NE["cy"]}" r="{NE["r"]}"/></clipPath>')
    add('<!--PHOTO_DEFS-->')
    add('</defs>')
    add(f'<rect width="{W}" height="{H}" fill="{C["paper"]}"/>')

    # ------------------------------------------------------------- the world
    add('<g clip-path="url(#world-clip)">')
    add(f'<path d="{d_frame}" fill="{C["water"]}"/>')
    grat = []
    for lon in range(-180, 181, 20):
        pts = [project(lon, lat / 2.0) for lat in range(LAT_S * 2, LAT_N * 2 + 1, 4)]
        grat.append("M" + " L".join("%s %s" % (f(p[0]), f(p[1])) for p in pts))
    for lat in range(-40, LAT_N + 1, 20):
        pts = [project(lon / 2.0, lat) for lon in range(-360, 361, 4)]
        grat.append("M" + " L".join("%s %s" % (f(p[0]), f(p[1])) for p in pts))
    add(f'<path d="{" ".join(grat)}" fill="none" stroke="{C["deep"]}" stroke-opacity=".15" stroke-width="1.2"/>')
    land = " ".join(d_feature(k, c, project, 0.5) for k, p, c in world)
    add(f'<path d="{land}" fill="{C["land"]}" stroke="{C["line"]}" stroke-width="1.4" stroke-linejoin="round"/>')
    dl = " ".join(d_feature(x["geometry"]["type"], x["geometry"]["coordinates"], project, 0.5)
                  for x in lakes)
    add(f'<path d="{dl}" fill="{C["water"]}" stroke="none"/>')
    for lon, lat, text, size in OCEANS:
        x, y = project(lon, lat)
        sea = "OCEAN" in text or "ATLANTIC" in text or "PACIFIC" in text
        # these are set in caps, the continent names with 6 units of tracking
        half = (0.33 * size + (0 if sea else 6)) * len(text) / 2
        if any(math.hypot(x + dx - L["cx"], y - L["cy"]) < L["r"] + 40
               for L in (CITY, NE) for dx in (-half, 0, half)):
            continue                      # a lens is sitting on it
        if any(abs(y - (L["cy"] + sgn * (L["r"] + 35))) < 46 and abs(x - L["cx"]) < 460
               for L in (CITY, NE) for sgn in (-1, 1)):
            continue                      # a lens caption or scale bar is
        style = 'font-style="italic"' if sea else 'letter-spacing="6"'
        fill, op = (C["deep"], ".8") if sea else (C["muted"], ".65")
        add(f'<text x="{f(x)}" y="{f(y)}" text-anchor="middle" class="t-display" {style} '
            f'font-size="{size}" fill="{fill}" fill-opacity="{op}">{esc(text)}</text>')
    add('</g>')
    add(f'<path d="{d_frame}" fill="none" stroke="{C["ink"]}" stroke-width="3.5"/>')

    # ---------------------------------------------------- lens cones + marks
    home_x, home_y = project(*HOME_LL)

    def cone(lens, tx, ty):
        """Two tangents from the lens rim back to the spot it magnifies."""
        dx, dy = tx - lens["cx"], ty - lens["cy"]
        dist = math.hypot(dx, dy)
        if dist <= lens["r"]:
            return
        a = math.atan2(dy, dx)
        spread = math.asin(min(1.0, lens["r"] / dist)) * 0.92
        pts = []
        for sgn in (-1, 1):
            ang = a + sgn * spread
            px = lens["cx"] + lens["r"] * math.cos(a + sgn * (math.pi / 2) * 0.55)
            py = lens["cy"] + lens["r"] * math.sin(a + sgn * (math.pi / 2) * 0.55)
            pts.append((px, py))
        add(f'<path d="M{f(pts[0][0])} {f(pts[0][1])} L{f(tx)} {f(ty)} L{f(pts[1][0])} {f(pts[1][1])}" '
            f'fill="{C["ink"]}" fill-opacity=".06" stroke="{C["ink"]}" stroke-width="1.2" '
            f'stroke-opacity=".45" stroke-dasharray="7 5"/>')

    cone(NE, home_x, home_y)
    add(f'<circle cx="{f(home_x)}" cy="{f(home_y)}" r="13" fill="none" stroke="{C["ink"]}" stroke-width="2"/>')
    add(f'<circle cx="{f(home_x)}" cy="{f(home_y)}" r="3.6" fill="{C["ink"]}"/>')
    add(f'<text x="{f(home_x)}" y="{f(home_y - 24)}" text-anchor="middle" class="t-body halo" '
        f'stroke-width="6" font-size="17" font-weight="700" letter-spacing="2" '
        f'fill="{C["ink"]}">NEW YORK</text>')

    # the city lens is a zoom of a spot inside the northeast lens
    city_in_ne = ne(*HOME_LL)
    cone(CITY, *city_in_ne)

    # ------------------------------------------------------------- the lenses
    def draw_lens(lens, clip, project_fn, body):
        add(f'<circle cx="{lens["cx"]}" cy="{lens["cy"]}" r="{lens["r"] + 7}" fill="{C["paper"]}"/>')
        add(f'<g clip-path="url(#{clip})">')
        add(f'<rect x="{lens["cx"] - lens["r"]}" y="{lens["cy"] - lens["r"]}" '
            f'width="{lens["r"] * 2}" height="{lens["r"] * 2}" fill="{C["water"]}"/>')
        body(project_fn)
        add('</g>')
        add(f'<circle cx="{lens["cx"]}" cy="{lens["cy"]}" r="{lens["r"]}" fill="none" '
            f'stroke="{C["ink"]}" stroke-width="4"/>')
        add(f'<circle cx="{lens["cx"]}" cy="{lens["cy"]}" r="{lens["r"] + 7}" fill="none" '
            f'stroke="{C["ink"]}" stroke-width="1.4" stroke-opacity=".5"/>')

    ne_box = lens_box(NE)
    city_box = lens_box(CITY)

    def ne_body(pr):
        d = " ".join(d_feature(k, c, pr, 0.4) for k, p, c in states
                     if overlaps(bbox_of(c), ne_box))
        add(f'<path d="{d}" fill="{C["land"]}" stroke="{C["line"]}" stroke-width="2" '
            f'stroke-linejoin="round"/>')
        dlk = " ".join(d_feature(x["geometry"]["type"], x["geometry"]["coordinates"], pr, 0.4)
                       for x in lakes if overlaps(bbox_of(x["geometry"]["coordinates"]), ne_box))
        add(f'<path d="{dlk}" fill="{C["water"]}" stroke="none"/>')

    def city_body(pr):
        d = " ".join(d_feature(k, c, pr, 0.3) for k, p, c in boroughs)
        add(f'<path d="{d}" fill="{C["land"]}" stroke="none"/>')
        parks = " ".join(d_feature(k, c, pr, 0.3) for k, p, c in osm if p.get("k") == "park")
        add(f'<path d="{parks}" fill="{C["park"]}" stroke="none"/>')
        roads = " ".join(d_feature(k, c, pr, 0.4) for k, p, c in osm if p.get("k") == "road")
        add(f'<path d="{roads}" fill="none" stroke="{C["road"]}" stroke-width="1.8" '
            f'stroke-opacity=".9" stroke-linecap="round"/>')

    draw_lens(NE, "ne-clip", ne, ne_body)
    draw_lens(CITY, "city-clip", city, city_body)

    # the city's own spot, marked inside the northeast lens
    add(f'<circle cx="{f(city_in_ne[0])}" cy="{f(city_in_ne[1])}" r="11" fill="none" '
        f'stroke="{C["ink"]}" stroke-width="2"/>')
    add(f'<circle cx="{f(city_in_ne[0])}" cy="{f(city_in_ne[1])}" r="3" fill="{C["ink"]}"/>')

    # lens captions above, scale bar below
    for lens in (CITY, NE):
        add(f'<text x="{lens["cx"]}" y="{f(lens["cy"] - lens["r"] - 30)}" text-anchor="middle" '
            f'class="t-body halo" stroke-width="7" font-size="26" font-weight="700" '
            f'letter-spacing="7" fill="{C["ink"]}">{lens["title"]}'
            f'<tspan font-weight="400" fill="{C["muted"]}">  &#183;  {lens["sub"].upper()}</tspan></text>')
        bar = lens["bar_km"] * lens["r"] / (lens["span_km"] / 2)
        bx, by = lens["cx"] - bar / 2, lens["cy"] + lens["r"] + 40
        add(f'<path d="M{f(bx)} {f(by - 7)} L{f(bx)} {f(by)} L{f(bx + bar)} {f(by)} '
            f'L{f(bx + bar)} {f(by - 7)} M{f(bx + bar / 2)} {f(by)} L{f(bx + bar / 2)} {f(by - 5)}" '
            f'fill="none" stroke="{C["ink"]}" stroke-width="2" class="halo" stroke-linecap="butt"/>')
        add(f'<text x="{f(bx + bar + 10)}" y="{f(by + 2)}" class="t-body halo" stroke-width="6" '
            f'font-size="16" fill="{C["muted"]}">{lens["bar_km"]} km</text>')

    # --------------------------------------------------------------- the pins
    dots, leaders, badges, labels = [], [], [], []

    def label_block(x, y, side, title, subs, r):
        anchor = {"left": "end", "right": "start"}.get(side, "middle")
        gap = r + 9
        ox = -gap if side == "left" else gap if side == "right" else 0
        oy = -(gap + 24 + 26 * (len(subs) - 1)) if side == "above" else (gap + 22) if side == "below" else 0
        tx, ty = x + ox, y + oy
        labels.append(f'<text x="{f(tx)}" y="{f(ty - 2)}" text-anchor="{anchor}" class="t-body halo" '
                      f'stroke-width="6" font-size="20" font-weight="700" fill="{C["ink"]}">{esc(title)}</text>')
        for i, s in enumerate(subs):
            labels.append(f'<text x="{f(tx)}" y="{f(ty + 24 + i * 26)}" text-anchor="{anchor}" '
                          f'class="t-hand halo" stroke-width="6" font-size="29" font-weight="600" '
                          f'fill="{C["tomato"]}">{esc(s)}</text>')

    def marker(bx, by, place, r):
        """A face for the stop, with its number on a chip at the lower left."""
        badges.extend(photo_disc(bx, by, r, first_thumb(place["people"][0])))
        nx, ny, nr = bx - r * 0.70, by + r * 0.70, r * 0.50
        badges.append(f'<circle cx="{f(nx)}" cy="{f(ny)}" r="{f(nr)}" fill="{C["tomato"]}" '
                      f'stroke="{C["paper"]}" stroke-width="2.2"/>')
        badges.append(f'<text x="{f(nx)}" y="{f(ny + nr * 0.37)}" text-anchor="middle" class="t-body" '
                      f'font-size="{f(nr * 1.15)}" font-weight="700" fill="#FFFFFF">{place["num"]}</text>')

    def pin(px, py, bx, by, place, side, title=None, r=25):
        if math.hypot(bx - px, by - py) > r + 2:
            leaders.append(f'<line x1="{f(px)}" y1="{f(py)}" x2="{f(bx)}" y2="{f(by)}" '
                           f'stroke="{C["ink"]}" stroke-width="1.3" stroke-opacity=".65"/>')
        dots.append(f'<circle cx="{f(px)}" cy="{f(py)}" r="4.6" fill="{C["ink"]}" '
                    f'stroke="{C["paper"]}" stroke-width="1.6"/>')
        marker(bx, by, place, r)
        label_block(bx, by, side, title or place["name"], name_lines(place), r + 4)

    for place in places:
        key = place["key"]
        if key in BADGE:
            lens, pr = (CITY, city) if place["region"] == "nyc" else (NE, ne)
            px, py = pr(place["lng"], place["lat"])
            dx, dy, side = BADGE[key]
            pin(px, py, lens["cx"] + dx * lens["r"], lens["cy"] + dy * lens["r"], place, side,
                r=28 if key == "home" else 24)
            if place.get("extra_pin"):
                ex, ey = pr(place["extra_pin"]["lng"], place["extra_pin"]["lat"])
                dots.append(f'<circle cx="{f(ex)}" cy="{f(ey)}" r="6" fill="{C["sun"]}" '
                            f'stroke="{C["ink"]}" stroke-width="1.4"/>')
        else:
            px, py = project(place["lng"], place["lat"])
            side, group, short = WORLD_LABEL[key]
            bx, by = WORLD_BADGE[key]
            if group:
                dots.append(f'<circle cx="{f(px)}" cy="{f(py)}" r="4.6" fill="{C["ink"]}" '
                            f'stroke="{C["paper"]}" stroke-width="1.6"/>')
                marker(bx, by, place, 23)
                label_block(bx, by, side, short or place["name"], name_lines(place), 27)
            else:
                pin(px, py, bx, by, place, side, short)

    # one bracket for the four Japan stops
    jp = [by_key[k] for k in ("ginza", "kiyomizu", "shinsaibashi", "usj")]
    jx = sum(project(p["lng"], p["lat"])[0] for p in jp) / 4
    jy = sum(project(p["lng"], p["lat"])[1] for p in jp) / 4
    ring = max(math.hypot(project(p["lng"], p["lat"])[0] - jx,
                          project(p["lng"], p["lat"])[1] - jy) for p in jp) + 16
    ys = [WORLD_BADGE[k][1] for k in ("ginza", "usj")]
    brx = WORLD_BADGE["ginza"][0] - 23 - 24
    mid = (ys[0] + ys[1]) / 2
    ang = math.atan2(mid - jy, brx - jx)
    seg = " ".join(f'M{f(brx + 24)} {f(WORLD_BADGE[k][1])} L{f(brx)} {f(WORLD_BADGE[k][1])}'
                   for k in ("ginza", "kiyomizu", "shinsaibashi", "usj"))
    leaders.append(f'<circle cx="{f(jx)}" cy="{f(jy)}" r="{f(ring)}" fill="none" stroke="{C["ink"]}" '
                   f'stroke-width="1.3" stroke-dasharray="4 4"/>')
    leaders.append(f'<path d="M{f(jx + ring * math.cos(ang))} {f(jy + ring * math.sin(ang))} '
                   f'L{f(brx)} {f(mid)} M{f(brx)} {f(ys[0])} L{f(brx)} {f(ys[1])} {seg}" fill="none" '
                   f'stroke="{C["ink"]}" stroke-width="1.3" stroke-opacity=".75"/>')
    leaders.append(f'<text x="{f(jx)}" y="{f(jy - ring - 12)}" text-anchor="middle" class="t-hand halo-w" '
                   f'stroke-width="5" font-size="34" font-weight="700" fill="{C["deep"]}">Japan</text>')

    out.extend(leaders)
    out.extend(dots)
    out.extend(badges)
    out.extend(labels)

    # ------------------------------------------------------------- the type
    add(f'<text x="{W / 2}" y="212" text-anchor="middle" class="t-display" font-size="190" '
        f'font-weight="560" letter-spacing="-3" fill="{C["ink"]}">Julia at '
        f'<tspan fill="{C["tomato"]}" font-style="italic">24</tspan></text>')
    add(f'<text x="{W / 2}" y="272" text-anchor="middle" class="t-display" font-size="38" '
        f'font-style="italic" fill="{C["muted"]}">the places she went, and the people she shared them with</text>')
    add(f'<text x="340" y="150" text-anchor="middle" transform="rotate(-8 340 150)" class="t-hand" '
        f'font-size="62" font-weight="700" fill="{C["tomato"]}">happy 25th!</text>')
    add(f'<text x="{W - 300}" y="150" text-anchor="middle" transform="rotate(7 {W - 300} 150)" '
        f'class="t-hand" font-size="54" font-weight="600" fill="{C["deep"]}">'
        f'{n_people} notes &#183; {len(places)} places</text>')
    add(f'<text x="{W - 150}" y="{MAP_BOT - 14}" text-anchor="end" class="t-hand" font-size="40" '
        f'font-weight="600" fill="{C["deep"]}">every pin is a person who loves you</text>')

    add(f'<text x="{W / 2}" y="{H - 44}" text-anchor="middle" class="t-body" font-size="15" '
        f'letter-spacing="2" fill="{C["muted"]}">MADE WITH LOVE BY PJ, FAMILY &amp; FRIENDS '
        f'&#183; OCTOBER 2026 &#183; WINKEL TRIPEL PROJECTION &#183; MAP DATA &#169; OPENSTREETMAP '
        f'CONTRIBUTORS, NATURAL EARTH, US CENSUS BUREAU, NYC OPEN DATA</text>')
    add('</svg>')
    return "\n".join(out).replace("<!--PHOTO_DEFS-->", "".join(_photo_defs.values()))


HOME_LL = (-73.99989, 40.71889)

FONTS = ("https://fonts.googleapis.com/css2?family=Caveat:wght@400..700&family=DM+Sans:ital,opsz,"
         "wght@0,9..40,300..800;1,9..40,300..800&family=Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,"
         "300..800,0..100,0..1;1,9..144,300..800,0..100,0..1&display=block")


# --------------------------------------------------------------- directory
def build_directory():
    """The key, as its own 18 x 24 in sheet: same height as the map, half as wide."""
    data = read_json(ROOT, "data", "memmap.json")
    places = data["places"]
    n_people = sum(len(p["people"]) for p in places)
    out = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {DW} {DH}" width="{DW}" height="{DH}">')
    add("""  <style>
    .t-display { font-family: 'Fraunces', Georgia, serif; font-variation-settings: "SOFT" 100, "WONK" 0; }
    .t-body { font-family: 'DM Sans', 'Helvetica Neue', Arial, sans-serif; }
    .t-hand { font-family: 'Caveat', 'Bradley Hand', cursive; }
  </style>""")
    add(f'<rect width="{DW}" height="{DH}" fill="{C["paper"]}"/>')

    add(f'<text x="{DW / 2}" y="186" text-anchor="middle" class="t-display" font-size="104" '
        f'font-weight="560" letter-spacing="-2" fill="{C["ink"]}">The '
        f'<tspan fill="{C["tomato"]}" font-style="italic">Directory</tspan></text>')
    add(f'<text x="{DW / 2}" y="240" text-anchor="middle" class="t-display" font-size="27" '
        f'font-style="italic" fill="{C["muted"]}">Julia at 24 &#183; '
        f'{n_people} notes from {len(places)} places</text>')
    add(f'<text x="{DW / 2}" y="296" text-anchor="middle" class="t-body" font-size="16" '
        f'letter-spacing="3" fill="{C["muted"]}">THE NUMBERS MATCH THE PINS ON THE MAP '
        f'AND THE NOTES IN THE PAMPHLET</text>')
    add(f'<line x1="130" y1="340" x2="{DW - 130}" y2="340" stroke="{C["line"]}" stroke-width="2.5"/>')

    rows = 15
    colw = (DW - 260) / 2
    rowh = 122
    for i, place in enumerate(places):
        cx = 130 + (i // rows) * colw
        cy = 414 + (i % rows) * rowh
        add(f'<circle cx="{f(cx + 20)}" cy="{f(cy - 9)}" r="20" fill="{C["tomato"]}"/>')
        add(f'<text x="{f(cx + 20)}" y="{f(cy - 2)}" text-anchor="middle" class="t-body" '
            f'font-size="21" font-weight="700" fill="#FFFFFF">{place["num"]}</text>')
        add(f'<text x="{f(cx + 54)}" y="{f(cy)}" class="t-body" font-size="25" font-weight="700" '
            f'fill="{C["ink"]}">{esc(place["name"])}</text>')
        add(f'<text x="{f(cx + 54)}" y="{f(cy + 27)}" class="t-body" font-size="18" '
            f'fill="{C["muted"]}">{esc(place["area"])}</text>')
        names = ", ".join(p["name"] for p in place["people"])
        fs = 34
        room = colw - 90
        lines = [names] if 0.37 * fs * len(names) <= room else name_lines(
            place, limit=max(12, int(room / (0.37 * fs))))
        for j, line in enumerate(lines):
            add(f'<text x="{f(cx + 54)}" y="{f(cy + 62 + j * 32)}" class="t-hand" font-size="{fs}" '
                f'font-weight="600" fill="{C["tomato"]}">{esc(line)}</text>')
        add(f'<line x1="{f(cx + 54)}" y1="{f(cy + 84)}" x2="{f(cx + colw - 60)}" y2="{f(cy + 84)}" '
            f'stroke="{C["line"]}" stroke-width="1.2" stroke-opacity=".7"/>')

    add(f'<text x="{DW / 2}" y="{DH - 48}" text-anchor="middle" class="t-hand" font-size="38" '
        f'font-weight="600" fill="{C["deep"]}">every pin is a person who loves you</text>')
    add('</svg>')
    return "\n".join(out)


def sheet_html(title, svg, w_in, h_in):
    return ("<!doctype html>" + chr(10) +
            '<html lang="en"><head><meta charset="utf-8">' + chr(10) +
            '<meta name="viewport" content="width=device-width, initial-scale=1">' + chr(10) +
            "<title>" + title + "</title>" + chr(10) +
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' + chr(10) +
            '<link rel="stylesheet" href="' + FONTS + '">' + chr(10) +
            "<style>" + chr(10) +
            "  @page { size: %gin %gin; margin: 0; }" % (w_in, h_in) + chr(10) +
            "  html, body { margin: 0; padding: 0; background: " + C["paper"] + "; }" + chr(10) +
            "  svg { display: block; width: %gin; height: %gin; }" % (w_in, h_in) + chr(10) +
            "  @media screen { svg { width: 100vw; height: auto; } }" + chr(10) +
            "</style></head>" + chr(10) + "<body>" + chr(10) + svg + chr(10) + "</body></html>" + chr(10))


def write_sheet(stem, title, svg, w_in, h_in):
    for name, text in ((stem + ".svg", svg),
                       (stem + ".html", sheet_html(title, svg, w_in, h_in))):
        with open(os.path.join(HERE, name), "w", encoding="utf-8", newline=chr(10)) as fh:
            fh.write(text)
    kb = os.path.getsize(os.path.join(HERE, stem + ".svg")) / 1024
    print("wrote poster/%s.svg (%.0f KB) and poster/%s.html" % (stem, kb, stem))


def render(stem, px_w, px_h):
    chrome = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    url = "file://" + os.path.join(HERE, stem + ".html").replace(chr(92), "/")
    with tempfile.TemporaryDirectory() as profile:
        base = ["--headless=new", "--disable-gpu", "--no-sandbox", "--user-data-dir=" + profile,
                "--virtual-time-budget=25000"]
        subprocess.run([chrome] + base + ["--no-pdf-header-footer",
                       "--print-to-pdf=" + os.path.join(HERE, stem + ".pdf"), url],
                       check=True, capture_output=True)
        subprocess.run([chrome] + base + ["--hide-scrollbars",
                       "--window-size=%d,%d" % (px_w, px_h),
                       "--screenshot=" + os.path.join(HERE, stem + "-preview.png"), url],
                       check=True, capture_output=True)
    print("wrote poster/%s.pdf and poster/%s-preview.png" % (stem, stem))


def main():
    write_sheet("atlas", "Julia at 24 &middot; atlas poster", build(), 36, 24)
    write_sheet("directory", "Julia at 24 &middot; the directory", build_directory(), 18, 24)
    if "--render" in sys.argv:
        render("atlas", 2700, 1800)
        render("directory", 1350, 1800)


if __name__ == "__main__":
    main()
