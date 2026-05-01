"""Unit tests for health record service."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date
from uuid import uuid4
from app.services.health_record_service import HealthRecordService
from app.models.base import HealthRecord, RecordType


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def record_service(mock_db):
    """Create HealthRecordService instance."""
    return HealthRecordService(mock_db)


@pytest.mark.asyncio
async def test_create_record(record_service, mock_db):
    """Test creating a health record."""
    member_id = uuid4()

    # Mock the duplicate check query — no existing record
    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=dup_result)
    mock_db.refresh = AsyncMock()

    record = await record_service.create_record(
        member_id=member_id,
        record_type=RecordType.LAB_REPORT,
        record_date=date(2024, 1, 15),
        clinical_data="HbA1c test",
    )

    assert record.record_type == RecordType.LAB_REPORT
    assert record.family_member_id == member_id


@pytest.mark.asyncio
async def test_get_record(record_service, mock_db):
    """Test getting a health record."""
    member_id = uuid4()
    record_id = uuid4()
    mock_record = HealthRecord(
        id=record_id,
        family_member_id=member_id,
        record_type=RecordType.LAB_REPORT,
        is_deleted=False,
    )

    mock_result = MagicMock()
    mock_result.unique.return_value.scalar_one_or_none.return_value = mock_record
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await record_service.get_record(member_id, record_id)

    assert result is not None
    assert result.id == record_id


@pytest.mark.asyncio
async def test_get_record_not_found(record_service, mock_db):
    """Test getting non-existent record."""
    member_id = uuid4()
    record_id = uuid4()

    mock_result = MagicMock()
    mock_result.unique.return_value.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="Record not found"):
        await record_service.get_record(member_id, record_id)


@pytest.mark.asyncio
async def test_soft_delete_record(record_service, mock_db):
    """Test soft-deleting a health record."""
    member_id = uuid4()
    record_id = uuid4()
    mock_record = HealthRecord(
        id=record_id,
        family_member_id=member_id,
        is_deleted=False,
    )

    get_result = MagicMock()
    get_result.unique.return_value.scalar_one_or_none.return_value = mock_record
    mock_db.execute = AsyncMock(return_value=get_result)

    await record_service.soft_delete_record(member_id, record_id)

    assert mock_record.is_deleted


@pytest.mark.asyncio
async def test_list_records_pagination(record_service, mock_db):
    """Test listing records with pagination."""
    member_id = uuid4()
    mock_record = HealthRecord(
        id=uuid4(),
        family_member_id=member_id,
        record_type=RecordType.LAB_REPORT,
        record_date=date(2024, 1, 15),
        is_deleted=False,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.unique.return_value.all.return_value = [mock_record]
    mock_db.execute = AsyncMock(return_value=mock_result)

    records, next_cursor, has_more = await record_service.list_records(member_id, limit=20)

    assert len(records) == 1
    assert records[0].record_type == RecordType.LAB_REPORT


@pytest.mark.asyncio
async def test_get_lab_records_view(record_service, mock_db):
    """Test getting lab records view."""
    member_id = uuid4()
    mock_record = HealthRecord(
        id=uuid4(),
        family_member_id=member_id,
        record_type=RecordType.LAB_REPORT,
        clinical_data="HbA1c",
        diagnosis="6.5%",
        is_deleted=False,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.unique.return_value.all.return_value = [mock_record]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await record_service.get_lab_records_view(member_id)

    assert len(result) == 1
    assert result[0]["test_name"] == "HbA1c"
