"""Add price import fields and stock flags

Revision ID: 023_price_import_stage1
Revises: 022_add_priceproduct_ai_fields
Create Date: 2025-12-07 05:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "023_price_import_stage1"
down_revision = "022_add_priceproduct_ai_fields"
branch_labels = None
depends_on = None


def upgrade():
    # price_products
    op.add_column("price_products", sa.Column("price_1", sa.Numeric(10, 2), nullable=True))
    op.add_column("price_products", sa.Column("price_2", sa.Numeric(10, 2), nullable=True))
    op.add_column("price_products", sa.Column("round_delta", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "price_products",
        sa.Column("is_in_stock", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "price_products",
        sa.Column("is_in_current_pricelist", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column("price_products", sa.Column("last_price_change_at", sa.DateTime(), nullable=True))

    # price_history
    op.add_column("price_history", sa.Column("old_price_1", sa.Numeric(10, 2), nullable=True))
    op.add_column("price_history", sa.Column("new_price_1", sa.Numeric(10, 2), nullable=True))
    op.add_column("price_history", sa.Column("old_price_2", sa.Numeric(10, 2), nullable=True))
    op.add_column("price_history", sa.Column("new_price_2", sa.Numeric(10, 2), nullable=True))
    op.add_column("price_history", sa.Column("old_round_delta", sa.Numeric(10, 2), nullable=True))
    op.add_column("price_history", sa.Column("new_round_delta", sa.Numeric(10, 2), nullable=True))
    op.add_column("price_history", sa.Column("changed_at", sa.DateTime(), nullable=True))

    # price_uploads
    op.add_column(
        "price_uploads",
        sa.Column("status", sa.String(), nullable=False, server_default="in_progress"),
    )
    op.add_column(
        "price_uploads",
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column("price_uploads", sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("price_uploads", sa.Column("added_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "price_uploads",
        sa.Column("updated_price_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "price_uploads",
        sa.Column("marked_out_of_stock_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_price_uploads_created_by",
        "price_uploads",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute("UPDATE price_products SET is_in_stock = is_active, is_in_current_pricelist = is_active")
    op.execute("UPDATE price_uploads SET status = 'done' WHERE status IS NULL OR status = 'in_progress'")


def downgrade():
    op.drop_constraint("fk_price_uploads_created_by", "price_uploads", type_="foreignkey")
    op.drop_column("price_uploads", "marked_out_of_stock_count")
    op.drop_column("price_uploads", "updated_price_count")
    op.drop_column("price_uploads", "added_count")
    op.drop_column("price_uploads", "total_rows")
    op.drop_column("price_uploads", "created_by_user_id")
    op.drop_column("price_uploads", "status")

    op.drop_column("price_history", "changed_at")
    op.drop_column("price_history", "new_round_delta")
    op.drop_column("price_history", "old_round_delta")
    op.drop_column("price_history", "new_price_2")
    op.drop_column("price_history", "old_price_2")
    op.drop_column("price_history", "new_price_1")
    op.drop_column("price_history", "old_price_1")

    op.drop_column("price_products", "last_price_change_at")
    op.drop_column("price_products", "is_in_current_pricelist")
    op.drop_column("price_products", "is_in_stock")
    op.drop_column("price_products", "round_delta")
    op.drop_column("price_products", "price_2")
    op.drop_column("price_products", "price_1")
