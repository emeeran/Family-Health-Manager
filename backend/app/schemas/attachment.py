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
    content_hash: str | None = Field(None, description="SHA-256 content hash")
    storage_backend: str = Field("local", description="Storage backend name")
    thumbnail_path: str | None = Field(None, description="Thumbnail storage path")
    encrypted: bool = Field(False, description="Whether file is encrypted at rest")
