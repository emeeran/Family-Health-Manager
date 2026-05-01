"""Integration tests for authentication endpoints."""
import pytest


pytestmark = pytest.mark.asyncio


async def test_register_success(client):
    """POST /auth/register with valid data returns 201."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "newuser1", "password": "Str0ng!Pass"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["username"] == "newuser1"
    assert body["is_active"] is True


async def test_register_duplicate(client):
    """Registering same username twice returns 400."""
    payload = {"username": "dupuser", "password": "Str0ng!Pass"}
    resp1 = await client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 400


async def test_register_weak_password(client):
    """Password without required complexity → 400."""
    # "weakpass" is 8 chars (passes schema min_length) but lacks
    # uppercase, digit, and special character.
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "weakuser", "password": "weakpass"},
    )
    assert resp.status_code == 400


async def test_login_success(client):
    """POST /auth/login returns 200 with access_token."""
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={"username": "loginuser", "password": "Str0ng!Pass"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "loginuser", "password": "Str0ng!Pass"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password(client):
    """Login with wrong password returns 401."""
    await client.post(
        "/api/v1/auth/register",
        json={"username": "wrongpwuser", "password": "Str0ng!Pass"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "wrongpwuser", "password": "WrongPass!99"},
    )
    assert resp.status_code == 401


async def test_login_nonexistent_user(client):
    """Login with unknown username returns 401."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "ghost_user_xyz", "password": "Whatever!12"},
    )
    assert resp.status_code == 401


async def test_protected_endpoint_without_token(client):
    """Accessing a protected endpoint without token returns 401."""
    resp = await client.get("/api/v1/members")
    assert resp.status_code == 401


async def test_protected_endpoint_with_token(auth_client):
    """Accessing a protected endpoint with valid token returns 200."""
    resp = await auth_client.get("/api/v1/members")
    assert resp.status_code == 200
