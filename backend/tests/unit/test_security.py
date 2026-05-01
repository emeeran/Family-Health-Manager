"""Unit tests for security utilities."""
from uuid import uuid4
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    _hash_token,
    create_refresh_token_value,
    validate_password_strength,
)


def test_hash_password():
    """Test password hashing."""
    password = "SecureP@ss123"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2")


def test_verify_password_success():
    """Test verifying correct password."""
    password = "SecureP@ss123"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_failure():
    """Test verifying wrong password."""
    password = "SecureP@ss123"
    hashed = hash_password(password)

    assert verify_password("WrongPassword", hashed) is False


def test_create_access_token():
    """Test JWT token creation."""
    user_id = uuid4()

    token, expires = create_access_token(user_id)

    assert isinstance(token, str)
    assert len(token) > 0
    assert expires is not None


def test_hash_token():
    """Test refresh token hashing is deterministic."""
    raw = create_refresh_token_value()
    h1 = _hash_token(raw)
    h2 = _hash_token(raw)
    assert h1 == h2
    assert _hash_token("different") != h1


def test_create_refresh_token_value():
    """Test refresh token generation."""
    t1 = create_refresh_token_value()
    t2 = create_refresh_token_value()
    assert isinstance(t1, str)
    assert len(t1) > 20
    assert t1 != t2


def test_validate_password_strength_valid():
    """Test valid password passes validation."""
    assert validate_password_strength("SecureP@ss123") is True
    assert validate_password_strength("MyP@ssw0rd!") is True


def test_validate_password_strength_too_short():
    """Test password too short."""
    assert validate_password_strength("Abc@1") is False


def test_validate_password_strength_no_upper():
    """Test password without uppercase."""
    assert validate_password_strength("securepass123@") is False


def test_validate_password_strength_no_digit():
    """Test password without digit."""
    assert validate_password_strength("Securepass@word") is False


def test_validate_password_strength_no_special():
    """Test password without special character."""
    assert validate_password_strength("SecurePass123") is False
