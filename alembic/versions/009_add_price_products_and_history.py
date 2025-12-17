"""Add price products and history, link to order items

Revision ID: 009_add_price_products_and_history
Revises: 008_add_price_permissions
Create Date: 2025-12-02 01:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009_add_price_products_and_history'
down_revision = '008_add_price_permissions'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'price_products' not in inspector.get_table_names():
        op.create_table(
            'price_products',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('external_article', sa.String(), nullable=False),
            sa.Column('raw_name', sa.Text(), nullable=True),
            sa.Column('brand', sa.String(), nullable=True),
            sa.Column('product_name', sa.String(), nullable=True),
            sa.Column('category', sa.String(), nullable=True),
            sa.Column('volume_value', sa.Numeric(10, 2), nullable=True),
            sa.Column('volume_unit', sa.String(), nullable=True),
            sa.Column('gender', sa.String(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('external_article', name='uq_price_products_external_article'),
        )
        op.create_index(op.f('ix_price_products_id'), 'price_products', ['id'], unique=False)

    if 'price_history' not in inspector.get_table_names():
        op.create_table(
            'price_history',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('price_product_id', sa.Integer(), nullable=False),
            sa.Column('price', sa.Numeric(10, 2), nullable=True),
            sa.Column('currency', sa.String(), nullable=True),
            sa.Column('source_date', sa.Date(), nullable=True),
            sa.Column('source_filename', sa.String(), nullable=True),
            sa.Column('direction', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['price_product_id'], ['price_products.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_price_history_id'), 'price_history', ['id'], unique=False)

    # В SQLite не поддерживается добавление внешнего ключа через ALTER, поэтому ограничимся столбцом
    columns = [col['name'] for col in inspector.get_columns('order_items')]
    if 'price_product_id' not in columns:
        op.add_column('order_items', sa.Column('price_product_id', sa.Integer(), nullable=True))


def downgrade():
    op.drop_constraint(None, 'order_items', type_='foreignkey')
    op.drop_column('order_items', 'price_product_id')
    op.drop_index(op.f('ix_price_history_id'), table_name='price_history')
    op.drop_table('price_history')
    op.drop_index(op.f('ix_price_products_id'), table_name='price_products')
    op.drop_table('price_products')
