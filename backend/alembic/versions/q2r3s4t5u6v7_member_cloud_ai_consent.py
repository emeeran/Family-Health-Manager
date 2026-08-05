"""member_cloud_ai_consent

Adds ``family_members.cloud_ai_consent`` (bool, default true) so a household
can opt an individual member out of cloud AI — their PHI then stays local
(Ollama only). Existence-guarded so it is a no-op on fresh databases (the
squashed baseline builds every column via ``Base.metadata.create_all``) and
safe to re-run. Backfills existing rows to true (legacy behaviour) so existing
members are unchanged until explicitly toggled.

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "q2r3s4t5u6v7"
down_revision: str | None = "p1q2r3s4t5u6"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "family_members"
_COLUMN = "cloud_ai_consent"


def upgrade() -> None:
    """Add cloud_ai_consent to family_members if missing; backfill true."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing:
        # NOT NULL DEFAULT 1 in one statement: SQLite/Postgres both backfill
        # existing rows with the default and apply it to future inserts.
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.text("1")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
