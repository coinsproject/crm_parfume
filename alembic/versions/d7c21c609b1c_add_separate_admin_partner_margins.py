"""add_separate_admin_partner_margins

Revision ID: d7c21c609b1c
Revises: d3e4f5a6b7c8
Create Date: 2026-01-04 02:00:29.246663

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7c21c609b1c'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Добавляем поля для раздельной маржи в order_items
    oi_cols = [c["name"] for c in inspector.get_columns("order_items")]
    if "line_admin_margin" not in oi_cols:
        op.add_column('order_items', sa.Column('line_admin_margin', sa.Numeric(10, 2), nullable=True))
    if "line_partner_margin" not in oi_cols:
        op.add_column('order_items', sa.Column('line_partner_margin', sa.Numeric(10, 2), nullable=True))
    
    # Добавляем поля для раздельной маржи в orders
    order_cols = [c["name"] for c in inspector.get_columns("orders")]
    if "total_admin_margin" not in order_cols:
        op.add_column('orders', sa.Column('total_admin_margin', sa.Numeric(10, 2), nullable=True))
    if "total_partner_margin" not in order_cols:
        op.add_column('orders', sa.Column('total_partner_margin', sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('order_items', 'line_partner_margin')
    op.drop_column('order_items', 'line_admin_margin')
    op.drop_column('orders', 'total_partner_margin')
    op.drop_column('orders', 'total_admin_margin')
