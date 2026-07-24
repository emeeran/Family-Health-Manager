"""Seed the local drug catalog (``local_drugs``) from the curated Indian CSV.

Run once per environment (dev SQLite + prod DB); idempotent (upserts by
``product_id``), so re-running after editing the CSV updates changed rows::

    uv run python -m app.scripts.seed_drug_catalog [path/to/drugs.csv]

With no path argument, uses ``settings.DRUG_CATALOG_CSV``. The CSV itself is
gitignored — each deployment points this script (or the setting) at its copy.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.drug_catalog import LocalDrug
from app.services.drug_info.composition import normalize_drug_name, parse_composition

logger = logging.getLogger(__name__)

# CSV header → LocalDrug column. Unmapped columns (medicine_type, Q_A,
# Packaging Detail, Qty) are intentionally ignored.
_COLUMN_MAP: dict[str, str] = {
    "Product ID": "product_id",
    "Product Name": "product_name",
    "Marketer": "marketer",
    "Composition": "composition",
    "Product Form": "product_form",
    "Package": "package",
    "MRP": "mrp",
    "prescription_required": "prescription_required",
    "Introduction": "introduction",
    "Benefits": "benefits",
    "how_to_use": "how_to_use",
    "safety_advise": "safety_advise",
    "if_miss": "if_miss",
    "side_effect": "side_effect",
    "drug-drug Interaction": "drug_drug_interaction",
    "How it works": "how_it_works",
    "Fact_Box": "fact_box",
    "primary_use": "primary_use",
    "storage": "storage",
    "alcoholInteraction": "alcohol_interaction",
    "pregnancyInteraction": "pregnancy_interaction",
    "lactationInteraction": "lactation_interaction",
    "drivingInteraction": "driving_interaction",
    "kidneyInteraction": "kidney_interaction",
    "liverInteraction": "liver_interaction",
    "country_of_origin": "country_of_origin",
    "Image_Urls": "image_urls",
}


def _resolve_csv_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    configured = get_settings().DRUG_CATALOG_CSV
    if configured:
        return Path(configured)
    raise SystemExit(
        "No CSV path given and DRUG_CATALOG_CSV is unset. Usage: "
        "uv run python -m app.scripts.seed_drug_catalog <path/to/drugs.csv>"
    )


async def run(csv_path: Path) -> dict:
    """Upsert every CSV row into ``local_drugs``. Returns {inserted, updated}."""
    inserted = updated = 0
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    async with SessionLocal() as db:
        for row in rows:
            product_id = (row.get("Product ID") or "").strip()
            product_name = (row.get("Product Name") or "").strip()
            if not product_id or not product_name:
                continue

            fields = {
                col: (row.get(header) or "").strip() or None
                for header, col in _COLUMN_MAP.items()
                if col not in {"product_id", "product_name"}
            }
            composition = fields.get("composition") or ""
            fields["name_normalized"] = normalize_drug_name(product_name)
            fields["ingredients"] = (
                json.dumps(parse_composition(composition)) if composition else None
            )

            existing = (
                await db.execute(
                    select(LocalDrug).where(LocalDrug.product_id == product_id)
                )
            ).scalar_one_or_none()
            if existing:
                for col, val in fields.items():
                    setattr(existing, col, val)
                updated += 1
            else:
                db.add(LocalDrug(product_id=product_id, product_name=product_name, **fields))
                inserted += 1
        await db.commit()

    counts = {"inserted": inserted, "updated": updated, "total": len(rows)}
    logger.info("Drug catalog seed complete: %s", counts)
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = _resolve_csv_path(sys.argv[1] if len(sys.argv) > 1 else None)
    import asyncio

    print(asyncio.run(run(path)))
