"""AI insight model."""

from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import String, DateTime, Integer, Date
from app.db_types import EncryptedText
from app.models.base import Base

# Cached insights (pre-consult / smart-report / medication-report /
# drug-interactions) are stored under a prompt that begins with a synthetic
# ``__type__{member_id}__`` token. That token is mirrored in the plaintext
# ``prompt_key`` column so per-member cache lookups don't have to ILIKE the
# encrypted ``prompt`` column. ``__`` suffix optional (DDI key has none).
_CACHE_PROMPT_RE = re.compile(r"^__[a-z_]+__[0-9a-fA-F-]+__?")


def cache_key_from_prompt(prompt: str | None) -> str | None:
    """Return the synthetic cache-key prefix of *prompt*, or ``None``.

    ``None`` for real (non-cached) prompts — chat messages, single-record
    insights — so those rows stay out of the cache-key lookups.
    """
    if not prompt:
        return None
    m = _CACHE_PROMPT_RE.match(prompt)
    return m.group(0) if m else None


@dataclass
class AIInsight(Base):
    """AI-generated insight or conversation response."""

    __tablename__ = "ai_insights"
    __table_args__ = (
        Index("ix_ai_insights_verification_status", "verification_status"),
        Index("ix_ai_insights_generated_at", "generated_at"),
        Index("ix_ai_insights_conversation_generated", "conversation_id", "generated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    health_record_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("health_records.id"), nullable=True, index=True
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # prompt holds the full AI prompt (member context = PHI), encrypted at rest.
    # prompt_key is the synthetic lookup prefix (e.g. "__preconsult__{mid}__"),
    # kept plaintext + indexed so the per-member cache lookups still work without
    # decrypting/ILIKE-ing the encrypted prompt. Null for non-cached insights.
    prompt: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    prompt_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    response: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    provider_used: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        server_default="CURRENT_TIMESTAMP",
        nullable=False,
    )

    # Verification fields — cross-checked by a different AI provider
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    verification_warnings_json: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    verification_claims_checked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verification_verifier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    verification_summary: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    verification_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Provenance + freshness (themes 1 & 3): the source records + date range that
    # fed a member-level insight, computed server-side from the member's records
    # (never from LLM output, so citations can't be hallucinated). Null for
    # non-member insights (chat, single-record).
    sources_json: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    freshness_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    range_start: Mapped[date | None] = mapped_column(Date, nullable=True)

    health_record: Mapped["HealthRecord | None"] = relationship(back_populates="ai_insights")
    conversation: Mapped["Conversation | None"] = relationship(back_populates="ai_insights")
