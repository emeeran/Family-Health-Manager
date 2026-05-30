"""Attachment model."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, Integer, DateTime
from app.models.base import Base


@dataclass
class Attachment(Base):
    """File attachment for health record."""

    __tablename__ = "attachments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    health_record_id: Mapped[UUID] = mapped_column(ForeignKey("health_records.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    health_record: Mapped["HealthRecord"] = relationship(back_populates="attachments")
