"""cascade deletes on foreign keys

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2025-01-15 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # family_members.household_id -> households.id
    op.drop_constraint('family_members_household_id_fkey', 'family_members', type_='foreignkey')
    op.create_foreign_key(
        'family_members_household_id_fkey', 'family_members',
        'households', ['household_id'], ['id'], ondelete='CASCADE',
    )

    # health_records.family_member_id -> family_members.id
    op.drop_constraint('health_records_family_member_id_fkey', 'health_records', type_='foreignkey')
    op.create_foreign_key(
        'health_records_family_member_id_fkey', 'health_records',
        'family_members', ['family_member_id'], ['id'], ondelete='CASCADE',
    )

    # attachments.health_record_id -> health_records.id
    op.drop_constraint('attachments_health_record_id_fkey', 'attachments', type_='foreignkey')
    op.create_foreign_key(
        'attachments_health_record_id_fkey', 'attachments',
        'health_records', ['health_record_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    # Revert to original FK without CASCADE
    op.drop_constraint('attachments_health_record_id_fkey', 'attachments', type_='foreignkey')
    op.create_foreign_key(
        'attachments_health_record_id_fkey', 'attachments',
        'health_records', ['health_record_id'], ['id'],
    )

    op.drop_constraint('health_records_family_member_id_fkey', 'health_records', type_='foreignkey')
    op.create_foreign_key(
        'health_records_family_member_id_fkey', 'health_records',
        'family_members', ['family_member_id'], ['id'],
    )

    op.drop_constraint('family_members_household_id_fkey', 'family_members', type_='foreignkey')
    op.create_foreign_key(
        'family_members_household_id_fkey', 'family_members',
        'households', ['household_id'], ['id'],
    )
