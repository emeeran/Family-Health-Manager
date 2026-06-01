"""Unit tests for attachment service."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from app.services.attachment_service import AttachmentService
from app.models.base import Attachment, HealthRecord


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def household_id():
    """Create a household ID."""
    return uuid4()


@pytest.fixture
def attachment_service(mock_db):
    """Create AttachmentService instance."""
    return AttachmentService(mock_db)


@pytest.mark.asyncio
async def test_upload_attachment(attachment_service, mock_db, household_id):
    """Test uploading an attachment."""
    record_id = uuid4()
    mock_record = HealthRecord(id=record_id)

    mock_file = MagicMock()
    mock_file.content_type = "application/pdf"
    mock_file.filename = "test.pdf"
    mock_file.read = AsyncMock(return_value=b"test content")

    get_result = MagicMock()
    get_result.scalar_one_or_none.return_value = mock_record
    mock_db.execute = AsyncMock(return_value=get_result)

    mock_path = MagicMock()
    mock_path.stat().st_size = 100
    mock_path.__str__ = lambda s: "/tmp/test_storage/files/ab/testhash.pdf"

    with patch(
        "app.services.attachment_service.save_file_hashed",
        new_callable=AsyncMock,
        return_value=(mock_path, "abcdef1234567890", ".pdf"),
    ):
        attachment = await attachment_service.upload_attachment(
            record_id, mock_file, household_id
        )

        assert attachment.health_record_id == record_id
        assert attachment.mime_type == "application/pdf"
        assert attachment.content_hash == "abcdef1234567890"
        assert attachment.storage_backend == "local"


@pytest.mark.asyncio
async def test_upload_attachment_record_not_found(attachment_service, mock_db, household_id):
    """Test uploading to non-existent record."""
    record_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_file = MagicMock()
    mock_file.content_type = "application/pdf"

    with pytest.raises(ValueError, match="Health record not found"):
        await attachment_service.upload_attachment(record_id, mock_file, household_id)


@pytest.mark.asyncio
async def test_get_attachment(attachment_service, mock_db, household_id):
    """Test getting attachment metadata."""
    attachment_id = uuid4()
    mock_attachment = Attachment(
        id=attachment_id,
        file_path="/test/file.pdf",
        mime_type="application/pdf",
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_attachment
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await attachment_service.get_attachment(attachment_id, household_id)

    assert result is not None
    assert result.id == attachment_id


@pytest.mark.asyncio
async def test_get_attachment_not_found(attachment_service, mock_db, household_id):
    """Test getting non-existent attachment."""
    attachment_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="Attachment not found"):
        await attachment_service.get_attachment(attachment_id, household_id)


@pytest.mark.asyncio
async def test_download_attachment(attachment_service, mock_db, household_id):
    """Test downloading attachment content returns stream + mime + filename."""
    attachment_id = uuid4()
    mock_attachment = Attachment(
        id=attachment_id,
        file_path="/test/file.pdf",
        mime_type="application/pdf",
        file_name="test.pdf",
        encrypted=False,
    )

    get_result = MagicMock()
    get_result.scalar_one_or_none.return_value = mock_attachment
    mock_db.execute = AsyncMock(return_value=get_result)

    with patch(
        "app.services.attachment_service.stream_file",
        new_callable=AsyncMock,
    ) as mock_stream:
        mock_stream.return_value = iter([b"file content"])

        stream, mime_type, file_name = await attachment_service.download_attachment(
            attachment_id, household_id
        )

        assert mime_type == "application/pdf"
        assert file_name == "test.pdf"


@pytest.mark.asyncio
async def test_delete_attachment(attachment_service, mock_db, household_id):
    """Test deleting an attachment with reference counting."""
    attachment_id = uuid4()
    mock_attachment = Attachment(
        id=attachment_id,
        file_path="/test/file.pdf",
        content_hash="abc123",
    )

    # First call: get_attachment returns the attachment
    get_result = MagicMock()
    get_result.scalar_one_or_none.return_value = mock_attachment

    # Second call: reference count returns 0 (no remaining refs)
    count_result = MagicMock()
    count_result.scalar.return_value = 0

    mock_db.execute = AsyncMock(side_effect=[get_result, count_result])

    with patch(
        "app.services.attachment_service.delete_file", new_callable=AsyncMock
    ) as mock_delete:
        await attachment_service.delete_attachment(attachment_id, household_id)

        mock_delete.assert_called_once()
        mock_db.delete.assert_called_once_with(mock_attachment)
