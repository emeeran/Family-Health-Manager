"""Add storage columns to attachments

Revision ID: e3f4df27a556
Revises: 2fd22ac8db51
Create Date: 2026-06-01

Adds content_hash, storage_backend, thumbnail_path, encrypted columns
for content-addressable storage, deduplication, thumbnails, and
encryption at rest.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e3f4df27a556"
down_revision = "2fd22ac8db51"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_attachments_content_hash", "attachments", ["content_hash"]
    )
    op.add_column(
        "attachments",
        sa.Column(
            "storage_backend",
            sa.String(20),
            nullable=False,
            server_default="local",
        ),
    )
    op.add_column(
        "attachments",
        sa.Column("thumbnail_path", sa.String(500), nullable=True),
    )
    op.add_column(
        "attachments",
        sa.Column(
            "encrypted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("attachments", "encrypted")
    op.drop_column("attachments", "thumbnail_path")
    op.drop_column("attachments", "storage_backend")
    op.drop_index("ix_attachments_content_hash", table_name="attachments")
    op.drop_column("attachments", "content_hash")
