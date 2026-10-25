"""Generate pamphlet/pamphlet.html from data/memmap.json.

Run from the repo root:  python3 pamphlet/build_pamphlet.py [--pages pages.json] [--fillers N]

Usually run via make_pdfs.py, which does both passes and the booklet.

The HTML is static (data baked in) and uses ../assets/photos/print/ images,
so it opens straight from disk or from GitHub Pages. `--pages` takes a JSON
map of place number -> page number (written by make_pdfs.py after a first
render) so the directory can show page numbers.
"""
import html
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Optional: printed on the intro page if set (e.g. the GitHub Pages URL).
SITE_URL = ""

REGIONS = [
    ("nyc", "New York City"),
    ("northeast", "Close to home"),
    ("world", "Around the world"),
]
COUNTRY = {"vancouver": "Canada", "ginza": "Japan", "kiyomizu": "Japan", "shinsaibashi": "Japan",
           "usj": "Japan", "chengdu": "China", "manila": "Philippines"}

# Labels on the "seen from home" map page. Stop numbers come from the data;
# these only shorten a name, blank it out, or (via PIN_SPANS) fold a run of pins
# into one label -- the four Japan pins share one.
PIN_NAMES = {"hamptons": "The Hamptons", "atlantic": "The Atlantic", "harvard": "Boston",
             "boston": "", "vancouver": "Vancouver",
             "ginza": "Japan", "kiyomizu": "", "shinsaibashi": "", "usj": "",
             "manila": "Manila"}
# One label covers this pin through that one (pins that land on top of each other
# at this scale: the four Japan stops, and Cambridge + Boston).
PIN_SPANS = {"ginza": "usj", "harvard": "boston"}


def pin_label(place, places):
    """'25-28 Japan' / '21 The Atlantic' / '' for a pin folded into the one before it."""
    name = PIN_NAMES.get(place["key"], place["name"])
    if not name:
        return ""
    span_to = PIN_SPANS.get(place["key"])
    if span_to:
        last = next(q["num"] for q in places if q["key"] == span_to)
        return f"{place['num']}\u2013{last} {name}"
    return f"{place['num']} {name}"


# Content box of a 5.5 x 8.5 in page with the @page margins below.
CONTENT_W = 4.5


def esc(s):
    return html.escape(s or "", quote=True)


def haversine_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def bearing(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return math.atan2(y, x)


def display_name(person):
    return person["name"]


# ---------------------------------------------------------------- motif
def motif_svg(places, size=300, with_labels=False, pin_numbers=False):
    """'The world from Julia's place': every pin at its true bearing from home,
    on a squashed (log) distance scale. Same idea as the poster."""
    home = places[0]
    c = size / 2
    rmax = c - 14
    dmax = 20015.0

    def radius(d):
        return rmax * math.log1p(d / 1.5) / math.log1p(dmax / 1.5)

    out = [f'<svg class="motif" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">']
    out.append(f'<circle cx="{c}" cy="{c}" r="{rmax + 8}" fill="#C9DFEA"/>')
    for d, lab in ((5, "5 km"), (100, "100 km"), (2000, "2,000 km"), (12000, "12,000 km")):
        r = radius(d)
        out.append(f'<circle cx="{c}" cy="{c}" r="{r:.1f}" fill="none" stroke="#2D5D7B" '
                   f'stroke-opacity=".35" stroke-width=".7" stroke-dasharray="2 3"/>')
        if with_labels:
            out.append(f'<text x="{c}" y="{c + r + 7:.1f}" text-anchor="middle" class="ring-lab">{lab}</text>')
    for ang in range(0, 360, 30):
        a = math.radians(ang)
        out.append(f'<line x1="{c}" y1="{c}" x2="{c + (rmax + 8) * math.sin(a):.1f}" '
                   f'y2="{c - (rmax + 8) * math.cos(a):.1f}" stroke="#2D5D7B" stroke-opacity=".12" stroke-width=".6"/>')
    pts = []
    for p in places:
        d = haversine_km(home, p)
        r = radius(d)
        b = bearing(home, p)
        pts.append((c + r * math.sin(b), c - r * math.cos(b), p))
    for x, y, p in pts[1:]:
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#E4572E" stroke="#FBF5EA" stroke-width="1"/>')
        label = pin_label(p, places)
        if pin_numbers and p["region"] != "nyc" and label:
            dx = 5 if x >= c else -5
            anchor = "start" if x >= c else "end"
            out.append(f'<text x="{x + dx:.1f}" y="{y + 2.2:.1f}" text-anchor="{anchor}" class="pin-lab">'
                       f'{esc(label)}</text>')
    if pin_numbers:
        nyc = [p["num"] for p in places if p["region"] == "nyc"]
        out.append(f'<text x="{c}" y="{c + 15}" text-anchor="middle" class="pin-lab home">')
        out.append(f'New York ({min(nyc)}&ndash;{max(nyc)})</text>')
    out.append(f'<circle cx="{c}" cy="{c}" r="5" fill="#F2B630" stroke="#2A2420" stroke-width="1"/>')
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- photos
def photo_size(photo, n_in_row, long_note=False):
    """Width/height in inches for a polaroid's image area."""
    w, h = photo["w"], photo["h"]
    ar = w / h
    low_res = photo["src_px"] < 800
    if n_in_row == 1:
        max_w = 2.2 if low_res else 3.3
        max_h = 3.0 if low_res else 3.3
        if long_note:  # keep long letters on one page where possible
            max_h = 2.3
    else:
        max_w = (CONTENT_W - 0.5) / n_in_row - 0.25
        max_h = 2.6
    width = min(max_w, max_h * ar)
    return width, width / ar


def photos_html(person, tilt_seed):
    photos = person["photos"]
    if not photos:
        return ""
    figs = []
    for i, ph in enumerate(photos):
        long_note = sum(len(par) + 80 for par in person["message"]) > 1000
        wi, hi = photo_size(ph, len(photos), long_note)
        tilt = (-1.6, 1.3, -0.8, 1.8)[(tilt_seed + i) % 4]
        cap = f'<figcaption>{esc(ph["caption"])}</figcaption>' if ph.get("caption") else ""
        figs.append(
            f'<figure class="polaroid{" has-cap" if cap else ""}" style="--tilt:{tilt}deg">'
            f'<img src="../{esc(ph["print"])}" style="width:{wi:.2f}in;height:{hi:.2f}in" alt="">'
            f'{cap}</figure>')
    return f'<div class="photos n{len(photos)}">{"".join(figs)}</div>'


# ---------------------------------------------------------------- sections
def cover(data):
    return f"""
<section class="page cover">
  <div class="cover-top">
    <div class="kicker">a memory map</div>
    <h1>Julia <em>at</em> 24</h1>
    <p class="cover-sub">{esc(data["subtitle"])}</p>
  </div>
  <div class="cover-motif">{motif_svg(data["places"], 300)}</div>
  <div class="cover-foot">
    <span class="hand">happy 25th birthday</span>
    <span class="cover-count">{sum(len(p["people"]) for p in data["places"])} notes &middot; {len(data["places"])} places</span>
  </div>
</section>"""


def intro(data):
    places = data["places"]
    home = places[0]
    n_people = sum(len(p["people"]) for p in places)
    countries = {COUNTRY.get(p["key"], "United States") for p in places}
    far = max(places, key=lambda p: haversine_km(home, p))
    far_mi = haversine_km(home, far) * 0.621371
    site = (f'<p>There is an interactive version too, where you can fly between the pins: '
            f'<span class="url">{esc(SITE_URL)}</span></p>') if SITE_URL else ""
    return f"""
<section class="page intro">
  <h2 class="section-title">How this works</h2>
  <p class="lede">For Julia&rsquo;s 25th birthday, everyone who shared her 24th year was asked one thing:
  pick a place you went with her, write a short note, and send a photo if you have one.</p>
  <p>{n_people} people answered, from her rooftop in Chinatown to a seafood buffet in Ginza.
  Together they make a map of the year.</p>
  <p>Every place has a number. Find it on the poster, then find it here to read what was written there.
  The journey starts at home, wanders across New York, heads out of the city, and then goes around the world.</p>
  {site}
  <div class="stats">
    <div><b>{n_people}</b><span>notes</span></div>
    <div><b>{len(places)}</b><span>places</span></div>
    <div><b>{len(countries)}</b><span>countries</span></div>
    <div><b>{far_mi:,.0f}</b><span>miles from home, at the farthest pin ({esc(far["area"].split(",")[0])})</span></div>
  </div>
  <figure class="intro-motif">
    {motif_svg(places, 300, with_labels=True, pin_numbers=True)}
    <figcaption>The year, seen from home: every pin in its true direction from Julia&rsquo;s place,
    distance squashed.</figcaption>
  </figure>
</section>"""


def directory(data, pages):
    blocks = []
    for region, label in REGIONS:
        rows = []
        for p in data["places"]:
            if p["region"] != region:
                continue
            names = ", ".join(esc(display_name(x)) for x in p["people"])
            pg = pages.get(str(p["num"]), "")
            rows.append(
                f'<li><span class="badge sm">{p["num"]}</span>'
                f'<span class="dir-main"><span class="dir-place">{esc(p["name"])}</span>'
                f'<span class="dir-names">{names}</span></span>'
                f'<span class="dir-page">{pg}</span></li>')
        blocks.append(f'<div class="dir-group"><h3>{label}</h3><ol>{"".join(rows)}</ol></div>')
    return f"""
<section class="page directory">
  <h2 class="section-title">The directory</h2>
  {"".join(blocks)}
</section>"""


def place_section(p, tilt_base):
    sub = esc(p["area"])
    if p["full_name"]:
        sub = f'{esc(p["full_name"])} &middot; {sub}'
    blurb = f'<p class="blurb">{esc(p["blurb"])}</p>' if p["blurb"] else ""
    extra = ""
    if p.get("extra_pin"):
        extra = f'<p class="extra-pin">also on the map: {esc(p["extra_pin"]["name"])}</p>'
    notes = []
    for i, person in enumerate(p["people"]):
        rel = f' <span class="rel">{esc(person["relation"])}</span>' if person["relation"] else ""
        paras = "".join(f"<p>{esc(par)}</p>" for par in person["message"])
        notes.append(f"""
  <article class="note{' no-photo' if not person['photos'] else ''}">
    <div class="note-head">
      <h3 class="who">{esc(display_name(person))}{rel}</h3>
      {photos_html(person, tilt_base + i)}
    </div>
    <div class="msg">{paras}</div>
  </article>""")
    return f"""
<section class="page place" id="place-{p['num']}">
  <header class="place-head">
    <span class="badge">{p['num']}</span>
    <div>
      <h2>{esc(p['name'])}</h2>
      <div class="area">{sub}</div>
    </div>
  </header>
  {blurb}{extra}
  {''.join(notes)}
</section>"""


def closing(data):
    names = []
    for p in data["places"]:
        for x in p["people"]:
            names.append(f'<span>{esc(display_name(x))}</span>')
    return f"""
<section class="page closing">
  <div class="closing-inner">
    <p class="hand big">with love from everyone on this map</p>
    <div class="names">{"".join(names)}</div>
    <p class="closing-line">Happy 25th, Julia.</p>
  </div>
</section>"""


CSS = r"""
@page { size: 5.5in 8.5in; margin: 0.55in 0.5in 0.62in 0.5in; background: #FBF5EA;
  @bottom-center { content: counter(page); font: 500 8pt "DM Sans", sans-serif; color: #6B5F55; } }
@page cover { margin: 0; @bottom-center { content: none; } }
@page closing { @bottom-center { content: none; } }
:root { --paper:#FBF5EA; --ink:#2A2420; --muted:#6B5F55; --tomato:#E4572E; --sun:#F2B630;
  --water:#C9DFEA; --blue:#2D5D7B; --land:#EFE6D2; --park:#BFD6A8; --blossom:#F4A6B8; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 400 9.8pt/1.47 "DM Sans", sans-serif; }
.page { break-before: page; }
.page:first-child { break-before: auto; }
h1, h2, h3 { font-family: "Fraunces", serif; font-weight: 500; margin: 0; }
.hand { font-family: "Caveat", cursive; }

/* screen preview: show page boxes */
@media screen {
  body { background: #e9e2d4; padding: 24px 0; }
  .page { width: 5.5in; min-height: 8.5in; margin: 0 auto 24px; background: var(--paper);
    padding: 0.55in 0.5in 0.62in; box-shadow: 0 2px 12px rgba(0,0,0,.12); }
  .cover { padding: 0; }
}

/* cover */
.cover { page: cover; height: 8.5in; position: relative; overflow: hidden; display: flex;
  flex-direction: column; align-items: center; justify-content: space-between; padding: 0.7in 0.5in 0.6in;
  background: radial-gradient(circle at 50% 58%, #fff8ec 0, var(--paper) 60%); }
@media print { .cover { padding: 0.7in 0.5in 0.6in; } }
.cover-top { text-align: center; }
.kicker { font: 600 7.5pt "DM Sans"; letter-spacing: .28em; text-transform: uppercase; color: var(--tomato); }
.cover h1 { font-size: 54pt; line-height: 1; margin-top: 10pt; letter-spacing: -.01em; font-weight: 400; }
.cover h1 em { font-style: italic; font-weight: 300; color: var(--tomato); font-size: .72em; }
.cover-sub { font: italic 300 11.5pt/1.35 "Fraunces"; color: var(--muted); max-width: 3.4in; margin: 10pt auto 0; text-wrap: balance; }
.cover-motif { width: 3.7in; height: 3.7in; }
.cover-motif svg { width: 100%; height: 100%; }
.cover-foot { text-align: center; display: flex; flex-direction: column; gap: 2pt; }
.cover-foot .hand { font-size: 26pt; color: var(--tomato); line-height: 1; }
.cover-count { font: 500 7.5pt "DM Sans"; letter-spacing: .2em; text-transform: uppercase; color: var(--muted); }

.section-title { font-size: 21pt; margin-bottom: 12pt; }
.section-title::after { content: ""; display: block; width: 0.5in; height: 2.5pt; background: var(--tomato);
  border-radius: 2pt; margin-top: 7pt; }

/* intro */
.intro p { margin: 0 0 8pt; }
.intro .lede { font: 400 12pt/1.4 "Fraunces"; }
.intro .url { font-weight: 600; color: var(--blue); }
.stats { display: grid; grid-template-columns: repeat(3, auto) 1fr; gap: 0 16pt; margin: 10pt 0 6pt;
  padding: 9pt 0; border-top: 1px solid #d9cdb8; border-bottom: 1px solid #d9cdb8; align-items: start; }
.stats div { display: flex; flex-direction: column; }
.stats b { font: 500 20pt/1 "Fraunces"; color: var(--tomato); }
.stats span { font-size: 7.5pt; color: var(--muted); line-height: 1.25; margin-top: 3pt; }
.intro-motif { margin: 2pt auto 0; width: 3.15in; text-align: center; }
.intro-motif svg { width: 3.15in; height: 3.15in; overflow: visible; }
.intro-motif figcaption { font-size: 7.5pt; color: var(--muted); line-height: 1.3; margin-top: 4pt; }
.ring-lab { font: 500 7.5px "DM Sans"; fill: #2D5D7B; opacity: .8; }

/* directory */
.dir-group { margin-bottom: 7pt; break-inside: avoid; }
.dir-group h3 { font: 600 7.5pt "DM Sans"; letter-spacing: .22em; text-transform: uppercase; color: var(--blue);
  margin-bottom: 3pt; }
.dir-group ol { list-style: none; margin: 0; padding: 0; }
.dir-group li { display: flex; align-items: baseline; gap: 6pt; padding: 0.7pt 0; border-bottom: 1px dotted #d9cdb8; }
.dir-main { flex: 1; line-height: 1.15; }
.dir-place { font: 500 9.2pt "Fraunces"; }
.dir-names { font-size: 7.6pt; color: var(--muted); margin-left: 5pt; }
.dir-page { font: 500 8pt "DM Sans"; color: var(--muted); min-width: 0.22in; text-align: right; }

.badge { display: inline-flex; align-items: center; justify-content: center; flex: none;
  width: 0.42in; height: 0.42in; border-radius: 50%; background: var(--tomato); color: var(--paper);
  font: 600 14pt "Fraunces"; }
.badge.sm { width: 12pt; height: 12pt; font: 600 6.6pt "DM Sans"; position: relative; top: -0.5pt; }

/* places */
.place-head { display: flex; gap: 10pt; align-items: center; padding-bottom: 8pt; margin-bottom: 6pt;
  border-bottom: 1.5px solid var(--ink); break-after: avoid; }
.place-head h2 { font-size: 17pt; line-height: 1.1; }
.place-head .area { font: 500 7.4pt "DM Sans"; letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted); margin-top: 3pt; }
.blurb { font: italic 300 10pt/1.4 "Fraunces"; color: var(--muted); margin: 6pt 0 2pt; break-after: avoid; }
.extra-pin { font-size: 7.6pt; color: var(--blue); margin: 4pt 0 0; }
.extra-pin::before { content: "◆ "; color: var(--sun); }

.note { margin-top: 12pt; }
.note + .note { padding-top: 12pt; border-top: 1px dashed #d4c6ae; }
.note-head { break-inside: avoid; break-after: avoid; }
.who { font-family: "Caveat", cursive; font-weight: 600; font-size: 22pt; line-height: 1; color: var(--ink); }
.who .rel { font: 500 7.4pt "DM Sans"; letter-spacing: .14em; text-transform: uppercase; color: var(--tomato);
  margin-left: 4pt; position: relative; top: -3pt; }
.photos { display: flex; justify-content: center; align-items: flex-start; gap: 0.2in; margin: 10pt 0 12pt; }
.polaroid { margin: 0; background: #fff; padding: 0.07in 0.07in 0.22in; transform: rotate(var(--tilt));
  box-shadow: 0 1px 4px rgba(42,36,32,.18), 0 0 0 0.5px rgba(42,36,32,.08); }
.polaroid.has-cap { padding-bottom: 0.08in; }
.polaroid img { display: block; object-fit: cover; }
.polaroid figcaption { font: 600 12pt/1.1 "Caveat"; color: var(--muted); text-align: center; margin-top: 5pt;
  max-width: 2.2in; }
.no-photo .who { margin-bottom: 6pt; }
.msg p { margin: 0 0 6pt; orphans: 3; widows: 3; }
.msg p:last-child { margin-bottom: 0; }

/* filler: blank pages that pad the booklet to a multiple of 4 */
.filler-sub { font: italic 300 10pt "Fraunces"; color: var(--muted); margin: -4pt 0 10pt; }
.rule { height: 0.36in; border-bottom: 1px solid #ddd0ba; }
.pin-lab { font: 500 8.5px "DM Sans"; fill: #2A2420; paint-order: stroke; stroke: #C9DFEA; stroke-width: 2.5px; }
.pin-lab.home { font-weight: 600; fill: #E4572E; }

/* closing */
.closing { page: closing; }
.closing-inner { min-height: 7.2in; display: flex; flex-direction: column; justify-content: center; text-align: center; }
.big { font-size: 28pt; color: var(--tomato); line-height: 1.05; margin: 0 auto 16pt; max-width: 3.6in; text-wrap: balance; }
.names { display: flex; flex-wrap: wrap; justify-content: center; gap: 4pt 12pt; font: 400 11pt "Fraunces";
  max-width: 4in; margin: 0 auto; }
.closing-line { font: italic 300 13pt "Fraunces"; margin-top: 22pt; color: var(--muted); }
"""


def filler(kind, places):
    """Pages that pad the booklet to a multiple of 4, for guests to write in."""
    title, sub = (("Add your own pin", "A place you went with Julia that didn&rsquo;t make the map."),
                  ("Notes for Julia", "For the things that didn&rsquo;t fit anywhere else."))[kind % 2]
    lines = "".join('<div class="rule"></div>' for _ in range(17))
    return f"""
<section class="page filler">
  <h2 class="section-title">{title}</h2>
  <p class="filler-sub">{sub}</p>
  <div class="rules">{lines}</div>
</section>"""


def build(pages, fillers=0):
    data = json.load(open(os.path.join(ROOT, "data", "memmap.json"), encoding="utf-8"))
    body = [cover(data), intro(data), directory(data, pages)]
    for i, p in enumerate(data["places"]):
        body.append(place_section(p, i))
    body.extend(filler(k, data["places"]) for k in range(fillers))
    body.append(closing(data))
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Julia at 24 — Pamphlet</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@400;600&family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,300;1,9..144,400&display=block" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<!-- Generated by pamphlet/build_pamphlet.py from data/memmap.json. Edit those, not this file. -->
{"".join(body)}
</body>
</html>
"""
    with open(os.path.join(HERE, "pamphlet.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)


if __name__ == "__main__":
    pages = {}
    if "--pages" in sys.argv:
        pages = json.load(open(sys.argv[sys.argv.index("--pages") + 1], encoding="utf-8"))
    fillers = int(sys.argv[sys.argv.index("--fillers") + 1]) if "--fillers" in sys.argv else 0
    build(pages, fillers)
    print("wrote pamphlet/pamphlet.html")
