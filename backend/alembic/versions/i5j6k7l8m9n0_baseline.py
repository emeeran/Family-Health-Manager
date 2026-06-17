"""baseline

Single squashed baseline migration.

Replaces the previously broken migration chain (whose root revision only ran an
``ALTER COLUMN`` against a non-existent table using PostgreSQL-only syntax, so
``alembic upgrade head`` could never run on any fresh database). This baseline
creates the entire schema straight from the current SQLAlchemy models via
``Base.metadata.create_all``.

Why create_all (not hand-written op.create_table):
- The application's SQLite bootstrap (``create_tables()`` / ``db-setup.py``) has
  always used ``create_all`` + ``alembic stamp head`` at this revision id, so
  building the migration the same way guarantees the migration-produced schema
  is byte-identical to what existing deployments already have.
- ``alembic check`` therefore reports no drift, and future model changes are
  detectable.

Safety for existing installs: every deployed SQLite database is stamped at
``i5j6k7l8m9n0`` (the previous head). This baseline reuses that exact revision
id, so for those databases ``alembic upgrade head`` is a no-op. Only *fresh*
databases run this migration.

Revision ID: i5j6k7l8m9n0
Revises:
Create Date: 2026-06-16
"""
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i5j6k7l8m9n0"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create all tables/indexes from the current models."""
    from app.models.base import Base  # registers every model on Base.metadata

    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    """Drop all tables (full reset — used only on intentional teardown)."""
    from app.models.base import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind)
