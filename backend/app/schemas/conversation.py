"""Conversation schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID
from app.models.base import ConversationScope


class ConversationCreate(BaseModel):
    """Conversation creation request."""

    family_member_id: UUID | None = Field(
        None, description="Family member ID for member-specific chat"
    )
    scope: ConversationScope = Field(..., description="Conversation scope")
    title: str | None = Field(None, min_length=1, max_length=200, description="Conversation title")


class ConversationResponse(BaseModel):
    """Conversation response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Conversation ID")
    household_id: UUID = Field(..., description="Household ID")
    family_member_id: UUID | None = Field(None, description="Family member ID")
    scope: ConversationScope = Field(..., description="Conversation scope")
    title: str | None = Field(None, description="Conversation title")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
