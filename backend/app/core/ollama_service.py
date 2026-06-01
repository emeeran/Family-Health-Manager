"""Ollama service manager — auto-start and health check."""
import asyncio
import logging
import shutil

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_process: asyncio.subprocess.Process | None = None


async def is_ollama_running(url: str | None = None) -> bool:
    """Check if Ollama server is responding."""
    base_url = url or _settings.OLLAMA_LOCAL_URL
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/api/tags")
            return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, OSError):
        return False


async def ensure_model_pulled(model: str, url: str | None = None) -> bool:
    """Check if a model is available locally; pull it if missing."""
    base_url = url or _settings.OLLAMA_LOCAL_URL
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code != 200:
                return False
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            if any(model in m for m in models):
                return True

        # Model not found — pull it
        logger.info("Pulling Ollama model '%s' (this may take a while)...", model)
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{base_url}/api/pull",
                json={"name": model, "stream": False},
            )
            if resp.status_code == 200:
                logger.info("Model '%s' pulled successfully", model)
                return True
            logger.error("Failed to pull model '%s': %s", model, resp.text[:200])
            return False
    except Exception as exc:
        logger.error("Error pulling model '%s': %s", model, exc)
        return False


async def start_ollama() -> bool:
    """Start Ollama server as a background process.

    Returns True if Ollama is running (was already or just started).
    """
    global _process

    # Already running?
    if await is_ollama_running():
        logger.info("Ollama already running at %s", _settings.OLLAMA_LOCAL_URL)
        return True

    # Check if ollama binary exists
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        logger.warning(
            "Ollama binary not found in PATH. "
            "Install it: curl -fsSL https://ollama.com/install.sh | sh"
        )
        return False

    logger.info("Starting Ollama server via '%s serve'...", ollama_bin)
    try:
        _process = await asyncio.create_subprocess_exec(
            ollama_bin, "serve",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as exc:
        logger.error("Failed to start Ollama: %s", exc)
        return False

    # Wait for it to become ready (up to 30 seconds)
    for attempt in range(30):
        await asyncio.sleep(1)
        if await is_ollama_running():
            logger.info("Ollama server ready after %ds", attempt + 1)
            return True
        if _process.returncode is not None:
            logger.error("Ollama process exited with code %d", _process.returncode)
            return False

    logger.error("Ollama did not become ready within 30s")
    return False


async def ensure_ollama_ready() -> bool:
    """Ensure Ollama is running and the primary model is available.

    Called during application startup. Starts Ollama if not running,
    then checks/pulls the configured model.
    """
    if not await start_ollama():
        return False

    # Ensure primary model is available
    models_ok = True
    for model in [_settings.OLLAMA_MODEL, _settings.OLLAMA_TEXT_MODEL]:
        if not await ensure_model_pulled(model):
            logger.warning("Model '%s' not available", model)
            models_ok = False

    return models_ok
