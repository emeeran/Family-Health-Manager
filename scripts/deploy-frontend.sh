#!/bin/bash
set -e

SRC="/home/em/code/finished/health-manager/frontend/dist"
DST="/opt/health-manager/frontend"

echo "=== Deploying frontend ==="
echo "Source: $SRC"
echo "Dest:   $DST"

if [ ! -f "$SRC/index.html" ]; then
  echo "ERROR: Build not found. Run 'npx vite build' in frontend/ first."
  exit 1
fi

echo "Files to deploy:"
ls "$SRC/assets/" | wc -l

echo "Clearing old assets..."
sudo rm -rf "$DST/assets"
sudo rm -f "$DST/index.html"

echo "Copying new build..."
sudo cp "$SRC/index.html" "$DST/index.html"
sudo cp -r "$SRC/assets" "$DST/assets"

# Copy other static files if they exist
for f in favicon.ico favicon.svg manifest.json icon-192.png icon-512.png sw.js; do
  if [ -f "$SRC/$f" ]; then
    sudo cp "$SRC/$f" "$DST/$f"
  fi
done

echo ""
echo "=== Verify ==="
echo "index.html size: $(wc -c < "$DST/index.html") bytes"
echo "Assets count:    $(ls "$DST/assets/" | wc -l)"
if ls "$DST/assets/" | grep -q member-assistant; then
  echo "OK: member-assistant page found"
else
  echo "WARN: member-assistant page NOT found"
fi

echo ""
echo "Done."
