"""add partner contact fields

Revision ID: 019_add_partner_contact_fields
Revises: 018_add_client_last_name
Create Date: 2025-12-06
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "019_add_partner_contact_fields"
down_revision = "018_add_client_last_name"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {col["name"] for col in insp.get_columns("partners")}
    if "first_name" not in existing_cols:
        op.add_column("partners", sa.Column("first_name", sa.String(), nullable=True))
    if "last_name" not in existing_cols:
        op.add_column("partners", sa.Column("last_name", sa.String(), nullable=True))
    if "can_access_catalog" not in existing_cols:
        # Для SQLite убираем изменение default отдельной командой
        op.add_column("partners", sa.Column("can_access_catalog", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade():
    op.drop_column("partners", "can_access_catalog")
    op.drop_column("partners", "last_name")
    op.drop_column("partners", "first_name")
