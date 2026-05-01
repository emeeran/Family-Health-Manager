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
    # record_type enum conversion (new enum values)
    op.alter_column('health_records', 'record_type',
               existing_type=sa.VARCHAR(length=13),
               type_=sa.Enum('DOCTOR_VISIT', 'LAB_REPORT', 'RX_EYEGLASS', 'BLOOD_GLUCOSE', 'HBA1C', 'MISC_RECORD', 'VITALS', 'PARKINSONS_LOG', name='recordtype'),
               existing_nullable=False)

    # Restore revoked_tokens table (dropped by 2fd22ac8db51 but still used by app)
    op.create_table('revoked_tokens',
        sa.Column('jti', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('jti')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('revoked_tokens')
    op.alter_column('health_records', 'record_type',
               existing_type=sa.Enum('DOCTOR_VISIT', 'LAB_REPORT', 'RX_EYEGLASS', 'BLOOD_GLUCOSE', 'HBA1C', 'MISC_RECORD', 'VITALS', 'PARKINSONS_LOG', name='recordtype'),
               type_=sa.VARCHAR(length=13),
               existing_nullable=False)
