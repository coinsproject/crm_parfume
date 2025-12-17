"""Rename price_history.direction to change_type

Revision ID: 014_rename_direction_to_change_type
Revises: 013_add_original_name_and_raw_name_not_null
Create Date: 2025-12-02 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "014_rename_direction_to_change_type"
down_revision = "013_add_original_name_and_raw_name_not_null"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"]: c for c in inspector.get_columns("price_history")}
    if "direction" in cols and "change_type" not in cols:
        with op.batch_alter_table("price_history") as batch:
            batch.alter_column("direction", new_column_name="change_type")


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"]: c for c in inspector.get_columns("price_history")}
    if "change_type" in cols and "direction" not in cols:
        with op.batch_alter_table("price_history") as batch:
            batch.alter_column("change_type", new_column_name="direction")
