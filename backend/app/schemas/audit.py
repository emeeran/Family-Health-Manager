"""Audit log schemas."""
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID


class AuditLogResponse(BaseModel):
    """Audit log response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    action: str
    resource_type: str
    resource_id: UUID
    previous_state: dict | None = None
    current_state: dict | None = None
    ip_address: str | None = None
    created_at: datetime
