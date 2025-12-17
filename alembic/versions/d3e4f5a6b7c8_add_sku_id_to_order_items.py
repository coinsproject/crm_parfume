"""Add sku_id to order_items.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2025-12-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("sku_id", sa.Integer(), nullable=True))
    op.create_index("ix_order_items_sku_id", "order_items", ["sku_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_order_items_sku_id", table_name="order_items")
    op.drop_column("order_items", "sku_id")

