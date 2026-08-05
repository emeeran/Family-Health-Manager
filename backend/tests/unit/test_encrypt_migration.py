"""Tests the encrypt_phi_columns data migration directly.

Builds a DB with PLAINTEXT PHI rows (raw SQL inserts bypass the EncryptedText
TypeDecorator), runs the migration's ``upgrade()`` against a real connection
(via ``Operations.context``), and asserts the columns become Fernet ciphertext
with the original values recoverable — plus idempotency on re-run and the
ai_insights.prompt_key backfill.
"""

import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

from app.core import encryption
from app.models.base import Base


def _load_migration_module():
    """Load the migration file by path (the project ``alembic/`` dir isn't an
    importable package — it collides with the installed alembic library)."""
    import importlib.util

    here = Path(__file__).resolve().parent
    migration_file = here.parent.parent / "alembic" / "versions" / "s4t5u6v7w8x9_encrypt_phi_columns.py"
    spec = importlib.util.spec_from_file_location("encrypt_phi_columns_migration", migration_file)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


migration = _load_migration_module()


def _run_upgrade(engine):
    with engine.begin() as conn:
        mc = MigrationContext.configure(conn)
        with Operations.context(mc):
            migration.upgrade()


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/mig.db")
    Base.metadata.create_all(eng)
    return eng


def _seed_plaintext(engine):
    """Insert plaintext PHI rows directly (bypassing the TypeDecorator)."""
    rid = str(uuid.uuid4())
    ts = "2026-01-01 00:00:00"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO health_records "
                "(id, family_member_id, record_type, record_date, clinical_data, "
                " diagnosis, is_deleted, created_at, updated_at) "
                "VALUES (:id, :fm, 'doctor_visit', '2026-01-01', :cd, :dx, 0, :ts, :ts)"
            ),
            {
                "id": rid,
                "fm": str(uuid.uuid4()),
                "cd": "Plaintext clinical note about hypertension",
                "dx": "Hypertension",
                "ts": ts,
            },
        )
        # An AI insight cached under a synthetic prompt prefix.
        conn.execute(
            text(
                "INSERT INTO ai_insights "
                "(id, prompt, response, provider_used, verification_status, "
                " verification_claims_checked, generated_at) "
                "VALUES (:id, :p, 'plain response', 'auto', 'pending', 0, :ts)"
            ),
            {
                "id": str(uuid.uuid4()),
                "p": f"__preconsult__{uuid.uuid4()}__\n\nmember context body",
                "ts": ts,
            },
        )
    return rid


def test_migration_encrypts_plaintext_phi(engine):
    rid = _seed_plaintext(engine)
    _run_upgrade(engine)

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT clinical_data, diagnosis FROM health_records WHERE id = :id"),
            {"id": rid},
        ).one()
    cd, dx = row
    assert encryption.is_secret_encrypted(cd)
    assert encryption.is_secret_encrypted(dx)
    # Original plaintext recoverable.
    assert encryption.decrypt_secret(cd) == "Plaintext clinical note about hypertension"
    assert encryption.decrypt_secret(dx) == "Hypertension"


def test_migration_backfills_prompt_key_and_encrypts_prompt(engine):
    _seed_plaintext(engine)
    _run_upgrade(engine)
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT prompt, prompt_key FROM ai_insights WHERE prompt_key IS NOT NULL")
        ).one()
    prompt, prompt_key = row
    assert prompt_key and prompt_key.startswith("__preconsult__") and prompt_key.endswith("__")
    assert encryption.is_secret_encrypted(prompt)


def test_migration_is_idempotent(engine):
    """Re-running must not double-encrypt (is_secret_encrypted skip)."""
    rid = _seed_plaintext(engine)
    _run_upgrade(engine)
    _run_upgrade(engine)  # second run
    with engine.begin() as conn:
        cd = conn.execute(
            text("SELECT clinical_data FROM health_records WHERE id = :id"), {"id": rid}
        ).scalar_one()
    # Still a single layer of ciphertext that decrypts to the original.
    assert encryption.is_secret_encrypted(cd)
    assert encryption.decrypt_secret(cd) == "Plaintext clinical note about hypertension"


def test_migration_noop_on_empty_db(engine):
    """A fresh DB with no PHI rows upgrades without error."""
    _run_upgrade(engine)  # should not raise
