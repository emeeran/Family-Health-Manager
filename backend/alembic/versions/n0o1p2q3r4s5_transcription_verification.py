"""transcription_verification

Adds ``health_records.transcription_verification`` (nullable Text/JSON) — stores
the second-model validation result for the AI-generated ``transcription_report``
(status, verifier, warnings, summary). Mirrors the ``AIInsight.verification_*``
fields but on the record, since transcription reports are persisted on
``HealthRecord`` rather than as insights.

Existence-guarded so it is a no-op on fresh databases (the squashed baseline
already builds every column via ``Base.metadata.create_all``) and safe to re-run.

Revision ID: n0o1p2q3r4s5
Revises: m9n0o1p2q3r4
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "n0o1p2q3r4s5"
down_revision: str | None = "m9n0o1p2q3r4"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "health_records"
_COLUMN = "transcription_verification"


def upgrade() -> None:
    """Add transcription_verification to health_records if missing."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    if _COLUMN in {c["name"] for c in inspector.get_columns(_TABLE)}:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE in set(inspector.get_table_names()) and _COLUMN in {
        c["name"] for c in inspector.get_columns(_TABLE)
    }:
        op.drop_column(_TABLE, _COLUMN)
