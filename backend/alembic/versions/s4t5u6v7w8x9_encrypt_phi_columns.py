"""encrypt_phi_columns

Encrypts structured PHI at rest (the remaining CRITICAL gap). The models now
declare these columns as ``EncryptedText`` (a SQLAlchemy TypeDecorator that
Fernet-encrypts on write / decrypts on read); this migration encrypts the
existing plaintext rows so the on-disk DB no longer holds diagnoses,
prescriptions, lab values, chat messages, etc. in cleartext.

Idempotent: rows already holding Fernet ciphertext (``is_secret_encrypted``) are
skipped, so re-runs and partially-completed runs are safe. The models' legacy
plaintext passthrough (``decrypt_secret`` returns non-token values unchanged)
means the app keeps reading correctly even if this runs after the code deploy.

Also adds ``ai_insights.prompt_key`` (plaintext, indexed) backfilled from each
cached insight's synthetic prompt prefix, so the per-member cache lookups still
work now that ``prompt`` itself is encrypted.

PostgreSQL enforces ``VARCHAR(N)`` lengths and Fernet ciphertext exceeds them,
so columns that were ``String(N)`` are widened to ``TEXT`` on Postgres. SQLite
ignores ``VARCHAR`` length (dynamic typing), so no DDL change is needed there.

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2026-08-05
"""

import logging

from alembic import op
import sqlalchemy as sa

revision: str = "s4t5u6v7w8x9"
down_revision: str | None = "r3s4t5u6v7w8"
branch_labels: str | None = None
depends_on: str | None = None

log = logging.getLogger(__name__)

# Columns already declared Text — encrypt only.
_TEXT_COLS: list[tuple[str, str]] = [
    ("health_records", "clinical_data"),
    ("health_records", "diagnosis"),
    ("health_records", "prescription_text"),
    ("health_records", "summary"),
    ("health_records", "transcription_report"),
    ("health_records", "transcription_verification"),
    ("health_records", "tags"),
    ("family_members", "medical_history_summary"),
    ("family_members", "family_history"),
    ("family_members", "allergies_json"),
    ("family_members", "notes"),
    ("family_members", "address"),
    ("lab_results", "result"),
    ("lab_results", "units"),
    ("lab_results", "ref_value"),
    ("lab_results", "note"),
    ("medications", "medicine"),
    ("medications", "dosage"),
    ("medications", "timing"),
    ("medications", "duration"),
    ("medications", "note"),
    ("medications", "provider_name"),
    ("medications", "type"),
    ("vaccinations", "notes"),
    ("ai_insights", "response"),
    ("ai_insights", "verification_warnings_json"),
    ("ai_insights", "sources_json"),
    ("ai_insights", "prompt"),
    ("messages", "content"),
    ("reminders", "description"),
    ("notifications", "message"),
    ("health_alerts", "message"),
    ("providers", "address"),
]

# Columns previously String(N) — widen to TEXT on Postgres, then encrypt.
# (table, column)
_EX_STRING_COLS: list[tuple[str, str]] = [
    ("family_members", "phone"),
    ("family_members", "patient_id"),
    ("family_members", "emergency_contact_name"),
    ("family_members", "emergency_contact_phone"),
    ("vaccinations", "name"),
    ("ai_insights", "verification_summary"),
    ("conversations", "title"),
    ("reminders", "title"),
    ("notifications", "title"),
    ("health_alerts", "title"),
    ("health_alerts", "value"),
    ("health_alerts", "reference"),
    ("providers", "speciality"),
    ("providers", "phone"),
]


def _existing_cols(inspector, table: str) -> set[str]:
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    """Widen ex-String columns (PG), add+backfill prompt_key, encrypt all PHI."""
    from app.core import encryption
    from app.models.ai import cache_key_from_prompt

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Widen ex-String(N) columns to TEXT on Postgres (ciphertext overflows
    #    VARCHAR). SQLite ignores VARCHAR length — no DDL needed there.
    if is_postgres:
        for table, col in _EX_STRING_COLS:
            if table in tables and col in _existing_cols(inspector, table):
                op.alter_column(table, col, type_=sa.Text(), existing_type=sa.String())

    # 2. ai_insights.prompt_key: add the column + index, then backfill it from
    #    each cached insight's (still-plaintext) prompt prefix BEFORE prompt is
    #    encrypted in step 3. Idempotent: only backfill rows where prompt_key is
    #    still NULL and the prompt is plaintext.
    if "ai_insights" in tables:
        cols = _existing_cols(inspector, "ai_insights")
        if "prompt_key" not in cols:
            op.add_column("ai_insights", sa.Column("prompt_key", sa.String(100), nullable=True))
            existing_indexes = {ix["name"] for ix in inspector.get_indexes("ai_insights")}
            if "ix_ai_insights_prompt_key" not in existing_indexes:
                op.create_index("ix_ai_insights_prompt_key", "ai_insights", ["prompt_key"])
        rows = bind.execute(
            sa.text("SELECT id, prompt, prompt_key FROM ai_insights")
        ).fetchall()
        for row_id, prompt, pkey in rows:
            if pkey is None and prompt and not encryption.is_secret_encrypted(prompt):
                key = cache_key_from_prompt(prompt)
                if key:
                    bind.execute(
                        sa.text("UPDATE ai_insights SET prompt_key = :k WHERE id = :id"),
                        {"k": key, "id": row_id},
                    )

    # 3. Encrypt every PHI column. Skip rows already holding ciphertext (re-run
    #    safety). table/col are compile-time constants, so the f-string SQL is
    #    safe (no user input).
    encrypted_total = 0
    for table, col in _TEXT_COLS + _EX_STRING_COLS:
        if table not in tables or col not in _existing_cols(inspector, table):
            continue
        rows = bind.execute(
            sa.text(f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL")
        ).fetchall()
        for row_id, val in rows:
            if val and not encryption.is_secret_encrypted(val):
                bind.execute(
                    sa.text(f"UPDATE {table} SET {col} = :v WHERE id = :id"),
                    {"v": encryption.encrypt_secret(val), "id": row_id},
                )
                encrypted_total += 1
    if encrypted_total:
        log.info("encrypt_phi_columns: encrypted %d PHI value(s) at rest", encrypted_total)


def downgrade() -> None:
    """Best-effort: decrypt PHI columns back to plaintext, drop prompt_key."""
    from app.core import encryption

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table, col in _TEXT_COLS + _EX_STRING_COLS:
        if table not in tables or col not in _existing_cols(inspector, table):
            continue
        rows = bind.execute(
            sa.text(f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL")
        ).fetchall()
        for row_id, val in rows:
            if val and encryption.is_secret_encrypted(val):
                bind.execute(
                    sa.text(f"UPDATE {table} SET {col} = :v WHERE id = :id"),
                    {"v": encryption.decrypt_secret(val), "id": row_id},
                )

    if "ai_insights" in tables and "prompt_key" in _existing_cols(inspector, "ai_insights"):
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("ai_insights")}
        if "ix_ai_insights_prompt_key" in existing_indexes:
            op.drop_index("ix_ai_insights_prompt_key", table_name="ai_insights")
        op.drop_column("ai_insights", "prompt_key")
