"""AI insight model."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, Text, DateTime, Integer
from app.models.base import Base


@dataclass
class AIInsight(Base):
    """AI-generated insight or conversation response."""

    __tablename__ = "ai_insights"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    health_record_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("health_records.id"), nullable=True, index=True
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    provider_used: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Verification fields — cross-checked by a different AI provider
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    verification_warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_claims_checked: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    verification_verifier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    verification_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    health_record: Mapped["HealthRecord | None"] = relationship(back_populates="ai_insights")
    conversation: Mapped["Conversation | None"] = relationship(back_populates="ai_insights")
