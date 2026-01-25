"""add_margin_percent_fields_simple

Revision ID: simple_margin_percent
Revises: d7c21c609b1c
Create Date: 2026-01-04 02:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'simple_margin_percent'
down_revision: Union[str, Sequence[str], None] = 'd7c21c609b1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Добавляем только нужные поля для процентов маржи
    op.add_column('order_items', sa.Column('line_admin_margin_percent', sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column('order_items', sa.Column('line_partner_margin_percent', sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column('orders', sa.Column('total_admin_margin_percent', sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column('orders', sa.Column('total_partner_margin_percent', sa.Numeric(precision=5, scale=2), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('orders', 'total_partner_margin_percent')
    op.drop_column('orders', 'total_admin_margin_percent')
    op.drop_column('order_items', 'line_partner_margin_percent')
    op.drop_column('order_items', 'line_admin_margin_percent')







