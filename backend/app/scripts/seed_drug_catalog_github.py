"""Bulk-import the junioralive/Indian-Medicine-Dataset into ``local_drugs``.

~254k Indian medicines (name, composition, manufacturer, price, packaging).
Public raw CSV, no auth. Idempotent upsert with the ``gh:`` product_id prefix so
it coexists with the curated CSV (``DRS…``) and other sources.

    uv run python -m app.scripts.seed_drug_catalog_github [--limit N] [--include-discontinued]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import tempfile
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.drug_info.bulk_upsert import upsert_local_drugs
from app.services.drug_info.composition import normalize_drug_name, parse_composition

logger = logging.getLogger(__name__)


def _clean_comp(c1: str | None, c2: str | None) -> str:
    """Join the two short-composition fields into one '+ '-separated string."""
    parts = []
    for raw in (c1 or "", c2 or ""):
        p = " ".join(raw.split()).rstrip(",")  # collapse whitespace, strip, drop trailing comma
        if p:
            parts.append(p)
    return " + ".join(parts)


async def _download(url: str, dest: Path) -> None:
    """Stream-download the CSV to ``dest`` (32 MB; don't hold it in memory)."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)


async def run(limit: int | None = None, include_discontinued: bool = False) -> dict:
    """Download + upsert. Returns {processed, batches, skipped}."""
    url = get_settings().INDIAN_MED_DATASET_URL
    rows: list[dict] = []
    skipped = 0

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        dest = Path(tf.name)
    try:
        logger.info("Downloading %s …", url)
        await _download(url, dest)
        with dest.open(newline="", encoding="utf-8") as f:
            for i, r in enumerate(csv.DictReader(f)):
                if limit is not None and i >= limit:
                    break
                discontinued = (r.get("Is_discontinued") or "").strip().upper().startswith("TRUE")
                if discontinued and not include_discontinued:
                    skipped += 1
                    continue
                name = (r.get("name") or "").strip()
                if not name:
                    skipped += 1
                    continue
                comp = _clean_comp(r.get("short_composition1"), r.get("short_composition2"))
                rows.append(
                    {
                        "product_id": f"gh:{(r.get('id') or '').strip()}",
                        "product_name": name,
                        "name_normalized": normalize_drug_name(name),
                        "composition": comp or None,
                        "ingredients": json.dumps(parse_composition(comp)) if comp else None,
                        "marketer": (r.get("manufacturer_name") or "").strip() or None,
                        "mrp": (r.get("price(₹)") or "").strip() or None,
                        "package": (r.get("pack_size_label") or "").strip() or None,
                    }
                )
        async with SessionLocal() as db:
            processed, batches = await upsert_local_drugs(db, rows)
    finally:
        dest.unlink(missing_ok=True)

    counts = {"processed": processed, "batches": batches, "skipped": skipped}
    logger.info("GitHub drug import complete: %s", counts)
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Import the Indian-Medicine-Dataset into local_drugs.")
    ap.add_argument("--limit", type=int, default=None, help="Process only the first N CSV rows (testing).")
    ap.add_argument("--include-discontinued", action="store_true")
    args = ap.parse_args()
    print(asyncio.run(run(limit=args.limit, include_discontinued=args.include_discontinued)))
