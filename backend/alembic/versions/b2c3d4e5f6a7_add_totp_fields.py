"""add_totp_fields

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add TOTP 2FA fields to users table."""
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('totp_secret', sa.String(32), nullable=True))
        batch_op.add_column(sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('backup_codes', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove TOTP fields from users table."""
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('backup_codes')
        batch_op.drop_column('totp_enabled')
        batch_op.drop_column('totp_secret')
