"""Shared test fixtures for integration tests."""
import asyncio
import os
import tempfile
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db
from app.models.base import Base  # noqa: F811 — models register on THIS Base

# Module-level temp file so all connections share the same DB
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
DB_PATH = _tmp.name
TEST_DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create async engine shared across tests."""
    eng = create_async_engine(
        TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()
    os.unlink(DB_PATH)


@pytest_asyncio.fixture
async def db_session(engine):
    """Fresh database session for each test.

    Drops and recreates all tables between tests for clean isolation.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    TestSession = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    """HTTP test client with DB session override.

    Shares a single session across all requests in a test so that
    uncommitted data (e.g. from register) is visible to subsequent
    requests (e.g. login).
    """
    async def override_get_db():
        yield db_session
        await db_session.commit()

    app.dependency_overrides[get_db] = override_get_db

    # Disable rate limiting during tests
    with patch("app.main.rate_limiter.check_limit", return_value=(True, 0)), \
         patch("app.main.auth_rate_limiter.check_limit", return_value=(True, 0)):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(client, db_session):
    """Authenticated client with a registered user and token."""
    # Register
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "TestP@ss123"},
    )
    assert resp.status_code == 201, f"Register failed: {resp.text}"

    # Login
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "TestP@ss123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]

    # Attach token as default query param
    client.params = {"token": token}
    yield client
