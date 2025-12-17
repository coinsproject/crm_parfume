"""Add email to clients

Revision ID: 006_add_client_email
Revises: 005_add_client_catalog_flag
Create Date: 2025-12-01 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_add_client_email'
down_revision = '005_add_client_catalog_flag'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('clients', sa.Column('email', sa.String(), nullable=True))


def downgrade():
    op.drop_column('clients', 'email')
