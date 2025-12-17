"""partner client markups

Revision ID: e49a30f6b35a
Revises: 026_add_client_city_notes
Create Date: 2025-12-14 02:11:08.814170

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e49a30f6b35a'
down_revision: Union[str, Sequence[str], None] = '026_add_client_city_notes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("partners") as batch_op:
        batch_op.add_column(sa.Column("admin_markup_percent", sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(sa.Column("max_partner_markup_percent", sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(sa.Column("partner_default_markup_percent", sa.Numeric(5, 2), nullable=True))

    op.create_table(
        "partner_client_markups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("partner_id", sa.Integer(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("partner_markup_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("partner_id", "client_id", name="uq_partner_client_markup"),
    )
    op.create_index(op.f("ix_partner_client_markups_id"), "partner_client_markups", ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_partner_client_markups_id"), table_name="partner_client_markups")
    op.drop_table("partner_client_markups")

    with op.batch_alter_table("partners") as batch_op:
        batch_op.drop_column("partner_default_markup_percent")
        batch_op.drop_column("max_partner_markup_percent")
        batch_op.drop_column("admin_markup_percent")
