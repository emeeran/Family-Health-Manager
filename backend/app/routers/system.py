"""Instance-wide admin endpoints — AI provider key management.

All endpoints require an admin user. Credentials are encrypted at rest with
Fernet (see :mod:`app.core.encryption`) and are never returned in plaintext;
GET exposes only a masked value plus ``is_set``/``using_env`` flags.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.provider_keys import (
    PROVIDER_SECRET_KEYS,
    SECRET_PROVIDERS,
    get_env_fallback,
    invalidate_provider_cache,
    normalize_ollama_url,
)
from app.models.app_secret import AppSecret
from app.models.base import User
from app.schemas.ai_provider_config import PROVIDER_LABELS
from app.schemas.system import (
    ImportFromEnvResponse,
    ProviderKeyStatus,
    ProviderKeyUpdate,
    ProviderKeysResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["System"])


def _mask(value: str, is_secret: bool) -> str:
    """Mask a secret to its last 4 chars; show non-secrets (URLs) in full."""
    if not is_secret:
        return value
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"


def _status_for(provider: str, stored_value: str | None) -> ProviderKeyStatus:
    """Build a masked status from the decrypted stored value (or ``None``)."""
    env_value = get_env_fallback(provider)
    is_set = bool(stored_value)
    is_secret = provider in SECRET_PROVIDERS
    if is_set:
        masked = _mask(stored_value, is_secret)
    elif env_value:
        masked = _mask(env_value, is_secret)
    else:
        masked = None
    return ProviderKeyStatus(
        provider=provider,
        label=PROVIDER_LABELS.get(provider, provider),
        is_set=is_set,
        using_env=(not is_set) and bool(env_value),
        masked=masked,
        is_secret=is_secret,
    )


async def _load_all(db: AsyncSession) -> dict[str, str | None]:
    """Decrypt every stored credential into ``{secret_key: plaintext}``."""
    rows = (await db.execute(select(AppSecret))).scalars().all()
    return {row.key: decrypt_secret(row.value) for row in rows}


async def _upsert(db: AsyncSession, secret_key: str, plaintext: str) -> None:
    """Insert or update the ciphertext for ``secret_key``."""
    existing = (
        await db.execute(select(AppSecret).where(AppSecret.key == secret_key))
    ).scalar_one_or_none()
    ciphertext = encrypt_secret(plaintext)
    if existing:
        existing.value = ciphertext
    else:
        db.add(AppSecret(key=secret_key, value=ciphertext))


@router.get("/provider-keys", response_model=ProviderKeysResponse)
async def list_provider_keys(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
) -> ProviderKeysResponse:
    """Return masked status for every provider credential (never plaintext)."""
    stored = await _load_all(db)
    keys = [
        _status_for(provider, stored.get(PROVIDER_SECRET_KEYS[provider]))
        for provider in PROVIDER_SECRET_KEYS
    ]
    return ProviderKeysResponse(keys=keys)


@router.put("/provider-keys", response_model=ProviderKeyStatus)
async def set_provider_key(
    body: ProviderKeyUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
) -> ProviderKeyStatus:
    """Store an encrypted credential. The DB becomes authoritative for that provider."""
    value = body.value
    if body.provider == "ollama":
        value = normalize_ollama_url(value)
    await _upsert(db, PROVIDER_SECRET_KEYS[body.provider], value)
    await db.flush()
    invalidate_provider_cache(body.provider)
    logger.info("provider key set: %s", body.provider)
    return _status_for(body.provider, value)


@router.delete("/provider-keys/{provider}")
async def delete_provider_key(
    provider: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
) -> dict[str, str]:
    """Clear a stored credential so resolution falls back to .env (or nothing)."""
    if provider not in PROVIDER_SECRET_KEYS:
        raise HTTPException(status_code=400, detail="Unknown provider")
    secret_key = PROVIDER_SECRET_KEYS[provider]
    row = (
        await db.execute(select(AppSecret).where(AppSecret.key == secret_key))
    ).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.flush()
    invalidate_provider_cache(provider)
    logger.info("provider key cleared: %s", provider)
    return {"deleted": provider}


@router.post("/provider-keys/import-from-env", response_model=ImportFromEnvResponse)
async def import_provider_keys_from_env(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
) -> ImportFromEnvResponse:
    """Copy every non-empty .env credential into the DB store (overwrites)."""
    imported: list[str] = []
    skipped: list[str] = []
    for provider in PROVIDER_SECRET_KEYS:
        env_value = get_env_fallback(provider)
        if env_value:
            await _upsert(db, PROVIDER_SECRET_KEYS[provider], env_value)
            imported.append(provider)
        else:
            skipped.append(provider)
    await db.flush()
    invalidate_provider_cache()
    logger.info("imported provider keys from .env: %s", imported)
    return ImportFromEnvResponse(imported=imported, skipped=skipped)
