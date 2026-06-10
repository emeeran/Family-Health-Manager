"""Add performance indexes

Revision ID: h4i5j6k7l8m9
Revises: g2h3i4j5k6l7
Create Date: 2026-06-10

Adds indexes for frequently queried columns:
- ai_insights: verification_status, generated_at, (conversation_id, generated_at)
- reminders: (is_active, start_datetime)
"""

from alembic import op

revision = "h4i5j6k7l8m9"
down_revision = "g2h3i4j5k6l7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_ai_insights_verification_status", "ai_insights", ["verification_status"])
    op.create_index("ix_ai_insights_generated_at", "ai_insights", ["generated_at"])
    op.create_index(
        "ix_ai_insights_conversation_generated",
        "ai_insights",
        ["conversation_id", "generated_at"],
    )
    op.create_index("ix_reminders_active_start", "reminders", ["is_active", "start_datetime"])


def downgrade() -> None:
    op.drop_index("ix_reminders_active_start", table_name="reminders")
    op.drop_index("ix_ai_insights_conversation_generated", table_name="ai_insights")
    op.drop_index("ix_ai_insights_generated_at", table_name="ai_insights")
    op.drop_index("ix_ai_insights_verification_status", table_name="ai_insights")
