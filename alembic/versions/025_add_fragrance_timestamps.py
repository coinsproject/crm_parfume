"""add timestamps to fragrances

Revision ID: 025_add_fragrance_timestamps
Revises: 024_partners_roles_refactor
Create Date: 2025-12-10
"""
from alembic import op
import sqlalchemy as sa

revision = "025_add_fragrance_timestamps"
down_revision = "024_partners_roles_refactor"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("fragrances")}
    if "created_at" not in cols:
        op.add_column("fragrances", sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")))
    if "updated_at" not in cols:
        op.add_column("fragrances", sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("fragrances", "updated_at")
    op.drop_column("fragrances", "created_at")
