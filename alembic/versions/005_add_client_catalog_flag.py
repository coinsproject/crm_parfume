"""Add can_access_catalog to clients

Revision ID: 005_add_client_catalog_flag
Revises: 004_add_permissions_and_rbac_tables
Create Date: 2025-12-01 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005_add_client_catalog_flag'
down_revision = '004_add_permissions_and_rbac_tables'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('clients', sa.Column('can_access_catalog', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    op.drop_column('clients', 'can_access_catalog')
