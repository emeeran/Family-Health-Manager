"""Bulk upsert for the local drug catalog.

Dialect-aware ``INSERT ... ON CONFLICT (product_id) DO UPDATE`` so the catalog
seeders (curated CSV, GitHub dataset, parse.bot, Kaggle) can upsert large
batches idempotently across SQLite (dev) and PostgreSQL (prod).
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.drug_catalog import LocalDrug

logger = logging.getLogger(__name__)

# Columns an importer may set (excludes the surrogate id + auto-timestamps).
_COLUMNS = [
    c.name
    for c in LocalDrug.__table__.columns
    if c.name not in {"id", "created_at", "updated_at"}
]


async def upsert_local_drugs(
    db: AsyncSession, rows: list[dict], batch_size: int = 1000
) -> tuple[int, int]:
    """Upsert ``rows`` (dicts of LocalDrug column→value) by ``product_id``.

    Returns ``(processed, batches)``. Idempotent — re-running updates changed
    rows. Each row is filtered to known columns.
    """
    if not rows:
        return 0, 0

    if get_settings().DATABASE_URL.startswith("sqlite"):
        from sqlalchemy.dialects.sqlite import insert as _insert
    else:
        from sqlalchemy.dialects.postgresql import insert as _insert

    known = set(_COLUMNS)
    # Normalize every row to the full column set (None for absent) so the batch
    # is uniform — a multi-row INSERT with differing keys won't compile.
    clean_rows = [{c: row.get(c) for c in _COLUMNS} for row in rows if known]
    set_cols = [c for c in _COLUMNS if c != "product_id"]

    batches = 0
    for i in range(0, len(clean_rows), batch_size):
        batch = clean_rows[i : i + batch_size]
        stmt = _insert(LocalDrug.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["product_id"],
            set_={c: stmt.excluded[c] for c in set_cols},
        )
        await db.execute(stmt)
        batches += 1
    await db.commit()
    return len(clean_rows), batches
