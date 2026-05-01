"""Unit tests for authentication service."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from app.services.auth_service import AuthService
from app.models.base import User
from app.core.security import hash_password


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def auth_service(mock_db):
    """Create AuthService instance."""
    return AuthService(mock_db)


@pytest.mark.asyncio
async def test_register_user_success(auth_service, mock_db):
    """Test successful user registration."""
    username = "testuser"
    password = "SecureP@ss123"

    # Mock the "check existing user" query to return None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    user, household = await auth_service.register_user(username, password)

    assert user.username == username
    assert household.primary_user_id == user.id


@pytest.mark.asyncio
async def test_register_user_weak_password(auth_service):
    """Test registration with weak password."""
    with pytest.raises(ValueError, match="Password does not meet strength requirements"):
        await auth_service.register_user("testuser", "weak")


@pytest.mark.asyncio
async def test_authenticate_success(auth_service, mock_db):
    """Test successful authentication."""
    username = "testuser"
    password = "SecureP@ss123"
    user_id = uuid4()

    mock_user = User(
        id=user_id,
        username=username,
        password_hash=hash_password(password),
        is_active=True,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await auth_service.authenticate(username, password)

    assert result is not None
    assert result.id == user_id


@pytest.mark.asyncio
async def test_authenticate_invalid_credentials(auth_service, mock_db):
    """Test authentication with wrong password."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await auth_service.authenticate("testuser", "wrongpassword")

    assert result is None


@pytest.mark.asyncio
async def test_create_session_token(auth_service):
    """Test session token creation."""
    user_id = uuid4()

    token, expires = auth_service.create_session_token(user_id)

    assert isinstance(token, str)
    assert len(token) > 0
    assert expires is not None


@pytest.mark.asyncio
async def test_get_user_by_id(auth_service, mock_db):
    """Test getting user by ID."""
    user_id = uuid4()
    mock_user = User(id=user_id, username="testuser", password_hash="hash")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await auth_service.get_user_by_id(user_id)

    assert result is not None
    assert result.id == user_id


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(auth_service, mock_db):
    """Test getting non-existent user."""
    user_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await auth_service.get_user_by_id(user_id)

    assert result is None
