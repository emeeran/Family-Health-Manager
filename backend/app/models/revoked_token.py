"""Revoked JWT token model for persistent logout."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


@dataclass
class RevokedToken(Base):
    """Persisted revoked JWT token (jti)."""

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
