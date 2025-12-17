"""add last_name_to_clients

Revision ID: 018_add_client_last_name
Revises: 017_add_catalog_item_fk_to_order_items
Create Date: 2025-12-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "018_add_client_last_name"
down_revision = "017_add_catalog_item_fk_to_order_items"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clients", sa.Column("last_name", sa.String(), nullable=True))


def downgrade():
    op.drop_column("clients", "last_name")
