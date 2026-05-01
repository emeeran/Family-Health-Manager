"""Message schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID
from app.models.base import MessageRole


class MessageCreate(BaseModel):
    """Message creation request."""

    content: str = Field(..., min_length=1, max_length=8000, description="Message content")


class MessageResponse(BaseModel):
    """Message response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Message ID")
    conversation_id: UUID = Field(..., description="Conversation ID")
    role: MessageRole = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    created_at: datetime = Field(..., description="Creation timestamp")
