"""add city and notes to clients

Revision ID: 026_add_client_city_notes
Revises: 025_add_fragrance_timestamps
Create Date: 2025-12-10
"""
from alembic import op
import sqlalchemy as sa

revision = "026_add_client_city_notes"
down_revision = "025_add_fragrance_timestamps"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("clients")}
    if "city" not in cols:
        op.add_column("clients", sa.Column("city", sa.String(), nullable=True))
    if "notes" not in cols:
        op.add_column("clients", sa.Column("notes", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("clients", "notes")
    op.drop_column("clients", "city")
