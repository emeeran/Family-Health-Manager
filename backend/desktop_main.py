"""PyInstaller entry point for the Tauri desktop sidecar.

Runs the FastAPI app under uvicorn on 127.0.0.1:<port>, generating any missing
secrets into ``<cwd>/config.env`` BEFORE importing ``app.main`` (whose
``Settings()`` requires ``SECRET_KEY``). The Tauri shell sets the process
working directory to the per-user data directory (``$XDG_DATA_HOME/HealthManager``)
so all CWD-relative paths (``./data/health.db``, ``data/scheduler.db``,
``./data/attachments``, ``data/backups``) land there, and passes the port via
``--port`` / ``HM_PORT``.

``APP_ENV`` defaults to ``"desktop"`` (not ``"production"``) so the cookie
``secure`` flag stays off — required for the httpOnly auth cookies to be set
over plain ``http://`` on 127.0.0.1 (see ``app/routers/auth.py``). Same-origin
serving (the backend serves the SPA when ``SERVE_FRONTEND`` is on) keeps those
cookies first-party, so login works without TLS.
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
from pathlib import Path


def _parse_port(argv: list[str]) -> int:
    """Resolve the listen port from --port=NN / HM_PORT, defaulting to 8000."""
    for arg in argv[1:]:
        if arg.startswith("--port="):
            return int(arg.split("=", 1)[1])
    if os.environ.get("HM_PORT"):
        return int(os.environ["HM_PORT"])
    return 8000


def _ensure_secrets(config_path: Path) -> None:
    """Generate any missing required secrets into config.env and export them.

    Idempotent across upgrades (existing values preserved). Uses the same
    generators as ``packaging/debian/postinst`` — ``SECRET_KEY``/
    ``HEALTH_CHECK_SECRET`` are urlsafe tokens, ``ENCRYPTION_KEY`` is a
    Fernet-compatible base64 of 32 random bytes — so keys are interchangeable
    with the server .deb.
    """
    values: dict[str, str] = {}
    if config_path.is_file():
        for line in config_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip()

    generators = {
        "SECRET_KEY": lambda: secrets.token_urlsafe(48),
        "ENCRYPTION_KEY": lambda: base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "HEALTH_CHECK_SECRET": lambda: secrets.token_urlsafe(24),
    }
    changed = False
    for key, gen in generators.items():
        if not values.get(key):
            values[key] = gen()
            changed = True

    if changed:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
        try:
            os.chmod(config_path, 0o600)
        except OSError:
            pass

    # Export into the environment BEFORE app.main is imported so Settings() can
    # read them at construction time.
    for key, val in values.items():
        os.environ.setdefault(key, val)


def _die_with_parent() -> None:
    """Ask the kernel to SIGTERM this process when its parent dies (Linux).

    The parent is the PyInstaller onefile bootloader, which the Tauri shell kills
    on exit. This is a backstop so we never leave an orphaned uvicorn behind if
    the shell is force-killed before its own process-tree teardown runs. No-op on
    non-Linux / if prctl is unavailable.
    """
    try:
        import ctypes

        PR_SET_PDEATHSIG = 1
        SIGTERM = 15
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG, SIGTERM, 0, 0, 0)
    except Exception:
        pass


def main() -> None:
    _die_with_parent()
    os.environ.setdefault("APP_ENV", "desktop")
    # The desktop sidecar serves the SPA itself for same-origin auth cookies.
    # When frozen, main.py reads the dist from sys._MEIPASS/frontend; FRONTEND_DIST
    # is only used for unfrozen runs (e.g. `python desktop_main.py` from backend/).
    os.environ.setdefault("SERVE_FRONTEND", "true")

    port = _parse_port(sys.argv)
    _ensure_secrets(Path("config.env"))

    # Imported after env is primed so app.main's Settings() sees the secrets.
    import uvicorn

    from app.main import app  # noqa: F401 — triggers Settings()/lifespan wiring

    # loop=asyncio + http=h11 avoid the uvloop/httptools/watchfiles native
    # optional deps, keeping the frozen binary lean and dependency-stable.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        workers=1,
        loop="asyncio",
        http="h11",
        log_level=os.environ.get("LOG_LEVEL", "warning").lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
