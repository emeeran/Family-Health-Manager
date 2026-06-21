"""inline_column_backfill

Resolves TODO #21. The columns below were added to the SQLAlchemy models but
only ever patched into SQLite *dev* databases via a runtime ``ALTER TABLE``
block in ``create_tables()`` (``app/core/database.py``). That block never ran
against PostgreSQL, so a production database that predated the columns had no
migration adding them — the gap TODO #21 flagged.

This revision adds all of them with an existence guard, so any database (old
SQLite dev file, PostgreSQL prod) reaching head via ``alembic upgrade head``
gets them. It mirrors the runtime block exactly (same types/defaults, the
``attachments.content_hash`` index, and the "promote first user to admin" side
effect on ``users.role``). The runtime block is removed in favour of this
migration; SQLite startup now runs ``alembic upgrade head``.

A fresh database already has these columns (the squashed baseline builds every
table via ``Base.metadata.create_all``), so the guards make this a no-op there.

Revision ID: m9n0o1p2q3r4
Revises: l8m9n0o1p2q3
Create Date: 2026-06-21
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "m9n0o1p2q3r4"
down_revision: str | None = "l8m9n0o1p2q3"
branch_labels: str | None = None
depends_on: str | None = None


# (table, column, type, nullable, server_default) — added if missing.
_COLUMNS: list[tuple[str, str, sa.types.TypeEngine, bool, "sa.text | None"]] = [
    ("attachments", "content_hash", sa.String(length=64), True, None),
    ("attachments", "storage_backend", sa.String(length=20), False, sa.text("'local'")),
    ("attachments", "thumbnail_path", sa.String(length=500), True, None),
    ("attachments", "encrypted", sa.Boolean(), False, sa.text("false")),
    ("providers", "provider_type", sa.String(length=20), False, sa.text("'doctor'")),
    ("households", "settings_json", sa.Text(), True, None),
    ("health_records", "summary", sa.Text(), True, None),
]


def upgrade() -> None:
    """Add the columns (and the users.role promotion) if not already present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    # users.role — NOT NULL DEFAULT 'user'; promote the first user to admin,
    # matching the previous runtime patch's bootstrap behaviour.
    if "users" in table_names:
        users_cols = {c["name"] for c in inspector.get_columns("users")}
        if "role" not in users_cols:
            op.add_column(
                "users",
                sa.Column("role", sa.String(length=20), nullable=False, server_default=sa.text("'user'")),
            )
            bind.execute(
                sa.text(
                    "UPDATE users SET role = 'admin' WHERE id = "
                    "(SELECT id FROM users ORDER BY created_at ASC LIMIT 1)"
                )
            )

    # Remaining columns.
    for table, column, col_type, nullable, default in _COLUMNS:
        if table not in table_names:
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        if column not in existing:
            op.add_column(
                table,
                sa.Column(column, col_type, nullable=nullable, server_default=default),
            )

    # attachments.content_hash index (model has index=True).
    if "attachments" in table_names:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("attachments")}
        if "ix_attachments_content_hash" not in existing_indexes:
            op.create_index("ix_attachments_content_hash", "attachments", ["content_hash"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "attachments" in table_names:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("attachments")}
        if "ix_attachments_content_hash" in existing_indexes:
            op.drop_index("ix_attachments_content_hash", table_name="attachments")

    for table, column, _type, _nullable, _default in reversed(_COLUMNS):
        if table in table_names and column in {c["name"] for c in inspector.get_columns(table)}:
            op.drop_column(table, column)

    if "users" in table_names and "role" in {c["name"] for c in inspector.get_columns("users")}:
        op.drop_column("users", "role")
