"""Add original_name to order_items and make raw_name required

Revision ID: 013_add_original_name_and_raw_name_not_null
Revises: 012_add_price_products_fts_sqlite
Create Date: 2025-12-02 03:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013_add_original_name_and_raw_name_not_null'
down_revision = '012_add_price_products_fts_sqlite'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # order_items.original_name
    cols = [c['name'] for c in inspector.get_columns('order_items')]
    if 'original_name' not in cols:
        with op.batch_alter_table('order_items') as batch:
            batch.add_column(sa.Column('original_name', sa.Text(), nullable=False, server_default=""))
        op.execute("UPDATE order_items SET original_name = COALESCE(name, '') WHERE original_name IS NULL")
        with op.batch_alter_table('order_items') as batch:
            batch.alter_column('original_name', server_default=None)

    # price_products.raw_name not null
    cols_pp = inspector.get_columns('price_products')
    raw_nullable = None
    for col in cols_pp:
        if col['name'] == 'raw_name':
            raw_nullable = col['nullable']
            break
    if raw_nullable:
        op.execute("UPDATE price_products SET raw_name = COALESCE(raw_name, '')")
        with op.batch_alter_table('price_products') as batch:
            batch.alter_column('raw_name', existing_type=sa.Text(), nullable=False, server_default="")
            batch.alter_column('raw_name', server_default=None)


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('order_items')]
    if 'original_name' in cols:
        with op.batch_alter_table('order_items') as batch:
            batch.drop_column('original_name')

    cols_pp = inspector.get_columns('price_products')
    raw_nullable = None
    for col in cols_pp:
        if col['name'] == 'raw_name':
            raw_nullable = col['nullable']
            break
    if raw_nullable is False:
        with op.batch_alter_table('price_products') as batch:
            batch.alter_column('raw_name', existing_type=sa.Text(), nullable=True, server_default=None)
