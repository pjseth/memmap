# Pamphlet: the directory for the memory map

A 40-page half-letter booklet (5.5 × 8.5 in). It has a cover, a "how this works" page with a small
"seen from home" map, a directory of all 26 places (the numbers match the poster pins), one
section per place with every friend's note and photos, pages for guests to write in, and a closing
page with all 33 names.

| File | What it is |
| --- | --- |
| `pamphlet.pdf` | The pages in reading order. Use it for screens, or for a print shop that does its own imposition. |
| `pamphlet-booklet.pdf` | The same pages laid out 2-up on landscape US Letter, in saddle-stitch order. Print this at home. |
| `pamphlet.html` | Generated HTML. Open it in a browser to preview the pages. |
| `build_pamphlet.py` | Writes `pamphlet.html` from `../data/memmap.json`. |
| `make_pdfs.py` | Renders both PDFs with headless Chrome. |

## Printing at home

1. Open `pamphlet-booklet.pdf` and print it on **US Letter**, **landscape**, **double-sided, flip on short edge**, at **100% / actual size** (not "fit to page").
2. That gives 10 sheets. Keep them in order, fold the stack in half, and staple twice along the fold.
3. Heavier paper (28–32 lb, or 100 gsm or more) keeps the photos from showing through.

If your printer has no duplex option, print the odd sheets, put the stack back in, and then print the even sheets. Run a test with the first two sheets before printing the whole booklet.

## Print shop

Send `pamphlet.pdf` and ask for a **5.5 × 8.5 in saddle-stitched booklet, 40 pages, self-cover**. The pages have no bleed, and the paper-colored background runs to the edge. If the shop wants bleed, ask them to scale to 101% or to use a cream stock.

## Rebuilding after edits

Make any data change in `scripts/build_data.py` first, such as giving the Wu's Wonton friend their name, and rerun it. Then run:

```sh
pip install pypdf
python3 pamphlet/make_pdfs.py      # from the repo root; needs Google Chrome
```

`make_pdfs.py` renders the pages twice. The first pass finds each place's page number for the directory. The second pass adds "Add your own pin" or "Notes for Julia" pages so the page count is a multiple of 4. To print the interactive map's address on the intro page, set `SITE_URL` in `build_pamphlet.py`.
