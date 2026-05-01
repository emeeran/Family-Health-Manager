"""Health record model."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, time, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Text, DateTime, Boolean, Date, Time, Enum
from app.models.base import Base, RecordType


@dataclass
class HealthRecord(Base):
    """Health record for a family member."""

    __tablename__ = "health_records"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    family_member_id: Mapped[UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    provider_id: Mapped[UUID | None] = mapped_column(ForeignKey("providers.id"), nullable=True, index=True)
    record_type: Mapped[RecordType] = mapped_column(Enum(RecordType), nullable=False, index=True)
    record_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    record_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    clinical_data: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    prescription_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    family_member: Mapped["FamilyMember"] = relationship(back_populates="health_records")
    provider: Mapped["Provider | None"] = relationship(back_populates="health_records")

    @property
    def provider_name(self) -> str | None:
        return self.provider.name if self.provider else None

    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="health_record", cascade="all, delete-orphan"
    )
    ai_insights: Mapped[list["AIInsight"]] = relationship(back_populates="health_record")

    __table_args__ = (
        Index("ix_health_records_member_deleted_date", "family_member_id", "is_deleted", "record_date"),
        Index("ix_health_records_member_type_deleted_date", "family_member_id", "record_type", "is_deleted", "record_date"),
    )
