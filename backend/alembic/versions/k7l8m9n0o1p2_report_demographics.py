"""report_demographics

Adds patient-identification columns to ``family_members`` (``patient_id``,
``phone``, ``address``) used to populate the header of a "Medical Records
Transcription Report", and a ``transcription_report`` text column to
``health_records`` where the AI-generated report is persisted.

The squashed baseline builds every table via ``Base.metadata.create_all``
(an idempotent, existence-checking call), so a *fresh* database already has
these columns once the models are registered. Existing installs upgraded
through the previous head do not, so this revision adds them with an
existence guard for the same idempotency guarantee.

Revision ID: k7l8m9n0o1p2
Revises: j6k7l8m9n0o1
Create Date: 2026-06-19
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "k7l8m9n0o1p2"
down_revision: str | None = "j6k7l8m9n0o1"
branch_labels: str | None = None
depends_on: str | None = None


# (table, column_name, column_type) — added if missing.
_NEW_COLUMNS = [
    ("family_members", "patient_id", sa.String(length=50)),
    ("family_members", "phone", sa.String(length=30)),
    ("family_members", "address", sa.Text()),
    ("health_records", "transcription_report", sa.Text()),
]


def upgrade() -> None:
    """Add the new columns if they are not already present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {t: {col["name"] for col in inspector.get_columns(t)} for t, _, _ in _NEW_COLUMNS}

    for table, column_name, column_type in _NEW_COLUMNS:
        if column_name not in existing.get(table, set()):
            op.add_column(table, sa.Column(column_name, column_type, nullable=True))


def downgrade() -> None:
    for table, column_name, _ in reversed(_NEW_COLUMNS):
        op.drop_column(table, column_name)
