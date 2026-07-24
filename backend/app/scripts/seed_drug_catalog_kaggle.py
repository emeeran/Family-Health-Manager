"""Import drugs.com review data (Kaggle) into ``local_drugs`` as indications.

Dataset: ``jessicali123456/drug-review-datadrugscom`` — drugName, condition,
review, rating, date, usefulCount. The useful extract is **drugName → top
condition(s)** (the indication) + popularity, since reviews aren't monographs.
Token-gated (``KAGGLE_API_TOKEN``); ``kaggle:`` product_id prefix.

    uv run python -m app.scripts.seed_drug_catalog_kaggle [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.drug_info.bulk_upsert import upsert_local_drugs
from app.services.drug_info.composition import normalize_drug_name

logger = logging.getLogger(__name__)


def _col(row: dict, *candidates: str) -> str | None:
    """First non-empty value among candidate column names (schema-flexible)."""
    for c in candidates:
        v = row.get(c)
        if v not in (None, ""):
            return str(v).strip()
    return None


def _aggregate(rows: list[dict], limit: int | None = None) -> list[dict]:
    """Aggregate review rows per drug → catalog rows (indication + popularity).

    Schema-flexible: reads the drug-name column (``drugName``/``urlDrugName``),
    ``condition``, and ``rating`` wherever they appear. Patient-review prose is
    deliberately not mapped (too noisy for structured fields).
    """
    agg: dict = defaultdict(lambda: {"conditions": Counter(), "ratings": [], "reviews": 0})
    for i, r in enumerate(rows):
        if limit is not None and i >= limit:
            break
        name = _col(r, "drugName", "urlDrugName", "drug_name", "name")
        if not name:
            continue
        a = agg[name]
        cond = _col(r, "condition", "indication")
        if cond and cond.lower() not in {"other", "not listed"}:
            a["conditions"][cond] += 1
        rating = _col(r, "rating")
        try:
            a["ratings"].append(float(rating))
        except (TypeError, ValueError):
            pass
        a["reviews"] += 1

    out: list[dict] = []
    for name, a in agg.items():
        top = a["conditions"].most_common(1)[0][0] if a["conditions"] else None
        avg = sum(a["ratings"]) / len(a["ratings"]) if a["ratings"] else None
        fact = f"★{avg:.1f} from {a['reviews']} reviews" if avg is not None else None
        out.append(
            {
                "product_id": f"kaggle:{name.lower()}",
                "product_name": name,
                "name_normalized": normalize_drug_name(name),
                "primary_use": top,
                "introduction": f"Used for: {top}" if top else None,
                "fact_box": fact,
            }
        )
    return out


def _read_review_rows(data_dir: Path) -> list[dict]:
    """Read all CSV/TXT review files in ``data_dir`` (try csv then tab-delimited)."""
    rows: list[dict] = []
    files = sorted([*data_dir.glob("*.csv"), *data_dir.glob("*.txt")])
    for path in files:
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            sample = f.read(2048)
            f.seek(0)
            delim = "\t" if "\t" in sample else ","
            rows.extend(csv.DictReader(f, delimiter=delim))
    return rows


def _has_kaggle_auth() -> bool:
    """True if a Kaggle credential is available (setting, env, or access-token file)."""
    return bool(
        get_settings().KAGGLE_API_TOKEN
        or os.environ.get("KAGGLE_API_TOKEN")
        or Path.home().joinpath(".kaggle/access_token").is_file()
    )


async def run(limit: int | None = None) -> dict:
    """Download + aggregate + upsert. Returns {drugs, reviews}."""
    settings = get_settings()
    token = settings.KAGGLE_API_TOKEN
    if not _has_kaggle_auth():
        raise SystemExit("KAGGLE_API_TOKEN is not set — Kaggle importer is token-gated.")
    if token:
        os.environ["KAGGLE_API_TOKEN"] = token  # kaggle package reads this env var

    try:
        import kaggle
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("kaggle package not installed — run `uv add kaggle`.") from exc

    slug = settings.KAGGLE_DRUG_REVIEW_DATASET
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        logger.info("Downloading Kaggle dataset %s …", slug)
        # kaggle.api self-authenticates from KAGGLE_API_TOKEN env on import;
        # authenticate() is a safe no-op when already configured.
        try:
            kaggle.api.authenticate()
        except Exception:  # noqa: BLE001
            pass
        kaggle.api.dataset_download_files(slug, path=str(tmpdir), unzip=True, quiet=True)
        review_rows = _read_review_rows(tmpdir)

    catalog_rows = _aggregate(review_rows, limit=limit)
    if catalog_rows:
        async with SessionLocal() as db:
            await upsert_local_drugs(db, catalog_rows)
    counts = {"drugs": len(catalog_rows), "reviews": len(review_rows)}
    logger.info("Kaggle drug import complete: %s", counts)
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Import drugs.com review data (Kaggle) into local_drugs.")
    ap.add_argument("--limit", type=int, default=None, help="Cap review rows processed (testing).")
    args = ap.parse_args()
    print(asyncio.run(run(limit=args.limit)))
