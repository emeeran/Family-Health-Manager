"""Local drug catalog model — seeded from the curated Indian drug CSV."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text, DateTime

from app.models.base import Base


@dataclass
class LocalDrug(Base):
    """One curated drug entry (brand → composition + rich metadata).

    Seeded from ``DRUG_CATALOG_CSV`` via :mod:`app.scripts.seed_drug_catalog`.
    Drives local-first drug-info resolution + flyout content for matched brands
    (falls back to ABDM/RxNorm/openFDA when a brand isn't in the catalog).
    """

    __tablename__ = "local_drugs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    product_id: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    marketer: Mapped[str | None] = mapped_column(Text, nullable=True)
    composition: Mapped[str | None] = mapped_column(Text, nullable=True)  # raw
    ingredients: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON [{name,strength}]
    product_form: Mapped[str | None] = mapped_column(Text, nullable=True)
    package: Mapped[str | None] = mapped_column(Text, nullable=True)
    mrp: Mapped[str | None] = mapped_column(Text, nullable=True)
    prescription_required: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rich metadata (long text).
    introduction: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)
    how_to_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_advise: Mapped[str | None] = mapped_column(Text, nullable=True)
    if_miss: Mapped[str | None] = mapped_column(Text, nullable=True)
    side_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    drug_drug_interaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    how_it_works: Mapped[str | None] = mapped_column(Text, nullable=True)
    fact_box: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Interaction flags.
    alcohol_interaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    pregnancy_interaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    lactation_interaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    driving_interaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    kidney_interaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    liver_interaction: Mapped[str | None] = mapped_column(Text, nullable=True)

    country_of_origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_urls: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        server_default="CURRENT_TIMESTAMP",
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        server_default="CURRENT_TIMESTAMP",
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (Index("ix_local_drugs_name_norm", "name_normalized"),)
