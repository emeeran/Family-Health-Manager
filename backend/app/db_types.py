"""SQLAlchemy column types for transparent at-rest encryption.

``EncryptedText`` stores Fernet ciphertext in a ``Text`` column, encrypting on
write and decrypting on read via :mod:`app.core.encryption`. ORM attributes
always yield plaintext, so every existing read path keeps working unchanged —
Pydantic ``from_attributes`` / ``model_dump``, backup ``model_validate``,
``json.loads(record.clinical_data)``, and the AI context builders all see
plaintext while the on-disk column holds ciphertext.

Legacy plaintext values read through unchanged: ``decrypt_secret`` returns the
raw value when it isn't a valid Fernet token, so the cutover is safe even if the
encrypting data migration runs after this code is deployed (and handles any row
the migration misses).

Columns previously declared ``String(N)`` are switched to ``EncryptedText``
because Fernet ciphertext (~76 chars overhead + 1.33× plaintext) exceeds short
``VARCHAR`` lengths. SQLite ignores ``VARCHAR`` length (dynamic typing), so
existing SQLite columns need no DDL change; the migration ``ALTER``s these to
``TEXT`` on PostgreSQL, which does enforce lengths.
"""

from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.encryption import decrypt_secret, encrypt_secret


class EncryptedText(TypeDecorator[str]):
    """A ``Text`` column whose value is Fernet-encrypted at rest.

    Writes: plaintext → ``encrypt_secret`` → ciphertext stored.
    Reads:  stored value → ``decrypt_secret`` → plaintext (legacy plaintext
            values pass through unchanged during/after migration).
    ``None`` and ``""`` pass through without encryption (no PHI in emptiness;
    ``encrypt_secret`` would otherwise produce a token of empty bytes).
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None or value == "":
            return value
        return encrypt_secret(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        # decrypt_secret(None)→None, ("")→"", (ciphertext)→plaintext,
        # (legacy plaintext)→unchanged.
        return decrypt_secret(value)
