"""Attachment schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class AttachmentResponse(BaseModel):
    """Attachment response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Attachment ID")
    health_record_id: UUID = Field(..., description="Health record ID")
    file_path: str = Field(..., description="Storage path")
    file_name: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type")
    file_size: int = Field(..., description="File size in bytes")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
