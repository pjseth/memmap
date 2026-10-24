#!/bin/sh
# Renders poster.html -> poster.pdf (18x24 in, vector) and poster-preview.png.
set -e
cd "$(dirname "$0")"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
URL="file://$PWD/poster.html"
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=15000 \
  --print-to-pdf="$PWD/poster.pdf" "$URL" 2>/dev/null
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=15000 \
  --window-size=1350,1800 --screenshot="$PWD/poster-preview.png" "$URL" 2>/dev/null
echo "wrote poster.pdf and poster-preview.png"
