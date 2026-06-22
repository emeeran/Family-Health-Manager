"""member_photo

Adds optional profile-photo columns to ``family_members``: ``photo_path`` (full
image, content-addressed + encrypted at rest), ``photo_content_hash`` (dedup +
reference-counted delete), ``photo_thumbnail_path`` (300px WebP served to the
UI), and ``photo_updated_at`` (client <img> cache-bust version).

As with the other recent revisions, the squashed baseline builds every table
via ``Base.metadata.create_all`` (idempotent, existence-checking), so a *fresh*
database already has these columns once the model registers them. Existing
installs upgraded through the previous head do not, so this revision adds them
with an existence guard for the same idempotency guarantee.

Revision ID: l8m9n0o1p2q3
Revises: k7l8m9n0o1p2
Create Date: 2026-06-21
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "l8m9n0o1p2q3"
down_revision: str | None = "k7l8m9n0o1p2"
branch_labels: str | None = None
depends_on: str | None = None


# (table, column_name, column_type) — added if missing.
_NEW_COLUMNS = [
    ("family_members", "photo_path", sa.String(length=500)),
    ("family_members", "photo_content_hash", sa.String(length=64)),
    ("family_members", "photo_thumbnail_path", sa.String(length=500)),
    ("family_members", "photo_updated_at", sa.DateTime()),
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
