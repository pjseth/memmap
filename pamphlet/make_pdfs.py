"""Render the pamphlet PDFs with headless Chrome.

Run from the repo root:  python3 pamphlet/make_pdfs.py      (needs: pip install pypdf)

  1. builds pamphlet.html and renders it once to find each place's page
  2. rebuilds with directory page numbers + "add your own pin" pages so the
     page count is a multiple of 4, and renders pamphlet.pdf (reading order)
  3. imposes pamphlet-booklet.pdf: 2-up on landscape US Letter, saddle-stitch
     order, for double-sided printing (flip on short edge), fold and staple
"""
import json
import os
import subprocess
import sys
import tempfile

from pypdf import PageObject, PdfReader, PdfWriter, Transformation

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_pamphlet  # noqa: E402

CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
HTML = os.path.join(HERE, "pamphlet.html")
PDF = os.path.join(HERE, "pamphlet.pdf")
BOOKLET = os.path.join(HERE, "pamphlet-booklet.pdf")
PT = 72


def render(out):
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([
            CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
            "--generate-pdf-document-outline", f"--user-data-dir={profile}",
            "--run-all-compositor-stages-before-draw", "--virtual-time-budget=15000",
            f"--print-to-pdf={out}", "file://" + HTML,
        ], check=True, capture_output=True)


def place_pages(pdf):
    """Map place number -> page number, from the PDF outline (h2 headings)."""
    reader = PdfReader(pdf)
    titles = {}
    for p in json.load(open(os.path.join(build_pamphlet.ROOT, "data", "memmap.json"), encoding="utf-8"))["places"]:
        titles.setdefault(p["name"], p["num"])

    found = {}

    def walk(items):
        for it in items:
            if isinstance(it, list):
                walk(it)
            elif it.title.strip() in titles and str(titles[it.title.strip()]) not in found:
                found[str(titles[it.title.strip()])] = reader.get_destination_page_number(it) + 1

    walk(reader.outline)
    return found, len(reader.pages)


def impose(src, dst):
    reader = PdfReader(src)
    pages = list(reader.pages)
    n = len(pages)
    assert n % 4 == 0, n
    w = float(pages[0].mediabox.width)
    h = float(pages[0].mediabox.height)
    writer = PdfWriter()
    for i in range(n // 4):
        for left, right in ((n - 1 - 2 * i, 2 * i), (2 * i + 1, n - 2 - 2 * i)):
            sheet = PageObject.create_blank_page(width=2 * w, height=h)
            sheet.merge_transformed_page(pages[left], Transformation())
            sheet.merge_transformed_page(pages[right], Transformation().translate(tx=w))
            writer.add_page(sheet)
    with open(dst, "wb") as f:
        writer.write(f)
    return n // 4


def main():
    build_pamphlet.build({}, 0)
    render(PDF)
    pages, n = place_pages(PDF)
    fillers = (-n) % 4
    for _ in range(3):
        build_pamphlet.build(pages, fillers)
        render(PDF)
        new_pages, n = place_pages(PDF)
        if new_pages == pages and n % 4 == 0:
            break
        pages, fillers = new_pages, fillers + ((-n) % 4)
    else:
        raise SystemExit("page numbers did not settle")
    n_places = len(json.load(open(os.path.join(build_pamphlet.ROOT, "data", "memmap.json"), encoding="utf-8"))["places"])
    missing = n_places - len(pages)
    if missing:
        print(f"warning: {missing} places not found in the PDF outline")
    sheets = impose(PDF, BOOKLET)
    print(f"pamphlet.pdf: {n} pages ({fillers} 'add your own pin' pages); "
          f"pamphlet-booklet.pdf: {sheets} sheets, {2 * sheets} sides")


if __name__ == "__main__":
    main()
