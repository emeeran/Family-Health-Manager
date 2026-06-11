"""Add summary column to health_records

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-06-10

Adds a nullable Text column for AI-generated consultation summaries.
"""

from alembic import op
import sqlalchemy as sa

revision = "i5j6k7l8m9n0"
down_revision = "h4i5j6k7l8m9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("health_records", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("health_records", "summary")
