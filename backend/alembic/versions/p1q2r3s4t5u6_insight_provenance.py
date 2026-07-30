"""insight_provenance

Adds provenance + freshness columns to ``ai_insights``: ``sources_json`` (the
source record ids/dates/types that fed a member-level insight, computed
server-side — never from LLM output), plus ``freshness_as_of`` and ``range_start``
(the max/min source record dates).

Existence-guarded so it is a no-op on fresh databases (the squashed baseline
builds every column via ``Base.metadata.create_all``) and safe to re-run.

Revision ID: p1q2r3s4t5u6
Revises: o0p1q2r3s4t5
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "p1q2r3s4t5u6"
down_revision: str | None = "o0p1q2r3s4t5"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "ai_insights"
_COLUMNS = [
    ("sources_json", sa.Text()),
    ("freshness_as_of", sa.Date()),
    ("range_start", sa.Date()),
]


def upgrade() -> None:
    """Add provenance/freshness columns to ai_insights if missing."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, typ in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, _typ in _COLUMNS:
        if name in existing:
            op.drop_column(_TABLE, name)
