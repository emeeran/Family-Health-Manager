"""Unit tests for audit service."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from uuid import uuid4
from app.services.audit_service import AuditService
from app.models.base import AuditLog


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def audit_service(mock_db):
    """Create AuditService instance."""
    return AuditService(mock_db)


@pytest.mark.asyncio
async def test_log_action(audit_service, mock_db):
    """Test logging an audit action."""
    user_id = uuid4()

    audit = await audit_service.log_action(
        user_id=user_id,
        action="CREATE",
        resource_type="health_record",
        resource_id=uuid4(),
        current_state={"id": "test"},
    )

    assert audit.action == "CREATE"
    assert audit.user_id == user_id


@pytest.mark.asyncio
async def test_log_action_with_all_fields(audit_service, mock_db):
    """Test logging with all optional fields."""
    user_id = uuid4()
    resource_id = uuid4()

    audit = await audit_service.log_action(
        user_id=user_id,
        action="UPDATE",
        resource_type="family_member",
        resource_id=resource_id,
        previous_state={"name": "Old"},
        current_state={"name": "New"},
        ip_address="192.168.1.1",
    )

    assert audit.previous_state == {"name": "Old"}
    assert audit.current_state == {"name": "New"}
    assert audit.ip_address == "192.168.1.1"


@pytest.mark.asyncio
async def test_list_audit_logs(audit_service, mock_db):
    """Test listing audit logs."""
    user_id = uuid4()
    mock_audit = AuditLog(
        id=uuid4(),
        user_id=user_id,
        action="CREATE",
        resource_type="health_record",
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_audit]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await audit_service.list_audit_logs(user_id)

    assert len(result) == 1
    assert result[0].action == "CREATE"


@pytest.mark.asyncio
async def test_list_audit_logs_filtered(audit_service, mock_db):
    """Test listing audit logs with filters."""
    user_id = uuid4()
    mock_audit = AuditLog(
        id=uuid4(),
        user_id=user_id,
        action="CREATE",
        resource_type="health_record",
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_audit]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await audit_service.list_audit_logs(
        user_id, action="CREATE", resource_type="health_record"
    )

    assert len(result) == 1


@pytest.mark.asyncio
async def test_list_audit_logs_date_range(audit_service, mock_db):
    """Test listing audit logs with date range."""
    user_id = uuid4()
    date_from = datetime(2024, 1, 1)
    date_to = datetime(2024, 1, 31)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    await audit_service.list_audit_logs(user_id, date_from=date_from, date_to=date_to)

    # Verify query was called (filtering is done in the service)
