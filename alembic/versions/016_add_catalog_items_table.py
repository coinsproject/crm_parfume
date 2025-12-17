"""create catalog_items table

Revision ID: 016_add_catalog_items_table
Revises: 015_add_price_history_indexes
Create Date: 2025-12-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "016_add_catalog_items_table"
down_revision = "015_add_price_history_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "catalog_items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("price_product_id", sa.Integer(), sa.ForeignKey("price_products.id"), nullable=False),
        sa.Column("article", sa.String(), nullable=False),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("volume", sa.String(), nullable=True),
        sa.Column("gender", sa.String(), nullable=True),
        sa.Column("description_short", sa.Text(), nullable=True),
        sa.Column("description_full", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("price_product_id", name="uq_catalog_item_price_product"),
    )
    op.create_index(op.f("ix_catalog_items_id"), "catalog_items", ["id"], unique=False)
    op.create_index("ix_catalog_items_article", "catalog_items", ["article"], unique=False)
    op.create_index("ix_catalog_items_brand", "catalog_items", ["brand"], unique=False)


def downgrade():
    op.drop_index("ix_catalog_items_brand", table_name="catalog_items")
    op.drop_index("ix_catalog_items_article", table_name="catalog_items")
    op.drop_index(op.f("ix_catalog_items_id"), table_name="catalog_items")
    op.drop_table("catalog_items")
