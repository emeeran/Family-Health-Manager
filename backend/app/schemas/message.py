"""Message schemas."""

from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    """Message creation request."""

    content: str = Field(..., min_length=1, max_length=8000, description="Message content")
