"""Add full_name column and make email nullable

Revision ID: 003_add_full_name_and_make_email_nullable
Revises: 002_add_pending_activation_field_safe
Create Date: 2025-12-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '003_add_full_name_and_make_email_nullable'
down_revision = '002_add_pending_activation_field_safe'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('full_name', sa.String(), nullable=True))
        batch_op.alter_column(
            'email',
            existing_type=sa.String(),
            nullable=True
        )


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'email',
            existing_type=sa.String(),
            nullable=False,
            existing_nullable=True,
            server_default=''
        )
        batch_op.drop_column('full_name')
