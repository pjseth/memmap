# Julia at 24: a memory map

A birthday gift for Julia's 25th: every place she went at 24, with notes and photos from the 33 people she shared them with.

Three pieces, all built from the same data so the numbers match everywhere:

| | What | Where |
|---|---|---|
| 🌍 | **Interactive globe**: free-roam Earth/Map views, hover pins for a preview, open full notes, or take the guided journey from New York around the world | `index.html` (open via any static server / GitHub Pages) |
| 🗺️ | **Poster**: 18×24 in, the world seen from Julia's place with NYC magnified in the middle | `poster/poster.pdf` |
| 📖 | **Pamphlet**: the directory, with every note and photo, in half-letter pages plus a print-and-fold booklet version | `pamphlet/pamphlet.pdf`, `pamphlet/pamphlet-booklet.pdf` |

Pin numbers are the same on the globe, the poster and the pamphlet.

## Editing the data

Everything editorial lives in `scripts/build_data.py`: display names, place names and journey order, which photo goes with whom, and message clean-up. After editing:

```sh
python3 scripts/build_data.py          # data/memmap.json, assets/data.js, assets/photos/*
python3 pamphlet/make_pdfs.py          # pamphlet (needs: pip install pypdf)
cd poster && npm install && ./render.sh # poster
```

Source material from the original doc (CSV/JSON/docx and the original photos) is kept in `source/`.

## Viewing the site locally

```sh
python3 -m http.server 8000   # then open http://localhost:8000
```

Handy links: `#stop=7` opens a stop, `#stop=1&tour` starts the journey there, `#roam` skips the intro, `#mode=map` uses the illustrated map instead of satellite.

## Credits

Satellite imagery © Esri, Maxar, Earthstar Geographics. Map tiles © OpenFreeMap, © OpenMapTiles, data © OpenStreetMap contributors. Built with MapLibre GL JS.
