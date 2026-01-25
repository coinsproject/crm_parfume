"""add_purchase_request_items_and_notifications

Revision ID: 285dc33c6319
Revises: d68fc24cd710
Create Date: 2026-01-19 02:19:52.195161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '285dc33c6319'
down_revision: Union[str, Sequence[str], None] = 'd68fc24cd710'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Создаём таблицу purchase_request_items
    op.create_table(
        "purchase_request_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_request_id", sa.Integer(), sa.ForeignKey("purchase_requests.id"), nullable=False),
        sa.Column("order_item_id", sa.Integer(), sa.ForeignKey("order_items.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="normal"),
        sa.Column("original_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("proposed_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("approved_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_change_comment", sa.Text(), nullable=True),
        sa.Column("admin_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_purchase_request_items_id"), "purchase_request_items", ["id"])
    op.create_index(op.f("ix_purchase_request_items_purchase_request_id"), "purchase_request_items", ["purchase_request_id"])
    
    # Создаём таблицу notifications
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("related_type", sa.String(), nullable=True),
        sa.Column("related_id", sa.Integer(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_notifications_id"), "notifications", ["id"])
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"])
    op.create_index(op.f("ix_notifications_is_read"), "notifications", ["is_read"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_notifications_is_read"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_id"), table_name="notifications")
    op.drop_table("notifications")
    
    op.drop_index(op.f("ix_purchase_request_items_purchase_request_id"), table_name="purchase_request_items")
    op.drop_index(op.f("ix_purchase_request_items_id"), table_name="purchase_request_items")
    op.drop_table("purchase_request_items")
