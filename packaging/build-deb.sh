#!/usr/bin/env bash
# build-deb.sh — Build health-manager_X.Y.Z_amd64.deb
#
# Prerequisites:
#   - Node.js (for frontend build)
#   - uv (for Python dependency resolution)
#   - dpkg-deb (for packaging)
#
# Usage:
#   bash packaging/build-deb.sh [VERSION]
#
# The VERSION defaults to what's in backend/pyproject.toml, overridable via arg.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STAGING="${PROJECT_ROOT}/staging"

# ── Version ──────────────────────────────────────────────────────────────────
# Default to the version declared in backend/pyproject.toml unless overridden.
PYPROJECT_VERSION="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' \
    "${PROJECT_ROOT}/backend/pyproject.toml" | head -n1)"
VERSION="${1:-${PYPROJECT_VERSION}}"
if [ -z "${VERSION}" ]; then
    echo "Error: could not determine version (pass it as arg, or set 'version' in backend/pyproject.toml)" >&2
    exit 1
fi
PKG_NAME="health-manager"
DEB_FILE="${PROJECT_ROOT}/${PKG_NAME}_${VERSION}_amd64.deb"

echo "=== Building ${PKG_NAME}_${VERSION}_amd64.deb ==="

# ── Cleanup previous build ───────────────────────────────────────────────────
rm -rf "${STAGING}"
mkdir -p "${STAGING}"

# ── 1. Build frontend ───────────────────────────────────────────────────────
echo "[1/8] Building frontend..."
cd "${PROJECT_ROOT}/frontend"
npm ci --prefer-offline
npm run build

# ── 2. Download Caddy ───────────────────────────────────────────────────────
echo "[2/8] Downloading Caddy..."
CADDY_VERSION="2.9.1"
CADDY_URL="https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz"
CADDY_TMP="$(mktemp -d)"
curl -fsSL "${CADDY_URL}" | tar -xz -C "${CADDY_TMP}" caddy
echo "      Caddy v${CADDY_VERSION} downloaded."

# ── 3. Create staging directory structure ────────────────────────────────────
echo "[3/8] Creating staging directories..."
mkdir -p "${STAGING}/DEBIAN"
mkdir -p "${STAGING}/opt/health-manager/backend"
mkdir -p "${STAGING}/opt/health-manager/frontend"
mkdir -p "${STAGING}/etc/health-manager"
mkdir -p "${STAGING}/etc/systemd/system"
mkdir -p "${STAGING}/var/lib/health-manager/data"
mkdir -p "${STAGING}/var/log/health-manager"
mkdir -p "${STAGING}/usr/share/applications"
mkdir -p "${STAGING}/usr/share/icons/hicolor/scalable/apps"

# ── 4. Copy backend source ──────────────────────────────────────────────────
echo "[4/8] Copying backend source..."
cp -r "${PROJECT_ROOT}/backend/app" "${STAGING}/opt/health-manager/backend/"
cp -r "${PROJECT_ROOT}/backend/alembic" "${STAGING}/opt/health-manager/backend/"
cp "${PROJECT_ROOT}/backend/alembic.ini" "${STAGING}/opt/health-manager/backend/"
cp "${PROJECT_ROOT}/backend/pyproject.toml" "${STAGING}/opt/health-manager/backend/"
cp "${SCRIPT_DIR}/db-setup.py" "${STAGING}/opt/health-manager/backend/"

# Repo-root prompts/*.md — runtime prompt templates loaded by the AI pipeline
# (extraction.md, transcription_report.md, consultation_summary.md). The loaders
# resolve 5 parents up from backend/app/services/ai/, i.e. /opt/health-manager/,
# so install them there (only the .md templates — not the SDD .txt artefacts).
mkdir -p "${STAGING}/opt/health-manager/prompts"
cp "${PROJECT_ROOT}"/prompts/*.md "${STAGING}/opt/health-manager/prompts/"

# ── 5. Copy frontend build output ───────────────────────────────────────────
echo "[5/8] Copying frontend build..."
cp -r "${PROJECT_ROOT}/frontend/dist/." "${STAGING}/opt/health-manager/frontend/"

# ── 6. Create Python virtualenv and install dependencies ─────────────────────
echo "[6/8] Creating Python virtualenv and installing dependencies..."
python3 -m venv "${STAGING}/opt/health-manager/backend/.venv"
VENV_PIP="${STAGING}/opt/health-manager/backend/.venv/bin/pip"

# Use uv to resolve a locked requirements.txt from pyproject.toml
REQUIREMENTS="$(mktemp)"
cd "${PROJECT_ROOT}/backend"
uv pip compile pyproject.toml -o "${REQUIREMENTS}"
echo "      Resolved $(grep -c '==' "${REQUIREMENTS}") packages."

# Install resolved dependencies into the staging venv
"${VENV_PIP}" install --quiet -r "${REQUIREMENTS}"
rm -f "${REQUIREMENTS}"

# Note: the project source is copied directly to /opt/health-manager/backend/app/
# and the systemd unit sets WorkingDirectory=/opt/health-manager/backend,
# so no pip-install of the project itself is needed.

echo "      Virtualenv ready."

# Fix venv paths: rewrite shebangs and pyvenv.cfg to use the install path
# instead of the build machine's staging path.
VENV_BIN="${STAGING}/opt/health-manager/backend/.venv/bin"
INSTALL_PREFIX="/opt/health-manager/backend/.venv"
STAGING_PREFIX="${STAGING}/opt/health-manager/backend/.venv"

# Fix pyvenv.cfg
sed -i "s|${STAGING_PREFIX}|${INSTALL_PREFIX}|g" "${STAGING_PREFIX}/pyvenv.cfg"

# Fix shebangs in all bin/ scripts
for script in "${VENV_BIN}"/*; do
    if [ -f "${script}" ] && head -1 "${script}" | grep -q "^#!"; then
        sed -i "1s|${STAGING_PREFIX}|${INSTALL_PREFIX}|" "${script}"
    fi
done
echo "      Venv paths fixed for install location."

# ── 7. Copy Caddy binary, config, and systemd units ──────────────────────────
echo "[7/8] Assembling package files..."
cp "${CADDY_TMP}/caddy" "${STAGING}/opt/health-manager/caddy"
chmod +x "${STAGING}/opt/health-manager/caddy"
rm -rf "${CADDY_TMP}"

cp "${SCRIPT_DIR}/Caddyfile" "${STAGING}/etc/health-manager/Caddyfile"
cp "${SCRIPT_DIR}/config.env" "${STAGING}/etc/health-manager/config.env"
cp "${SCRIPT_DIR}/systemd/health-manager.service" "${STAGING}/etc/systemd/system/"
cp "${SCRIPT_DIR}/systemd/health-manager-caddy.service" "${STAGING}/etc/systemd/system/"
cp "${SCRIPT_DIR}/systemd/health-manager-restore.path" "${STAGING}/etc/systemd/system/"
cp "${SCRIPT_DIR}/systemd/health-manager-restore.service" "${STAGING}/etc/systemd/system/"

# Privileged disaster-recovery restore helper (root-run, triggered by the
# health-manager-restore.path unit when the app writes a restore-request flag).
cp "${SCRIPT_DIR}/restore-archive.sh" "${STAGING}/opt/health-manager/restore-archive.sh"
chmod 755 "${STAGING}/opt/health-manager/restore-archive.sh"

# Desktop entry and icon
cp "${SCRIPT_DIR}/health-manager.desktop" "${STAGING}/usr/share/applications/"
cp "${PROJECT_ROOT}/frontend/public/favicon.svg" "${STAGING}/usr/share/icons/hicolor/scalable/apps/health-manager.svg"

# ── Tidy: strip stray Python caches/bytecode before packaging ────────────────
# The copied app/ source may carry __pycache__/.pyc from local dev/test runs,
# and the staged venv carries installed-package bytecode. Both are regenerated
# by the interpreter at runtime, so drop them for a leaner, source-clean package.
echo "[7.5/8] Tidying staged Python trees..."
find "${STAGING}/opt/health-manager/backend" -type d \
    \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) \
    -prune -exec rm -rf {} +
find "${STAGING}/opt/health-manager/backend" -type f \
    \( -name '*.pyc' -o -name '*.pyo' \) -delete

# ── 8. Generate DEBIAN control files ─────────────────────────────────────────
echo "[8/8] Generating DEBIAN control files..."

# Compute installed size (in KB)
INSTALLED_SIZE=$(du -sk "${STAGING}" | cut -f1)

# control file — inject Version and Installed-Size
{
    sed "s/Version: .*/Version: ${VERSION}/" "${SCRIPT_DIR}/debian/control"
    echo "Installed-Size: ${INSTALLED_SIZE}"
} > "${STAGING}/DEBIAN/control"

# Maintainer scripts
cp "${SCRIPT_DIR}/debian/postinst" "${STAGING}/DEBIAN/postinst"
cp "${SCRIPT_DIR}/debian/prerm" "${STAGING}/DEBIAN/prerm"
cp "${SCRIPT_DIR}/debian/postrm" "${STAGING}/DEBIAN/postrm"
chmod 755 "${STAGING}/DEBIAN/postinst" "${STAGING}/DEBIAN/prerm" "${STAGING}/DEBIAN/postrm"

# conffiles
cp "${SCRIPT_DIR}/debian/conffiles" "${STAGING}/DEBIAN/conffiles"

# ── Build the .deb ───────────────────────────────────────────────────────────
echo ""
echo "Building ${DEB_FILE}..."
# --root-owner-group forces every file in the archive to root:root. Without it,
# dpkg-deb stamps the build user's uid/gid onto the contents, and `dpkg -i` then
# extracts config files (/etc/health-manager/*, systemd units, /usr/share/*)
# owned by a regular user instead of root. Harmless on the app dir (postinst
# chowns it to the health-manager user) but wrong — and a real defect on strict
# dpkg setups — everywhere else.
dpkg-deb --build --root-owner-group "${STAGING}" "${DEB_FILE}"

# ── Summary ──────────────────────────────────────────────────────────────────
DEB_SIZE=$(du -sh "${DEB_FILE}" | cut -f1)
echo ""
echo "=== Build complete ==="
echo "  Package:  ${DEB_FILE}"
echo "  Size:     ${DEB_SIZE}"
echo ""
echo "Install with:  sudo dpkg -i ${DEB_FILE}"
echo "Remove with:   sudo dpkg --remove ${PKG_NAME}"
echo "Purge with:    sudo dpkg --purge ${PKG_NAME}"

# ── Cleanup staging ──────────────────────────────────────────────────────────
rm -rf "${STAGING}"
