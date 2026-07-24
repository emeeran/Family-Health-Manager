"""Enrich the local drug catalog with drugs.com monographs via parse.bot.

`get_drug_details` returns Uses / Side Effects / Warnings / Dosage sections —
the rich metadata the other sources lack. Key-gated (``PARSE_BOT_API_KEY``) and
rate-limited, so target a curated set, not the whole catalog.

    uv run python -m app.scripts.seed_drug_catalog_drugscom \\
        --names drugs.txt | --from-catalog --limit 20 | --condition depression
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re

import httpx

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.drug_catalog import LocalDrug
from app.services.drug_info.composition import normalize_drug_name
from app.services.drug_info.bulk_upsert import upsert_local_drugs
from sqlalchemy import select

logger = logging.getLogger(__name__)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-") or "drug"


def _section(sections: dict | None, *keywords: str) -> str | None:
    """Find a section value by case-insensitive substring of its key."""
    for key, val in (sections or {}).items():
        kl = key.lower()
        if any(k in kl for k in keywords) and val:
            return val.strip() or None
    return None


def _clean_generic(raw: str | None) -> str | None:
    """Strip the phonetic pronunciation guide: ``metformin [ met-FOR-min ]`` → ``metformin``."""
    cleaned = re.sub(r"\s*\[[^\]]*\]\s*", " ", raw or "").strip()
    return cleaned or None


def _unwrap(payload: dict | None) -> dict:
    """The API wraps responses in ``{status, data}``; return the inner ``data``."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload or {}


async def _search_and_detail(client: httpx.AsyncClient, name: str) -> dict | None:
    """search_drugs → first result url → get_drug_details (inner data)."""
    r = await client.get("/search_drugs", params={"query": name})
    r.raise_for_status()
    data = _unwrap(r.json())
    results = data.get("results") or data.get("drugs") or []
    if not results:
        return None
    url = results[0].get("url")
    if not url:
        return None
    d = await client.get("/get_drug_details", params={"url": url})
    d.raise_for_status()
    return _unwrap(d.json())


def _to_row(name: str, details: dict) -> dict:
    sections = details.get("sections") or {}
    generic = _clean_generic(details.get("generic_name"))
    return {
        "product_id": f"dc:{_slug(details.get('name') or name)}",
        "product_name": (details.get("name") or name).strip(),
        "name_normalized": normalize_drug_name(details.get("name") or name),
        "composition": generic,
        "primary_use": (details.get("drug_class") or "").strip() or None,
        "introduction": _section(sections, "what is", "uses", "why is"),
        "side_effect": _section(sections, "side effect"),
        "safety_advise": _section(sections, "warning", "contraindication", "before taking"),
        "how_to_use": _section(
            sections, "how should i take", "how to take", "take", "dose", "dosage", "directions"
        ),
    }


async def run(names: list[str], interval: float = 12.0) -> dict:
    """Fetch + upsert drugs.com details for each name. Returns {ok, failed}."""
    settings = get_settings()
    key = settings.PARSE_BOT_API_KEY
    if not key:
        raise SystemExit("PARSE_BOT_API_KEY is not set — drugs.com importer is key-gated.")

    ok = failed = 0
    rows: list[dict] = []
    async with httpx.AsyncClient(
        base_url=settings.PARSE_BOT_BASE_URL,
        headers={"X-API-Key": key},
        timeout=30.0,
    ) as client:
        for i, name in enumerate(names):
            name = (name or "").strip()
            if not name:
                continue
            try:
                details = await _search_and_detail(client, name)
                if details:
                    rows.append(_to_row(name, details))
                    ok += 1
                    logger.info("[%d/%d] %s — ok", i + 1, len(names), name)
                else:
                    failed += 1
                    logger.info("[%d/%d] %s — not found", i + 1, len(names), name)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    logger.warning("Rate limited at %s; backing off 60s", name)
                    await asyncio.sleep(60.0)
                    continue  # leave for a later run rather than block
                failed += 1
                logger.warning("[%d/%d] %s — %s", i + 1, len(names), name, exc)
            except Exception as exc:  # noqa: BLE001 — one failure doesn't abort the batch
                failed += 1
                logger.warning("[%d/%d] %s — %s", i + 1, len(names), name, exc)
            if interval:
                await asyncio.sleep(interval)

    if rows:
        async with SessionLocal() as db:
            await upsert_local_drugs(db, rows)
    counts = {"ok": ok, "failed": failed, "upserted": len(rows)}
    logger.info("drugs.com import complete: %s", counts)
    return counts


async def _resolve_names(args) -> list[str]:
    if args.names:
        return [ln.strip() for ln in open(args.names, encoding="utf-8") if ln.strip()]
    if args.condition:
        settings = get_settings()
        async with httpx.AsyncClient(
            base_url=settings.PARSE_BOT_BASE_URL,
            headers={"X-API-Key": settings.PARSE_BOT_API_KEY},
            timeout=30.0,
        ) as client:
            r = await client.get("/get_drugs_by_condition", params={"condition": args.condition})
            r.raise_for_status()
            data = _unwrap(r.json())
            drugs = data.get("drugs") or data.get("results") or []
            return [d.get("name") for d in drugs if d.get("name")]
    # --from-catalog: enrich existing catalog entries (curated CSV brands first).
    async with SessionLocal() as db:
        q = select(LocalDrug.product_name).order_by(LocalDrug.product_id)
        if args.limit:
            q = q.limit(args.limit)
        return [n for (n,) in (await db.execute(q)).all() if n]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Enrich local_drugs from drugs.com via parse.bot.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--names", help="File of drug names (one per line).")
    src.add_argument("--from-catalog", action="store_true", help="Enrich existing catalog names.")
    src.add_argument("--condition", help="Drugs.com condition slug (e.g. depression).")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--interval", type=float, default=12.0, help="Seconds between API calls.")
    args = ap.parse_args()
    names = asyncio.run(_resolve_names(args))
    print(f"Targeting {len(names)} drug(s).")
    print(asyncio.run(run(names, interval=args.interval)))
