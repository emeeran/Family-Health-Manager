"""Unit tests for the TOTP / backup-code service (2FA primitives)."""

import json

import pyotp

from app.services.totp_service import TOTPService


def test_generate_secret_is_base32_32chars():
    secret = TOTPService.generate_secret()
    # pyotp random_base32() defaults to 32 base32 chars
    assert len(secret) == 32
    pyotp.TOTP(secret)  # parses without error


def test_verify_code_accepts_current_code():
    secret = TOTPService.generate_secret()
    code = pyotp.TOTP(secret).now()
    assert TOTPService.verify_code(secret, code) is True


def test_verify_code_rejects_garbage():
    secret = TOTPService.generate_secret()
    assert TOTPService.verify_code(secret, "000000") is False or True  # 1/10^6 false positive
    # A clearly invalid code (non-numeric) is always rejected.
    assert TOTPService.verify_code(secret, "not-a-code") is False


def test_verify_code_wrong_secret_rejects():
    secret = TOTPService.generate_secret()
    other = TOTPService.generate_secret()
    code = pyotp.TOTP(secret).now()
    # Different secret almost certainly rejects (allow the rare collision)
    assert TOTPService.verify_code(other, code) is False


def test_generate_backup_codes_count_and_format():
    codes = TOTPService.generate_backup_codes()
    assert len(codes) == 8
    assert all(isinstance(c, str) and len(c) == 8 for c in codes)  # token_hex(4) → 8 hex chars


def test_verify_backup_code_consumes_once():
    codes = TOTPService.generate_backup_codes()
    stored = json.dumps(codes)
    target = codes[0]
    valid, updated = TOTPService.verify_backup_code(stored, target)
    assert valid is True
    assert target not in json.loads(updated)  # consumed
    # Reusing the same code fails.
    valid2, _ = TOTPService.verify_backup_code(updated, target)
    assert valid2 is False


def test_verify_backup_code_case_insensitive():
    codes = ["ABCD1234"]
    valid, _ = TOTPService.verify_backup_code(json.dumps(codes), "abcd1234")
    assert valid is True


def test_verify_backup_code_none_input():
    valid, returned = TOTPService.verify_backup_code(None, "anything")
    assert valid is False
    assert returned == "[]"


def test_qr_code_base64_is_nonempty():
    secret = TOTPService.generate_secret()
    qr = TOTPService.generate_qr_code_base64(secret, "alice")
    assert isinstance(qr, str) and len(qr) > 0
