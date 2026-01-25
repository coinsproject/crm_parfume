"""add_product_type_and_subtype_filters

Revision ID: 3f4b2ada01c5
Revises: 01da41bfc10a
Create Date: 2025-01-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3f4b2ada01c5'
down_revision = '01da41bfc10a'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поля product_type и product_subtype
    op.add_column('price_products', sa.Column('product_type', sa.String(length=32), nullable=True))
    op.add_column('price_products', sa.Column('product_subtype', sa.String(length=32), nullable=True))
    
    # Добавляем индексы для быстрой фильтрации
    op.create_index('idx_price_products_product_type', 'price_products', ['product_type'])
    op.create_index('idx_price_products_product_subtype', 'price_products', ['product_subtype'])
    op.create_index('idx_price_products_type_subtype', 'price_products', ['product_type', 'product_subtype'])


def downgrade():
    # Удаляем индексы
    op.drop_index('idx_price_products_type_subtype', table_name='price_products')
    op.drop_index('idx_price_products_product_subtype', table_name='price_products')
    op.drop_index('idx_price_products_product_type', table_name='price_products')
    
    # Удаляем поля
    op.drop_column('price_products', 'product_subtype')
    op.drop_column('price_products', 'product_type')
