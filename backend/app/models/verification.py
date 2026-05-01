"""Response verification model."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, Text, String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


@dataclass
class ResponseVerification(Base):
    """AI response verification result."""

    __tablename__ = "response_verifications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id"), nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    # verified | warnings | unverifiable | pending | failed
    warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    claims_checked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verifier_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    message: Mapped["Message"] = relationship(back_populates="verification")  # noqa: F821
