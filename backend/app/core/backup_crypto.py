"""Passphrase encryption for backup archives + key bundling for offsite restore.

Two concerns live here:

1. **Flow A (household ZIP export)** — ``data.json`` carries structured PHI in
   plaintext. When the user supplies a passphrase, the archive's data payload is
   encrypted so a leaked/stolen ``.zip`` is unreadable without it
   (:func:`encrypt_payload` / :func:`decrypt_payload`).

2. **Key bundling** — the app's at-rest ``ENCRYPTION_KEY`` (Fernet) is needed to
   decrypt attachments, 2FA secrets, and provider keys. The disaster-recovery
   ``tar.gz`` previously bundled only ``health.db`` + attachments, so restoring
   onto fresh hardware left every encrypted file unrecoverable (see AUDIT.md).
   :func:`bundle_app_key` writes the key — wrapped under the passphrase when one
   is set — so an offsite restore is self-contained.

Scheme::

    DEK = fresh random Fernet key per archive
    DEK wrapped with scrypt(passphrase, salt)         → stored in key.bundle
    structured data.json encrypted with DEK            → data.json.enc
    app ENCRYPTION_KEY wrapped with DEK               → stored in key.bundle
    manifest.json stays plaintext (carries KDF params + encrypted flag)

Passphraseless (legacy) archives are unchanged: ``manifest.encrypted`` is False
and ``data.json`` is plaintext. The key bundle is only written when a passphrase
is supplied — a plaintext archive already exposes everything, so bundling the
key there would add no protection.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

# scrypt parameters. Backups are infrequent and offline (a user picks a
# passphrase at export/import), so a deliberately expensive derivation is
# appropriate — ~0.5-1s on commodity hardware, ~128 MB memory.
SCRYPT_N = 1 << 17
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 256 * 1024 * 1024  # 256 MB (N*r*p*128 needs ~128 MB)
SALT_BYTES = 16


class BackupCryptoError(Exception):
    """Raised when a backup payload cannot be encrypted/decrypted."""


@dataclass(frozen=True)
class KeyBundle:
    """The wrapped keys + KDF parameters stored alongside an encrypted archive.

    Serialized as JSON (``key.bundle``). Contains no plaintext secrets — the DEK
    is wrapped under the passphrase-derived key, and the app ``ENCRYPTION_KEY``
    is wrapped under the DEK.
    """

    salt_b64: str
    n: int
    r: int
    p: int
    wrapped_dek: str  # Fernet(DEK) where Fernet key = scrypt(passphrase, salt)
    wrapped_app_key: str | None = None  # Fernet(app ENCRYPTION_KEY) under the DEK

    def to_json(self) -> str:
        return json.dumps(
            {
                "salt": self.salt_b64,
                "n": self.n,
                "r": self.r,
                "p": self.p,
                "wrapped_dek": self.wrapped_dek,
                "wrapped_app_key": self.wrapped_app_key,
            }
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> KeyBundle:
        data = json.loads(raw)
        return cls(
            salt_b64=data["salt"],
            n=data["n"],
            r=data["r"],
            p=data["p"],
            wrapped_dek=data["wrapped_dek"],
            wrapped_app_key=data.get("wrapped_app_key"),
        )


def _derive_fernet(passphrase: str, salt: bytes, *, n: int, r: int, p: int) -> Fernet:
    """Derive a Fernet instance from a passphrase + salt via scrypt."""
    import base64

    dk = hashlib.scrypt(
        passphrase.encode(),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=32,
        maxmem=SCRYPT_MAXMEM,
    )
    return Fernet(base64.urlsafe_b64encode(dk))


def encrypt_payload(plaintext: bytes, passphrase: str, app_key: str | None) -> tuple[bytes, KeyBundle]:
    """Encrypt *plaintext* under *passphrase*.

    Returns ``(ciphertext, key_bundle)``. The fresh DEK is wrapped with the
    passphrase-derived key; the optional ``app_key`` (the app's at-rest
    ENCRYPTION_KEY) is wrapped with the DEK so a restore onto fresh hardware can
    recover encrypted attachments/2FA secrets.
    """
    if not passphrase:
        raise BackupCryptoError("A passphrase is required to encrypt a backup")
    salt = secrets.token_bytes(SALT_BYTES)
    wrapper = _derive_fernet(passphrase, salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    dek = Fernet.generate_key()
    dek_fernet = Fernet(dek)
    ciphertext = dek_fernet.encrypt(plaintext)
    wrapped_app_key = dek_fernet.encrypt(app_key.encode()).decode() if app_key else None
    import base64

    bundle = KeyBundle(
        salt_b64=base64.urlsafe_b64encode(salt).decode(),
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        wrapped_dek=wrapper.encrypt(dek).decode(),
        wrapped_app_key=wrapped_app_key,
    )
    return ciphertext, bundle


def decrypt_payload(ciphertext: bytes, passphrase: str, bundle: KeyBundle) -> bytes:
    """Decrypt *ciphertext* with *passphrase* + *bundle*.

    Raises :class:`BackupCryptoError` on a wrong passphrase or corrupt payload.
    """
    if not passphrase:
        raise BackupCryptoError("A passphrase is required to decrypt this backup")
    import base64

    try:
        salt = base64.urlsafe_b64decode(bundle.salt_b64)
        wrapper = _derive_fernet(passphrase, salt, n=bundle.n, r=bundle.r, p=bundle.p)
        dek = wrapper.decrypt(bundle.wrapped_dek.encode())
        dek_fernet = Fernet(dek)
        return dek_fernet.decrypt(ciphertext)
    except (InvalidToken, ValueError, TypeError) as exc:
        # Wrong passphrase, truncated token, or tampered bundle — all surface as
        # the same opaque error to avoid leaking which part failed.
        raise BackupCryptoError(
            "Could not decrypt backup — wrong passphrase or corrupt archive"
        ) from exc


def unwrap_app_key(bundle: KeyBundle, passphrase: str) -> str | None:
    """Recover the bundled app ``ENCRYPTION_KEY`` (or ``None`` if none was bundled).

    Called during restore so the destination install can decrypt attachments and
    2FA secrets that were encrypted under the source's key.
    """
    if not bundle.wrapped_app_key:
        return None
    import base64

    try:
        salt = base64.urlsafe_b64decode(bundle.salt_b64)
        wrapper = _derive_fernet(passphrase, salt, n=bundle.n, r=bundle.r, p=bundle.p)
        dek = wrapper.decrypt(bundle.wrapped_dek.encode())
        dek_fernet = Fernet(dek)
        return dek_fernet.decrypt(bundle.wrapped_app_key.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        raise BackupCryptoError(
            "Could not unwrap the bundled encryption key — wrong passphrase"
        )


def bundle_app_key_plaintext(app_key: str | None) -> str | None:
    """Write the app ``ENCRYPTION_KEY`` to a plain ``secrets.bundle`` JSON string.

    Used for the passphraseless disaster-recovery tar.gz so an offsite restore
    onto fresh hardware can recover encrypted attachments/2FA secrets. The tar.gz
    already contains the plaintext ``health.db``, so a plaintext key bundle adds
    no new exposure for that flow.
    """
    if not app_key:
        return None
    return json.dumps({"encryption_key": app_key})
