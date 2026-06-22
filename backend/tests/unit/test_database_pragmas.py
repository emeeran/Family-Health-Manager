"""SQLite PRAGMA configuration regression guard.

The connection listener in ``app.core.database`` sets WAL journal mode and a
``busy_timeout`` long enough to ride out concurrent writes under
``uvicorn --workers 2`` (batch extraction + record saves + background
summary/insight tasks). The old 5s value surfaced as recurring
``sqlite3.OperationalError: database is locked``; these tests fail if it is
lowered again.
"""

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine

settings = get_settings()

pytestmark = pytest.mark.skipif(
    not settings.DATABASE_URL.startswith("sqlite"),
    reason="PRAGMA configuration is SQLite-only",
)


async def test_busy_timeout_is_at_least_30s():
    async with engine.connect() as conn:
        value = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
    assert value is not None
    assert int(value) >= 30000


async def test_journal_mode_is_wal():
    async with engine.connect() as conn:
        mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
    assert str(mode).lower() == "wal"
