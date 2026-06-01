"""Lab result model."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Text, DateTime, Date
from app.models.base import Base


@dataclass
class LabResult(Base):
    """First-class lab result extracted from clinical_data tests."""

    __tablename__ = "lab_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    family_member_id: Mapped[UUID] = mapped_column(
        ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    health_record_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("health_records.id", ondelete="SET NULL"), nullable=True
    )
    test_name: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    units: Mapped[str] = mapped_column(Text, default="")
    ref_value: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    family_member: Mapped["FamilyMember"] = relationship(back_populates="lab_results")

    __table_args__ = (
        Index("ix_lab_results_member_test", "family_member_id", "test_name"),
        Index("ix_lab_results_member_date", "family_member_id", "record_date"),
        Index("ix_lab_results_record_id", "health_record_id"),
    )
