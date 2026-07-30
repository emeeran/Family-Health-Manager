"""Frozen-aware loader for externalised prompt templates.

Prompt templates live in ``prompts/`` at the repo root in dev and in the
server .deb (installed alongside the backend). When the backend is frozen
with PyInstaller for the Tauri desktop app they are bundled as data under
``sys._MEIPASS/prompts``. This helper resolves the correct location in both
cases and raises ``FileNotFoundError`` when the template is absent, so each
caller can fall back to its own inline directive (preserving the original
per-loader behaviour).

It also fixes a latent inconsistency: the three loaders previously used
different ``__file__`` parent counts (4-up vs 5-up), so
``consultation_summary.md`` never resolved and always fell back. Everything
now resolves through one repo-root path.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _prompts_dir() -> Path:
    """Resolve the directory holding ``prompts/*.md`` for the current mode."""
    # PyInstaller-frozen: data files are unpacked under sys._MEIPASS.
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "prompts"
    # Dev / server .deb: repo-root prompts/ — 4 dirs up from app/services/ai/.
    return Path(__file__).resolve().parents[4] / "prompts"


def load_prompt(name: str) -> str:
    """Return the contents of ``prompts/<name>``.

    Raises ``FileNotFoundError`` if the template is missing so callers can
    substitute an inline fallback.
    """
    return (_prompts_dir() / name).read_text()
