"""app_secrets

Adds the ``app_secrets`` table for instance-wide encrypted secrets
(AI provider API keys managed via the Settings UI).

The squashed baseline builds every table via ``Base.metadata.create_all`` (an
idempotent, existence-checking call), so a *fresh* database already has
``app_secrets`` once the model is registered. Existing installs stamped at the
baseline head (``i5j6k7l8m9n0``) do not, so this revision adds it for them.
``create_all`` is reused here for the same idempotency guarantee: it is a no-op
on fresh databases and creates the table on upgraded ones.

Revision ID: j6k7l8m9n0o1
Revises: i5j6k7l8m9n0
Create Date: 2026-06-18
"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j6k7l8m9n0o1"
down_revision: str | None = "i5j6k7l8m9n0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the app_secrets table if it does not already exist."""
    from app.models.base import Base  # registers every model on Base.metadata

    bind = op.get_bind()
    # Idempotent: only creates tables missing from the database.
    Base.metadata.create_all(bind, tables=[Base.metadata.tables["app_secrets"]])


def downgrade() -> None:
    op.drop_table("app_secrets")
