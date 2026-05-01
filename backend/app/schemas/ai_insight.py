"""AI insight schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class AIInsightRequest(BaseModel):
    """AI insight generation request."""

    health_record_id: UUID | None = Field(None, description="Health record ID to analyze")
    prompt: str = Field(..., min_length=1, max_length=4000, description="Prompt for AI analysis")


class AIInsightResponse(BaseModel):
    """AI insight response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Insight ID")
    health_record_id: UUID | None = Field(None, description="Health record ID")
    conversation_id: UUID | None = Field(None, description="Conversation ID")
    prompt: str = Field(..., description="Original prompt")
    response: str = Field(..., description="AI response")
    provider_used: str = Field(..., description="AI provider used")
    generated_at: datetime = Field(..., description="Generation timestamp")
    disclaimer: str = Field(..., description="Medical disclaimer")
