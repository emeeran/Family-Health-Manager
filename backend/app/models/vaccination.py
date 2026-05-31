"""Vaccination model."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, Text, DateTime, Date
from app.models.base import Base


@dataclass
class Vaccination(Base):
    """Vaccination record for a family member."""

    __tablename__ = "vaccinations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    family_member_id: Mapped[UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    date_administered: Mapped[date] = mapped_column(Date, nullable=False)
    booster_due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    family_member: Mapped["FamilyMember"] = relationship(back_populates="vaccinations")

    __table_args__ = (
        Index("ix_vaccinations_member_booster", "family_member_id", "booster_due_date"),
    )
