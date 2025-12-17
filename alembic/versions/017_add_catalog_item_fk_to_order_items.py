"""add catalog_item_id to order_items

Revision ID: 017_add_catalog_item_fk_to_order_items
Revises: 016_add_catalog_items_table
Create Date: 2025-12-05 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "017_add_catalog_item_fk_to_order_items"
down_revision = "016_add_catalog_items_table"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("order_items")]
    if "catalog_item_id" not in cols:
        with op.batch_alter_table("order_items") as batch:
            batch.add_column(sa.Column("catalog_item_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_order_items_catalog_item",
                "catalog_items",
                ["catalog_item_id"],
                ["id"],
            )
            batch.create_index("ix_order_items_catalog_item_id", ["catalog_item_id"], unique=False)


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("order_items")]
    if "catalog_item_id" in cols:
        with op.batch_alter_table("order_items") as batch:
            batch.drop_index("ix_order_items_catalog_item_id")
            batch.drop_constraint("fk_order_items_catalog_item", type_="foreignkey")
            batch.drop_column("catalog_item_id")
