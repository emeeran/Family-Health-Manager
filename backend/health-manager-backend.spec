# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Tauri desktop backend sidecar (onefile).

Produces a single ``dist/health-manager-backend`` executable that:
  * runs uvicorn + the FastAPI app (entry: desktop_main.py)
  * serves the built SPA same-origin (bundled as ``frontend/`` data)
  * loads prompt templates (bundled as ``prompts/*.md``)
  * runs alembic migrations on startup (alembic.ini + alembic/ bundled as data,
    so create_tables() -> alembic upgrade head works in frozen mode via %(here)s)

The onefile form is required by Tauri's ``externalBin`` sidecar mechanism, which
references a single executable (target-triple-suffixed at packaging time).
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

REPO = Path(SPECPATH).resolve().parent  # backend/ -> repo root

datas = []
binaries = []
hiddenimports = []


def _safe_collect(pkg: str) -> None:
    """Collect submodules + data + binaries for a package, tolerating misses."""
    try:
        d, b, h = collect_all(pkg)
        datas.extend(d)
        binaries.extend(b)
        hiddenimports.extend(h)
    except Exception as exc:  # noqa: BLE001 — keep building even if a hook misses
        print(f"[spec] collect_all({pkg!r}) skipped: {exc}")


# Native / metadata-heavy packages: collect everything to avoid runtime
# "No module named ..." / missing-data errors (the main risk with PyInstaller).
for pkg in [
    "pymupdf",
    "fitz",
    "cryptography",
    "argon2",
    "argon2_cffi",
    "pydantic",
    "pydantic_core",
    "PIL",
    "passlib",
    "redis",
]:
    _safe_collect(pkg)

# SQLAlchemy dialects/drivers are imported lazily; PyInstaller's static analysis
# misses them. uvicorn/fastapi optional bits likewise.
hiddenimports += collect_submodules("sqlalchemy.dialects")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("fastapi")
hiddenimports += [
    "aiosqlite",
    "asyncpg",
    "h11",
    "anyio",
    "starlette",
    "starlette.routing",
    "apscheduler.jobstores.sqlalchemy",
    "apscheduler.schedulers.asyncio",
    "apscheduler.triggers.cron",
    "apscheduler.triggers.interval",
    "apscheduler.triggers.date",
    "passlib.handlers",
    "qrcode",
    "pyotp",
    "jwt",
    "multipart",
    "python_multipart",
    "alembic",
    "alembic.command",
    "alembic.config",
    "alembic.runtime.migration",
    # NOTE: mako/email_validator/dnspython intentionally omitted — mako is only
    # needed to *generate* migrations (we only `upgrade`), and the others aren't
    # runtime deps of this app.
]

# --- Data files --------------------------------------------------------------
# Prompt templates (repo-root prompts/*.md) -> _MEIPASS/prompts/
datas += [(str(p), "prompts") for p in sorted((REPO / "prompts").glob("*.md"))]
# Built SPA (frontend/dist) -> _MEIPASS/frontend/  (served same-origin by main.py)
datas += [(str(REPO / "frontend" / "dist"), "frontend")]
# Alembic (ini + migration scripts) -> _MEIPASS/alembic(.ini); create_tables()
# runs `alembic upgrade head` on every SQLite start via script_location=%(here)s/alembic
datas += [("alembic.ini", ".")]
datas += [("alembic", "alembic")]

# --- Modules to exclude (not in the runtime import path; trim the binary) -----
excludes = [
    "app.scripts",  # kaggle/seed importers — never imported by the running app
    "pytest",
    "_pytest",
    "tkinter",
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "jupyter_client",
    "jupyter_core",
    "kaggle",
]


a = Analysis(
    ["desktop_main.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="health-manager-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX can break native exts (pymupdf/cryptography); leave off
    runtime_tmpdir=None,
    console=True,  # sidecar: stdout/stderr are captured by the Tauri shell
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
