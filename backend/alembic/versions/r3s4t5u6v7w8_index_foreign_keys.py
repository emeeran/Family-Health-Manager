"""index_foreign_keys

Adds missing indexes on foreign-key columns that sit on hot/auth-critical query
paths but were never indexed — each one was a full-table scan per lookup:

- ``refresh_tokens.user_id``        — queried on every login + refresh-token
                                      rotation (token-family revocation).
- ``households.primary_user_id``    — joins to the owning user.
- ``provider_assignments.provider_id``        — provider → members lookup.
- ``provider_assignments.family_member_id``   — member → providers lookup.
- ``health_alerts.record_id``       — alert lookup per record (household_id /
                                        member_id already had a composite index).

Existence-guarded so it's a no-op on fresh databases (the squashed baseline
declares these via ``Base.metadata.create_all``) and safe to re-run.

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-08-05
"""

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "r3s4t5u6v7w8"
down_revision: str | None = "q2r3s4t5u6v7"
branch_labels: str | None = None
depends_on: str | None = None

# (table, column, index_name) — the foreign-key columns to index.
_INDEXES: list[tuple[str, str, str]] = [
    ("refresh_tokens", "user_id", "ix_refresh_tokens_user_id"),
    ("households", "primary_user_id", "ix_households_primary_user_id"),
    ("provider_assignments", "provider_id", "ix_provider_assignments_provider_id"),
    (
        "provider_assignments",
        "family_member_id",
        "ix_provider_assignments_family_member_id",
    ),
    ("health_alerts", "record_id", "ix_health_alerts_record_id"),
]


def upgrade() -> None:
    """Create the FK indexes if the table exists and the index doesn't yet."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    for table, column, index_name in _INDEXES:
        if table not in tables:
            continue
        existing = {ix["name"] for ix in inspector.get_indexes(table)}
        if index_name in existing:
            continue
        op.create_index(index_name, table, [column])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    for table, _column, index_name in _INDEXES:
        if table not in tables:
            continue
        existing = {ix["name"] for ix in inspector.get_indexes(table)}
        if index_name in existing:
            op.drop_index(index_name, table_name=table)
