"""add price indexes"""

from alembic import op
import sqlalchemy as sa

revision = '013_add_price_indexes'
down_revision = '014_rename_direction_to_change_type'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('idx_price_products_external_article', 'price_products', ['external_article'], unique=False)
    op.create_index('idx_price_products_raw_name', 'price_products', ['raw_name'], unique=False)
    op.create_index('idx_price_products_product_name', 'price_products', ['product_name'], unique=False)
    op.create_index('idx_price_history_price_product_id', 'price_history', ['price_product_id'], unique=False)
    op.create_index('idx_price_history_price_upload_id', 'price_history', ['price_upload_id'], unique=False)


def downgrade():
    op.drop_index('idx_price_history_price_upload_id', table_name='price_history')
    op.drop_index('idx_price_history_price_product_id', table_name='price_history')
    op.drop_index('idx_price_products_product_name', table_name='price_products')
    op.drop_index('idx_price_products_raw_name', table_name='price_products')
    op.drop_index('idx_price_products_external_article', table_name='price_products')
