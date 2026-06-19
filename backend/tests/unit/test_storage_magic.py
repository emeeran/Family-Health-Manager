"""Magic-byte verification, focused on the WebP RIFF/WEBP case (#14)."""

from app.core.storage import _magic_matches, ALLOWED_MIME_TYPES


def _webp_chunk() -> bytes:
    # RIFF header (4) + file size (4) + "WEBP" + payload
    return b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"VP8 "


def _wav_chunk() -> bytes:
    # RIFF container but WAVE, not WEBP
    return b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"fmt "


def test_webp_is_in_allow_list() -> None:
    assert "image/webp" in ALLOWED_MIME_TYPES


def test_webp_magic_matches_riff_webp() -> None:
    assert _magic_matches(_webp_chunk(), "image/webp") is True


def test_webp_magic_rejects_non_webp_riff() -> None:
    assert _magic_matches(_wav_chunk(), "image/webp") is False


def test_existing_types_still_match() -> None:
    assert _magic_matches(b"%PDF-1.4...", "application/pdf") is True
    assert _magic_matches(b"\xff\xd8\xff\xe0...", "image/jpeg") is True
    assert _magic_matches(b"\x89PNG\r\n\x1a\n...", "image/png") is True


def test_unknown_mime_does_not_match() -> None:
    assert _magic_matches(b"RIFF\x00\x00\x00\x00WEBP", "application/octet-stream") is False
