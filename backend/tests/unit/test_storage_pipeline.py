"""Unit tests for the storage pipeline (PDF optimization + encryption-at-rest)."""
import hashlib
from types import SimpleNamespace

import pytest

import app.core.storage as storage
from app.core.encryption import decrypt_file


def _settings(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(
        STORAGE_PATH=str(tmp_path),
        OPTIMIZE_PDFS=False,
        PDF_OPTIMIZE_DPI="ebook",
    )


@pytest.mark.asyncio
async def test_store_plaintext_file_encrypts_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "settings", _settings(tmp_path))
    plaintext = b"confidential medical record content " * 100
    src = tmp_path / "src.bin"
    src.write_bytes(plaintext)

    final, content_hash = await storage._store_plaintext_file(
        src, ".bin", "application/octet-stream"
    )

    assert content_hash == hashlib.sha256(plaintext).hexdigest()
    # The stored file is encrypted, not the raw plaintext.
    assert final.read_bytes() != plaintext
    assert await decrypt_file(final) == plaintext


@pytest.mark.asyncio
async def test_store_plaintext_file_dedups(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "settings", _settings(tmp_path))
    data = b"identical content"
    src1 = tmp_path / "a.bin"
    src1.write_bytes(data)
    src2 = tmp_path / "b.bin"
    src2.write_bytes(data)

    f1, h1 = await storage._store_plaintext_file(src1, ".bin", "application/octet-stream")
    f2, h2 = await storage._store_plaintext_file(src2, ".bin", "application/octet-stream")

    assert h1 == h2 and f1 == f2  # same content → same content-addressed path
    assert f1.exists()


@pytest.mark.asyncio
async def test_stream_plaintext_decrypts_and_raw(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "settings", _settings(tmp_path))
    data = b"streaming plaintext " * 50
    src = tmp_path / "s.bin"
    src.write_bytes(data)
    final, _ = await storage._store_plaintext_file(src, ".bin", "application/octet-stream")

    decrypted = b"".join([c async for c in storage.stream_plaintext(final, encrypted=True)])
    assert decrypted == data

    raw = b"".join([c async for c in storage.stream_plaintext(src, encrypted=False)])
    assert raw == data


def test_optimize_pdf_disabled_returns_src(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "settings", _settings(tmp_path))
    src = tmp_path / "x.pdf"
    src.write_bytes(b"%PDF-1.4 fake")
    assert storage.optimize_pdf(src) is src


def test_optimize_pdf_noop_without_gs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "settings",
        SimpleNamespace(STORAGE_PATH=str(tmp_path), OPTIMIZE_PDFS=True, PDF_OPTIMIZE_DPI="ebook"),
    )
    src = tmp_path / "x.pdf"
    src.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(storage.shutil, "which", lambda *a, **k: None)
    assert storage.optimize_pdf(src) is src


@pytest.mark.asyncio
async def test_store_plaintext_file_hash_is_of_plaintext(tmp_path, monkeypatch):
    """content_hash must be the plaintext hash (so integrity/dedup work), not
    of the ciphertext (Fernet is non-deterministic)."""
    monkeypatch.setattr(storage, "settings", _settings(tmp_path))
    plaintext = b"some record bytes"
    src = tmp_path / "r.bin"
    src.write_bytes(plaintext)
    final, content_hash = await storage._store_plaintext_file(
        src, ".bin", "application/octet-stream"
    )
    # ciphertext hash must NOT equal the stored content_hash
    assert hashlib.sha256(final.read_bytes()).hexdigest() != content_hash
    assert content_hash == hashlib.sha256(plaintext).hexdigest()
