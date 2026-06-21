"""Phase 0 — encrypted-at-rest staging + content-hash sidecar.

The original record must be encrypted the moment it lands (it used to sit as
plaintext in ``staging/`` until attach, or for 24h if the upload was abandoned),
and its SHA-256 must be available at extraction time so dedup/caching work.
"""

import hashlib
import io

import pytest
from cryptography.fernet import Fernet
from fastapi import UploadFile

from app.core import encryption as enc
from app.core import storage as storage_mod
from app.core.encryption import decrypt_file
from app.core.storage import (
    _read_staging_meta,
    finalize_staged_to_content_addressed,
    get_files_dir,
    get_staging_dir,
    save_staged_secured,
)

PDF_BODY = b"%PDF-1.4\nfake medical document content for testing\n" + b"x" * 200


def _pdf_upload(body: bytes = PDF_BODY, name: str = "scan.pdf") -> UploadFile:
    # Starlette's UploadFile derives content_type from headers (no content_type kwarg).
    return UploadFile(
        file=io.BytesIO(body),
        filename=name,
        headers={"content-type": "application/pdf"},
    )


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    """Point storage at a temp dir with a fixed Fernet so tests are hermetic."""
    monkeypatch.setattr(storage_mod.settings, "STORAGE_PATH", str(tmp_path))
    fernet = Fernet(Fernet.generate_key())
    monkeypatch.setattr(enc, "get_fernet", lambda: fernet)
    get_staging_dir().mkdir(parents=True, exist_ok=True)
    get_files_dir().mkdir(parents=True, exist_ok=True)
    return tmp_path


async def test_save_staged_secured_encrypts_and_writes_sidecar(isolated_storage):
    upload = _pdf_upload()
    staged_path, unique_filename, content_hash = await save_staged_secured(upload)

    # Original bytes are encrypted at rest — not stored in plaintext.
    assert staged_path.read_bytes() != PDF_BODY
    assert await decrypt_file(staged_path) == PDF_BODY

    # content_hash is the SHA-256 of the plaintext (dedup + cache key).
    assert content_hash == hashlib.sha256(PDF_BODY).hexdigest()

    # Sidecar carries hash + ext + mime for the attach step.
    meta = _read_staging_meta(unique_filename)
    assert meta is not None
    assert meta["content_hash"] == content_hash
    assert meta["ext"] == ".pdf"
    assert meta["mime"] == "application/pdf"
    assert meta["original_name"] == "scan.pdf"


async def test_finalize_relocates_encrypted_file_and_cleans_up(isolated_storage):
    upload = _pdf_upload()
    staged_path, unique_filename, content_hash = await save_staged_secured(upload)
    meta_path = get_staging_dir() / f"{unique_filename}.meta"

    final_path, returned_hash = await finalize_staged_to_content_addressed(
        staged_path, content_hash, ".pdf"
    )

    assert returned_hash == content_hash
    assert final_path.exists()  # relocated to content-addressable path
    assert not staged_path.exists()  # staged copy gone
    assert meta_path.exists()  # meta sidecar persists until attach cleans it
    assert await decrypt_file(final_path) == PDF_BODY
    # Sharded content-addressable layout: files/<2-char-shard>/<hash>.pdf
    assert final_path.parent.name == content_hash[:2]
    assert final_path.name == f"{content_hash}.pdf"


async def test_finalize_dedups_identical_content(isolated_storage):
    # First upload of the content.
    staged1, _name1, h1 = await save_staged_secured(_pdf_upload())
    final1, _ = await finalize_staged_to_content_addressed(staged1, h1, ".pdf")
    assert final1.exists()

    # Second upload of the SAME bytes — must reuse, not duplicate.
    staged2, _name2, h2 = await save_staged_secured(_pdf_upload())
    assert h2 == h1  # identical plaintext → identical hash
    final2, _ = await finalize_staged_to_content_addressed(staged2, h2, ".pdf")

    assert final2 == final1  # same path (reused)
    assert not staged2.exists()  # duplicate staged copy dropped
    shard = get_files_dir() / h1[:2]
    assert len(list(shard.glob(f"{h1}*"))) == 1  # exactly one physical file


async def test_save_staged_secured_records_member_id(isolated_storage):
    """The owning member_id is recorded in the sidecar so the staging-download
    endpoint can verify ownership (IDOR defense — a leaked staging id must not
    stream another member's document)."""
    upload = _pdf_upload()
    _path, unique_filename, _hash = await save_staged_secured(upload, member_id="mem-123")
    meta = _read_staging_meta(unique_filename)
    assert meta is not None
    assert meta["member_id"] == "mem-123"

    # Without a member_id the field is None (legacy/anonymous staging allowed
    # through the ownership check during rollout).
    _p2, name2, _h2 = await save_staged_secured(_pdf_upload())
    assert _read_staging_meta(name2)["member_id"] is None


async def test_save_staged_secured_rejects_magic_mismatch(isolated_storage):
    # PNG magic bytes declared as PDF must be rejected during staging.
    bad = _pdf_upload(body=b"\x89PNG\r\n\x1a\n" + b"not actually a pdf")
    with pytest.raises(ValueError, match="does not match declared type"):
        await save_staged_secured(bad)


async def test_attach_round_trip_uses_encrypted_relocate(isolated_storage, db_session):
    """Full extract→attach round trip: staged-encrypted file becomes an
    encrypted, content-addressed, dedup-aware Attachment retrievable as plaintext."""
    from uuid import uuid4

    from app.services.attachment_service import AttachmentService

    # 1. "Extract" path: secure-stage the original.
    staged_path, unique_filename, content_hash = await save_staged_secured(_pdf_upload())
    assert staged_path.exists()

    # 2. "Create record" path: attach the staged file (relocate, no re-encrypt).
    svc = AttachmentService(db_session)
    record_id = uuid4()
    attachment = await svc.attach_staged_file(
        record_id, unique_filename, original_file_name="scan.pdf"
    )
    await db_session.flush()

    assert attachment.encrypted is True
    assert attachment.content_hash == content_hash
    from pathlib import Path

    final = Path(attachment.file_path)
    assert final.exists()
    assert not staged_path.exists()  # staged file consumed
    assert not (get_staging_dir() / f"{unique_filename}.meta").exists()
    assert await decrypt_file(final) == PDF_BODY  # original retrievable
