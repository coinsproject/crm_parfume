"""add price history indexes"""

from alembic import op
import sqlalchemy as sa

revision = '015_add_price_history_indexes'
down_revision = '013_add_price_indexes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_price_history_upload_id', 'price_history', ['price_upload_id'], unique=False)
    op.create_index('ix_price_history_product_id', 'price_history', ['price_product_id'], unique=False)


def downgrade():
    op.drop_index('ix_price_history_product_id', table_name='price_history')
    op.drop_index('ix_price_history_upload_id', table_name='price_history')
