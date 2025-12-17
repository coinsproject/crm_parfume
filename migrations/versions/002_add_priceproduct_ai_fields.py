"""Add AI normalization fields to price_products

Revision ID: 022_add_priceproduct_ai_fields
Revises: 021_make_catalog_article_nullable
Create Date: 2025-12-07 03:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '022_add_priceproduct_ai_fields'
down_revision = '021_make_catalog_article_nullable'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('price_products', sa.Column('ai_brand', sa.String(), nullable=True))
    op.add_column('price_products', sa.Column('ai_base_name', sa.String(), nullable=True))
    op.add_column('price_products', sa.Column('ai_line', sa.String(), nullable=True))
    op.add_column('price_products', sa.Column('ai_kind', sa.String(), nullable=True))
    op.add_column('price_products', sa.Column('ai_group_key', sa.String(), nullable=True))
    op.add_column('price_products', sa.Column('ai_status', sa.String(), nullable=False, server_default='pending'))
    op.create_index('ix_price_products_ai_group_key', 'price_products', ['ai_group_key'], unique=False)


def downgrade():
    op.drop_index('ix_price_products_ai_group_key', table_name='price_products')
    op.drop_column('price_products', 'ai_status')
    op.drop_column('price_products', 'ai_group_key')
    op.drop_column('price_products', 'ai_kind')
    op.drop_column('price_products', 'ai_line')
    op.drop_column('price_products', 'ai_base_name')
    op.drop_column('price_products', 'ai_brand')
