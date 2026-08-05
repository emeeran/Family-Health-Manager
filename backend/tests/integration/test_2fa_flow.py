"""End-to-end 2FA flow: setup → verify → login requires code → complete login.

Closes the previously-untested TOTP auth path (enrollment + the /login/2fa
completion endpoint + backup-code login + wrong-code rejection).
"""

import pyotp
import pytest

pytestmark = pytest.mark.asyncio

USERNAME = "testuser"
PASSWORD = "TestP@ss123"


async def test_2fa_setup_returns_secret_and_backup_codes(auth_client):
    resp = await auth_client.post("/api/v1/auth/2fa/setup")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["secret"]) == 32
    assert len(data["backup_codes"]) == 8
    assert data["qr_code_base64"]


async def test_2fa_enable_then_login_requires_and_completes(auth_client):
    # 1. Setup returns the plaintext secret (for QR display).
    setup = (await auth_client.post("/api/v1/auth/2fa/setup")).json()
    secret = setup["secret"]

    # 2. Verify with a live code → enables 2FA.
    code = pyotp.TOTP(secret).now()
    verify = await auth_client.post("/api/v1/auth/2fa/verify", json={"code": code})
    assert verify.status_code == 200, verify.text

    # 3. Password login now signals 2FA required (no tokens).
    login = await auth_client.post(
        "/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD}
    )
    assert login.status_code == 200
    assert login.json().get("requires_2fa") is True

    # 4. Complete login with a fresh TOTP code → tokens issued.
    complete = await auth_client.post(
        "/api/v1/auth/login/2fa",
        json={"username": USERNAME, "code": pyotp.TOTP(secret).now()},
    )
    assert complete.status_code == 200, complete.text
    assert "access_token" in complete.json()


async def test_2fa_login_with_backup_code(auth_client):
    setup = (await auth_client.post("/api/v1/auth/2fa/setup")).json()
    code = pyotp.TOTP(setup["secret"]).now()
    await auth_client.post("/api/v1/auth/2fa/verify", json={"code": code})

    backup = setup["backup_codes"][0]
    resp = await auth_client.post(
        "/api/v1/auth/login/2fa", json={"username": USERNAME, "code": backup}
    )
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()


async def test_2fa_login_rejects_wrong_code(auth_client):
    setup = (await auth_client.post("/api/v1/auth/2fa/setup")).json()
    code = pyotp.TOTP(setup["secret"]).now()
    await auth_client.post("/api/v1/auth/2fa/verify", json={"code": code})

    resp = await auth_client.post(
        "/api/v1/auth/login/2fa", json={"username": USERNAME, "code": "000000"}
    )
    assert resp.status_code == 401


async def test_2fa_login_rejects_user_without_2fa(auth_client):
    """A user who never enabled 2FA can't use the /login/2fa endpoint."""
    resp = await auth_client.post(
        "/api/v1/auth/login/2fa", json={"username": USERNAME, "code": "123456"}
    )
    assert resp.status_code == 401


async def test_2fa_disable_requires_valid_code(auth_client):
    setup = (await auth_client.post("/api/v1/auth/2fa/setup")).json()
    code = pyotp.TOTP(setup["secret"]).now()
    await auth_client.post("/api/v1/auth/2fa/verify", json={"code": code})

    # Wrong code → disable rejected.
    bad = await auth_client.post(
        "/api/v1/auth/2fa/disable", json={"code": "000000", "backup_code": None}
    )
    assert bad.status_code in (400, 401)
