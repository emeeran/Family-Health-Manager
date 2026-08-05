"""Tests for passphrase-encrypted backups (Flow A) + at-rest key bundling.

Covers:
- Pure crypto round-trip (encrypt/decrypt, wrong passphrase, app-key unwrap).
- BackupService.export_backup / validate_backup / import_backup with and without
  a passphrase, including the bundled-app-key path used for offsite restore.
"""

import io
import json
import zipfile
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.core import backup_crypto
from app.models.base import (
    FamilyMember,
    Gender,
    HealthRecord,
    Household,
    RecordType,
    Relationship,
    User,
)
from app.services.backup_service import BackupService

PASSPHRASE = "correct horse battery staple"


# ── Pure crypto ──────────────────────────────────────────────────────────────


def test_encrypt_decrypt_round_trip():
    plaintext = b'secret PHI {"diagnosis": "hypertension"}'
    ciphertext, bundle = backup_crypto.encrypt_payload(plaintext, PASSPHRASE, app_key="k")
    assert ciphertext != plaintext
    recovered = backup_crypto.decrypt_payload(ciphertext, PASSPHRASE, bundle)
    assert recovered == plaintext


def test_wrong_passphrase_fails_opaquely():
    ciphertext, bundle = backup_crypto.encrypt_payload(b"data", PASSPHRASE, app_key=None)
    with pytest.raises(backup_crypto.BackupCryptoError):
        backup_crypto.decrypt_payload(ciphertext, "wrong passphrase", bundle)


def test_tampered_ciphertext_fails():
    ciphertext, bundle = backup_crypto.encrypt_payload(b"data", PASSPHRASE, app_key=None)
    # Flip a byte mid-token (appending a char doesn't always break Fernet's base64).
    tampered = bytearray(ciphertext)
    tampered[5] ^= 0xFF
    with pytest.raises(backup_crypto.BackupCryptoError):
        backup_crypto.decrypt_payload(bytes(tampered), PASSPHRASE, bundle)


def test_app_key_unwrap_round_trip():
    app_key = "ZZZZ-this-is-a-fernet-key"
    _ciphertext, bundle = backup_crypto.encrypt_payload(b"data", PASSPHRASE, app_key=app_key)
    assert bundle.wrapped_app_key is not None
    assert backup_crypto.unwrap_app_key(bundle, PASSPHRASE) == app_key


def test_app_key_absent_returns_none():
    _ciphertext, bundle = backup_crypto.encrypt_payload(b"data", PASSPHRASE, app_key=None)
    assert bundle.wrapped_app_key is None
    assert backup_crypto.unwrap_app_key(bundle, PASSPHRASE) is None


def test_encrypt_requires_passphrase():
    with pytest.raises(backup_crypto.BackupCryptoError):
        backup_crypto.encrypt_payload(b"data", "", app_key=None)


def test_bundle_app_key_plaintext():
    assert backup_crypto.bundle_app_key_plaintext(None) is None
    raw = backup_crypto.bundle_app_key_plaintext("some-key")
    assert json.loads(raw)["encryption_key"] == "some-key"


# ── BackupService round-trip ─────────────────────────────────────────────────


@pytest.fixture
async def household_with_data(db_session):
    """Build a minimal household + member + record for export."""
    user = User(id=uuid4(), username="backupuser", password_hash="x")
    household = Household(id=uuid4(), name="Backup Home", primary_user_id=user.id)
    member = FamilyMember(
        id=uuid4(),
        household_id=household.id,
        first_name="Test",
        last_name="Patient",
        date_of_birth=date(1980, 1, 1),
        gender=Gender.MALE,
        relationship_type=Relationship.SELF,
    )
    record = HealthRecord(
        id=uuid4(),
        family_member_id=member.id,
        record_type=RecordType.LAB_REPORT,
        record_date=date(2026, 1, 1),
        clinical_data='{"hemoglobin": "14.1"}',
        diagnosis=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add_all([user, household, member, record])
    await db_session.commit()
    return household


@pytest.mark.asyncio
async def test_export_without_passphrase_is_plaintext(household_with_data, db_session):
    zip_bytes = await BackupService(db_session).export_backup(household_with_data.id)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "data.json" in names
        assert "data.json.enc" not in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["encrypted"] is False
        data = json.loads(zf.read("data.json"))
        assert len(data["members"]) == 1


@pytest.mark.asyncio
async def test_export_with_passphrase_encrypts_payload(household_with_data, db_session):
    zip_bytes = await BackupService(db_session).export_backup(
        household_with_data.id, passphrase=PASSPHRASE
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "data.json.enc" in names
        assert "key.bundle" in names
        assert "data.json" not in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["encrypted"] is True
        # The ciphertext must not contain plaintext PHI.
        enc = zf.read("data.json.enc")
        assert b"Test Patient" not in enc


@pytest.mark.asyncio
async def test_validate_encrypted_requires_passphrase(household_with_data, db_session, tmp_path):
    zip_bytes = await BackupService(db_session).export_backup(
        household_with_data.id, passphrase=PASSPHRASE
    )
    archive = tmp_path / "backup.zip"
    archive.write_bytes(zip_bytes)

    # No passphrase → rejected.
    no_pass = BackupService(db_session).validate_backup(archive)
    assert not no_pass.valid
    assert "passphrase" in no_pass.errors[0].lower()

    # Wrong passphrase → rejected.
    wrong = BackupService(db_session).validate_backup(archive, passphrase="nope")
    assert not wrong.valid

    # Correct passphrase → valid + manifest parsed.
    ok = BackupService(db_session).validate_backup(archive, passphrase=PASSPHRASE)
    assert ok.valid
    assert ok.manifest is not None
    assert ok.manifest.counts.members == 1


@pytest.mark.asyncio
async def test_import_encrypted_round_trip(household_with_data, db_session, tmp_path):
    """Export encrypted → import into a fresh household; data survives."""
    service = BackupService(db_session)
    zip_bytes = await service.export_backup(
        household_with_data.id, passphrase=PASSPHRASE
    )
    archive = tmp_path / "backup.zip"
    archive.write_bytes(zip_bytes)

    validation = service.validate_backup(archive, passphrase=PASSPHRASE)
    assert validation.valid

    # A second household acts as the restore target.
    user2 = User(id=uuid4(), username="restoreuser", password_hash="x")
    target = Household(id=uuid4(), name="Restore Home", primary_user_id=user2.id)
    db_session.add_all([user2, target])
    await db_session.commit()

    result = await service.import_backup(
        target.id, validation.validation_id, "merge", passphrase=PASSPHRASE
    )
    assert result.errors == []
    # The record survived the encrypted round-trip: it was decrypted, parsed,
    # and processed by the importer (imported fresh, or skipped because its id
    # already exists in this shared-DB fixture). Either way, the passphrase-
    # encrypted payload was recovered end to end.
    assert result.imported.health_records + result.skipped.health_records == 1
