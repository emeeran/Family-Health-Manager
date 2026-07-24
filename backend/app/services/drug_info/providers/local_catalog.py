"""Local drug-catalog provider — the curated Indian CSV loaded into ``local_drugs``.

Brand-keyed and DB-backed (unlike the live openFDA/ABDM/RxNorm providers). For a
matched brand it serves resolution (brand→active ingredients) and the flyout
content directly by name — which both uses richer local data and keeps
combination drugs intact (the generic-resolution path collapses combos to one
ingredient). Returns ``None`` on any miss so the service falls back to
ABDM/RxNorm/openFDA unchanged.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drug_catalog import LocalDrug
from app.services.drug_info.composition import ingredient_names, normalize_drug_name

logger = logging.getLogger(__name__)


async def is_configured(db: AsyncSession) -> bool:
    """True when the local catalog table has at least one row."""
    try:
        row = (
            await db.execute(select(LocalDrug.product_id).limit(1))
        ).scalar_one_or_none()
        return row is not None
    except Exception:  # noqa: BLE001 — table missing/unavailable = not configured
        return False


async def find(db: AsyncSession, name: str) -> LocalDrug | None:
    """The best-matching catalog row for ``name``, or ``None``.

    Matches on the normalized name (dosage/form stripped): exact first, then a
    contains fallback so "glycomet" still finds "glycomet gp".
    """
    norm = normalize_drug_name(name)
    if not norm:
        return None
    # Exact normalized match — return the first. Different-strength variants of
    # the same brand collapse to one normalized name (e.g. "augmentin duo"); they
    # are the same drug (same composition), so any one is correct for resolution.
    exact = (
        await db.execute(
            select(LocalDrug).where(LocalDrug.name_normalized == norm).limit(1)
        )
    ).scalars().first()
    if exact:
        return exact
    # Fallback: row's normalized name contains the query (most specific first).
    rows = (
        await db.execute(
            select(LocalDrug)
            .where(LocalDrug.name_normalized.ilike(f"%{norm}%"))
            .order_by(LocalDrug.name_normalized.asc())
            .limit(1)
        )
    ).scalars().all()
    return rows[0] if rows else None


async def resolve(db: AsyncSession, name: str) -> dict | None:
    """Brand → active-ingredient resolution from the local catalog.

    Returns ``{"name": <primary ingredient>, "ingredients": [...],
    "product_name": ..., "source": "local"}`` or ``None``. ``name`` is the first
    ingredient (the single-generic contract downstream expects); combination
    drugs carry all ingredients in ``ingredients``.
    """
    row = await find(db, name)
    if not row:
        return None
    names = ingredient_names(row.composition or "")
    primary = names[0] if names else normalize_drug_name(row.product_name or "")
    return {
        "name": primary,
        "ingredients": names,
        "product_name": row.product_name,
        "source": "local",
    }


def parsed_ingredients(row: LocalDrug) -> list[dict]:
    """The row's parsed ``ingredients`` JSON (``[{name, strength}]``), or ``[]``."""
    if not row.ingredients:
        return []
    try:
        data = json.loads(row.ingredients)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
