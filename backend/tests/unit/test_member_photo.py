"""Unit tests for member profile-photo handling (MemberService + schema)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.family_member import FamilyMemberResponse
from app.services.member_service import MemberService


def _base_member_kwargs():
    """Minimal kwargs to construct a FamilyMemberResponse for schema tests."""
    return {
        "id": uuid4(),
        "household_id": uuid4(),
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": "1990-01-01",
        "gender": "female",
        "relationship_type": "self",
        "is_active": True,
        "cloud_ai_consent": True,
        "created_at": "2024-01-01T00:00:00",
    }


def test_response_has_photo_derived_and_path_hidden():
    """has_photo is computed from photo_path; the raw path is never serialized."""
    no_photo = FamilyMemberResponse(**_base_member_kwargs(), photo_path=None)
    with_photo = FamilyMemberResponse(**_base_member_kwargs(), photo_path="/data/files/ab/x.jpg")

    assert no_photo.has_photo is False
    assert with_photo.has_photo is True

    dumped = with_photo.model_dump(mode="json")
    assert "photo_path" not in dumped  # internal path never exposed
    assert dumped["has_photo"] is True
    assert "photo_updated_at" in dumped  # cache-bust field is exposed


@pytest.mark.asyncio
async def test_set_member_photo_sets_fields():
    db = AsyncMock()
    db.flush = AsyncMock()
    service = MemberService(db)

    member = MagicMock()
    member.photo_content_hash = None
    member.photo_path = None
    member.photo_thumbnail_path = None
    file = MagicMock()
    file.content_type = "image/jpeg"

    with (
        patch.object(MemberService, "get_member", new_callable=AsyncMock, return_value=member),
        patch(
            "app.core.storage.save_file_hashed",
            new_callable=AsyncMock,
            return_value=(Path("/tmp/files/ab/hash123.jpg"), "hash123", ".jpg"),
        ),
        patch(
            "app.core.thumbnails.generate_thumbnail",
            new_callable=AsyncMock,
            return_value=Path("/tmp/thumbs/hash123.webp"),
        ),
    ):
        result = await service.set_member_photo(uuid4(), file, uuid4())

    assert result is member
    assert member.photo_content_hash == "hash123"
    assert member.photo_path == "/tmp/files/ab/hash123.jpg"
    assert member.photo_thumbnail_path == "/tmp/thumbs/hash123.webp"
    assert member.photo_updated_at is not None
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_set_member_photo_rejects_non_image():
    db = AsyncMock()
    db.flush = AsyncMock()
    service = MemberService(db)

    member = MagicMock()
    file = MagicMock()
    file.content_type = "application/pdf"

    with patch.object(MemberService, "get_member", new_callable=AsyncMock, return_value=member):
        with pytest.raises(ValueError, match="jpeg"):
            await service.set_member_photo(uuid4(), file, uuid4())

    db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_set_member_photo_replaces_and_deletes_old_blob():
    db = AsyncMock()
    db.flush = AsyncMock()
    service = MemberService(db)

    member = MagicMock()
    member.photo_content_hash = "oldhash"
    member.photo_path = "/tmp/files/old.jpg"
    member.photo_thumbnail_path = None  # no thumbnail to clean
    file = MagicMock()
    file.content_type = "image/png"

    # Reference-count queries: 0 remaining → old blob is deleted.
    count_result = MagicMock()
    count_result.scalar.return_value = 0
    db.execute = AsyncMock(side_effect=[count_result, count_result])

    with (
        patch.object(MemberService, "get_member", new_callable=AsyncMock, return_value=member),
        patch(
            "app.core.storage.save_file_hashed",
            new_callable=AsyncMock,
            return_value=(Path("/tmp/files/new.png"), "newhash", ".png"),
        ),
        patch(
            "app.core.thumbnails.generate_thumbnail",
            new_callable=AsyncMock,
            return_value=Path("/tmp/thumbs/new.webp"),
        ),
        patch("app.core.storage.delete_file", new_callable=AsyncMock) as mock_delete,
    ):
        await service.set_member_photo(uuid4(), file, uuid4())

    mock_delete.assert_awaited_once_with(Path("/tmp/files/old.jpg"))
    assert member.photo_content_hash == "newhash"


@pytest.mark.asyncio
async def test_replace_keeps_blob_when_shared():
    """A blob dedup-shared with another member/attachment is not deleted."""
    db = AsyncMock()
    db.flush = AsyncMock()
    service = MemberService(db)

    member = MagicMock()
    member.photo_content_hash = "oldhash"
    member.photo_path = "/tmp/files/old.jpg"
    member.photo_thumbnail_path = None
    file = MagicMock()
    file.content_type = "image/jpeg"

    # Another reference exists → blob must survive.
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    db.execute = AsyncMock(side_effect=[count_result, count_result])

    with (
        patch.object(MemberService, "get_member", new_callable=AsyncMock, return_value=member),
        patch(
            "app.core.storage.save_file_hashed",
            new_callable=AsyncMock,
            return_value=(Path("/tmp/files/new.jpg"), "newhash", ".jpg"),
        ),
        patch(
            "app.core.thumbnails.generate_thumbnail",
            new_callable=AsyncMock,
            return_value=Path("/tmp/thumbs/new.webp"),
        ),
        patch("app.core.storage.delete_file", new_callable=AsyncMock) as mock_delete,
    ):
        await service.set_member_photo(uuid4(), file, uuid4())

    mock_delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_member_photo_clears_fields():
    db = AsyncMock()
    db.flush = AsyncMock()
    service = MemberService(db)

    member = MagicMock()
    member.photo_content_hash = "hash123"
    member.photo_path = "/tmp/files/x.jpg"
    member.photo_thumbnail_path = None

    count_result = MagicMock()
    count_result.scalar.return_value = 0
    db.execute = AsyncMock(side_effect=[count_result, count_result])

    with (
        patch.object(MemberService, "get_member", new_callable=AsyncMock, return_value=member),
        patch("app.core.storage.delete_file", new_callable=AsyncMock) as mock_delete,
    ):
        result = await service.delete_member_photo(uuid4(), uuid4())

    assert result is member
    assert member.photo_path is None
    assert member.photo_content_hash is None
    assert member.photo_thumbnail_path is None
    assert member.photo_updated_at is not None
    mock_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_member_photo_member_not_found():
    db = AsyncMock()
    service = MemberService(db)

    with patch.object(MemberService, "get_member", new_callable=AsyncMock, side_effect=ValueError):
        with pytest.raises(ValueError):
            await service.delete_member_photo(uuid4(), uuid4())
