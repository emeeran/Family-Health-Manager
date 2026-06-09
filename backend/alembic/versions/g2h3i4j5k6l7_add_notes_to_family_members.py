"""Add notes column to family_members

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-09

Adds a nullable Text column for general notes about a family member.
"""

from alembic import op
import sqlalchemy as sa

revision = "g2h3i4j5k6l7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("family_members", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("family_members", "notes")
