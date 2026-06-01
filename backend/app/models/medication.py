"""Medication model."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Text, DateTime, Date, Integer
from app.models.base import Base


@dataclass
class Medication(Base):
    """First-class medication extracted from clinical_data prescriptions."""

    __tablename__ = "medications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    family_member_id: Mapped[UUID] = mapped_column(
        ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    health_record_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("health_records.id", ondelete="SET NULL"), nullable=True
    )
    medicine: Mapped[str] = mapped_column(Text, nullable=False)
    medicine_key: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, default="")
    dosage: Mapped[str] = mapped_column(Text, default="")
    timing: Mapped[str] = mapped_column(Text, default="")
    duration: Mapped[str] = mapped_column(Text, default="")
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    note: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="active")
    prescription_index: Mapped[int] = mapped_column(Integer, default=0)
    provider_name: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    family_member: Mapped["FamilyMember"] = relationship(back_populates="medications")

    __table_args__ = (
        Index("ix_medications_member_status", "family_member_id", "status"),
        Index("ix_medications_member_key", "family_member_id", "medicine_key"),
        Index("ix_medications_record_id", "health_record_id"),
    )
