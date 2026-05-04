"""sync_schema_to_current_models

Revision ID: 55b22b059456
Revises: 2fd22ac8db51
Create Date: 2026-04-30 18:05:36.426510

Note: Only contains operations NOT already in 2fd22ac8db51.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55b22b059456'
down_revision: Union[str, Sequence[str], None] = '2fd22ac8db51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — only genuinely new operations."""
    # record_type column widening (VARCHAR(13) -> VARCHAR(14)) is skipped for SQLite.
    # The app stores record_type as a string anyway; the wider enum values fit in VARCHAR(13).
    # If needed on PostgreSQL, run: ALTER TABLE health_records ALTER COLUMN record_type TYPE VARCHAR(14);

    # Restore revoked_tokens table (dropped by 2fd22ac8db51 but still used by app)
    # Guard: table may already exist if create_tables() was called at startup
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='revoked_tokens'"
    ))
    if not result.fetchone():
        op.create_table('revoked_tokens',
            sa.Column('jti', sa.String(length=64), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('jti')
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('revoked_tokens')
    with op.batch_alter_table('health_records') as batch_op:
        batch_op.alter_column('record_type',
                   existing_type=sa.String(length=14),
                   type_=sa.VARCHAR(length=13),
                   existing_nullable=False)
