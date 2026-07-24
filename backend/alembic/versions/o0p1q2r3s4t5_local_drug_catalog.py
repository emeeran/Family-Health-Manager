"""local_drug_catalog

Creates the ``local_drugs`` table for the curated Indian drug catalog (brand →
composition + rich metadata). Seeded from ``DRUG_CATALOG_CSV`` via
``app.scripts.seed_drug_catalog``; drives local-first drug-info resolution and
flyout content for matched brands.

Guarded so it is a no-op on databases that already have the table (and a no-op
on fresh databases, which build it via ``Base.metadata.create_all``).

Revision ID: o0p1q2r3s4t5
Revises: n0o1p2q3r4s5
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa

revision: str = "o0p1q2r3s4t5"
down_revision: str | None = "n0o1p2q3r4s5"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "local_drugs"


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE in set(sa.inspect(bind).get_table_names()):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("name_normalized", sa.Text(), nullable=False),
        sa.Column("marketer", sa.Text(), nullable=True),
        sa.Column("composition", sa.Text(), nullable=True),
        sa.Column("ingredients", sa.Text(), nullable=True),
        sa.Column("product_form", sa.Text(), nullable=True),
        sa.Column("package", sa.Text(), nullable=True),
        sa.Column("mrp", sa.Text(), nullable=True),
        sa.Column("prescription_required", sa.Text(), nullable=True),
        sa.Column("introduction", sa.Text(), nullable=True),
        sa.Column("benefits", sa.Text(), nullable=True),
        sa.Column("how_to_use", sa.Text(), nullable=True),
        sa.Column("safety_advise", sa.Text(), nullable=True),
        sa.Column("if_miss", sa.Text(), nullable=True),
        sa.Column("side_effect", sa.Text(), nullable=True),
        sa.Column("drug_drug_interaction", sa.Text(), nullable=True),
        sa.Column("how_it_works", sa.Text(), nullable=True),
        sa.Column("fact_box", sa.Text(), nullable=True),
        sa.Column("primary_use", sa.Text(), nullable=True),
        sa.Column("storage", sa.Text(), nullable=True),
        sa.Column("alcohol_interaction", sa.Text(), nullable=True),
        sa.Column("pregnancy_interaction", sa.Text(), nullable=True),
        sa.Column("lactation_interaction", sa.Text(), nullable=True),
        sa.Column("driving_interaction", sa.Text(), nullable=True),
        sa.Column("kidney_interaction", sa.Text(), nullable=True),
        sa.Column("liver_interaction", sa.Text(), nullable=True),
        sa.Column("country_of_origin", sa.Text(), nullable=True),
        sa.Column("image_urls", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_local_drugs_product_id", _TABLE, ["product_id"], unique=True)
    op.create_index("ix_local_drugs_name_norm", _TABLE, ["name_normalized"])


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(sa.inspect(bind).get_table_names()):
        return
    op.drop_index("ix_local_drugs_name_norm", table_name=_TABLE)
    op.drop_index("ix_local_drugs_product_id", table_name=_TABLE)
    op.drop_table(_TABLE)
