"""Thumbnail background task opens its own session.

Regression for the closed-request-session bug: generate_thumbnail_background used
to receive the request `db`, but FastAPI BackgroundTasks run after get_db() has
committed AND closed it — so the write raised and was swallowed, leaving
thumbnail_path unset on the create path. The fix mirrors _generate_insight_background
(open its own SessionLocal).
"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.database as db_mod
import app.core.thumbnails as thumb_mod
from app.models.attachment import Attachment


async def test_generate_thumbnail_background_uses_own_session(db_session, monkeypatch, tmp_path):
    att = Attachment(
        health_record_id=uuid4(),
        file_path=str(tmp_path / "scan.pdf"),
        file_name="scan.pdf",
        mime_type="application/pdf",
        file_size=10,
        content_hash="abc",
        storage_backend="local",
        encrypted=True,
    )
    db_session.add(att)
    await db_session.flush()
    att_id = att.id
    # Commit so the write lock is free for the task's own session — and because
    # in production the task runs post-commit (that's the bug being tested).
    await db_session.commit()

    # Point the function's internal SessionLocal at the test engine (it would
    # otherwise open the production DB), and skip real image rendering.
    monkeypatch.setattr(
        db_mod,
        "SessionLocal",
        lambda: AsyncSession(db_session.bind, expire_on_commit=False),
    )
    fake_thumb = tmp_path / "thumb.webp"
    fake_thumb.write_bytes(b"x")

    async def _fake_generate(*_a, **_kw):
        return fake_thumb

    monkeypatch.setattr(thumb_mod, "generate_thumbnail", _fake_generate)

    # No `db` argument — the function opens its own session.
    await thumb_mod.generate_thumbnail_background(
        att_id, tmp_path / "scan.pdf", "abc", "application/pdf", True
    )

    # Read back through a fresh session to prove it persisted via its own.
    async with AsyncSession(db_session.bind) as s:
        row = (
            await s.execute(select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert row.thumbnail_path == str(fake_thumb)
