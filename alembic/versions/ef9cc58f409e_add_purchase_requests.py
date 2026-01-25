"""add_purchase_requests

Revision ID: ef9cc58f409e
Revises: f3c9b1a2d4e5
Create Date: 2026-01-19 01:36:34.100973

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef9cc58f409e'
down_revision: Union[str, Sequence[str], None] = 'f3c9b1a2d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Создаём таблицу purchase_requests
    op.create_table(
        "purchase_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("partner_id", sa.Integer(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("actual_delivery_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_purchase_requests_id"), "purchase_requests", ["id"])
    op.create_index(op.f("ix_purchase_requests_partner_id"), "purchase_requests", ["partner_id"])
    op.create_index(op.f("ix_purchase_requests_status"), "purchase_requests", ["status"])
    
    # Создаём промежуточную таблицу для связи заказов с запросами
    op.create_table(
        "purchase_request_orders",
        sa.Column("purchase_request_id", sa.Integer(), sa.ForeignKey("purchase_requests.id"), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), primary_key=True),
        sa.Column("added_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_purchase_request_orders_purchase_request_id"), "purchase_request_orders", ["purchase_request_id"])
    op.create_index(op.f("ix_purchase_request_orders_order_id"), "purchase_request_orders", ["order_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_purchase_request_orders_order_id"), table_name="purchase_request_orders")
    op.drop_index(op.f("ix_purchase_request_orders_purchase_request_id"), table_name="purchase_request_orders")
    op.drop_table("purchase_request_orders")
    
    op.drop_index(op.f("ix_purchase_requests_status"), table_name="purchase_requests")
    op.drop_index(op.f("ix_purchase_requests_partner_id"), table_name="purchase_requests")
    op.drop_index(op.f("ix_purchase_requests_id"), table_name="purchase_requests")
    op.drop_table("purchase_requests")
