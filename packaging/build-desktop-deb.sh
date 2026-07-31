#!/usr/bin/env bash
# build-desktop-deb.sh — Build the Tauri desktop .deb
#   health-manager-desktop_<version>_amd64.deb
#
# Pipeline:
#   1. build the React frontend (-> frontend/dist)
#   2. freeze the FastAPI backend into a PyInstaller onefile (-> the sidecar)
#   3. stage the sidecar under desktop/binaries as health-manager-backend-<triple>
#      (Tauri's externalBin sidecar resolution requires the target-triple suffix)
#   4. cargo tauri build  ->  desktop/target/release/bundle/deb/*.deb
#
# Prerequisites: node + npm, uv, rust (+ tauri-cli), the WebKit/GTK dev headers
# (libwebkit2gtk-4.1-dev, libgtk-3-dev, librsvg2-dev, libayatana-appindicator3-dev),
# and pyinstaller (a backend dev dependency: uv add --dev pyinstaller).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Reproducibility: refuse to build from a dirty working tree unless explicitly
# overridden (HM_ALLOW_DIRTY=1) — a .deb built from uncommitted edits can't be
# traced back to a commit.
if [ -z "${HM_ALLOW_DIRTY:-}" ] && ! git -C "$PROJECT_ROOT" diff-index --quiet HEAD --; then
  echo "Error: dirty working tree — commit or stash first (or HM_ALLOW_DIRTY=1 to override)" >&2
  git -C "$PROJECT_ROOT" status --short >&2
  exit 1
fi

# ── Version (from backend/pyproject.toml) + host target triple ────────────────
VERSION="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' \
    "${PROJECT_ROOT}/backend/pyproject.toml" | head -n1)"
if [ -z "${VERSION}" ]; then
    echo "Error: could not determine version from backend/pyproject.toml" >&2
    exit 1
fi
TARGET_TRIPLE="$(rustc -vV | sed -nE 's/^host: //p')"
if [ -z "${TARGET_TRIPLE}" ]; then
    echo "Error: could not determine rust target triple" >&2
    exit 1
fi

SIDECAR_BIN="${PROJECT_ROOT}/desktop/binaries/health-manager-backend-${TARGET_TRIPLE}"

echo "=== Building health-manager-desktop_${VERSION}_amd64.deb (target: ${TARGET_TRIPLE}) ==="

# ── 1. Frontend ───────────────────────────────────────────────────────────────
echo "[1/4] Building frontend..."
cd "${PROJECT_ROOT}/frontend"
npm ci --prefer-offline
npm run build

# ── 2. PyInstaller sidecar ───────────────────────────────────────────────────
echo "[2/4] Freezing backend with PyInstaller..."
cd "${PROJECT_ROOT}/backend"
uv run pyinstaller health-manager-backend.spec --noconfirm --clean

# ── 3. Stage sidecar for Tauri externalBin ────────────────────────────────────
echo "[3/4] Staging sidecar -> ${SIDECAR_BIN#${PROJECT_ROOT}/}"
mkdir -p "${PROJECT_ROOT}/desktop/binaries"
cp "${PROJECT_ROOT}/backend/dist/health-manager-backend" "${SIDECAR_BIN}"
chmod +x "${SIDECAR_BIN}"

# ── 4. Sync version + cargo tauri build ───────────────────────────────────────
echo "[4/4] Building Tauri .deb (release LTO; this takes a few minutes)..."
cd "${PROJECT_ROOT}/desktop"
python3 - "$VERSION" <<'PY'
import json, pathlib, sys
version = sys.argv[1]
p = pathlib.Path("tauri.conf.json")
conf = json.loads(p.read_text())
conf["version"] = version
p.write_text(json.dumps(conf, indent=2) + "\n")
print(f"      synced tauri.conf.json version -> {version}")
PY

cargo tauri build

# ── Locate + report the produced .deb ─────────────────────────────────────────
DEB="$(find "${PROJECT_ROOT}/desktop/target" -path '*bundle/deb/*.deb' -print -quit 2>/dev/null || true)"
echo
echo "=== Build complete ==="
if [ -n "${DEB}" ]; then
    echo "  Package: ${DEB}"
    echo "  Size:    $(du -sh "${DEB}" | cut -f1)"
    echo
    echo "  Install:   sudo apt install ./${DEB##*/}"
    echo "  Remove:    sudo apt remove health-manager-desktop"
    echo "  Run:       Health Manager (application menu) or health-manager-desktop"
else
    echo "  WARNING: no .deb found under desktop/target/**/bundle/deb/" >&2
    exit 1
fi
