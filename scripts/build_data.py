"""Build the cleaned memory-map dataset + web/print photos from source/.

Run from the repo root:  python3 scripts/build_data.py

Outputs
  data/memmap.json          places (in journey order) with the people at each
  assets/data.js            same data as `window.MEMMAP = {...}` for the web map
  assets/photos/web/*.jpg   max 1600px, EXIF stripped
  assets/photos/thumb/*.jpg 320px square crops for map pins
  assets/photos/print/*.jpg max 3000px, for the poster + pamphlet

Everything editorial (display names, place names, photo reassignment, message
clean-up) lives in the tables below so it can be tweaked by hand.
"""
import json
import os
import re

from PIL import Image, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source")
SRC_PHOTOS = os.path.join(SRC, "photos_original", "photos")
OUT_ASSETS = os.path.join(ROOT, "assets", "photos")

# --------------------------------------------------------------------------
# People: display name, relation, photos (original file names), captions.
# Photos for entries 6-15 were shifted by one entry in the organized doc
# (e.g. Lareina's Mimi's froyo photo sat under Hannah), so they are reassigned
# here to match each message.
# --------------------------------------------------------------------------
PEOPLE = {
    1: dict(name="Ella", photos=["01_Ella_1.png"]),
    2: dict(name="Mom", relation="Marcia", photos=["02_Marcia_1.jpg"]),
    3: dict(name="Alicia", photos=["03_Alicia_1.jpg"]),
    4: dict(name="Marcos", photos=["04_Marcos_1.jpg"]),
    5: dict(name="Ashna", photos=["05_Ashna_1.jpg"]),
    6: dict(name="Isabella", photos=["05_Ashna_2.jpg", "05_Ashna_3.jpg"]),
    7: dict(name="LJ", photos=["06_Isabella_1.png"]),
    8: dict(name="Alan", photos=["07_LJ_1.png"]),
    9: dict(name="A friend", needs_name=True, photos=["08_Alan_1.png"]),
    10: dict(name="Caroline", photos=["09_Wus-Wonton_1.png"]),
    11: dict(name="Zoe", relation="cousin", photos=["10_Caroline_1.png"]),
    12: dict(name="Hannah", relation="cousin", photos=["11_Zoe_1.png"]),
    13: dict(name="Lareina", photos=["12_Hannah_2.png", "12_Hannah_1.png"]),
    14: dict(name="Kim", photos=["13_Lareina_1.png"]),
    15: dict(name="Angela", photos=["14_Kim_1.png"]),
    16: dict(name="Tatiana", photos=["16_Tatiana_1.jpg"]),
    17: dict(name="Lance", photos=["17_Lance_1.jpg"]),
    18: dict(name="Stella", relation="roommate & cousin", photos=["18_Stella_1.jpg"]),
    19: dict(name="Sam Li", photos=["19_Sam-Li_1.jpg"]),
    20: dict(name="Meagan", photos=["20_Meagan_1.jpg"],
             captions={"20_Meagan_1.jpg": "might be our only pic of just the two of us"}),
    21: dict(name="Jonathan", photos=["21_Jonathan_1.jpg"]),
    22: dict(name="Dad", photos=["22_Dad_1.jpg"]),
    23: dict(name="Mick", photos=["23_Mick_1.jpg"]),
    24: dict(name="Gabby", photos=["24_Gabby_1.jpg"]),
    25: dict(name="Noah", relation="cousin", photos=["25_Noah_1.jpg"]),
    26: dict(name="Kaavya", photos=["26_Kaavya_1.jpg"]),
    27: dict(name="PJ", photos=["27_PJ_1.jpg", "27_PJ_2.jpg"]),
    28: dict(name="Grace", photos=["28_Grace_1.jpg"]),
    29: dict(name="Chris", photos=["29_Chris_1.jpg"]),
    30: dict(name="Jui", photos=["30_Jui_1.jpg"]),
    31: dict(name="Mint", photos=["31_Mint_1.jpg"]),
    32: dict(name="Pavin", photos=["32_Pavin_1.jpg"]),
    33: dict(name="Rachel", photos=["33_Rachel_1.jpg"]),
}

# Photos that arrived sideways (degrees clockwise).
ROTATE_CW = {"27_PJ_1.jpg": 90, "27_PJ_2.jpg": 90}

# Where to centre square pin crops (fraction of height; faces sit high).
THUMB_FOCUS_Y = {"01_Ella_1.png": 0.35, "11_Zoe_1.png": 0.45, "28_Grace_1.jpg": 0.4}

# --------------------------------------------------------------------------
# Message clean-up: strip location headers people typed for PJ, and put back
# the inline emoji that came through as tiny images (skipped_emoji_icons/).
# --------------------------------------------------------------------------
MESSAGE_FIXES = {
    4: [("Her house - ", "")],
    7: [("included me in  You", "included me in 🙂 You")],
    10: [("* Spongies ", "")],
    11: [(re.compile(r"^Julia Birthday Project: Location: .*? Birthday note: "), ""),
         (re.compile(r"harvests$"), "harvests 🌸🌼🥚🐣")],
    12: [("birthday  for", "birthday ❤️ for"), ("dms  i’ve", "dms 🥲 i’ve")],
    13: [("juju  even", "juju 💌 even"), ("night  i still", "night 🐟🐟 i still"),
         (re.compile(r"day 1$"), "day 1 🎁🎁🎁")],
    14: [(" It’s the Brooklyn botanic", "")],
    17: [(" this was at beacon ny.", "")],
    18: [(re.compile(r"^this is at julia's place \(129 Lafayette St\)\n"), "")],
    20: [(re.compile(r"^beacon, ny \(might be our only pic of just the two of us\)\n"), "")],
    21: [(re.compile(r"^the hamptons\n+"), "")],
    27: [(re.compile(r"^universal studios japan\n"), "")],
    31: [(re.compile(r"^Universal studios Japan\n+"), "")],
}

# --------------------------------------------------------------------------
# Places, in journey order (home first, then out across NYC, the region, and
# the world). No street addresses are published for private homes.
# --------------------------------------------------------------------------
PLACES = [
    dict(key="home", name="Julia's place", area="Chinatown, Manhattan", region="nyc",
         lat=40.71889, lng=-73.99989, people=[2, 18, 1, 6, 4, 28, 32],
         blurb="Home base: hot pot nights, rooftop charcuterie, Lupa experiments and one very spilled bag of popcorn."),
    dict(key="spongies", name="Spongies Cafe", area="Little Italy, Manhattan", region="nyc",
         lat=40.71798, lng=-73.99882, people=[10]),
    dict(key="bao", name="The basement bao joint", area="East Broadway, Chinatown", region="nyc",
         lat=40.71384, lng=-73.99418, people=[23], full_name="Fu Zhou Wei Zhong Wei Jia Xiang Feng Wei"),
    dict(key="wus", name="Wu's Wonton King", area="Lower East Side, Manhattan", region="nyc",
         lat=40.71383, lng=-73.98996, people=[9]),
    dict(key="ludlow", name="Ludlow Flea", area="Lower East Side, Manhattan", region="nyc",
         lat=40.72105, lng=-73.98804, people=[7]),
    dict(key="recente", name="Recente", area="East Village, Manhattan", region="nyc",
         lat=40.73061, lng=-73.98586, people=[19]),
    dict(key="mimis", name="Mimi's Frozen Yogurt", area="Nolita, Manhattan", region="nyc",
         lat=40.72238, lng=-73.99689, people=[13]),
    dict(key="sobs", name="SOB's", area="Hudson Square, Manhattan", region="nyc",
         lat=40.72845, lng=-74.00513, people=[5], full_name="Sounds of Brazil"),
    dict(key="msg", name="Madison Square Garden", area="Midtown, Manhattan", region="nyc",
         lat=40.7505, lng=-73.99344, people=[25]),
    dict(key="pennclub", name="The Penn Club", area="Midtown, Manhattan", region="nyc",
         lat=40.7553555, lng=-73.9817721, people=[15]),
    dict(key="centralpark", name="Central Park, The Mall", area="Central Park, Manhattan", region="nyc",
         lat=40.77235, lng=-73.97159, people=[8]),
    dict(key="sonic", name="Sonic", area="Long Island City, Queens", region="nyc",
         lat=40.74387, lng=-73.92778, people=[26]),
    dict(key="mccarren", name="McCarren Park Greenmarket", area="Williamsburg, Brooklyn", region="nyc",
         lat=40.72104, lng=-73.95135, people=[24],
         extra_pin=dict(name="Oberon & the secret tunnel", lat=40.71869, lng=-73.95487)),
    dict(key="williamsburg", name="Williamsburg waterfront", area="Williamsburg, Brooklyn", region="nyc",
         lat=40.7081156, lng=-73.9570696, people=[3]),
    dict(key="botanic", name="Brooklyn Botanic Garden", area="Prospect Heights, Brooklyn", region="nyc",
         lat=40.6685798, lng=-73.9644696, people=[14]),
    dict(key="oley", name="Oley", area="Pennsylvania", region="northeast",
         lat=40.38875, lng=-75.79142, people=[33]),
    dict(key="beacon", name="Beacon", area="Hudson Valley, New York", region="northeast",
         lat=41.50482, lng=-73.96958, people=[17, 20]),
    dict(key="hamptons", name="The Hamptons", area="Long Island, New York", region="northeast",
         lat=40.92462, lng=-72.35479, people=[21]),
    dict(key="harvard", name="Harvard", area="Cambridge, Massachusetts", region="northeast",
         lat=42.37444, lng=-71.11825, people=[22]),
    # Private home: city-level pin only.
    dict(key="vancouver", name="Vancouver Thanksgiving", area="Richmond, British Columbia", region="world",
         lat=49.123, lng=-123.174, people=[11]),
    dict(key="ginza", name="Seafood Buffet Ginza Happo", area="Ginza, Tokyo", region="world",
         lat=35.66721, lng=139.76182, people=[27]),
    dict(key="kiyomizu", name="Kiyomizu-dera", area="Kyoto, Japan", region="world",
         lat=34.99467, lng=135.78466, people=[30]),
    dict(key="shinsaibashi", name="Shinsaibashi-suji", area="Osaka, Japan", region="world",
         lat=34.67251, lng=135.50137, people=[29]),
    dict(key="usj", name="Universal Studios Japan", area="Osaka, Japan", region="world",
         lat=34.66568, lng=135.43232, people=[31]),
    dict(key="chengdu", name="Chengdu", area="Sichuan, China", region="world",
         lat=30.57226, lng=104.06651, people=[16]),
    dict(key="manila", name="Robinsons Place Manila", area="Manila, Philippines", region="world",
         lat=14.57584, lng=120.98394, people=[12],
         blurb="This year lived in iMessage and Instagram DMs."),
]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def clean_message(pid, msg):
    for old, new in MESSAGE_FIXES.get(pid, []):
        if isinstance(old, re.Pattern):
            msg, n = old.subn(new, msg)
        else:
            n = msg.count(old)
            msg = msg.replace(old, new)
        if n == 0:
            raise SystemExit(f"message fix for entry {pid} did not match: {old!r}")
    msg = msg.replace("\r", "")
    paras = [re.sub(r"[ \t]+", " ", p).strip() for p in re.split(r"\n\s*\n|\n", msg)]
    return [p for p in paras if p]


def load_image(fname):
    im = ImageOps.exif_transpose(Image.open(os.path.join(SRC_PHOTOS, fname)))
    if fname in ROTATE_CW:
        im = im.rotate(-ROTATE_CW[fname], expand=True)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    return im.convert("RGB")


def save_resized(im, path, max_side, quality):
    im = im.copy()
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    im.save(path, "JPEG", quality=quality, optimize=True, progressive=True)  # no EXIF carried over
    return im.size


def save_thumb(im, path, fname, size=320):
    w, h = im.size
    side = min(w, h)
    fy = THUMB_FOCUS_Y.get(fname, 0.42)
    left = (w - side) // 2
    top = int(min(max(h * fy - side / 2, 0), h - side))
    im.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS).save(
        path, "JPEG", quality=85, optimize=True)


def main():
    raw = {e["id"]: e for e in json.load(open(os.path.join(SRC, "mem map data FINAL (33 entries).json")))}
    for sub in ("web", "thumb", "print"):
        os.makedirs(os.path.join(OUT_ASSETS, sub), exist_ok=True)

    people = {}
    for pid, meta in PEOPLE.items():
        photos = []
        for i, fname in enumerate(meta["photos"], 1):
            base = f"{pid:02d}-{slug(meta['name'] if not meta.get('needs_name') else 'friend')}-{i}"
            im = load_image(fname)
            w, h = save_resized(im, os.path.join(OUT_ASSETS, "web", base + ".jpg"), 1600, 82)
            save_resized(im, os.path.join(OUT_ASSETS, "print", base + ".jpg"), 3000, 92)
            save_thumb(im, os.path.join(OUT_ASSETS, "thumb", base + ".jpg"), fname)
            photos.append(dict(
                web=f"assets/photos/web/{base}.jpg",
                thumb=f"assets/photos/thumb/{base}.jpg",
                print=f"assets/photos/print/{base}.jpg",
                w=w, h=h, src_px=max(im.size),
                caption=meta.get("captions", {}).get(fname, ""),
                original=fname,
            ))
        people[pid] = dict(
            id=pid,
            name=meta["name"],
            relation=meta.get("relation", ""),
            needs_name=meta.get("needs_name", False),
            message=clean_message(pid, raw[pid]["message"]),
            photos=photos,
        )

    places = []
    seen = set()
    for num, pl in enumerate(PLACES, 1):
        seen.update(pl["people"])
        places.append(dict(
            num=num,
            key=pl["key"],
            name=pl["name"],
            full_name=pl.get("full_name", ""),
            area=pl["area"],
            region=pl["region"],
            lat=pl["lat"],
            lng=pl["lng"],
            blurb=pl.get("blurb", ""),
            extra_pin=pl.get("extra_pin"),
            people=[dict(people[p], place=pl["key"]) for p in pl["people"]],
        ))
    missing = set(PEOPLE) - seen
    if missing:
        raise SystemExit(f"people not placed on the map: {sorted(missing)}")

    data = dict(
        title="Julia at 24",
        subtitle="the places she went, and the people she shared them with",
        places=places,
    )
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "memmap.json"), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(ROOT, "assets", "data.js"), "w") as f:
        f.write("// Generated by scripts/build_data.py. Edit that script, not this file.\n")
        f.write("window.MEMMAP = " + json.dumps(data, ensure_ascii=False) + ";\n")
    print(f"{len(places)} places, {sum(len(p['people']) for p in places)} people, "
          f"{sum(len(x['photos']) for x in people.values())} photos")


if __name__ == "__main__":
    main()
