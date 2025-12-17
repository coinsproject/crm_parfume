"""Add pricing and margin fields plus partner prices table

Revision ID: 007_add_price_and_margin_fields
Revises: 006_add_client_email
Create Date: 2025-12-01 04:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007_add_price_and_margin_fields'
down_revision = '006_add_client_email'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # fragrances: создать, если отсутствует, иначе добавить недостающие колонки
    if not inspector.has_table("fragrances"):
        op.create_table(
            "fragrances",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("brand", sa.String(), nullable=False),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("gender", sa.String(), nullable=True),
            sa.Column("country", sa.String(), nullable=True),
            sa.Column("oil_type", sa.String(), nullable=True),
            sa.Column("rating", sa.Numeric(3, 2), nullable=True),
            sa.Column("price", sa.Numeric(10, 2), nullable=True),
            sa.Column("base_cost", sa.Numeric(10, 2), nullable=True),
            sa.Column("base_retail_price", sa.Numeric(10, 2), nullable=True),
            sa.Column("image_url", sa.String(), nullable=True),
            sa.Column("main_accords", sa.JSON(), nullable=True),
            sa.Column("notes", sa.JSON(), nullable=True),
            sa.Column("longevity", sa.String(), nullable=True),
            sa.Column("sillage", sa.String(), nullable=True),
            sa.Column("seasons", sa.JSON(), nullable=True),
            sa.Column("occasions", sa.JSON(), nullable=True),
            sa.Column("external_source", sa.String(), nullable=True),
            sa.Column("external_key", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_fragrances_id"), "fragrances", ["id"], unique=False)
        op.create_index(op.f("ix_fragrances_name"), "fragrances", ["name"], unique=False)
        op.create_index(op.f("ix_fragrances_brand"), "fragrances", ["brand"], unique=False)
    else:
        cols = [c["name"] for c in inspector.get_columns("fragrances")]
        if "base_cost" not in cols:
            op.add_column("fragrances", sa.Column("base_cost", sa.Numeric(10, 2), nullable=True))
        if "base_retail_price" not in cols:
            op.add_column("fragrances", sa.Column("base_retail_price", sa.Numeric(10, 2), nullable=True))

    # partner_prices
    if not inspector.has_table("partner_prices"):
        op.create_table(
            'partner_prices',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('partner_id', sa.Integer(), sa.ForeignKey('partners.id'), nullable=False),
            sa.Column('fragrance_id', sa.Integer(), sa.ForeignKey('fragrances.id'), nullable=False),
            sa.Column('purchase_price_for_partner', sa.Numeric(10, 2), nullable=True),
            sa.Column('recommended_client_price', sa.Numeric(10, 2), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('partner_id', 'fragrance_id', name='uq_partner_fragrance_price'),
        )
        op.create_index(op.f('ix_partner_prices_id'), 'partner_prices', ['id'], unique=False)

    # orders
    order_cols = [c["name"] for c in inspector.get_columns("orders")]
    if "total_client_amount" not in order_cols:
        op.add_column('orders', sa.Column('total_client_amount', sa.Numeric(10, 2), nullable=True))
    if "total_cost_for_owner" not in order_cols:
        op.add_column('orders', sa.Column('total_cost_for_owner', sa.Numeric(10, 2), nullable=True))
    if "total_margin_for_owner" not in order_cols:
        op.add_column('orders', sa.Column('total_margin_for_owner', sa.Numeric(10, 2), nullable=True))
    if "total_margin_percent" not in order_cols:
        op.add_column('orders', sa.Column('total_margin_percent', sa.Numeric(5, 2), nullable=True))

    # order_items
    oi_cols = [c["name"] for c in inspector.get_columns("order_items")]
    if "client_price" not in oi_cols:
        op.add_column('order_items', sa.Column('client_price', sa.Numeric(10, 2), nullable=True))
    if "cost_for_owner" not in oi_cols:
        op.add_column('order_items', sa.Column('cost_for_owner', sa.Numeric(10, 2), nullable=True))
    if "line_client_amount" not in oi_cols:
        op.add_column('order_items', sa.Column('line_client_amount', sa.Numeric(10, 2), nullable=True))
    if "line_cost_amount" not in oi_cols:
        op.add_column('order_items', sa.Column('line_cost_amount', sa.Numeric(10, 2), nullable=True))
    if "line_margin" not in oi_cols:
        op.add_column('order_items', sa.Column('line_margin', sa.Numeric(10, 2), nullable=True))
    if "line_margin_percent" not in oi_cols:
        op.add_column('order_items', sa.Column('line_margin_percent', sa.Numeric(5, 2), nullable=True))


def downgrade():
    op.drop_column('order_items', 'line_margin_percent')
    op.drop_column('order_items', 'line_margin')
    op.drop_column('order_items', 'line_cost_amount')
    op.drop_column('order_items', 'line_client_amount')
    op.drop_column('order_items', 'cost_for_owner')
    op.drop_column('order_items', 'client_price')

    op.drop_column('orders', 'total_margin_percent')
    op.drop_column('orders', 'total_margin_for_owner')
    op.drop_column('orders', 'total_cost_for_owner')
    op.drop_column('orders', 'total_client_amount')

    op.drop_index(op.f('ix_partner_prices_id'), table_name='partner_prices')
    op.drop_table('partner_prices')

    op.drop_column('fragrances', 'base_retail_price')
    op.drop_column('fragrances', 'base_cost')
