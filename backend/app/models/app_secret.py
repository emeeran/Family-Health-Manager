"""Instance-wide application secrets (e.g. AI provider API keys), encrypted at rest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, String, Text

from app.models.base import Base


@dataclass
class AppSecret(Base):
    """Encrypted key/value store for instance-wide secrets.

    ``value`` holds Fernet ciphertext produced by
    :func:`app.core.encryption.encrypt_secret` — never plaintext. The ``key``
    namespace is the canonical secret name (e.g. ``"openai_api_key"``).
    """

    __tablename__ = "app_secrets"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default="CURRENT_TIMESTAMP",
        nullable=False,
    )
